"""
Firebase credential resolution.

Deploying to a managed host is the reason this logic exists: the
service-account file is gitignored (it carries a private key), so on
Render/Railway/Fly the credentials have to arrive as an env var instead.
These tests pin the resolution order and, more importantly, the failure
messages — a silent or cryptic credential failure here means every
authenticated request 500s with nothing useful in the logs.

The Firebase SDK itself is mocked: what's under test is which credential
source gets chosen and how bad input is reported, not Google's verifier.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DISABLE_AUTH", "true")

from app.utils import auth_verifier  # noqa: E402


def _fake_service_account(private_key: str = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n") -> dict:
    return {
        "type": "service_account",
        "project_id": "senova-dashboard",
        "private_key_id": "key-id",
        "private_key": private_key,
        "client_email": "sa@senova-dashboard.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@pytest.fixture(autouse=True)
def _reset_cached_app():
    """The Admin app is initialised once and memoised; clear it per test."""
    auth_verifier._firebase_app = None
    yield
    auth_verifier._firebase_app = None


def test_json_env_var_is_preferred_over_the_file_path():
    """
    On a managed host both may be set (the path left over from local dev).
    The env var has to win, otherwise the host tries to read a file that
    was never deployed.
    """
    account = _fake_service_account()

    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps(account)):
        with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_PATH", "/nonexistent/should-not-be-read.json"):
            with patch.object(auth_verifier.credentials, "Certificate") as mock_cert:
                with patch.object(auth_verifier.firebase_admin, "initialize_app", return_value=MagicMock()):
                    auth_verifier.get_firebase_app()

    # Certificate was handed a parsed dict (the env var), not a path string.
    mock_cert.assert_called_once()
    passed = mock_cert.call_args[0][0]
    assert isinstance(passed, dict)
    assert passed["client_email"] == account["client_email"]


def test_escaped_newlines_in_the_private_key_are_repaired():
    """
    Plenty of dashboards store the JSON with newlines already escaped, so the
    key arrives with the two characters \\n where real line breaks belong.
    Left alone the PEM is rejected with an unhelpful "No key could be
    detected" error.
    """
    mangled = "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"
    account = _fake_service_account(private_key=mangled)

    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps(account)):
        with patch.object(auth_verifier.credentials, "Certificate") as mock_cert:
            with patch.object(auth_verifier.firebase_admin, "initialize_app", return_value=MagicMock()):
                auth_verifier.get_firebase_app()

    repaired = mock_cert.call_args[0][0]["private_key"]
    assert "\\n" not in repaired
    assert repaired.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert repaired.endswith("-----END PRIVATE KEY-----\n")


def test_a_well_formed_key_is_left_untouched():
    account = _fake_service_account()
    original = account["private_key"]

    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps(account)):
        with patch.object(auth_verifier.credentials, "Certificate") as mock_cert:
            with patch.object(auth_verifier.firebase_admin, "initialize_app", return_value=MagicMock()):
                auth_verifier.get_firebase_app()

    assert mock_cert.call_args[0][0]["private_key"] == original


def test_file_path_is_used_when_no_json_env_var_is_set():
    account = _fake_service_account()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(account, handle)
        path = handle.name

    try:
        with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", ""):
            with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_PATH", path):
                with patch.object(auth_verifier.credentials, "Certificate") as mock_cert:
                    with patch.object(auth_verifier.firebase_admin, "initialize_app", return_value=MagicMock()):
                        auth_verifier.get_firebase_app()

        # The file path is passed through as-is for this branch.
        mock_cert.assert_called_once_with(path)
    finally:
        os.unlink(path)


def test_missing_file_path_says_so_plainly():
    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", ""):
        with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_PATH", "/nope/missing.json"):
            with pytest.raises(RuntimeError, match="does not exist"):
                auth_verifier.get_firebase_app()


def test_no_credentials_at_all_names_both_options():
    """
    The error a fresh deployment is most likely to hit, so it must name the
    env var (the deployed-host answer), the file path (the local answer) and
    the DISABLE_AUTH escape hatch.
    """
    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", ""):
        with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_PATH", ""):
            with pytest.raises(RuntimeError) as excinfo:
                auth_verifier.get_firebase_app()

    message = str(excinfo.value)
    assert "FIREBASE_SERVICE_ACCOUNT_JSON" in message
    assert "FIREBASE_SERVICE_ACCOUNT_PATH" in message
    assert "DISABLE_AUTH" in message


def test_malformed_json_is_reported_as_such():
    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", "{not valid json"):
        with pytest.raises(RuntimeError, match="not valid JSON"):
            auth_verifier.get_firebase_app()


def test_json_that_is_not_an_object_is_rejected():
    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", '["a", "list"]'):
        with pytest.raises(RuntimeError, match="must be a JSON object"):
            auth_verifier.get_firebase_app()


def test_the_admin_app_is_only_initialised_once():
    account = _fake_service_account()

    with patch.object(auth_verifier, "FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps(account)):
        with patch.object(auth_verifier.credentials, "Certificate"):
            with patch.object(auth_verifier.firebase_admin, "initialize_app", return_value=MagicMock()) as mock_init:
                first = auth_verifier.get_firebase_app()
                second = auth_verifier.get_firebase_app()

    assert first is second
    mock_init.assert_called_once()
