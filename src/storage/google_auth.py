import logging
import os
import json
from typing import Optional
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials

from storage.db import get_pool

logger = logging.getLogger(__name__)


class GoogleAuthStore:
    def __init__(self):
        # Generate a key if not provided (for development/testing only)
        # In production, this MUST be provided via environment variable
        key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
        if not key:
            logger.warning(
                "GOOGLE_TOKEN_ENCRYPTION_KEY not set. Generating a temporary key."
            )
            key = Fernet.generate_key().decode()

        try:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            logger.error(f"Invalid encryption key: {e}")
            # Fallback for safety, though this will fail to decrypt previously stored tokens
            self.fernet = Fernet(Fernet.generate_key())

    def _encrypt(self, data: str) -> str:
        if not data:
            return None
        return self.fernet.encrypt(data.encode()).decode()

    def _decrypt(self, token: str) -> str:
        if not token:
            return None
        try:
            return self.fernet.decrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            return None

    async def save_credentials(
        self, user_id: str, credentials: Credentials, email: str = None
    ) -> None:
        """Store OAuth tokens in PostgreSQL (encrypted)."""
        pool = get_pool()

        access_token_enc = self._encrypt(credentials.token)
        refresh_token_enc = (
            self._encrypt(credentials.refresh_token)
            if credentials.refresh_token
            else None
        )

        # If we have a refresh token, update it. If not, keep the existing one (OAuth2 flow sometimes doesn't return it on re-auth)
        if refresh_token_enc:
            query = """
                INSERT INTO google_credentials (user_id, access_token, refresh_token, token_expiry, email)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    token_expiry = EXCLUDED.token_expiry,
                    email = COALESCE(EXCLUDED.email, google_credentials.email),
                    updated_at = NOW()
            """
            await pool.execute(
                query,
                user_id,
                access_token_enc,
                refresh_token_enc,
                credentials.expiry,
                email,
            )
        else:
            query = """
                INSERT INTO google_credentials (user_id, access_token, token_expiry, email)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    token_expiry = EXCLUDED.token_expiry,
                    email = COALESCE(EXCLUDED.email, google_credentials.email),
                    updated_at = NOW()
            """
            await pool.execute(
                query, user_id, access_token_enc, credentials.expiry, email
            )

        logger.info(f"Saved Google credentials for user {user_id}")

    async def get_credentials(self, user_id: str) -> Optional[Credentials]:
        """Retrieve and refresh tokens if needed."""
        pool = get_pool()

        row = await pool.fetchrow(
            "SELECT access_token, refresh_token, token_expiry FROM google_credentials WHERE user_id = $1",
            user_id,
        )

        if not row:
            return None

        access_token = self._decrypt(row["access_token"])
        refresh_token = self._decrypt(row["refresh_token"])

        if not access_token:
            return None

        # Reconstruct Credentials object
        expiry = row["token_expiry"]
        # Ensure expiry is naive UTC for compatibility with google-auth
        if expiry and expiry.tzinfo:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=[
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.readonly",
            ],
            expiry=expiry,
        )

        return creds

    async def get_email(self, user_id: str) -> Optional[str]:
        """Retrieve stored email for user."""
        pool = get_pool()
        return await pool.fetchval(
            "SELECT email FROM google_credentials WHERE user_id = $1", user_id
        )

    async def delete_credentials(self, user_id: str) -> None:
        """Remove stored credentials."""
        pool = get_pool()
        await pool.execute("DELETE FROM google_credentials WHERE user_id = $1", user_id)
        logger.info(f"Deleted Google credentials for user {user_id}")
