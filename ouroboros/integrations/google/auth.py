"""Google API authentication module."""

import logging
import os
import pathlib
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

log = logging.getLogger(__name__)

# Scopes for Google APIs
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
]

# Token storage location
TOKEN_PATH = pathlib.Path('/content/ouroboros_data/tokens/google_token.json')


def _ensure_token_dir() -> None:
    """Ensure token directory exists."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_colab_credentials() -> Optional[Credentials]:
    """Try to get credentials from Colab's built-in auth."""
    try:
        from google.colab import auth as colab_auth
        colab_auth.authenticate_user()
        # In Colab, after auth, ADC (Application Default Credentials) are available
        # We need to obtain them as a Credentials object
        import google.auth
        creds, _ = google.auth.default(scopes=SCOPES)
        return creds
    except Exception as e:
        log.debug("Colab auth failed or unavailable: %s", e, exc_info=True)
        return None


def _get_oauth_file_credentials() -> Optional[Credentials]:
    """Get credentials from OAuth client secrets file."""
    # Look for client secrets in repo root or Drive
    possible_paths = [
        pathlib.Path('/content/ouroboros_repo/credentials.json'),
        pathlib.Path('/content/ouroboros_data/credentials.json'),
    ]
    client_secrets_file = None
    for p in possible_paths:
        if p.exists():
            client_secrets_file = p
            break

    if not client_secrets_file:
        log.debug("No credentials.json found for OAuth flow")
        return None

    _ensure_token_dir()
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            log.debug("Failed to load token: %s", e, exc_info=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log.debug("Token refresh failed: %s", e, exc_info=True)
                creds = None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_secrets_file), SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                log.debug("OAuth flow failed: %s", e, exc_info=True)
                return None
        # Save the credentials for the next run
        try:
            with open(TOKEN_PATH, 'w') as token:
                token.write(creds.to_json())
        except Exception as e:
            log.debug("Failed to save token: %s", e, exc_info=True)
    return creds


def get_credentials() -> Credentials:
    """
    Get Google API credentials with fallback chain:
    1. Colab authentication (if running in Colab)
    2. OAuth file-based flow (credentials.json + cached token)
    Raises RuntimeError if no credentials could be obtained.
    """
    creds = _get_colab_credentials()
    if creds:
        log.info("Using Colab credentials")
        return creds

    creds = _get_oauth_file_credentials()
    if creds:
        log.info("Using OAuth file credentials")
        return creds

    raise RuntimeError(
        "Google credentials not available. "
        "Either run in Colab (already authenticated) "
        "or place credentials.json in /content/ouroboros_repo/ or /content/ouroboros_data/ "
        "and complete OAuth flow."
    )


# Alias for backward compatibility with modules that import 'authenticate'
authenticate = get_credentials