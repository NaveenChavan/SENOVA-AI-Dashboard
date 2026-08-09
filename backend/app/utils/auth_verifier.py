"""
FastAPI dependency that verifies Firebase-issued ID tokens sent by the
frontend in the ``Authorization`` header.

The frontend authenticates users with Firebase Auth (Google sign-in
provider). On every API call it attaches the current user's Firebase ID
token as a Bearer token; this module verifies that token's signature,
expiry, and issuer using the Firebase Admin SDK before letting the
request reach the route handler.
"""

import json

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import (
    DISABLE_AUTH,
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_JSON,
    FIREBASE_SERVICE_ACCOUNT_PATH,
)

# FastAPI security scheme — automatically extracts the Bearer token
# from the ``Authorization`` header. auto_error=False lets us return a
# clean 401 (instead of FastAPI's default 403) when the header is missing.
_bearer = HTTPBearer(auto_error=False)

_firebase_app = None


def _credential_from_json_env():
    """
    Build a credential from ``FIREBASE_SERVICE_ACCOUNT_JSON``.

    Managed hosts have no good way to receive a gitignored key file, so the
    whole service-account JSON is passed as one secret env var instead.

    The ``private_key`` fix-up matters in practice: many dashboards store the
    value with the newlines already escaped, so the key arrives containing
    the two characters ``\\n`` where it needs real line breaks, and the
    resulting PEM is rejected with a confusing "No key could be detected"
    error. Repairing it here is much easier to live with than asking every
    deployment to paste the key in exactly the right shape.
    """
    try:
        info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is set but is not valid JSON. "
            "Paste the entire contents of the service-account file, including "
            f"the outer braces. Parser said: {exc}"
        ) from exc

    if not isinstance(info, dict):
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON must be a JSON object (the contents "
            "of the service-account file), not a list or bare value."
        )

    private_key = info.get("private_key")
    if isinstance(private_key, str) and "\\n" in private_key:
        info["private_key"] = private_key.replace("\\n", "\n")

    return credentials.Certificate(info)


def get_firebase_app():
    """
    Lazily initialise the Firebase Admin app exactly once.

    Credentials are resolved in this order:

    1. ``FIREBASE_SERVICE_ACCOUNT_JSON`` — the service-account JSON inline in
       an env var. Preferred on any managed host, because the key file is
       gitignored and therefore cannot travel with the repo.
    2. ``FIREBASE_SERVICE_ACCOUNT_PATH`` — the same JSON as a file on disk.
       This is the local-development path.

    Neither is required when ``DISABLE_AUTH=true``, which is local-only and
    refused at startup in production (see ``app.core.config``).

    We do NOT silently fall back to Application Default Credentials: that
    fallback only works inside Google Cloud / Firebase Hosting and produces a
    confusing "default credentials not found" 401 on every request everywhere
    else, which is what causes the "token verification failed" error seen
    locally.

    Public (no leading underscore) because other modules that need the
    Firebase Admin app for non-token-verification purposes — e.g.
    `app/services/email_service.py` generating password-reset links —
    share this same lazily-initialised app instance rather than each
    creating their own.
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred = _credential_from_json_env()
    elif FIREBASE_SERVICE_ACCOUNT_PATH:
        if not Path(FIREBASE_SERVICE_ACCOUNT_PATH).is_file():
            raise RuntimeError(
                f"FIREBASE_SERVICE_ACCOUNT_PATH points to '{FIREBASE_SERVICE_ACCOUNT_PATH}' "
                "but that file does not exist. Double-check the path in backend/.env."
            )
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    else:
        raise RuntimeError(
            "No Firebase credentials configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
            "to the full service-account JSON (recommended on a deployed host), "
            "or FIREBASE_SERVICE_ACCOUNT_PATH to the JSON file on disk (local "
            "development). Download the file from Firebase Console > Project "
            "Settings > Service Accounts > Generate new private key. "
            "For local development without Firebase, set DISABLE_AUTH=true instead."
        )

    _firebase_app = firebase_admin.initialize_app(
        cred, {"projectId": FIREBASE_PROJECT_ID}
    )
    return _firebase_app


def get_current_user(
    credentials_: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    Dependency that verifies the Firebase ID token and returns the user's
    email (falls back to their Firebase UID if no email is present, e.g.
    for anonymous auth).

    Usage in a route::

        @router.get("/protected")
        def my_route(user_email: str = Depends(get_current_user)):
            ...

    Raises
    ------
    HTTPException 401
        If the token is missing, expired, revoked, or the signature is
        invalid.
    HTTPException 500
        If Firebase Admin credentials are not configured on the server.
    """
    if DISABLE_AUTH:
        return "dev-user@localhost"

    if credentials_ is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Sign in and retry.",
        )

    token = credentials_.credentials

    try:
        app = get_firebase_app()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    try:
        decoded = firebase_auth.verify_id_token(token, app=app, check_revoked=True)
    except firebase_auth.ExpiredIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        ) from exc
    except firebase_auth.RevokedIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked. Please sign in again.",
        ) from exc
    except firebase_auth.InvalidIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
        ) from exc

    email: str | None = decoded.get("email")
    return email or decoded.get("uid", "unknown-user")
