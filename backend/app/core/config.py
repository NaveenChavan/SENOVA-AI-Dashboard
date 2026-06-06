"""
Central configuration for the SENOVA backend.
Keeps CORS origins, upload limits, and other env-specific values in one place.
"""

import os

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

# --- Google OAuth ---
# Client ID from Google Cloud Console — used to verify JWT tokens.
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

# --- Uploads ---
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "temp_uploads")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
