"""
FastAPI dependency that verifies Firebase-issued ID tokens sent by the
frontend in the ``Authorization`` header.

The frontend authenticates users with Firebase Auth (Google sign-in
provider). On every API call it attaches the current user's Firebase ID
token as a Bearer token; this module verifies that token's signature,
expiry, and issuer using the Firebase Admin SDK before letting the
request reach the route handler.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import (
    DISABLE_AUTH,
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_PATH,
)

# FastAPI security scheme — automatically extracts the Bearer token
# from the ``Authorization`` header. auto_error=False lets us return a
# clean 401 (instead of FastAPI's default 403) when the header is missing.
_bearer = HTTPBearer(auto_error=False)

_firebase_app = None


def _get_firebase_app():
    """
    Lazily initialise the Firebase Admin app exactly once.

    Requires an explicit service-account credential file
    (``FIREBASE_SERVICE_ACCOUNT_PATH``) unless ``DISABLE_AUTH=true``. We do
    NOT silently fall back to Application Default Credentials on a
    developer's laptop — that fallback only works inside Google Cloud /
    Firebase Hosting and produces a confusing "default credentials not
    found" 401 on every request everywhere else, which is what causes the
    "token verification failed" error seen locally.
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    if not FIREBASE_SERVICE_ACCOUNT_PATH:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_PATH is not set. Download a service "
            "account key from Firebase Console > Project Settings > "
            "Service Accounts > Generate new private key, save it as "
            "backend/firebase-service-account.json, and set "
            "FIREBASE_SERVICE_ACCOUNT_PATH in backend/.env. "
            "For local development without Firebase, set DISABLE_AUTH=true instead."
        )

    if not Path(FIREBASE_SERVICE_ACCOUNT_PATH).is_file():
        raise RuntimeError(
            f"FIREBASE_SERVICE_ACCOUNT_PATH points to '{FIREBASE_SERVICE_ACCOUNT_PATH}' "
            "but that file does not exist. Double-check the path in backend/.env."
        )

    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
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
        app = _get_firebase_app()
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
