"""
Tests for the Tier 2 Gemini client.

``httpx.AsyncClient.post`` is replaced with a recording stub, which buys two
things a plain mock could not give us: we can assert on the **exact request body
that would have been sent** (so "no customer name in the payload" is a real
assertion about real bytes, not an intention), and we can assert that the
transport was **never touched at all** when consent is withheld.
"""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest

from app.core.config import GEMINI_API_KEY, GEMINI_MAX_RETRIES
from app.services import tier2_gemini
from app.services.tier2_gemini import (
    SOURCE_CACHE,
    SOURCE_FAILED,
    SOURCE_GEMINI,
    SOURCE_SKIPPED,
    _build_prompt,
    _extract_json,
    _sanitise_verdicts,
    describe_column,
    resolve_columns,
)


# ── Test doubles ─────────────────────────────────────────────────────────────


class _Recorder:
    """
    Stand-in for ``httpx.AsyncClient`` that records every request body.

    ``script`` is consumed one entry per call: an int status code, or a callable
    receiving the request body and returning ``(status, text)``.
    """

    def __init__(self, script):
        self.script = list(script)
        self.bodies: list[dict] = []
        self.headers: list[dict] = []

    def post(self, url, json=None, **kwargs):
        self.bodies.append(json)
        self.headers.append(dict(kwargs.get("headers") or {}))

        item = self.script.pop(0) if self.script else (200, "{}")
        if callable(item):
            item = item(json)
        status, text = item
        return httpx.Response(
            status_code=status,
            json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
            request=httpx.Request("POST", url),
        )

    @property
    def call_count(self):
        return len(self.bodies)

    def sent_text(self) -> str:
        """The full request body as one string, for absence assertions."""
        return json.dumps(self.bodies[0], ensure_ascii=False)


def _install(monkeypatch, recorder):
    """Swap AsyncClient for the recorder, inside and outside the context manager."""

    class _FakeClient:
        async def __aenter__(self):
            # Must return the client, not the recorder. ``async with
            # httpx.AsyncClient(...) as client`` binds whatever this returns and
            # that is the object ``_call_gemini`` awaits ``.post`` on — returning
            # the recorder (whose ``post`` is synchronous) produces "object
            # Response can't be used in 'await' expression".
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, **kwargs):
            # Must be a coroutine, since the real client is awaited.
            return recorder.post(url, json=json, **kwargs)

    monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", lambda **kwargs: _FakeClient())
    return recorder


@pytest.fixture
def ai_on(monkeypatch):
    """Operator switch on and a key present."""
    monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
    monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(tier2_gemini, "GEMINI_TOTAL_BUDGET_SECONDS", 5.0)


def _columns(**overrides):
    base = {
        "name": "Sales Value",
        "dtype": "float64",
        "stats": {"numeric_ratio": 1.0, "date_parse_ratio": 0.0, "unique_ratio": 0.4},
        "samples": ["1200", "1500"],
        "suppressed": False,
    }
    base.update(overrides)
    return base


def _ok_body(label="revenue", confidence=0.9):
    return json.dumps(
        {"columns": [{"column": "Sales Value", "label": label, "confidence": confidence, "reason": "ok"}]}
    )


# ── The consent gate ─────────────────────────────────────────────────────────


class TestConsentGate:
    async def test_consent_false_makes_zero_calls(self, monkeypatch, ai_on):
        """The headline guarantee: with AI enabled on the server but consent
        withheld on the request, the transport is never touched."""
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        result = await resolve_columns([_columns()], ai_consent=False)

        assert recorder.call_count == 0
        assert result.source == SOURCE_SKIPPED
        assert result.verdicts == {}
        assert "not approved" in (result.notice or "")

    async def test_master_switch_off_makes_zero_calls(self, monkeypatch):
        monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", False)
        monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "test-key-not-real")

        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))
        result = await resolve_columns([_columns()], ai_consent=True)

        assert recorder.call_count == 0
        assert result.source == SOURCE_SKIPPED
        assert "switched off" in (result.notice or "")

    async def test_missing_key_makes_zero_calls_and_says_so(self, monkeypatch):
        monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
        monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "")

        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))
        result = await resolve_columns([_columns()], ai_consent=True)

        assert recorder.call_count == 0
        assert result.source == SOURCE_SKIPPED
        assert "no API key" in (result.notice or "")

    async def test_consent_is_not_persisted_via_the_cache(self, monkeypatch, ai_on):
        """A declined request must not leave a cache entry, or the next request
        would be served a verdict the user never agreed to."""
        saved = {}
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        await resolve_columns(
            [_columns()],
            ai_consent=False,
            cache_load=lambda key: {},
            cache_save=lambda key, verdicts: saved.__setitem__(key, verdicts),
            cache_key="abc",
        )

        assert recorder.call_count == 0
        assert saved == {}

    async def test_cache_is_not_even_consulted_without_consent(self, monkeypatch, ai_on):
        consulted = []
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        await resolve_columns(
            [_columns()],
            ai_consent=False,
            cache_load=lambda key: consulted.append(key) or {"Sales Value": {"label": "revenue"}},
            cache_key="abc",
        )

        assert consulted == []

    async def test_empty_column_list_short_circuits(self, ai_on):
        result = await resolve_columns([], ai_consent=True)
        assert result.source == SOURCE_SKIPPED
        assert result.verdicts == {}


# ── The happy path ───────────────────────────────────────────────────────────


class TestSuccess:
    async def test_valid_response_is_returned(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        result = await resolve_columns([_columns()], ai_consent=True)

        assert recorder.call_count == 1
        assert result.source == SOURCE_GEMINI
        assert result.verdicts["Sales Value"]["label"] == "revenue"
        assert result.elapsed_ms >= 0

    async def test_api_key_travels_only_as_a_header(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))
        await resolve_columns([_columns()], ai_consent=True)

        body_text = recorder.sent_text()
        assert "test-key-not-real" not in body_text
        # The key must never reach the prompt or the generation config.
        assert "x-goog-api-key" not in body_text

    async def test_fenced_json_is_accepted(self, monkeypatch, ai_on):
        fenced = "```json\n" + _ok_body() + "\n```"
        _install(monkeypatch, _Recorder([(200, fenced)]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_GEMINI

    async def test_cache_hit_skips_the_network(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        result = await resolve_columns(
            [_columns()],
            ai_consent=True,
            cache_load=lambda key: {"Sales Value": {"label": "cost", "confidence": 0.7, "reason": ""}},
            cache_key="abc",
        )

        assert recorder.call_count == 0
        assert result.source == SOURCE_CACHE
        assert result.verdicts["Sales Value"]["label"] == "cost"

    async def test_success_is_cached(self, monkeypatch, ai_on):
        _install(monkeypatch, _Recorder([(200, _ok_body())]))
        saved = {}

        await resolve_columns(
            [_columns()],
            ai_consent=True,
            cache_save=lambda key, verdicts: saved.update({key: verdicts}),
            cache_key="abc",
        )

        assert saved["abc"]["Sales Value"]["label"] == "revenue"

    async def test_system_instruction_states_the_constraints(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))
        await resolve_columns([_columns()], ai_consent=True)

        instruction = recorder.bodies[0]["systemInstruction"]["parts"][0]["text"]
        assert '"other"' in instruction
        assert "aggregate only" in instruction


# ── Failure and retry ────────────────────────────────────────────────────────


class TestFailureHandling:
    async def test_timeout_falls_back(self, monkeypatch, ai_on):
        class _TimeoutClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, json=None, **kwargs):
                raise httpx.ConnectTimeout("too slow")

        monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", lambda **kwargs: _TimeoutClient())

        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_FAILED
        assert result.verdicts == {}
        assert result.reason_code == "timeout"

    async def test_401_unauthorized(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(401, "unauthorized")]))
        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_FAILED
        assert result.reason_code == "key_invalid"

    async def test_403_forbidden(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(403, "forbidden")]))
        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_FAILED
        assert result.reason_code == "key_invalid"

    async def test_404_model_unavailable(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        # 404 for primary, 404 for fallback
        recorder = _install(monkeypatch, _Recorder([(404, "not found"), (404, "not found")]))
        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_FAILED
        assert result.reason_code == "model_unavailable"

    async def test_fallback_used(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(404, "not found"), (200, _ok_body())]))
        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_GEMINI
        assert result.reason_code == "fallback_used"


    async def test_rate_limit_is_retried_then_succeeds(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(
            monkeypatch,
            _Recorder([(429, "rate limited"), (200, _ok_body())]),
        )

        result = await resolve_columns([_columns()], ai_consent=True)

        assert recorder.call_count == 2
        assert result.source == SOURCE_GEMINI
        assert result.reason_code is None

    async def test_server_error_is_retried(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(503, "unavailable"), (200, _ok_body())]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert recorder.call_count == 2
        assert result.source == SOURCE_GEMINI
        assert result.reason_code is None

    async def test_bad_json_is_retried_once_then_succeeds(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(200, "not json at all"), (200, _ok_body())]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert recorder.call_count == 2
        assert result.source == SOURCE_GEMINI

    async def test_bad_json_exhausted_falls_back(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(200, "nope"), (200, "still nope"), (200, "nope again")]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.source == SOURCE_FAILED
        assert recorder.call_count == GEMINI_MAX_RETRIES + 1

    async def test_client_error_is_not_retried(self, monkeypatch, ai_on):
        """A 400 means our request is wrong; retrying it just wastes the budget."""
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(400, "bad request")]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert recorder.call_count == 1
        assert result.source == SOURCE_FAILED
        assert result.reason_code == "bad_request"

    async def test_rate_limit_exhausted_returns_reason(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, '_BACKOFF_BASE', 0.0)
        recorder = _install(monkeypatch, _Recorder([(429, 'rate limited')] * 5))
        result = await tier2_gemini.resolve_columns([_columns()], ai_consent=True)
        assert result.source == tier2_gemini.SOURCE_FAILED
        assert result.reason_code == 'rate_limit'

    async def test_server_error_exhausted_returns_reason(self, monkeypatch, ai_on):
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        recorder = _install(monkeypatch, _Recorder([(503, "unavailable")] * 5))
        result = await tier2_gemini.resolve_columns([_columns()], ai_consent=True)
        assert result.source == tier2_gemini.SOURCE_FAILED
        assert result.reason_code == "server_error"

    async def test_strict_budgeting_halts_slow_server(self, monkeypatch, ai_on):
        # Even if the client timeout is huge (e.g. 100s), the total budget (15s) must win.
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        monkeypatch.setattr(tier2_gemini, "GEMINI_TOTAL_BUDGET_SECONDS", 1.0)
        monkeypatch.setattr(tier2_gemini, "GEMINI_TIMEOUT_SECONDS", 10.0)
        
        class _SlowClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, url, json=None, timeout=None, **kwargs):
                import asyncio
                # Sleep longer than the total budget to simulate a slow response.
                await asyncio.sleep(1.5)
                raise httpx.TimeoutException("too slow")
                
        monkeypatch.setattr(tier2_gemini.httpx, "AsyncClient", lambda **kwargs: _SlowClient())
        
        import time
        start = time.monotonic()
        result = await tier2_gemini.resolve_columns([_columns()], ai_consent=True)
        elapsed = time.monotonic() - start
        
        assert result.source == tier2_gemini.SOURCE_FAILED
        assert result.reason_code == "timeout"
        assert elapsed < 3.0, f"Took {elapsed}s, meaning it retried despite budget exhaustion"

    async def test_exhausted_budget_short_circuits(self, monkeypatch, ai_on):
        """When the deadline has already passed we must not start another
        10-second attempt, or the upload could blow past the frontend timeout."""
        monkeypatch.setattr(tier2_gemini, "_BACKOFF_BASE", 0.0)
        monkeypatch.setattr(tier2_gemini, "GEMINI_TOTAL_BUDGET_SECONDS", 0.0)
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert recorder.call_count == 0
        assert result.source == SOURCE_FAILED

    async def test_hallucinated_column_is_discarded(self, monkeypatch, ai_on):
        payload = json.dumps(
            {
                "columns": [
                    {"column": "Sales Value", "label": "revenue", "confidence": 0.9},
                    {"column": "Customer SSN", "label": "customer", "confidence": 0.9},
                ]
            }
        )
        _install(monkeypatch, _Recorder([(200, payload)]))

        result = await resolve_columns([_columns()], ai_consent=True)
        assert "Sales Value" in result.verdicts
        assert "Customer SSN" not in result.verdicts

    async def test_invented_label_is_discarded(self, monkeypatch, ai_on):
        _install(monkeypatch, _Recorder([(200, _ok_body(label="profit_margin"))]))
        result = await resolve_columns([_columns()], ai_consent=True)
        assert result.verdicts == {}


# ── What actually goes over the wire ─────────────────────────────────────────


class TestPayloadPrivacy:
    async def test_customer_values_never_appear_in_the_request(self, monkeypatch, ai_on):
        """The core privacy assertion, made on real request bytes."""
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body(label="customer"))]))

        series = pd.Series(["Ramesh Sharma", "Sunita Verma", "Ajay Gupta", "Priya Nair"])
        column = describe_column(series, "Buyer", label="customer")
        assert column["suppressed"] is True

        await resolve_columns([column], ai_consent=True)

        sent = recorder.sent_text()
        for name in ("Ramesh", "Sharma", "Sunita", "Ajay", "Priya", "Nair"):
            assert name not in sent, f"{name} leaked into the request body"

    async def test_unmapped_text_values_never_appear_in_the_request(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        series = pd.Series(["delivered to 14B Linking Road", "customer waited 3 days", "second attempt"])
        column = describe_column(series, "Vendor Remark XYZ", label="other")
        assert column["suppressed"] is True

        await resolve_columns([column], ai_consent=True)

        sent = recorder.sent_text()
        for fragment in ("Linking Road", "customer waited", "second attempt"):
            assert fragment not in sent

    async def test_suppressed_column_sends_no_samples_key_at_all(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        column = describe_column(pd.Series(["Ramesh Sharma", "Sunita Verma"]), "Buyer", label="customer")
        await resolve_columns([column], ai_consent=True)

        described = recorder.bodies[0]["contents"][0]["parts"][0]["text"]
        entry = json.loads(described.split("Columns:\n", 1)[1])[0]
        assert "sample_values" not in entry
        # The header and the statistics are still there — they're the useful part.
        assert entry["column"] == "Buyer"
        assert "shape" in entry

    async def test_permitted_samples_are_masked(self, monkeypatch, ai_on):
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        series = pd.Series(["contact ramesh@shop.in or 9876543210", "call 9876543210 again"])
        column = describe_column(series, "Reference Note", label="id")
        assert column["suppressed"] is False

        await resolve_columns([column], ai_consent=True)

        sent = recorder.sent_text()
        assert "ramesh@shop.in" not in sent
        assert "9876543210" not in sent
        assert "[email]" in sent and "[phone]" in sent

    async def test_no_raw_rows_are_ever_sent(self, monkeypatch, ai_on):
        """A file with 200 rows must still produce a prompt describing a handful
        of columns — never the rows themselves."""
        recorder = _install(monkeypatch, _Recorder([(200, _ok_body())]))

        frame = pd.DataFrame(
            {
                "Sales Value": [100 + i for i in range(200)],
                "Buyer": [f"Customer Number {i}" for i in range(200)],
            }
        )
        columns = [
            describe_column(frame["Sales Value"], "Sales Value", label="other"),
            describe_column(frame["Buyer"], "Buyer", label="customer"),
        ]

        await resolve_columns(columns, ai_consent=True)

        sent = recorder.sent_text()
        assert "Customer Number 137" not in sent
        assert len(sent) < 4000


# ── Pure helpers ─────────────────────────────────────────────────────────────


class TestHelpers:
    def test_build_prompt_omits_absent_samples(self):
        prompt = _build_prompt([_columns(samples=[], suppressed=True)])
        assert "sample_values" not in prompt

    def test_build_prompt_includes_present_samples(self):
        prompt = _build_prompt([_columns(samples=["1200"])])
        assert '"sample_values"' in prompt

    def test_extract_json_rejects_empty(self):
        with pytest.raises(ValueError):
            _extract_json("")

    def test_extract_json_rejects_prose(self):
        with pytest.raises(ValueError):
            _extract_json("I'm sorry, I can't help with that.")

    def test_sanitise_lowers_and_strips_labels(self):
        payload = {"columns": [{"column": "A", "label": "  Revenue ", "confidence": 0.8}]}
        assert _sanitise_verdicts(payload, ["A"])["A"]["label"] == "revenue"

    def test_sanitise_rejects_out_of_range_confidence(self):
        from pydantic import ValidationError

        payload = {"columns": [{"column": "A", "label": "revenue", "confidence": 5.0}]}
        with pytest.raises(ValidationError):
            _sanitise_verdicts(payload, ["A"])

    def test_gemini_enabled_requires_both_switch_and_key(self, monkeypatch):
        monkeypatch.setattr(tier2_gemini, "AI_ASSIST_ENABLED", True)
        monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "")
        assert tier2_gemini.gemini_enabled() is False

        monkeypatch.setattr(tier2_gemini, "GEMINI_API_KEY", "k")
        assert tier2_gemini.gemini_enabled() is True