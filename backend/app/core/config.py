"""
Central configuration for the SENOVA backend.
Keeps CORS origins, upload limits, and other env-specific values in one place.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env into the process environment before reading any
# os.getenv() calls below. Without this, values set in .env are silently
# ignored and every setting falls back to its default.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# --- CORS ---
# In development Vite runs on port 5173; add production domains here later.
ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

# --- Environment ---
# Which environment this process is running as. Defaults to "development" so
# a missing/unset value never accidentally behaves like production. Set to
# "production" on any real deployment — this gates the DISABLE_AUTH check
# directly below.
ENV: str = os.getenv("ENV", "development")

# --- Firebase Auth ---
# Two ways to supply the Admin SDK service account, checked in this order:
#
# 1. FIREBASE_SERVICE_ACCOUNT_JSON — the whole service-account JSON as a single
#    env var. This is the one to use on a managed host (Render, Railway, Fly):
#    the JSON file itself is gitignored (it holds a private key), so it can
#    never reach the host through the repo, and pasting it into a secret env
#    var avoids depending on host-specific file mounting.
# 2. FIREBASE_SERVICE_ACCOUNT_PATH — path to the JSON file on disk. This is
#    the local-development path.
FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
# Path to the Firebase service-account JSON used by firebase-admin to verify
# ID tokens issued by the frontend's Firebase Auth (Google sign-in).
# Download from Firebase Console > Project Settings > Service Accounts.
FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
# Firebase project ID — used to validate the token's audience.
FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "senova-dashboard")
# Set to "true" to disable auth enforcement (local dev only).
DISABLE_AUTH: bool = os.getenv("DISABLE_AUTH", "false").lower() == "true"

# Fail hard at import time rather than silently serving an unauthenticated
# API in production. This is the only thing standing between an accidental
# `DISABLE_AUTH=true` left over from a local .env and every route on a
# production deployment requiring no credentials at all.
if DISABLE_AUTH and ENV == "production":
    raise RuntimeError(
        "DISABLE_AUTH cannot be true when ENV=production. "
        "Remove DISABLE_AUTH (or set it to false) and configure "
        "FIREBASE_SERVICE_ACCOUNT_PATH / FIREBASE_PROJECT_ID instead."
    )

# --- Uploads ---
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "temp_uploads")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
# How long an uploaded file is kept on disk before the background sweep
# removes it. Long enough that a user can switch date filters on the
# dashboard without the file disappearing mid-session.
UPLOAD_TTL_MINUTES: int = int(os.getenv("UPLOAD_TTL_MINUTES", "120"))
# How often the background sweep runs.
UPLOAD_SWEEP_INTERVAL_MINUTES: int = int(os.getenv("UPLOAD_SWEEP_INTERVAL_MINUTES", "30"))

# --- Frame cache (memory tuning) ---
# The normalised-DataFrame LRU. These are env-tunable because the right values
# depend entirely on how much RAM the host gives you: a Render free instance
# has 512 MB total, shared with the Python process, pandas/numpy themselves and
# every in-flight request, so the defaults here are deliberately conservative
# rather than as-large-as-possible. Raise them on a bigger instance to trade
# memory for fewer re-parses.
FRAME_CACHE_MAX_ENTRIES: int = int(os.getenv("FRAME_CACHE_MAX_ENTRIES", "3"))
# Frames with more rows than this are served but never cached — slow beats
# being killed by the host's OOM reaper.
FRAME_CACHE_MAX_ROWS: int = int(os.getenv("FRAME_CACHE_MAX_ROWS", "120000"))

# --- Password reset email (SendGrid) ---
# API key for SendGrid's Mail Send API. Required only when the
# /auth/forgot-password endpoint is actually called — left empty, that
# endpoint logs a clear error and still returns its generic success message
# (never reveals whether the email is configured to the caller).
SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
# The verified "From" address for password-reset emails. Must belong to a
# domain that has completed SendGrid's domain authentication (SPF/DKIM),
# otherwise these emails land in spam exactly like Firebase's own default
# sender does today.
SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "noreply@example.com")
# Base URL of the deployed frontend. Used to build the branded
# /reset-password-confirm link that replaces Firebase's hosted action page.
# No trailing slash.
APP_DOMAIN: str = os.getenv("APP_DOMAIN", "http://localhost:5173")

# ═══════════════════════════════════════════════════════════════════════════
#  Smart Column Understanding — 2-Tier pipeline (Tier 1 local, Tier 2 Gemini)
# ═══════════════════════════════════════════════════════════════════════════
#
# Read the privacy note in the repo README before changing anything here.
#
# SENOVA's founding promise is that a shop's sales data never leaves the
# backend. That promise is what this block exists to keep honest:
#
# * ``AI_ASSIST_ENABLED`` is the master switch and defaults to **false**. With
#   it false, no code path constructs a Gemini request — the app behaves
#   exactly as it did before this feature existed.
# * Even when it is true, Tier 2 only runs if the *request* also carries
#   ``ai_consent=true`` (a form field on upload, a body field on
#   ai-insights). Both must be true. A client that omits the flag is treated
#   as declining, never as consenting.
# * What Tier 2 may see is narrowed server-side by ``pii_mask`` regardless of
#   what the client sends: no values from customer/name-like columns, and no
#   values at all from unmapped text columns.
#
# So "data never leaves our backend" is *literally* true with the switch off,
# and precisely describable with it on. Never weaken a default here.

#: Master switch for every Gemini call. False = no Gemini code path runs.
AI_ASSIST_ENABLED: bool = os.getenv("AI_ASSIST_ENABLED", "false").lower() == "true"

#: Google's Gemini API key. Read from the environment only — never hardcoded,
#: never logged, never returned in a response. Passed solely as the
#: ``x-goog-api-key`` request header. Left blank, Tier 2 is skipped.
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

#: Gemini model id. Flash-class by design: this only disambiguates column
#: headers, which is not a reasoning-heavy job. Note gemini-2.0-flash needs an
#: explicit ``propertyOrdering`` to produce well-formed structured output, so
#: prefer 2.5+ here.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

#: Per-attempt HTTP timeout for a Gemini call, in seconds.
GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10"))

#: Retry attempts after the first failure (so 2 == 3 total tries).
GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

#: Hard ceiling on the whole Tier 2 stage, in seconds. This — not the per
#: attempt timeout — is what actually protects the request: 3 attempts x 10 s
#: plus exponential backoff would otherwise run to roughly 33 s and trip the
#: frontend's request timeout on a slow response.
GEMINI_TOTAL_BUDGET_SECONDS: float = float(os.getenv("GEMINI_TOTAL_BUDGET_SECONDS", "15"))

#: Load the FastEmbed model and classify locally. When false, Tier 1 falls
#: back to the existing alias map + fuzzy keyword heuristic, so the app still
#: works — just with the older, lower-accuracy guesser.
#:
#: Set this to false on a memory-constrained host: onnxruntime plus a
#: multilingual model is a large native allocation, and the Render free tier
#: has 512 MB shared with pandas/numpy and every in-flight request.
FASTEMBED_ENABLED: bool = os.getenv("FASTEMBED_ENABLED", "true").lower() == "true"

#: FastEmbed model id. Defaults to the multilingual one because shop headers
#: are routinely Hindi or Hinglish.
#:
#: Chosen over the previously-configured ``minishlab/potion-multilingual-128M``
#: because **that model is not in FastEmbed's supported list at all**.
#: ``TextEmbedding(model_name="minishlab/potion-multilingual-128M")`` raises
#: ``ValueError``, ``embedder._load_model`` swallows it, and Tier 1 silently
#: degraded to the alias map on *every* upload — the embedding classifier was
#: inert while still paying the "fastembed is enabled" appearance. Verified
#: against ``TextEmbedding.list_supported_models()`` (30 entries).
#:
#: This is the only multilingual MiniLM-class model FastEmbed carries:
#:
#:   sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2   384-dim, ~0.22 GB
#:
#: ~50 languages including Hindi, and *smaller* than the broken default's 0.512 GB
#: — so this fixes Tier 1 without costing memory. The English-only alternatives
#: are cheaper still (BAAI/bge-small-en-v1.5 ~0.067 GB) but would push Hindi and
#: Hinglish headers onto the alias map and Tier 2.
FASTEMBED_MODEL: str = os.getenv(
    "FASTEMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

#: Where the downloaded ONNX model is cached. Gitignored — it is a ~0.22 GB
#: binary that must never reach the repo.
FASTEMBED_CACHE_PATH: str = os.getenv("FASTEMBED_CACHE_PATH", "fastembed_cache")

#: Cosine score at or above which a Tier 1 column match is trusted outright and
#: never escalated to Gemini.
HIGH_CONF_THRESHOLD: float = float(os.getenv("HIGH_CONF_THRESHOLD", "0.80"))

#: Minimum gap between the best and second-best catalog label. Below this the
#: top two meanings are too close to call on a header alone, so the column is
#: escalated to Tier 2 even if it cleared ``HIGH_CONF_THRESHOLD`` — this is
#: what catches MRP-vs-Selling-Price, where both labels are strongly present.
AMBIGUITY_MARGIN: float = float(os.getenv("AMBIGUITY_MARGIN", "0.05"))

#: How much of a Tier 1 column score comes from the header text versus the
#: value-shape statistics. They must sum to 1.
TIER1_HEADER_WEIGHT: float = float(os.getenv("TIER1_HEADER_WEIGHT", "0.7"))
TIER1_STATS_WEIGHT: float = float(os.getenv("TIER1_STATS_WEIGHT", "0.3"))
