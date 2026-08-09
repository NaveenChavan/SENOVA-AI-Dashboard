"""
Auth-adjacent backend routes that don't fit the Firebase client SDK alone —
currently just password-reset email delivery (see
`app/services/email_service.py` for why this exists instead of calling
Firebase's `sendPasswordResetEmail()` directly from the frontend).

This route is intentionally unauthenticated (no `get_current_user`
dependency) — a signed-out user who forgot their password is, by
definition, not signed in yet.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from app.services.email_service import (
    is_email_delivery_configured,
    send_password_reset_email,
)

logger = logging.getLogger("senova.auth")

router = APIRouter()

# Always the same response regardless of whether the email exists, whether
# sending succeeded, or whether it failed for a configuration reason — this
# is the standard mitigation against using password reset as an
# account-enumeration oracle, and must not change per-branch.
_GENERIC_RESPONSE_MESSAGE = "If that email exists, a reset link has been sent."


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str = _GENERIC_RESPONSE_MESSAGE
    email_dispatched: bool = Field(
        ...,
        description=(
            "True when this backend attempted delivery itself (SendGrid is "
            "configured). False means the frontend should fall back to "
            "Firebase's own reset email. Reflects server configuration only "
            "— never whether the submitted account exists."
        ),
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest) -> ForgotPasswordResponse:
    """
    Triggers a branded password-reset email via `email_service`.

    Every outcome — account doesn't exist, Firebase link generation fails,
    SendGrid rejects the send — is caught and logged server-side, then
    answered with the same generic message. The caller can never
    distinguish "no such account" from "email sent" from the response.

    The one thing the response does report is whether this backend is
    *configured* to send at all (`email_dispatched`). While SendGrid domain
    authentication is still pending, that flag is False and the frontend
    falls back to Firebase's built-in sender so password reset keeps
    working — just with Firebase's weaker inbox placement.
    """
    if not is_email_delivery_configured():
        logger.warning(
            "SENDGRID_API_KEY is not set — password reset will fall back to "
            "Firebase's own email sender. Configure SendGrid for reliable "
            "inbox delivery."
        )
        return ForgotPasswordResponse(email_dispatched=False)

    try:
        send_password_reset_email(payload.email)
    except Exception:
        # Deliberately broad: any failure here must still resolve to the
        # generic response below. The real reason is only ever visible in
        # server logs, never in the API response. `email_dispatched` stays
        # True so a non-existent account is indistinguishable from a real
        # one that was emailed successfully.
        logger.exception("Password reset request failed for a submitted email.")

    return ForgotPasswordResponse(email_dispatched=True)
