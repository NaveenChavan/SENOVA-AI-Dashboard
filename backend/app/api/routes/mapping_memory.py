"""
User-facing memory management routes.
All endpoints require a verified Firebase token and are strictly scoped to
the authenticated user identity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services import mapping_memory
from app.utils.auth_verifier import get_current_user

router = APIRouter()


class DeleteEntryRequest(BaseModel):
    template_signature: str = Field(..., description="16-character template signature")
    normalized_header: str = Field(..., description="Normalized column header name")


class MemoryEntryResponse(BaseModel):
    template_signature: str
    updated_at: float
    mappings: dict[str, str]


@router.get("/", response_model=list[MemoryEntryResponse])
def get_user_memories(user: str = Depends(get_current_user)):
    """Return all saved template mappings for the authenticated user."""
    return mapping_memory.list_user_memories(user)


@router.delete("/entry")
def delete_entry(
    body: DeleteEntryRequest,
    user: str = Depends(get_current_user),
):
    """Delete a specific column mapping from a template."""
    deleted = mapping_memory.delete_memory_entry(
        user, body.template_signature, body.normalized_header
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found.",
        )
    return {"message": "Memory entry deleted successfully."}


@router.delete("/template/{template_signature}")
def delete_template(
    template_signature: str,
    user: str = Depends(get_current_user),
):
    """Delete all mappings for an entire template."""
    deleted = mapping_memory.delete_template_memory(user, template_signature)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template memory not found.",
        )
    return {"message": "Template memory deleted successfully."}


@router.delete("/")
def clear_all_memories(user: str = Depends(get_current_user)):
    """Clear all saved mapping memory for the authenticated user."""
    mapping_memory.clear_user_memory(user)
    return {"message": "All mapping memory cleared successfully."}
