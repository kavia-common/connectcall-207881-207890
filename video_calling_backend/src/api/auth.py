import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.api.db import get_db
from src.api.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def _get_secret_key() -> str:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret:
        # Must be set by environment variable system; don't hardcode secrets.
        raise RuntimeError("JWT_SECRET is not configured.")
    return secret


def _get_algorithm() -> str:
    return (os.getenv("JWT_ALGORITHM") or "HS256").strip()


def _get_access_token_minutes() -> int:
    try:
        return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "10080")  # default 7 days
    except ValueError:
        return 10080


def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(password, password_hash)


def create_access_token(*, subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token.

    subject is typically the user_id (UUID as string).
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=_get_access_token_minutes()))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, _get_secret_key(), algorithm=_get_algorithm())


def _decode_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[_get_algorithm()])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
        return uuid.UUID(str(sub))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")


# PUBLIC_INTERFACE
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to fetch the current authenticated user via Bearer JWT."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    user_id = _decode_token(credentials.credentials)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user
