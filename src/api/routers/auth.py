import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from google_auth_oauthlib.flow import Flow
from storage.google_auth import GoogleAuthStore
from api.dependencies import get_google_auth_store

router = APIRouter()
logger = logging.getLogger(__name__)

# Google Auth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)
DEFAULT_USER_ID = "default"


@router.get("/auth/google/login")
async def google_login():
    """Initiates the OAuth2 flow - redirects to Google."""
    if not Flow:
        raise HTTPException(status_code=501, detail="Google Auth not configured")

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google credentials not configured")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )

    # Redirect the browser directly to Google's OAuth page
    return Response(status_code=307, headers={"Location": authorization_url})


@router.get("/auth/google/callback")
async def google_callback(
    code: str,
    error: Optional[str] = None,
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
):
    """Handles the OAuth2 callback."""
    if error:
        logger.error(f"OAuth error: {error}")
        return Response(
            status_code=307,
            headers={"Location": "http://localhost:3000/calendar?error=" + error},
        )

    if not Flow:
        return Response(
            status_code=307,
            headers={
                "Location": "http://localhost:3000/calendar?error=configuration_error"
            },
        )

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=[
                "openid",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
            redirect_uri=GOOGLE_REDIRECT_URI,
        )

        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Get user email
        try:
            session = flow.authorized_session()
            user_info = session.get("https://www.googleapis.com/userinfo/v2/me").json()
            email = user_info.get("email")
        except Exception as e:
            logger.error(f"Failed to fetch user email: {e}")
            email = None

        if google_auth_store:
            # We assume credentials are google.oauth2.credentials.Credentials for this flow
            # Type ignore because Flow can theoretically return other types, but in this context it's OAuth2
            await google_auth_store.save_credentials(
                DEFAULT_USER_ID,
                credentials,
                str(email) if email else None,  # type: ignore
            )

        return Response(
            status_code=307,
            headers={"Location": "http://localhost:3000/calendar?success=true"},
        )

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return Response(
            status_code=307,
            headers={"Location": f"http://localhost:3000/calendar?error={str(e)}"},
        )


@router.get("/auth/google/status")
async def google_status(
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
) -> dict:
    """Check if user is connected."""
    if not google_auth_store:
        return {"connected": False, "error": "Auth store not initialized"}

    try:
        email = await google_auth_store.get_email(DEFAULT_USER_ID)
        creds = await google_auth_store.get_credentials(DEFAULT_USER_ID)
        return {"connected": creds is not None, "email": email}
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return {"connected": False, "error": str(e)}


@router.post("/auth/google/disconnect")
async def google_disconnect(
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
) -> dict:
    """Revoke and delete stored credentials."""
    if not google_auth_store:
        raise HTTPException(status_code=500, detail="Auth store not initialized")

    try:
        await google_auth_store.delete_credentials(DEFAULT_USER_ID)
        return {"status": "disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting: {e}")
        raise HTTPException(status_code=500, detail=str(e))
