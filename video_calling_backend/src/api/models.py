import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class User(Base):
    """Application user."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    sent_invites: Mapped[list["Invite"]] = relationship(
        back_populates="from_user",
        cascade="all, delete-orphan",
        foreign_keys="Invite.from_user_id",
    )
    received_invites: Mapped[list["Invite"]] = relationship(
        back_populates="to_user",
        cascade="all, delete-orphan",
        foreign_keys="Invite.to_user_id",
    )


class Contact(Base):
    """A saved contact entry for a user (always points to another user)."""
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    contact_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    # Optional "friendly name" set by the owner.
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_user_id], back_populates="contacts")
    contact_user: Mapped["User"] = relationship("User", foreign_keys=[contact_user_id])

    __table_args__ = (
        UniqueConstraint("owner_user_id", "contact_user_id", name="uq_contacts_owner_contact"),
        Index("ix_contacts_owner", "owner_user_id"),
    )


class Invite(Base):
    """An invitation from one user to another to become contacts."""
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    from_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    to_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|accepted|declined
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    from_user: Mapped["User"] = relationship("User", foreign_keys=[from_user_id], back_populates="sent_invites")
    to_user: Mapped["User"] = relationship("User", foreign_keys=[to_user_id], back_populates="received_invites")

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_invites_from_to"),
        Index("ix_invites_to", "to_user_id"),
    )


class CallSession(Base):
    """
    Stores minimal call session metadata for observability / debugging.
    Signaling payloads are not persisted; we store who called whom and state transitions.
    """
    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    room_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    caller_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    callee_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_event_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
