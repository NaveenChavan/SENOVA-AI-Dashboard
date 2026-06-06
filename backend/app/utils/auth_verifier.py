"""
FastAPI dependency that verifies Google-issued JWT tokens
sent by the frontend in the ``Authorization`` header.

Uses the ``google-auth`` library to fetch Google's public key set
and validate the token's signature, expiry, and audience.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests

from app.core.config import GOOGLE_CLIENT_ID

# FastAPI security scheme — automatically extracts the Bearer token
# from the ``Authorization`` header.
_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """
    Dependency that verifies the Google JWT and returns the user's email.

    Usage in a route::

        @router.get("/protected")
        def my_route(user_email: str = Depends(get_current_user)):
            ...

    Raises
    ------
    HTTPException 401
        If the token is missing, expired, or the signature is invalid.
    """
    token = credentials.credentials

    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GOOGLE_CLIENT_ID is not configured on the server.",
        )

    try:
        # `verify_oauth2_token` downloads Google's current public keys,
        # checks the JWT signature, ``exp``, ``iat``, and ``iss``.
        info = id_token.verify_oauth2_token(
            token, requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        # Raised when the token is malformed, expired, or audience mismatch.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc
    except Exception as exc:
        # Catch-all for network / transport errors during cert fetch.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
        ) from exc

    email: str | None = info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain an email claim.",
        )

    return email
