"""
Upload flow — two steps, because every shop's export format is different.

Step 1: ``POST /upload/``
    Accepts a CSV/Excel file, saves it to disk **bound to the calling user**,
    and returns a ``ColumnMappingPreview``: our best guess at how the file's
    raw columns map to the canonical fields, which optional fields are
    available, and a few sample rows for a live preview. Nothing is validated
    or analysed yet.

Step 2: ``POST /upload/{file_id}/confirm-mapping``
    The frontend shows the guess, the user corrects it, and the confirmed
    ``{raw_column: canonical_field}`` map is posted here. This is where
    row-level validation runs and where the mapping is persisted so every
    later read (filters, charts, insights, PDF) reuses it automatically.

Security notes
--------------
* Both routes require a verified Firebase ID token.
* The upload records the caller as the file's owner; every analytics route
  re-checks that ownership, so one user can never read another's sales data.
* Only the *extension* of the client-supplied filename is used when writing to
  disk — the name itself never becomes part of a path.
* Confirming a mapping invalidates the cached frame for that file, so a
  corrected mapping can't be shadowed by a stale cache entry.
"""

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
import pandas as pd

from app.core.config import MAX_UPLOAD_SIZE_MB
from app.models.schemas import (
    AiNotice,
    ColumnGuess,
    ColumnMappingPreview,
    DataDateRange,
    PipelineTimings,
    RowError,
    UploadResponse,
)

class Tier2Response(BaseModel):
    detected_columns: list[ColumnGuess]
    ai_notice: AiNotice | None = None
    pipeline_timings: PipelineTimings
    #: Phase 4.1 — counts measured from this actual call, never estimated.
    #: ``columns_evaluated`` is how many columns were actually sent to Gemini
    #: this time (0 on a skip/cache-served/cooldown-blocked call);
    #: ``columns_resolved`` is how many of those came back with a verdict
    #: (``source == "gemini"``). Both are 0, not omitted, when nothing ran —
    #: the UI must never fabricate a count for a call that made no request.
    columns_evaluated: int = 0
    columns_resolved: int = 0
from app.services import column_understanding, frame_cache, mapping_memory, tier2_cooldown, tier2_gemini
from app.services.file_handler import (
    assert_owner,
    cleanup,
    get_original_filename,
    read_to_dataframe,
    save_column_mapping,
    save_extra_registry,
    save_upload,
    validate_file_id,
)
from app.services.sales_calculations import compute_data_date_range
from app.utils.auth_verifier import get_current_user
from app.utils.data_validator import (
    MAPPABLE_FIELDS,
    OPTIONAL_DIMENSION_COLUMNS,
    OPTIONAL_MEASURE_COLUMNS,
    normalize_dataframe,
)

router = APIRouter()

#: How many sample rows to send back for the live preview on the mapping screen.
_SAMPLE_ROW_COUNT = 5

#: Cap on how many raw columns we will describe. A file with thousands of
#: columns is almost certainly not a sales register, and rendering them all
#: would lock up the mapping screen.
_MAX_COLUMNS = 100

#: Helper text shown under each field on the mapping screen. Written for a shop
#: owner, not a developer — this is the screen where a wrong choice quietly
#: corrupts every number downstream.
_FIELD_HELP: dict[str, str] = {
    "Date": "When the sale happened (invoice / bill / voucher date).",
    "Category": "Product group — Kurta, Saree, Shirt, Grocery…",
    "Item": "The product name, style or SKU that was sold.",
    "Quantity": "How many pieces were sold on that line.",
    "Selling Price": "Price of ONE piece. Leave unmapped if your file only has a line total.",
    "Cost Price": "Your purchase cost for ONE piece.",
    "Line Total": "Line amount = quantity × rate. Map this if your file has Amount / Net Amount instead of a unit price.",
    "Discount": "Discount given on the line, in rupees. Revenue is reported net of this.",
    "MRP": "Original price before discount. Used only to calculate discount.",
    "Tax": "GST / VAT collected on the line. Shown separately, never counted as profit.",
    "Stock On Hand": "Pieces still in stock. Unlocks days-of-cover and reorder alerts.",
    "Branch": "Shop, store or godown name — becomes a filter and a chart axis.",
    "Payment Mode": "Cash / UPI / Card — becomes a filter and a chart axis.",
    "Customer": "Customer or party name.",
    "Salesperson": "Who made the sale.",
    "Brand": "Brand or manufacturer.",
    "Size": "Size or variant.",
    "Colour": "Colour or shade.",
    "Invoice No": "Bill / invoice / order number.",
}


def _validate_upload_constraints(file: UploadFile) -> None:
    """Reject anything that isn't a CSV or XLSX by declared extension."""
    allowed_extensions = (".csv", ".xlsx")
    if not file.filename or not any(
        file.filename.lower().endswith(ext) for ext in allowed_extensions
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(allowed_extensions)}.",
        )


@router.post("/", response_model=ColumnMappingPreview, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    ai_consent: bool = Form(False),
    user: str = Depends(get_current_user),
):
    """
    Step 1 — save the file (owned by the caller) and return a best-guess
    column mapping. No rows are validated and no analysis runs yet.

    ``ai_consent`` is the user's explicit permission for this upload to use
    Gemini Flash on the columns Tier 1 couldn't settle. It defaults to
    ``False``, so a client that doesn't send it is treated as *declining* rather
    than consenting. It only matters when the server also has
    ``AI_ASSIST_ENABLED=true``; both must hold before anything leaves the
    server. Tier 1 always runs locally.
    """
    _validate_upload_constraints(file)

    contents = await file.read()

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB}MB.",
        )

    file_id = save_upload(contents, file.filename, owner=user)

    try:
        df = read_to_dataframe(file_id)
    except Exception as exc:
        # A file we can't parse is worthless — delete it rather than leaving an
        # orphan on disk waiting for the TTL sweep.
        cleanup(file_id)
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    if df.empty or len(df.columns) == 0:
        cleanup(file_id)
        raise HTTPException(status_code=400, detail="The uploaded file has no columns or rows.")

    if len(df.columns) > _MAX_COLUMNS:
        cleanup(file_id)
        raise HTTPException(
            status_code=400,
            detail=f"This file has {len(df.columns)} columns; the maximum supported is {_MAX_COLUMNS}.",
        )

    # The 2-tier column-understanding pipeline: Tier 1 classifies locally,
    # escalating only the columns it can't settle to Tier 2. To avoid blocking the upload,
    # we explicitly skip Tier 2 here. The frontend will request it asynchronously if needed.
    reports, timings, ai_notice, reason_code = await column_understanding.analyse(
        df, ai_consent=ai_consent, file_id=file_id, run_tier2=False, owner=user
    )

    # Sample rows for the live preview: NaN → None so the JSON stays valid, and
    # PII values masked/redacted so raw emails and phone numbers never leak.
    from app.services.extra_columns import is_personal_pii
    from app.services.pii_mask import mask_text

    pii_cols = {col for col in df.columns if is_personal_pii(str(col), df[col])}
    sample_rows = [
        {
            str(col): (
                None
                if pd.isna(value)
                else (
                    "[redacted]"
                    if col in pii_cols
                    else mask_text(value)[:120]
                )
            )
            for col, value in row.items()
        }
        for row in df.head(_SAMPLE_ROW_COUNT).to_dict(orient="records")
    ]

    unresolved = sum(
        1 for report in reports
        if report.get("needs_review") and not report.get("recognised_unused")
    )

    return ColumnMappingPreview(
        file_id=file_id,
        filename=file.filename,
        detected_columns=[ColumnGuess(**report) for report in reports],
        # The mapping screen enforces the alternate sales-basis rule below;
        # Date is the only single required target. Quantity + Selling Price or
        # Line Total together satisfy the second requirement.
        required_fields=["Date"],
        optional_fields=[f for f in MAPPABLE_FIELDS if f != "Date"],
        field_help=_FIELD_HELP,
        row_count=len(df),
        sample_rows=sample_rows,
        pipeline_timings=PipelineTimings(**timings.as_dict()),
        ai_notice=(
            AiNotice(message=ai_notice, tone="info", affected_columns=unresolved, reason_code=reason_code)
            if ai_notice
            else None
        ),
        ai_enabled=tier2_gemini.gemini_enabled(),
    )

class Tier2Request(BaseModel):
    ai_consent: bool = False
    #: Phase 4.1 — "Check again with AI". False (the default) is the original,
    #: automatic once-per-upload pass and is unaffected by anything below.
    force_recheck: bool = False
    #: Restrict a forced recheck to specific raw column headers. ``None``
    #: (the default) means "every column Tier 1 still considers ambiguous",
    #: matching the original endpoint's behaviour.
    target_columns: list[str] | None = None


@router.post("/{file_id}/tier2", response_model=Tier2Response)
async def run_tier2(
    file_id: str,
    body: Tier2Request,
    user: str = Depends(get_current_user)
):
    """
    Run Tier 2 — once automatically per upload, or again on explicit request.

    Phase 4.1, "Check again with AI": when ``force_recheck`` is set, this call
    bypasses the Gemini verdict cache for this upload (so a stale answer is
    never replayed) and is subject to a 10-second cooldown per (user, file_id)
    so repeated clicks cannot fire unlimited Gemini requests. The cooldown is
    enforced *before* any of the existing consent/availability gates are even
    consulted, because a user mashing the button should see "wait a moment",
    not a reason code that implies something is actually wrong.

    Every other gate from the automatic pass is unchanged: no consent, no AI
    available, or no API key still means zero Gemini calls, exactly as before
    this parameter existed.
    """
    try:
        assert_owner(file_id, user)
        df = read_to_dataframe(file_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="File not found or invalid.")

    if body.force_recheck:
        remaining = tier2_cooldown.seconds_remaining(user, file_id)
        if remaining > 0:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": f"Please wait {remaining:.0f}s before checking again.",
                    "reason_code": "cooldown",
                    "retry_after_seconds": round(remaining, 1),
                },
            )
        # Record the attempt before the call, not after: a slow/erroring
        # Gemini call must not let a second click slip in under the window.
        tier2_cooldown.record_attempt(user, file_id)

    force_columns = set(body.target_columns) if body.target_columns else None

    reports, timings, ai_notice, reason_code = await column_understanding.analyse(
        df,
        ai_consent=body.ai_consent,
        file_id=file_id,
        run_tier2=True,
        owner=user,
        bypass_cache=body.force_recheck,
        force_columns=force_columns,
    )
    unresolved = sum(
        1 for report in reports
        if report.get("needs_review") and not report.get("recognised_unused")
    )

    # Measured, not estimated — read directly off the pipeline's own record of
    # the moment it called Tier 2, before any later route recompute could make
    # a resolved column look unescalated again (a fully resolved column's
    # ``needs_review`` becomes false, which would otherwise make a post-hoc
    # "was this routed to gemini" check undercount). Both are 0 whenever Tier 2
    # was skipped for any reason — no consent, AI off, cooldown, nothing
    # ambiguous — because ``analyse()`` never reaches the line that sets them.
    columns_evaluated = timings.tier2_requested
    columns_resolved = timings.tier2_resolved

    return Tier2Response(
        detected_columns=[ColumnGuess(**report) for report in reports],
        ai_notice=(
            AiNotice(message=ai_notice, tone="info", affected_columns=unresolved, reason_code=reason_code)
            if ai_notice
            else None
        ),
        pipeline_timings=PipelineTimings(**timings.as_dict()),
        columns_evaluated=columns_evaluated,
        columns_resolved=columns_resolved,
    )



# ── Phase 4.2 — Custom note per column ───────────────────────────────────────


class ColumnNoteInput(BaseModel):
    """One column's header plus the user's short explanatory note."""

    column: str = Field(..., description="Raw column header this note is about.")
    note: str = Field(
        "",
        max_length=5000,
        description=(
            "Short user note, e.g. 'this is the delivery charge'. Sanitised and "
            "truncated to 200 characters server-side regardless of length sent — "
            "an over-long note is trimmed, not rejected. The 5000-char field limit "
            "here is only a request-size guard, well above any legitimate note; "
            "the real, user-facing limit is the 200-char truncation."
        ),
    )


class ColumnNoteSuggestion(BaseModel):
    """A single proposed role for a noted column, pending user confirmation."""

    column: str
    role: str = Field(..., description="One of the canonical fields, extra_dimension, extra_measure, or ignore.")
    reason: str = ""
    money_sensitive: bool = Field(
        False,
        description="True for Selling Price/Cost Price/Line Total/Quantity — the client must demand explicit confirmation.",
    )


class ColumnNotesRequest(BaseModel):
    ai_consent: bool = False
    notes: list[ColumnNoteInput] = Field(
        default_factory=list,
        description="Up to 20 columns with a note each; extras beyond 20 are dropped, not erred on.",
    )


class ColumnNotesResponse(BaseModel):
    suggestions: list[ColumnNoteSuggestion] = Field(default_factory=list)
    ai_notice: AiNotice | None = None
    #: Sanitised notes, echoed back so the client can show them as a display
    #: label immediately — including on the AI-off/AI-failure path, where
    #: there is no suggestion at all but the note itself is still usable.
    notes_echo: dict[str, str] = Field(default_factory=dict)


@router.post("/{file_id}/column-notes", response_model=ColumnNotesResponse)
async def submit_column_notes(
    file_id: str,
    body: ColumnNotesRequest,
    user: str = Depends(get_current_user),
):
    """
    Phase 4.2 — ask AI about up to 20 user-written column notes in one request.

    This never mutates the file's mapping by itself. It only returns proposed
    roles; applying any of them is a separate, explicit client action (the
    mapping screen's existing dropdown / confirm flow), and money-sensitive
    roles additionally require the client to collect its own extra
    confirmation before calling ``confirm-mapping`` with that role. A note is
    never written to the Gemini cache or to mapping memory — it lives only
    for the duration of this request.
    """
    try:
        assert_owner(file_id, user)
        df = read_to_dataframe(file_id)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found or invalid.")

    from app.services.note_sanitizer import sanitize_note

    # Sanitise first, then cap at 20 — a caller that sends 25 notes gets the
    # first 20 processed and the note text itself is never trusted as-sent.
    seen: dict[str, str] = {}
    for item in body.notes:
        if item.column not in df.columns:
            continue
        clean_note = sanitize_note(item.note)
        if not clean_note:
            continue
        seen[item.column] = clean_note
        if len(seen) >= tier2_gemini.MAX_NOTE_COLUMNS:
            break

    notes_echo = dict(seen)

    if not seen:
        return ColumnNotesResponse(suggestions=[], ai_notice=None, notes_echo={})

    columns_payload = [
        {
            **tier2_gemini.describe_column(df[column], column, None),
            "note": note,
        }
        for column, note in seen.items()
    ]

    result = await tier2_gemini.resolve_with_notes(columns_payload, ai_consent=body.ai_consent)

    suggestions = [
        ColumnNoteSuggestion(
            column=column,
            role=verdict.role,
            reason=verdict.reason,
            money_sensitive=verdict.money_sensitive,
        )
        for column, verdict in result.verdicts.items()
    ]

    ai_notice = (
        AiNotice(message=result.notice, tone="info", affected_columns=len(seen) - len(suggestions), reason_code=result.reason_code)
        if result.notice
        else None
    )

    return ColumnNotesResponse(suggestions=suggestions, ai_notice=ai_notice, notes_echo=notes_echo)


class ConfirmMappingRequest(BaseModel):
    """Body for ``POST /upload/{file_id}/confirm-mapping``."""

    mapping: dict[str, str] = Field(
        ..., description="{raw_column: canonical_field}; unrecognised fields are ignored."
    )
    user_selected_columns: list[str] = Field(
        default_factory=list,
        description="Raw columns the user explicitly reviewed, changed, or confirmed.",
    )
    remember_mapping: bool = Field(
        default=False,
        description="Whether to persist user-approved mappings to safe mapping memory (opt-in by default).",
    )
    acknowledge_warnings: bool = Field(
        default=False,
        description=(
            "Set True to proceed past non-blocking advisories (e.g. a single-invoice "
            "amount that might be a bill-level total). Hard rejections (strong "
            "multi-invoice invoice-total evidence) are never bypassed by this flag."
        ),
    )


@router.post("/{file_id}/confirm-mapping", response_model=UploadResponse)
async def confirm_mapping(
    file_id: str,
    body: ConfirmMappingRequest,
    user: str = Depends(get_current_user),
):
    """
    Step 2 — apply the confirmed mapping, run full row-level validation,
    persist the mapping, and report what came out: valid row count, every
    row-level error, the data's real date span, and which optional fields this
    file unlocked.
    """
    try:
        validate_file_id(file_id)
        assert_owner(file_id, user)
        df = read_to_dataframe(file_id)
    except (ValueError, PermissionError, FileNotFoundError):
        # One indistinguishable 404 for malformed / missing / someone else's id.
        raise HTTPException(status_code=404, detail="File not found. Upload a file first.")

    # ── Module 2.2: Validate user-confirmed mapping payload ─────────────────
    allowed_fields = set(MAPPABLE_FIELDS)
    assigned_targets: list[str] = []
    for raw_col, canonical in body.mapping.items():
        if raw_col not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Column '{raw_col}' does not exist in the uploaded file.",
            )
        if canonical:
            if canonical not in allowed_fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"Target field '{canonical}' is not a valid canonical field.",
                )
            assigned_targets.append(canonical)

    seen_targets: set[str] = set()
    for target in assigned_targets:
        if target in seen_targets:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate mapping detected for field '{target}'. Each canonical field can only be mapped to one column.",
            )
        seen_targets.add(target)

    # ── Module 2.4: Invoice-total repeat guard on a user-forced Line Total ───
    # Reuses the Module 2.1 detector. A column the user explicitly maps to
    # Line Total that is provably an invoice-level total (constant across the
    # line items of ≥2 invoices) would inflate revenue when summed row-wise, so
    # it is rejected outright. A weaker single-invoice signal becomes a
    # non-blocking warning the user may acknowledge.
    from app.services.ambiguity_engine import assess_forced_line_total

    confirm_warnings: list[str] = []
    for raw_col, canonical in body.mapping.items():
        if canonical != "Line Total":
            continue
        assessment = assess_forced_line_total(raw_col, df, body.mapping)
        if assessment.verdict == "reject":
            raise HTTPException(status_code=400, detail=assessment.message)
        if assessment.verdict == "warn":
            confirm_warnings.append(assessment.message)

    if confirm_warnings and not body.acknowledge_warnings:
        # Surface the advisory without committing. The client re-submits with
        # acknowledge_warnings=True once the user has intentionally confirmed.
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Please confirm this mapping before proceeding.",
                "warnings": confirm_warnings,
                "requires_acknowledgement": True,
            },
        )

    try:
        pandas_started = time.perf_counter()
        valid_df, error_dicts = normalize_dataframe(df, soft_fail=True, column_mapping=body.mapping)
        errors = [RowError(**e) for e in error_dicts]
        pandas_ms = (time.perf_counter() - pandas_started) * 1000.0
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Persist the mapping, then drop any cached frame built from an older one.
    save_column_mapping(file_id, body.mapping)
    if hasattr(valid_df, "attrs") and "extra_registry" in valid_df.attrs:
        save_extra_registry(file_id, valid_df.attrs["extra_registry"])
    frame_cache.invalidate(file_id)

    # Module 2.3: Persist explicitly approved mappings to owner memory (opt-in only)
    if body.remember_mapping and body.user_selected_columns:
        mapping_memory.record_confirmed_mappings(
            owner=user,
            raw_headers=list(df.columns),
            confirmed_mapping=body.mapping,
            user_selected_columns=body.user_selected_columns,
            remember_mapping=body.remember_mapping,
            df=df,
        )

    optional_present = [
        field
        for field in sorted(OPTIONAL_MEASURE_COLUMNS | OPTIONAL_DIMENSION_COLUMNS)
        if field in valid_df.columns
    ]

    return UploadResponse(
        file_id=file_id,
        filename=get_original_filename(file_id),
        message=f"Uploaded {len(valid_df)} valid row(s) with {len(errors)} error(s).",
        valid_count=len(valid_df),
        error_count=len(errors),
        errors=errors,
        date_range=DataDateRange(**compute_data_date_range(valid_df)),
        optional_fields=optional_present,
        pipeline_timings=PipelineTimings(pandas_ms=round(pandas_ms, 2), total_ms=round(pandas_ms, 2)),
        warnings=confirm_warnings,
    )
