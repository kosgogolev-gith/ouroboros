"""Google API authentication module for Colab and local environments."""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes required for Drive operations (read/write/delete)
SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_token_path() -> Path:
    """Path to stored credentials token."""
    return Path("/root/.google_token") if os.path.exists("/root") else Path.home() / ".google_token"


def _get_credentials_path() -> Path:
    """Path to OAuth client secrets file."""
    return Path("/root/credentials.json") if os.path.exists("/root") else Path.home() / "credentials.json"


def authenticate() -> Credentials:
    """
    Authenticate for Google API access.

    Strategy:
    1. If running in Colab, use google.colab.auth.authenticate_user()
    2. Otherwise, try to load existing token from disk
    3. If no valid token, run OAuth flow (needs credentials.json)

    Returns:
        Credentials object ready to use with Google API clients.

    Raises:
        FileNotFoundError: If credentials.json is missing and no token exists.
        Exception: For other authentication failures.
    """
    # Try Colab authentication first
    try:
        from google.colab import auth
        auth.authenticate_user()
        print("✅ Authenticated via Colab")
        # Colab auth provides credentials through gcloud, we need to build our own
        # For now, assume Colab has a valid token in the default location
        # We'll use the Application Default Credentials
        import google.auth
        creds, _ = google.auth.default(scopes=SCOPES)
        return creds
    except Exception as colab_err:
        print(f"Colab auth not available: {colab_err}. Falling back to OAuth file.")

    token_path = _get_token_path()
    credentials_path = _get_credentials_path()

    creds = None
    if token_path.exists():
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found at {credentials_path}. "
                    "Please download credentials.json from Google Cloud Console "
                    "and place it in the appropriate directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the token for future use
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
        print(f"✅ Authentication successful, token saved to {token_path}")
    else:
        print(f"✅ Loaded existing credentials from {token_path}")

    return creds
