"""
src/api/auth.py
────────────────
Authentication and Security Utilities.
Provides password hashing via bcrypt to ensure zero plain-text storage.
"""
import bcrypt
import uuid
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.database import get_db
from src.db.models import User

def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against its hashed version."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# ─────────────────────────────────────────────────────────────
# JSON Web Token (JWT) Utilities
# ─────────────────────────────────────────────────────────────
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

# Hardcoded for prototyping. In production, load from os.getenv("SECRET_KEY")
SECRET_KEY = "hiring-ai-b2b-saas-super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def create_token(data: dict) -> str:
    """
    Create a new JWT token.
    Must contain 'user_id' and 'organization_id'.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict | None:
    """
    Decode and verify a JWT token. Returns the payload dict if valid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# ─────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ─────────────────────────────────────────────────────────────
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Dependency: Extract JWT and strictly resolve User ID from database."""
    # 1. Extract Token
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    if not token:
        token = request.query_params.get("token")
        
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # 2. Decode Token
    payload = decode_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 3. Resolve actual user record from DB
    user_id = payload["user_id"]
    from sqlalchemy import select
    stmt = select(User).where(User.id == uuid.UUID(user_id))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    """
    Like get_current_user but returns None instead of raising 401.
    Used for endpoints that should work both authenticated (frontend)
    and unauthenticated (email link clicks).
    """
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


async def authenticate_websocket(token: str, db: AsyncSession) -> Optional[User]:
    """Helper for WebSocket auth as headers are not easily available in JS WebSocket API."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id") # Consistent with other endpoints
        if user_id is None:
            return None
            
        from src.db.models import User as UserDB
        stmt = select(UserDB).where(UserDB.id == uuid.UUID(user_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    except JWTError:
        return None
async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: blocks access unless user role is 'admin'.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: admin role required"
        )
    return current_user


def require_interviewer_or_above(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: allows admin and interviewer roles.
    """
    allowed = {"admin", "interviewer"}
    if current_user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient role"
        )
    return current_user
