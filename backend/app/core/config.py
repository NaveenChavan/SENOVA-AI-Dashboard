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

# --- Firebase Auth ---
# Path to the Firebase service-account JSON used by firebase-admin to verify
# ID tokens issued by the frontend's Firebase Auth (Google sign-in).
# Download from Firebase Console > Project Settings > Service Accounts.
FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
# Firebase project ID — used to validate the token's audience.
FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "senova-dashboard")
# Set to "true" to disable auth enforcement (local dev only).
DISABLE_AUTH: bool = os.getenv("DISABLE_AUTH", "false").lower() == "true"

# --- Uploads ---
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "temp_uploads")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
# How long an uploaded file is kept on disk before the background sweep
# removes it. Long enough that a user can switch date filters on the
# dashboard without the file disappearing mid-session.
UPLOAD_TTL_MINUTES: int = int(os.getenv("UPLOAD_TTL_MINUTES", "120"))
# How often the background sweep runs.
UPLOAD_SWEEP_INTERVAL_MINUTES: int = int(os.getenv("UPLOAD_SWEEP_INTERVAL_MINUTES", "30"))
