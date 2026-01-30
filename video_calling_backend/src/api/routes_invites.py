from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.api.auth import get_current_user
from src.api.db import get_db
from src.api.models import Contact, Invite, User
from src.api.schemas import InviteAcceptResponse, InviteCreateRequest, InviteResponse

router = APIRouter(prefix="/invites", tags=["invites"])


def _invite_to_schema(inv: Invite) -> InviteResponse:
    return InviteResponse(
        id=inv.id,
        from_user_id=inv.from_user_id,
        to_user_id=inv.to_user_id,
        status=inv.status,
        created_at=inv.created_at,
        responded_at=inv.responded_at,
    )


@router.get(
    "",
    response_model=list[InviteResponse],
    summary="List invites",
    description="List incoming invites for the authenticated user.",
    operation_id="invites_list",
)
def list_invites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[InviteResponse]:
    """List incoming invites."""
    invites = db.execute(
        select(Invite).where(Invite.to_user_id == current_user.id).order_by(Invite.created_at.desc())
    ).scalars().all()
    return [_invite_to_schema(i) for i in invites]


@router.post(
    "",
    response_model=InviteResponse,
    summary="Create invite",
    description="Create an invite to another user by their email address.",
    status_code=status.HTTP_201_CREATED,
    operation_id="invites_create",
)
def create_invite(
    payload: InviteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteResponse:
    """Create a new invite."""
    to_email = payload.to_email.strip().lower()
    to_user = db.execute(select(User).where(User.email == to_email)).scalar_one_or_none()
    if not to_user:
        raise HTTPException(status_code=404, detail="Target user not found.")

    if to_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot invite yourself.")

    # If already contacts, deny.
    already = db.execute(
        select(Contact).where(
            and_(
                Contact.owner_user_id == current_user.id,
                Contact.contact_user_id == to_user.id,
            )
        )
    ).scalar_one_or_none()
    if already:
        raise HTTPException(status_code=409, detail="Already contacts.")

    existing = db.execute(
        select(Invite).where(and_(Invite.from_user_id == current_user.id, Invite.to_user_id == to_user.id))
    ).scalar_one_or_none()
    if existing and existing.status == "pending":
        raise HTTPException(status_code=409, detail="Invite already pending.")
    if existing and existing.status in {"accepted", "declined"}:
        # Create a new invite instead of reusing, to keep history.
        pass

    inv = Invite(from_user_id=current_user.id, to_user_id=to_user.id, status="pending")
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _invite_to_schema(inv)


@router.post(
    "/{invite_id}/accept",
    response_model=InviteAcceptResponse,
    summary="Accept invite",
    description="Accept an invite and create mutual contacts between the two users.",
    operation_id="invites_accept",
)
def accept_invite(
    invite_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteAcceptResponse:
    """Accept an invite and create mutual contacts."""
    inv = db.execute(select(Invite).where(Invite.id == invite_id)).scalar_one_or_none()
    if not inv or inv.to_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Invite not found.")

    if inv.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is already {inv.status}.")

    inv.status = "accepted"
    inv.responded_at = datetime.utcnow()

    created = 0

    # Create contact A->B
    c1 = db.execute(
        select(Contact).where(and_(Contact.owner_user_id == inv.from_user_id, Contact.contact_user_id == inv.to_user_id))
    ).scalar_one_or_none()
    if not c1:
        db.add(Contact(owner_user_id=inv.from_user_id, contact_user_id=inv.to_user_id, name=None))
        created += 1

    # Create contact B->A
    c2 = db.execute(
        select(Contact).where(and_(Contact.owner_user_id == inv.to_user_id, Contact.contact_user_id == inv.from_user_id))
    ).scalar_one_or_none()
    if not c2:
        db.add(Contact(owner_user_id=inv.to_user_id, contact_user_id=inv.from_user_id, name=None))
        created += 1

    db.add(inv)
    db.commit()
    db.refresh(inv)

    return InviteAcceptResponse(invite=_invite_to_schema(inv), created_contacts=created)
