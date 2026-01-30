from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, get_current_user, hash_password, verify_password
from src.api.db import get_db
from src.api.models import User
from src.api.schemas import AuthLoginRequest, AuthLoginResponse, AuthSignupRequest, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserPublic,
    summary="Sign up",
    description="Create a new user account with email/password.",
    status_code=status.HTTP_201_CREATED,
    operation_id="auth_signup",
)
def signup(payload: AuthSignupRequest, db: Session = Depends(get_db)) -> UserPublic:
    """Create a new user account."""
    email = payload.email.strip().lower()

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserPublic(id=user.id, email=user.email, created_at=user.created_at)


@router.post(
    "/login",
    response_model=AuthLoginResponse,
    summary="Login",
    description="Authenticate with email/password and receive a JWT access token.",
    operation_id="auth_login",
)
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthLoginResponse:
    """Authenticate a user."""
    email = payload.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    token = create_access_token(subject=str(user.id))
    return AuthLoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserPublic(id=user.id, email=user.email, created_at=user.created_at),
    )


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Current user",
    description="Return the currently authenticated user.",
    operation_id="auth_me",
)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return the authenticated user's profile."""
    return UserPublic(id=current_user.id, email=current_user.email, created_at=current_user.created_at)
