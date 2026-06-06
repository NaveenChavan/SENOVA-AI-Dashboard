"""
DEPRECATED — Supabase integration has been removed from the SENOVA AI
Dashboard. Uploaded files are now processed directly from local disk via
``app.services.file_handler`` and the ``/process/{file_id}`` route.

This module is kept only as a no-op so any stale imports fail loudly
rather than silently re-enabling a dead code path. Safe to delete.
"""

raise ImportError(
    "supabase_client has been removed. The dashboard now uses local disk "
    "storage only — see app.services.file_handler and /process/{file_id}."
)