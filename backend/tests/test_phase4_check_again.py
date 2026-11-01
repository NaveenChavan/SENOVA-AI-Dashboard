"""
Phase 4.1 — "Check again with AI" (explicit forced Tier 2 retry).

What is proven here
--------------------
* ``force_recheck=True`` always reaches Gemini fresh — the verdict cache is
  bypassed on both read and write for that call.
* A 10-second cooldown blocks a second forced recheck for the same
  (user, file) before it elapses, and allows it again once the window passes.
* AI disabled and consent withheld both still make zero Gemini calls even
  with ``force_recheck=True`` — forcing a retry can widen *when* Tier 2 is
  asked to run, never *whether* consent/availability gates it.
* ``columns_evaluated`` / ``columns_resolved`` are counts measured from the
  actual call, including the zero case.
* A Gemini failure during a forced recheck still returns a complete,
  explained mapping — Phases 1-3 behaviour is untouched.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services import tier2_cooldown
from tests.conftest import INTRUDER, OWNER

UNKNOWN_FILE_ID = "0" * 32


@pytest.fixture(autouse=True)
def _reset_cooldown():
    """Every test starts with a clean cooldown tracker."""
    tier2_cooldown.reset()
    yield
    tier2_cooldown.reset()


@pytest.fixture
def gemini_reachable(monkeypatch):
    """Force AI on server-side and make every transport attempt observable."""
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")

    attempts: list[dict] = []

    class _Recording:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, **kwargs):
            attempts.append(json)
            import httpx

            body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"columns": [{"column": "Zorp Factor", '
                                        '"label": "product", "confidence": 0.9, '
                                        '"reason": "test"}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Recording)
    return attempts


def _ambiguous_frame() -> pd.DataFrame:
    """Headers Tier 1 cannot settle, so Tier 2 always has something to do."""
    return pd.DataFrame({"Zorp Factor": ["alpha", "beta", "gamma"], "Date": ["2026-01-01", "2026-01-02", "2026-01-03"]})


def _upload(client, frame, **form):
    csv_bytes = frame.to_csv(index=False).encode("utf-8")
    return client.post(
        "/upload/", files={"file": ("export.csv", io.BytesIO(csv_bytes), "text/csv")}, data=form
    )


# ── Forces a fresh Tier 2 request and bypasses the cache ───────────────────


def test_force_recheck_bypasses_the_cache(client, gemini_reachable):
    """
    A cached verdict must not be served back on a forced recheck: the whole
    point of the button is a second, fresh opinion. Both calls hit the
    transport.
    """
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    assert upload.status_code == 201
    file_id = upload.json()["file_id"]

    first = client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True})
    assert first.status_code == 200
    assert len(gemini_reachable) == 1, "the automatic pass should have called Gemini once"

    # Advance past the cooldown window so the second call isn't blocked by it —
    # this test is about the cache, not the cooldown.
    tier2_cooldown.reset(OWNER, file_id)

    second = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True},
    )
    assert second.status_code == 200
    assert len(gemini_reachable) == 2, "force_recheck must bypass the cache and call Gemini again"


def test_non_forced_call_is_served_from_cache(client, gemini_reachable):
    """Sanity check for the test above: without force_recheck, a second
    identical call is cache-served and makes no second Gemini call."""
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True})
    assert len(gemini_reachable) == 1

    client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True})
    assert len(gemini_reachable) == 1, "an unforced repeat call should hit the cache, not Gemini"


# ── Cooldown ─────────────────────────────────────────────────────────────────


def test_cooldown_rejects_a_repeated_forced_request(client, gemini_reachable):
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    first = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert first.status_code == 200
    calls_after_first = len(gemini_reachable)

    second = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert second.status_code == 429
    body = second.json()["detail"]
    assert body["reason_code"] == "cooldown"
    assert body["retry_after_seconds"] > 0
    # No additional Gemini call was made while the cooldown was active.
    assert len(gemini_reachable) == calls_after_first


def test_cooldown_allows_another_forced_request_once_elapsed(client, gemini_reachable):
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True})
    assert len(gemini_reachable) == 1

    # Simulate the cooldown window having passed, without sleeping real time.
    tier2_cooldown.record_attempt(OWNER, file_id, now=tier2_cooldown.time.monotonic() - 11.0)

    second = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert second.status_code == 200
    assert len(gemini_reachable) == 2


def test_cooldown_is_scoped_per_owner_and_file(client, gemini_reachable):
    """A cooldown on one file must not block a forced recheck on another."""
    file_a = _upload(client, _ambiguous_frame(), ai_consent="true").json()["file_id"]
    file_b = _upload(client, _ambiguous_frame(), ai_consent="true").json()["file_id"]

    r1 = client.post(f"/upload/{file_a}/tier2", json={"ai_consent": True, "force_recheck": True})
    assert r1.status_code == 200

    r2 = client.post(f"/upload/{file_b}/tier2", json={"ai_consent": True, "force_recheck": True})
    assert r2.status_code == 200, "a different file must not be blocked by file_a's cooldown"


# ── Zero-call guarantees, even when forced ──────────────────────────────────


def test_force_recheck_with_ai_disabled_makes_zero_calls(client, monkeypatch):
    """AI off server-side must still produce zero Gemini calls even when the
    user explicitly asks for a recheck."""
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", False)

    attempts: list[str] = []

    class _Tripped:
        def __init__(self, *a, **k):
            attempts.append("client")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            attempts.append("post")
            raise AssertionError("Gemini was contacted while AI_ASSIST_ENABLED=False.")

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Tripped)

    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert response.status_code == 200
    assert attempts == []
    assert response.json()["columns_evaluated"] == 0
    assert response.json()["columns_resolved"] == 0


def test_force_recheck_without_consent_makes_zero_calls(client, gemini_reachable):
    """Consent withheld must still produce zero Gemini calls even when the
    user's own action is the forced-recheck button."""
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": False, "force_recheck": True}
    )
    assert response.status_code == 200
    assert gemini_reachable == []
    assert response.json()["columns_evaluated"] == 0
    assert response.json()["columns_resolved"] == 0


# ── Honest counts ────────────────────────────────────────────────────────────


def test_counts_reflect_actual_resolution(client, gemini_reachable):
    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert response.status_code == 200
    body = response.json()
    # Exactly one ambiguous column ("Zorp Factor"; "Date" resolves locally),
    # and the stub always answers it, so evaluated == resolved == 1.
    assert body["columns_evaluated"] == 1
    assert body["columns_resolved"] == 1


def test_counts_are_zero_when_nothing_is_ambiguous(client, gemini_reachable):
    """A file with no ambiguous columns must report 0/0, not a stale number."""
    frame = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02"], "Line Total": [100.0, 200.0]})
    upload = _upload(client, frame, ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["columns_evaluated"] == 0
    assert body["columns_resolved"] == 0
    assert gemini_reachable == []


# ── Errors stay recoverable ──────────────────────────────────────────────────


def test_force_recheck_failure_leaves_a_usable_mapping(client, monkeypatch):
    """A Gemini failure during a forced recheck must degrade exactly like the
    automatic pass does: a complete mapping, a clear reason, nothing thrown."""
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(tier2_gemini, "GEMINI_FALLBACK_MODEL", "")

    class _Failing:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise __import__("httpx").TransportError("boom")

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Failing)

    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_notice"] is not None
    assert body["columns_resolved"] == 0
    rows = {row["raw_column"]: row for row in body["detected_columns"]}
    assert rows["Zorp Factor"]["source"] == "fallback"


# ── Ownership ────────────────────────────────────────────────────────────────


def test_force_recheck_enforces_file_ownership(client, gemini_reachable):
    from app.main import app
    from app.utils.auth_verifier import get_current_user

    upload = _upload(client, _ambiguous_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    app.dependency_overrides[get_current_user] = lambda: INTRUDER
    response = client.post(
        f"/upload/{file_id}/tier2", json={"ai_consent": True, "force_recheck": True}
    )
    app.dependency_overrides[get_current_user] = lambda: OWNER
    assert response.status_code == 404



# ── Targeted forced retry (target_columns / force_columns) ─────────────────
#
# These close the coverage gap the Phase 4 security review found: the
# backend accepts and filters on ``target_columns``, but no test had ever
# exercised a request that actually named a subset. The frontend's one
# button always omits this field (retrying "everything still ambiguous"),
# which remains the only behaviour the UI exposes — see the final report for
# that explicit scope note. These tests exist to verify the underlying
# route/service contract on its own terms, not to imply a UI affordance.


def _two_ambiguous_columns_frame() -> pd.DataFrame:
    """Two headers Tier 1 cannot settle, plus a clean Date column."""
    return pd.DataFrame(
        {
            "Zorp Factor": ["alpha", "beta", "gamma"],
            "Quibble Code": ["x1", "y2", "z3"],
            "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        }
    )


@pytest.fixture
def gemini_multi_column_stub(monkeypatch):
    """
    Like ``gemini_reachable``, but answers whichever columns were actually
    asked about, so a test can assert on exactly which subset reached the
    transport in a given call.
    """
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")

    requests: list[list[str]] = []

    class _Recording:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, **kwargs):
            import httpx

            prompt_text = json["contents"][0]["parts"][0]["text"]
            # Recover which columns were actually described in this call from
            # the prompt body the production code built — the same evidence
            # standard the existing suite already uses for request-body proofs.
            asked = [name for name in ("Zorp Factor", "Quibble Code") if name in prompt_text]
            requests.append(asked)

            columns_payload = [
                {"column": name, "label": "product", "confidence": 0.9, "reason": "test"}
                for name in asked
            ]
            body = {
                "candidates": [
                    {"content": {"parts": [{"text": __import__("json").dumps({"columns": columns_payload})}]}}
                ]
            }
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Recording)
    return requests


def test_targeted_retry_escalates_only_the_named_column(client, gemini_multi_column_stub):
    """Two columns are ambiguous; naming one in target_columns must leave the
    other column untouched by this call."""
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    # Automatic pass resolves both columns once.
    first = client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True})
    assert first.status_code == 200
    assert sorted(gemini_multi_column_stub[0]) == ["Quibble Code", "Zorp Factor"]

    tier2_cooldown.reset(OWNER, file_id)

    # Forced, targeted retry naming only "Zorp Factor".
    second = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    assert second.status_code == 200
    assert gemini_multi_column_stub[1] == ["Zorp Factor"], (
        "a targeted forced retry must describe only the named column to Gemini"
    )
    body = second.json()
    assert body["columns_evaluated"] == 1
    assert body["columns_resolved"] == 1


def test_targeted_retry_ignores_unknown_or_nonexistent_column_names(client, gemini_multi_column_stub):
    """A target naming a column that doesn't exist (or was never ambiguous)
    must not expand escalation — it is silently excluded, not force-escalated."""
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2",
        json={
            "ai_consent": True,
            "force_recheck": True,
            "target_columns": ["Zorp Factor", "Nonexistent Column", "Date"],
        },
    )
    assert response.status_code == 200
    # "Date" resolves locally and was never routed to Gemini; "Nonexistent
    # Column" isn't in the file at all. Only "Zorp Factor" is both present
    # and actually ambiguous, so only it reaches the transport.
    assert gemini_multi_column_stub[0] == ["Zorp Factor"]
    body = response.json()
    assert body["columns_evaluated"] == 1


def test_omitted_targets_preserve_default_whole_ambiguous_set_behaviour(client, gemini_multi_column_stub):
    """No target_columns (or an empty list) must retry every still-ambiguous
    column, unchanged from the pre-Phase-4.1 behaviour."""
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": []},
    )
    assert response.status_code == 200
    assert sorted(gemini_multi_column_stub[0]) == ["Quibble Code", "Zorp Factor"]
    assert response.json()["columns_evaluated"] == 2

    tier2_cooldown.reset(OWNER, file_id)

    # And the field omitted entirely (the default) behaves identically.
    response2 = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True},
    )
    assert response2.status_code == 200
    assert sorted(gemini_multi_column_stub[1]) == ["Quibble Code", "Zorp Factor"]
    assert response2.json()["columns_evaluated"] == 2


def test_targeted_retry_still_makes_zero_calls_without_consent(client, gemini_multi_column_stub):
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": False, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    assert response.status_code == 200
    assert gemini_multi_column_stub == []
    assert response.json()["columns_evaluated"] == 0


def test_targeted_retry_still_makes_zero_calls_when_ai_disabled(client, monkeypatch):
    from app.services import tier2_gemini

    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", False)

    attempts: list[str] = []

    class _Tripped:
        def __init__(self, *a, **k):
            attempts.append("client")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            attempts.append("post")
            raise AssertionError("Gemini was contacted despite AI_ASSIST_ENABLED=False.")

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", _Tripped)

    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    response = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    assert response.status_code == 200
    assert attempts == []
    assert response.json()["columns_evaluated"] == 0


def test_targeted_retry_still_bypasses_the_cache(client, gemini_multi_column_stub):
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    client.post(f"/upload/{file_id}/tier2", json={"ai_consent": True})
    calls_after_auto = len(gemini_multi_column_stub)

    tier2_cooldown.reset(OWNER, file_id)
    response = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    assert response.status_code == 200
    assert len(gemini_multi_column_stub) == calls_after_auto + 1, (
        "a targeted forced retry must still bypass the cache and reach Gemini again"
    )


def test_targeted_retry_still_respects_the_10_second_cooldown(client, gemini_multi_column_stub):
    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    first = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    assert first.status_code == 200
    calls_after_first = len(gemini_multi_column_stub)

    second = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Quibble Code"]},
    )
    assert second.status_code == 429
    assert second.json()["detail"]["reason_code"] == "cooldown"
    # No additional Gemini call for the second (different) target either —
    # the cooldown is per (owner, file), not per target column.
    assert len(gemini_multi_column_stub) == calls_after_first


def test_targeted_retry_enforces_file_ownership(client, gemini_multi_column_stub):
    from app.main import app
    from app.utils.auth_verifier import get_current_user

    upload = _upload(client, _two_ambiguous_columns_frame(), ai_consent="true")
    file_id = upload.json()["file_id"]

    app.dependency_overrides[get_current_user] = lambda: INTRUDER
    response = client.post(
        f"/upload/{file_id}/tier2",
        json={"ai_consent": True, "force_recheck": True, "target_columns": ["Zorp Factor"]},
    )
    app.dependency_overrides[get_current_user] = lambda: OWNER
    assert response.status_code == 404
