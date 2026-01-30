import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from src.api.db import engine, get_db
from src.api.models import Base, User
from src.api.routes_auth import router as auth_router
from src.api.routes_contacts import router as contacts_router
from src.api.routes_invites import router as invites_router
from src.api.schemas import SignalingHelpResponse
from src.api.signaling import signaling_loop

openapi_tags = [
    {"name": "health", "description": "Service health checks."},
    {"name": "auth", "description": "JWT authentication endpoints (signup/login/me)."},
    {"name": "contacts", "description": "Manage contact list."},
    {"name": "invites", "description": "Invite/accept flow to become contacts."},
    {"name": "signaling", "description": "WebSocket signaling relay for WebRTC SDP/ICE exchange."},
]

app = FastAPI(
    title="ConnectCall Backend API",
    description=(
        "FastAPI backend for ConnectCall: JWT auth, contacts & invites, and WebRTC signaling via WebSocket.\n\n"
        "WebSocket usage:\n"
        "- Connect to `/ws` and pass JWT as query param: `/ws?token=<JWT>`\n"
        "- Send JSON messages: {type, to, roomId, ...payload}\n"
        "- Server forwards to the recipient with `from` added."
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# Create tables (simple template approach; in real deployments, use migrations).
Base.metadata.create_all(bind=engine)

# CORS: allow frontend preview origin + optionally REACT_APP frontend URL.
# Env vars to be provided by platform/user:
# - FRONTEND_ORIGIN: e.g. https://...:3000
# - FRONTEND_ORIGINS: comma-separated list of allowed origins
frontend_origin = (os.getenv("FRONTEND_ORIGIN") or "").strip()
frontend_origins = (os.getenv("FRONTEND_ORIGINS") or "").strip()

allow_origins = []
if frontend_origin:
    allow_origins.append(frontend_origin)
if frontend_origins:
    allow_origins.extend([o.strip() for o in frontend_origins.split(",") if o.strip()])

# Fallback: in preview we still allow localhost:3000 to avoid dev friction.
allow_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])

# If nothing configured, don't break existing template behavior.
if not allow_origins:
    allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allow_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(invites_router)


@app.get("/", tags=["health"], summary="Health check", operation_id="health_check")
def health_check():
    """Health check endpoint used by preview/runtime monitors."""
    return {"message": "Healthy"}


@app.get(
    "/docs/signaling",
    response_model=SignalingHelpResponse,
    tags=["signaling"],
    summary="WebSocket signaling usage",
    description="Returns instructions for connecting and message formats for the signaling WebSocket.",
    operation_id="signaling_help",
)
def signaling_help() -> SignalingHelpResponse:
    """Help endpoint for WebSocket signaling clients."""
    return SignalingHelpResponse(
        websocket_url="/ws",
        auth="Pass JWT token as query parameter: /ws?token=<JWT>",
        message_envelope={
            "type": "offer|answer|candidate|hangup",
            "to": "<target_user_id>",
            "roomId": "<string>",
            "...": "payload depends on type (sdp/candidate etc.)",
        },
        routing={
            "server_forwards_to_recipient": {"from": "<sender_user_id>", "roomId": "<roomId>", "...": "payload"},
            "offline_behavior": {"type": "peer_offline", "to": "<target_user_id>", "roomId": "<roomId>"},
        },
    )


def _token_to_user_id(token: str, db: Session) -> Optional[uuid.UUID]:
    """
    Validate a bearer JWT and return user_id, reusing the HTTP auth dependency logic.
    """
    # Reuse get_current_user by simulating the Authorization header is not feasible directly;
    # instead, call /auth/me in frontend normally and use Bearer for REST.
    # For WebSocket we validate token by creating a small request context below.
    from src.api.auth import _decode_token  # local import to keep module API clean

    try:
        user_id = _decode_token(token)
    except HTTPException:
        return None

    user = db.get(User, user_id)
    if not user:
        return None
    return user_id


@app.websocket(
    "/ws",
)
async def websocket_signaling(
    websocket: WebSocket,
    token: str = Query(default="", description="JWT access token; also accepted as `?token=` in URL."),
):
    """
    WebSocket endpoint for WebRTC signaling relay.

    Authentication:
    - Pass JWT access token as query param: `/ws?token=<JWT>` (matches frontend SignalingClient).

    Message routing:
    - Client sends `{type, to, roomId, ...payload}`
    - Server forwards to `{type, from, roomId, ...payload}` to the `to` user if connected.
    """
    await websocket.accept()

    # We need DB session here; WS dependencies are limited, so we create manually.
    db: Session = next(get_db())
    try:
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id = _token_to_user_id(token, db)
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await signaling_loop(websocket=websocket, current_user_id=user_id, db=db)
    finally:
        db.close()
