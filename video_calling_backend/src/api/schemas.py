from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserPublic(BaseModel):
    id: UUID = Field(..., description="User ID.")
    email: str = Field(..., description="User email address.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")


class AuthSignupRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., min_length=6, description="User password (min length 6).")


class AuthLoginRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., description="User password.")


class AuthLoginResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    token_type: str = Field("bearer", description="Token type.")
    user: UserPublic = Field(..., description="Authenticated user.")


class ContactCreateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Friendly name for the contact.")
    handle: str = Field(
        ...,
        description="Identifier of the user to add. For this backend: contact user's email.",
    )


class ContactResponse(BaseModel):
    id: UUID = Field(..., description="Contact record ID.")
    name: Optional[str] = Field(None, description="Friendly name for the contact.")
    user_id: UUID = Field(..., description="The referenced user's ID.")
    email: str = Field(..., description="The referenced user's email.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")


class InviteCreateRequest(BaseModel):
    to_email: str = Field(..., description="Email address of the user to invite.")


class InviteResponse(BaseModel):
    id: UUID = Field(..., description="Invite ID.")
    from_user_id: UUID = Field(..., description="Sender user ID.")
    to_user_id: UUID = Field(..., description="Receiver user ID.")
    status: str = Field(..., description="Invite status: pending|accepted|declined.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")
    responded_at: Optional[datetime] = Field(None, description="Response timestamp (UTC) if responded.")


class InviteAcceptResponse(BaseModel):
    invite: InviteResponse = Field(..., description="Updated invite.")
    created_contacts: int = Field(..., description="Number of contacts created as part of accepting the invite.")


class SignalingHelpResponse(BaseModel):
    websocket_url: str = Field(..., description="WebSocket endpoint URL path (relative).")
    auth: str = Field(..., description="How to authenticate to WebSocket.")
    message_envelope: dict = Field(..., description="Expected JSON message envelope.")
    routing: dict = Field(..., description="How messages are routed between users.")
