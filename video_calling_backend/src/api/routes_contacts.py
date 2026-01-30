from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from src.api.auth import get_current_user
from src.api.db import get_db
from src.api.models import Contact, User
from src.api.schemas import ContactCreateRequest, ContactResponse

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get(
    "",
    response_model=list[ContactResponse],
    summary="List contacts",
    description="List contacts for the authenticated user.",
    operation_id="contacts_list",
)
def list_contacts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ContactResponse]:
    """List contacts."""
    rows = db.execute(
        select(Contact, User)
        .join(User, User.id == Contact.contact_user_id)
        .where(Contact.owner_user_id == current_user.id)
        .order_by(Contact.created_at.desc())
    ).all()

    return [
        ContactResponse(
            id=contact.id,
            name=contact.name,
            user_id=user.id,
            email=user.email,
            created_at=contact.created_at,
        )
        for contact, user in rows
    ]


@router.post(
    "",
    response_model=ContactResponse,
    summary="Create contact",
    description="Create a new contact by providing the other user's email as `handle`.",
    status_code=status.HTTP_201_CREATED,
    operation_id="contacts_create",
)
def create_contact(
    payload: ContactCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactResponse:
    """Create a contact for the current user."""
    handle = payload.handle.strip().lower()
    contact_user = db.execute(select(User).where(User.email == handle)).scalar_one_or_none()
    if not contact_user:
        raise HTTPException(status_code=404, detail="User not found for given handle (email).")

    if contact_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a contact.")

    existing = db.execute(
        select(Contact).where(
            and_(
                Contact.owner_user_id == current_user.id,
                Contact.contact_user_id == contact_user.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Contact already exists.")

    contact = Contact(owner_user_id=current_user.id, contact_user_id=contact_user.id, name=payload.name)
    db.add(contact)
    db.commit()
    db.refresh(contact)

    return ContactResponse(
        id=contact.id,
        name=contact.name,
        user_id=contact_user.id,
        email=contact_user.email,
        created_at=contact.created_at,
    )


@router.delete(
    "/{contact_id}",
    summary="Delete contact",
    description="Delete a contact by contact record id.",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="contacts_delete",
)
def delete_contact(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a contact record belonging to the authenticated user."""
    deleted = db.execute(
        delete(Contact).where(and_(Contact.id == contact_id, Contact.owner_user_id == current_user.id))
    ).rowcount
    db.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return None
