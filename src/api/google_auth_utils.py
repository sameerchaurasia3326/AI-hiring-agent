import os
import secrets
import hashlib
import base64
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.config import settings
from src.db.models import User

# Allow OAuth over plain HTTP for local development
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]


def _generate_pkce():
    """Generate a PKCE code_verifier and code_challenge (S256) pair."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


def _build_flow(state: str = None) -> Flow:
    """Creates a Google OAuth flow object from settings."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [settings.google_redirect_uri]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, state=state)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def get_google_auth_url(user_id: str) -> str:
    """
    Generates the Google OAuth URL for connecting Google Calendar.
    Stores the PKCE code_verifier in the JWT state for use at callback.
    """
    from src.api.auth import create_token
    code_verifier, code_challenge = _generate_pkce()
    state = create_token({"user_id": user_id, "purpose": "google_oauth", "cv": code_verifier})

    flow = _build_flow(state=state)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256"
    )
    return authorization_url


def get_google_login_url() -> str:
    """
    Generates the Google OAuth URL for login (no prior user session needed).
    Stores the PKCE code_verifier in the JWT state for use at callback.
    """
    from src.api.auth import create_token
    code_verifier, code_challenge = _generate_pkce()
    state = create_token({"purpose": "google_login", "cv": code_verifier})

    flow = _build_flow(state=state)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256"
    )
    return authorization_url


async def exchange_code_for_tokens(code: str, state: str):
    """
    Exchanges the authorization code for tokens.
    Retrieves the code_verifier from the JWT state and passes it to satisfy PKCE.
    Returns (user_id | None, credentials | None).
    """
    from src.api.auth import decode_token
    payload = decode_token(state)
    if not payload:
        return None, None

    purpose = payload.get("purpose")
    if purpose not in ("google_oauth", "google_login"):
        return None, None

    user_id = payload.get("user_id")       # May be None for google_login
    code_verifier = payload.get("cv", "")  # Required for PKCE

    flow = _build_flow(state=state)
    flow.fetch_token(code=code, code_verifier=code_verifier)

    return user_id, flow.credentials


async def get_user_credentials(user_id: str, db):
    """Retrieves and refreshes Google OAuth credentials for a user."""
    from sqlalchemy.future import select
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.google_access_token:
        return None

    creds = Credentials(
        token=user.google_access_token,
        refresh_token=user.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=GOOGLE_SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        user.google_access_token = creds.token
        user.google_token_expiry = creds.expiry
        await db.commit()

    return creds


async def get_user_calendar_service(user_id: str, db):
    """Returns a Google Calendar API service for the specified user."""
    creds = await get_user_credentials(user_id, db)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)
