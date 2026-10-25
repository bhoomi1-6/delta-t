"""Google Calendar OAuth routes for a local Next.js + FastAPI demo.

Uses a browser session cookie as an anonymous local identity. For a deployed
multi-user app, bind this to your REAL authenticated application user instead.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

router = APIRouter()
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
COOKIE_NAME = "delta_t_session"
DB_PATH = Path(os.getenv("OAUTH_DB_PATH", str(Path(__file__).resolve().parents[2] / "oauth_connections.sqlite3")))


def db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS oauth_pending (state TEXT PRIMARY KEY, session_id TEXT NOT NULL, verifier TEXT NOT NULL, created INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS google_accounts (session_id TEXT PRIMARY KEY, google_sub TEXT NOT NULL, email TEXT, encrypted_credentials BLOB NOT NULL)")
    return db


def cipher() -> Fernet:
    key = os.getenv("OAUTH_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("OAUTH_ENCRYPTION_KEY must be set (Fernet key)")
    return Fernet(key.encode())


def flow(*, state=None, verifier=None) -> Flow:
    # Reuses your existing JSON containing a "web" OAuth client.
    # This is not a token JSON and must never be committed to Git.
    credentials_file = Path(os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS_FILE", "google-calendar-credentials.json"
    ))
    if not credentials_file.is_absolute():
        credentials_file = Path(__file__).resolve().parents[2] / credentials_file
    if not credentials_file.is_file():
        raise RuntimeError(f"OAuth client JSON not found: {credentials_file}")
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback"
    )
    options = {"scopes": SCOPES, "redirect_uri": redirect_uri}
    if state is not None:
        options["state"] = state
    if verifier is not None:
        options["code_verifier"] = verifier
    else:
        options["autogenerate_code_verifier"] = True
    return Flow.from_client_secrets_file(str(credentials_file), **options)


def google_client_id() -> str:
    import json as _json
    credentials_file = Path(os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS_FILE", "google-calendar-credentials.json"
    ))
    if not credentials_file.is_absolute():
        credentials_file = Path(__file__).resolve().parents[2] / credentials_file
    with credentials_file.open(encoding="utf-8") as handle:
        return _json.load(handle)["web"]["client_id"]


def current_session(request: Request) -> str | None:
    value = request.cookies.get(COOKIE_NAME)
    # Cookie value is random and unguessable, not a user-supplied account ID.
    return value if value and len(value) == 64 and all(c in '0123456789abcdef' for c in value) else None


@router.get("/auth/google")
def start_google_auth(request: Request):
    session_id = current_session(request) or secrets.token_hex(32)
    oauth = flow()
    url, state = oauth.authorization_url(
        access_type="offline", prompt="select_account consent", include_granted_scopes="false"
    )
    if not oauth.code_verifier:
        raise HTTPException(500, "OAuth PKCE verifier missing")
    with db_connection() as db:
        db.execute("DELETE FROM oauth_pending WHERE created < ?", (int(time.time()) - 600,))
        db.execute("INSERT INTO oauth_pending VALUES (?, ?, ?, ?)", (state, session_id, oauth.code_verifier, int(time.time())))
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(COOKIE_NAME, session_id, httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="lax", max_age=60 * 60 * 24 * 30, path="/")
    return response


@router.get("/auth/google/callback")
def google_callback(request: Request, state: str | None = None, code: str | None = None, error: str | None = None):
    if error:
        return RedirectResponse("/?calendar=denied", status_code=302)
    session_id = current_session(request)
    if not state or not code or not session_id:
        raise HTTPException(400, "Missing OAuth session or authorization code")
    with db_connection() as db:
        # Consume state exactly once, even if the token exchange fails.
        row = db.execute("SELECT session_id, verifier, created FROM oauth_pending WHERE state = ?", (state,)).fetchone()
        db.execute("DELETE FROM oauth_pending WHERE state = ?", (state,))
    if not row or not secrets.compare_digest(row[0], session_id) or time.time() - row[2] > 600:
        raise HTTPException(400, "Invalid or expired OAuth state")

    oauth = flow(state=state, verifier=row[1])
    # OAuth state was validated above. Exchange the code using the configured redirect URI.
    oauth.fetch_token(code=code)
    credentials = oauth.credentials
    if not credentials.id_token:
        raise HTTPException(400, "Google did not return an ID token")
    identity = id_token.verify_oauth2_token(credentials.id_token, GoogleRequest(), google_client_id())
    if not identity.get("email_verified"):
        raise HTTPException(400, "Google email is not verified")
    encrypted = cipher().encrypt(credentials.to_json().encode())
    with db_connection() as db:
        db.execute("INSERT OR REPLACE INTO google_accounts VALUES (?, ?, ?, ?)", (session_id, identity["sub"], identity.get("email"), encrypted))
    return RedirectResponse("/?calendar=connected", status_code=302)


@router.get("/api/calendar/account")
def calendar_account(request: Request):
    session_id = current_session(request)
    if not session_id:
        return {"connected": False, "email": None}
    with db_connection() as db:
        row = db.execute("SELECT email FROM google_accounts WHERE session_id = ?", (session_id,)).fetchone()
    return {"connected": bool(row), "email": row[0] if row else None}


@router.post("/api/calendar/disconnect")
def disconnect_calendar(request: Request):
    # Same-origin check prevents cross-site form submissions using this cookie.
    origin = request.headers.get("origin")
    expected = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    if origin != expected:
        raise HTTPException(403, "Invalid request origin")
    session_id = current_session(request)
    if session_id:
        with db_connection() as db:
            db.execute("DELETE FROM google_accounts WHERE session_id = ?", (session_id,))
    return {"connected": False}


def get_calendar_credentials(request: Request) -> Credentials:
    """Use in authenticated prediction routes to read the linked calendar."""
    session_id = current_session(request)
    if not session_id:
        raise HTTPException(401, "Connect Google Calendar first")
    with db_connection() as db:
        row = db.execute("SELECT encrypted_credentials FROM google_accounts WHERE session_id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(401, "Connect Google Calendar first")
    data = json.loads(cipher().decrypt(row[0]).decode())
    credentials = Credentials.from_authorized_user_info(data, scopes=SCOPES)
    if not credentials.valid:
        if not credentials.refresh_token:
            raise HTTPException(401, "Reconnect Google Calendar")
        try:
            credentials.refresh(GoogleRequest())
        except Exception as exc:
            raise HTTPException(401, "Google Calendar authorization expired; reconnect") from exc
        with db_connection() as db:
            db.execute("UPDATE google_accounts SET encrypted_credentials = ? WHERE session_id = ?", (cipher().encrypt(credentials.to_json().encode()), session_id))
    return credentials
