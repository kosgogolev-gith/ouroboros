"""Google API authentication — VPS version."""
import logging, pathlib
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

log = logging.getLogger(__name__)
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

def _get_token_path() -> pathlib.Path:
    return pathlib.Path.home() / "ouroboros_data" / "tokens" / "google_token.json"

def _load_existing_token() -> Optional[Credentials]:
    p = _get_token_path()
    if not p.exists():
        return None
    try:
        c = Credentials.from_authorized_user_file(str(p), SCOPES)
        if c and c.valid:
            return c
        if c and c.expired and c.refresh_token:
            try:
                c.refresh(Request())
                try: p.write_text(c.to_json())
                except: pass
                return c
            except Exception as e:
                log.warning("Token refresh failed: %s", e)
        return None
    except Exception as e:
        log.debug("Load token failed: %s", e)
        return None

def get_credentials() -> Credentials:
    c = _load_existing_token()
    if c:
        return c
    raise RuntimeError(
        f"Google credentials not available. Token at {_get_token_path()} missing or expired."
    )

authenticate = get_credentials
