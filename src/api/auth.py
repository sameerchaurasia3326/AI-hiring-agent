"""
src/api/auth.py
────────────────
Authentication and Security Utilities.
Provides password hashing via bcrypt to ensure zero plain-text storage.
"""
import bcrypt

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

def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency to extract JWT token from Authorization header OR ?token= query parameter.
    """
    # 1. Try Header
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # 2. Try Query Param (for email clicks)
    if not token:
        token = request.query_params.get("token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency: blocks access unless user role is 'admin'.
    Use on endpoints like POST /jobs, POST /invite-user.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: admin role required"
        )
    return current_user


def require_interviewer_or_above(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency: allows admin, hiring_manager, and interviewer roles.
    Blocks any unknown or unauthenticated user.
    """
    allowed = {"admin", "hiring_manager", "interviewer"}
    if current_user.get("role") not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient role"
        )
    return current_user
