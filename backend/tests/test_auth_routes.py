"""
Tests for POST /auth/forgot-password.

The core security property under test: the HTTP response must be byte-for-
byte identical regardless of whether `send_password_reset_email` succeeds,
raises because the account doesn't exist, or raises for any other reason
(SendGrid down, misconfigured API key, etc). `email_service.py` itself is
mocked out here — this endpoint's own response-shaping logic is what's
under test, not Firebase/SendGrid integration.
"""

from __future__ import annotations

import os
import tempfile

_TEMP_UPLOAD_DIR = tempfile.mkdtemp(prefix="senova-test-uploads-")
os.environ["UPLOAD_DIR"] = _TEMP_UPLOAD_DIR
os.environ["DISABLE_AUTH"] = "true"

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

GENERIC_MESSAGE = "If that email exists, a reset link has been sent."


def test_returns_generic_message_when_send_succeeds():
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=True):
        with patch("app.api.routes.auth.send_password_reset_email") as mock_send:
            mock_send.return_value = None
            with TestClient(app) as client:
                response = client.post("/auth/forgot-password", json={"email": "real-user@example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_MESSAGE, "email_dispatched": True}
    mock_send.assert_called_once_with("real-user@example.com")


def test_returns_identical_generic_message_when_account_does_not_exist():
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=True):
        with patch("app.api.routes.auth.send_password_reset_email") as mock_send:
            mock_send.side_effect = Exception("simulated: no user record found for the given identifier")
            with TestClient(app) as client:
                response = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert response.status_code == 200
    # Byte-for-byte identical to the success case above — including
    # email_dispatched — so a non-existent account cannot be told apart
    # from a real one that was emailed.
    assert response.json() == {"message": GENERIC_MESSAGE, "email_dispatched": True}


def test_returns_identical_generic_message_when_email_provider_fails():
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=True):
        with patch("app.api.routes.auth.send_password_reset_email") as mock_send:
            mock_send.side_effect = Exception("simulated: SendGrid API error")
            with TestClient(app) as client:
                response = client.post("/auth/forgot-password", json={"email": "real-user@example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_MESSAGE, "email_dispatched": True}


def test_signals_fallback_when_sendgrid_is_not_configured():
    """
    With no SENDGRID_API_KEY the backend must not pretend it sent anything —
    it reports email_dispatched=False so the frontend falls back to
    Firebase's own sender instead of silently doing nothing.
    """
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=False):
        with patch("app.api.routes.auth.send_password_reset_email") as mock_send:
            with TestClient(app) as client:
                response = client.post("/auth/forgot-password", json={"email": "real-user@example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_MESSAGE, "email_dispatched": False}
    # Must not have attempted a send it can't perform.
    mock_send.assert_not_called()


def test_email_dispatched_flag_does_not_depend_on_account_existence():
    """
    The flag reports server configuration, never account state — the same
    configured backend answers identically for a real and a fake address.
    """
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=True):
        with patch("app.api.routes.auth.send_password_reset_email") as mock_send:
            with TestClient(app) as client:
                real = client.post("/auth/forgot-password", json={"email": "real-user@example.com"})
                mock_send.side_effect = Exception("simulated: no user record found")
                fake = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert real.json() == fake.json()


def test_rejects_malformed_email_client_side():
    with TestClient(app) as client:
        response = client.post("/auth/forgot-password", json={"email": "not-an-email"})

    # Pydantic's EmailStr validation rejects this before send_password_reset_email
    # is ever called — a 422 here reveals nothing about account existence,
    # only that the submitted string isn't shaped like an email address.
    assert response.status_code == 422


def test_does_not_require_authentication():
    """A signed-out user forgetting their password must not need a token."""
    with patch("app.api.routes.auth.is_email_delivery_configured", return_value=True):
        with patch("app.api.routes.auth.send_password_reset_email"):
            with TestClient(app) as client:
                response = client.post(
                    "/auth/forgot-password",
                    json={"email": "real-user@example.com"},
                    headers={},  # explicitly no Authorization header
                )
    assert response.status_code == 200



def test_reset_link_points_at_our_own_page_carrying_the_oob_code():
    """
    The emailed link must land on our branded /reset-password-confirm page
    with Firebase's oobCode intact — not on Firebase's hosted action page,
    which is the unbranded experience this whole flow replaces.
    """
    from app.services import email_service

    firebase_style_link = (
        "https://senova-dashboard.firebaseapp.com/__/auth/action"
        "?mode=resetPassword&oobCode=ABC123token&apiKey=AIzaFake"
        "&continueUrl=http%3A%2F%2Flocalhost%3A5173%2Freset-password-confirm"
    )

    with patch.object(email_service.firebase_auth, "generate_password_reset_link", return_value=firebase_style_link):
        with patch.object(email_service, "get_firebase_app", return_value=None):
            link = email_service._build_reset_link("someone@example.com")

    assert "/reset-password-confirm" in link
    assert "oobCode=ABC123token" in link
    assert "firebaseapp.com" not in link


def test_reset_link_falls_back_to_firebase_link_if_oob_code_is_missing():
    """
    If Firebase ever changes its link shape, emailing the raw Firebase link
    is still better than emailing a URL with no token in it at all.
    """
    from app.services import email_service

    link_without_code = "https://senova-dashboard.firebaseapp.com/__/auth/action?mode=resetPassword"

    with patch.object(email_service.firebase_auth, "generate_password_reset_link", return_value=link_without_code):
        with patch.object(email_service, "get_firebase_app", return_value=None):
            link = email_service._build_reset_link("someone@example.com")

    assert link == link_without_code


def test_delivery_is_reported_unconfigured_without_an_api_key():
    from app.services import email_service

    with patch.object(email_service, "SENDGRID_API_KEY", ""):
        assert email_service.is_email_delivery_configured() is False
    with patch.object(email_service, "SENDGRID_API_KEY", "SG.real-looking-key"):
        assert email_service.is_email_delivery_configured() is True
