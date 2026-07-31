# SENOVA Upgrade Plan — History, WhatsApp Sharing, Reorder Point

Status: **design spec — not yet implemented.** This document specifies three
upgrades chosen for SENOVA AI Dashboard, in enough detail to build from. It
describes the target architecture, API surface, and UI changes before any
code is written, so the eventual implementation can be reviewed against a
fixed plan rather than improvised as it goes.

---

## 1. Persistent upload history with automatic merge

### Why
Today every upload is a standalone, temporary file (`UPLOAD_DIR`, cleaned up
by a TTL sweep after `UPLOAD_TTL_MINUTES`). There is no way to see "this
month vs last month" unless both periods happen to be inside a *single*
upload. Retail owners think in continuous time, not in discrete file
uploads — every time they get a new day's/week's export from Tally, Vyapar,
or their POS, it should extend the picture, not replace it.

### What it does
- Every confirmed upload is kept **permanently** (no TTL) and is automatically
  registered against the uploading user's history — no manual "save to
  history" step.
- The dashboard can operate in two modes:
  - **Single file** (today's behavior, unchanged) — analyse exactly one
    upload.
  - **All-time / history mode** (new) — analyse the *merged* view across
    every upload that user has ever confirmed.
- Merging happens at **row/date granularity**: if two uploads both contain
  rows for, say, 12 March, the rows from whichever upload was confirmed
  **later** win for that date. Dates that only exist in one upload are kept
  as-is. This avoids both silent double-counting (naive concatenation) and
  losing a whole file just because one day of it overlaps another upload.

### How it works
No relational database is introduced. The existing sidecar-file pattern in
`file_handler.py` is extended with one more sidecar per user:

```
{owner_hash}.history.json
[
  { "file_id": "ab12…", "min_date": "2026-01-01", "max_date": "2026-01-20", "uploaded_at": 1785000000 },
  { "file_id": "cd34…", "min_date": "2026-01-15", "max_date": "2026-02-10", "uploaded_at": 1785600000 }
]
```

At merge time (`resolve_canonical_frame(owner)`):
1. Load every file_id in the user's history index.
2. Read + normalise each into a DataFrame (`_prepare()`, already exists).
3. Concatenate all rows, sort by `uploaded_at` ascending.
4. For each date present in more than one upload, keep only the rows from
   the upload with the latest `uploaded_at`; `drop_duplicates` semantics
   applied per-date, not per-row-hash, so a genuinely repeated transaction
   inside the *same* upload is never dropped.
5. Feed the merged frame into the existing aggregation/insights/forecast/
   inventory pipeline unchanged — none of that code needs to know whether
   its input came from one file or twelve.

### API additions
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/history` | List the current user's uploads: file_id, filename, date range, uploaded_at |
| `DELETE` | `/history/{file_id}` | Remove one upload from history (and disk) |
| *(existing routes)* | `/analytics/{id}/...?use_history=true` | Run the same analytics endpoint against the merged canonical frame instead of a single file |

### UI changes
- New small panel/tab: **Upload History** — a list of past uploads with
  their date ranges and a delete action.
- A mode toggle: **This file** / **All-time**, next to the existing date
  filter presets. Selecting "All-time" switches every existing chart, KPI,
  insight, and export to the merged frame — no new visual components needed
  elsewhere.

### Security
- History index lookups reuse the existing `assert_owner()` check — merging
  must never cross users. The index itself is scoped by owner (hashed
  identity as the filename prefix), same trust boundary as `.meta.json`
  today.
- Deleting a file from history also removes it from disk immediately
  (no TTL wait), since permanence was the point of keeping it — until the
  user explicitly deletes it.

### Known limitations (stated honestly, matching this project's existing style)
- Merge granularity is per calendar date, not per transaction. If two
  uploads both contain five transactions on the same date but they are
  *different* transactions (not a re-export of the same day), the older
  upload's five transactions for that date are still fully discarded, not
  merged line-by-line. This is a deliberate simplicity trade-off for phase
  one; a future phase could dedupe on invoice number where available.
- No conflict UI — the newer upload always wins for a shared date, silently.
  If this proves surprising in practice, a "review overlap" screen could be
  added later without changing the underlying merge function's contract.

---

## 2. On-demand WhatsApp sharing of the PDF report

### Why
WhatsApp is the dominant business communication channel for Indian MSMEs.
Meta retired the on-premise WhatsApp Business API in October 2025 — the
Cloud API plus **Embedded Signup** is now the standard way for a platform to
let its own end customers connect their own WhatsApp Business number, without
the platform running a shared BSP (Business Solution Provider) subscription.
That fits SENOVA's model: each shop owner connects *their own* WhatsApp
Business number, so SENOVA never handles anyone else's message traffic or
per-message billing.

### What it does
- A shop owner connects their own WhatsApp Business API credentials once
  (via Meta's Embedded Signup flow, or by pasting a phone_number_id + access
  token generated in their own Meta Business account).
- From the dashboard, a **"Send to WhatsApp"** button next to the existing
  "Download PDF" button lets them send the already-generated PDF report to
  any WhatsApp number, on demand — no scheduling, no automation, in this
  phase.

### How it works

**Connecting credentials** (`POST /whatsapp/connect`)
1. User submits their Meta Cloud API `phone_number_id` and access token.
2. Backend makes one lightweight validation call to Meta's Graph API
   (e.g. fetch phone number metadata) to confirm the token works *before*
   storing anything.
3. Token is encrypted at rest (`cryptography.fernet`, keyed off a
   server-side secret — never off anything derived from user input) and
   saved in a new per-user sidecar, e.g. `{owner_hash}.whatsapp.json`
   (encrypted blob only — never plaintext on disk).
4. `GET /whatsapp/status` reports `connected: true/false` and the masked
   phone number — **never** returns the token itself once stored.

**Sending a report** (`POST /analytics/{id}/report.pdf/send-whatsapp`)
1. Generates the PDF exactly as `/analytics/{id}/report.pdf` does today
   (same `pdf_report.py` code path, unchanged).
2. Uploads the PDF bytes to Meta's media endpoint using the user's stored
   credentials.
3. Sends a WhatsApp message with that media to the recipient number
   supplied in the request body.
4. Returns a clear success/failure status — on failure (expired token,
   invalid number, template/session-window rejection), the error message
   is specific enough for the user to act on, not a raw stack trace.

### API additions
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/whatsapp/connect` | Validate and store the user's own WhatsApp Business API credentials |
| `GET` | `/whatsapp/status` | Check connection state (masked number only, never the token) |
| `DELETE` | `/whatsapp/connect` | Disconnect / remove stored credentials |
| `POST` | `/analytics/{id}/report.pdf/send-whatsapp` | Send the existing PDF report to a given number |

### UI changes
- Settings area: a "Connect WhatsApp" card — paste credentials, see
  connected status, disconnect.
- Dashboard report section: "Send to WhatsApp" button next to "Download
  PDF". If not connected, it opens the connect flow first. If connected,
  it prompts for a recipient number and confirms once sent.

### Security
- Access tokens are secrets: encrypted at rest, never logged, never echoed
  back in any API response after the initial save.
- This is a **bring-your-own-credentials** model — SENOVA never becomes a
  party to any user's WhatsApp Business account, never sees message content
  beyond the PDF it itself generated, and never bears BSP/per-message cost.
- Rate limiting on `/send-whatsapp` (bounded per user per minute) to prevent
  the endpoint being used as an open relay for unrelated WhatsApp spam using
  a stolen SENOVA session.

### Known limitations (stated honestly)
- WhatsApp's **24-hour customer-service window** rule applies: a business
  can freely message a number that has messaged it within the last 24
  hours, or use a pre-approved message template outside that window. A
  first-time recipient who has never messaged the shop's WhatsApp Business
  number may not receive a free-form PDF until either they initiate contact
  once, or the shop owner submits a message template for Meta's approval.
  This is a real WhatsApp platform constraint, not a SENOVA bug — the UI
  must surface this clearly rather than silently failing.
- No scheduled/automatic sending in this phase — every send is a manual
  button click, per the agreed scope.

---

## 3. Reorder point (ROP) and safety stock

### Why
The inventory panel already computes `velocity_per_day`, `trend_factor`,
and (when a stock column is mapped) `days_of_cover` and a 0–100
`reorder_priority` ranking. That ranking answers "what should I look at
first?" — but the number a shop owner actually needs to act on is
**"how many units before I run out, and how many should I keep as a
buffer?"** — the classic reorder point and safety stock.

### What it does
- Adds a single **global lead-time-in-days** setting, editable in the
  Inventory panel, defaulting to a sensible value (e.g. 7 days).
- Computes, per item (stock-aware mode only — same honesty rule as
  `days_of_cover` today: never guess a number the data can't support):
  - `safety_stock = z × σ_demand × √lead_time_days`
  - `reorder_point = (velocity_per_day × lead_time_days) + safety_stock`
- Changing the lead-time field live-recalculates both columns for every
  item, without needing a new upload or a new API contract per item.

### How it works
Extends `inventory_intel.py`:

```python
def compute_reorder_point(velocity_per_day, demand_std, lead_time_days, z=1.65):
    """
    z=1.65 corresponds to ~95% service level, consistent with standard
    inventory-planning practice. Returns (reorder_point, safety_stock),
    or (None, None) when velocity is 0 — matching the existing
    days_of_cover convention of returning null rather than a fabricated
    number.
    """
```

`demand_std` (day-to-day demand variability) is derived from data already
computed during the existing trend-factor calculation (the early/late
window split) — no new statistical machinery, and no new required column.

`lead_time_days` becomes a request parameter on the inventory endpoint
(default 7), and two new fields are added to the response schema:
`reorder_point`, `safety_stock` — both `null` in demand-only mode, following
the same pattern as `days_of_cover`/`capital_locked` today.

### API changes
`POST /analytics/{id}/inventory` gains an optional `lead_time_days` field
in the request body (default 7, bounded to a sane range e.g. 1–90).
`InventoryItem` gains `reorder_point: float | None` and
`safety_stock: float | None`.

### UI changes
- A "Default lead time: [ 7 ] days" numeric input above the inventory
  table, debounced so it doesn't refetch on every keystroke.
- Two new columns in the inventory table: **Reorder Point** and **Safety
  Stock**, shown only in stock-aware mode (consistent with how
  `days_of_cover`/`capital_locked` are already conditionally shown).
- The lead-time value is stored in the view's URL state, matching this
  project's existing "deep-linkable view state" convention (tab, date
  window, and filters already work this way).

### Known limitations (stated honestly)
- One global lead time applies to every item, even though a real shop's
  supplier lead times vary by category (e.g. imported items take longer
  than locally sourced ones). This phase intentionally ships the simpler
  global default; a later phase could add a per-item/category override
  without changing the underlying formula.
- Only available in stock-aware mode — a sales-register-only upload (no
  stock column mapped) cannot support a reorder point, for the same reason
  it cannot support `days_of_cover` today: there's no stock level to count
  down from.

---

## Cross-cutting notes

- None of these three upgrades require a new third-party analytics service,
  and none send raw transaction data to a third party without the user's
  explicit action — WhatsApp sharing only transmits the same PDF the user
  can already download, and only to a number the user themselves specifies,
  using credentials the user themselves controls.
- All three extend existing, already-tested modules (`file_handler.py`,
  `inventory_intel.py`, `pdf_report.py`) rather than introducing a parallel
  architecture — consistent with this project's existing design.
- GST e-invoicing (mandatory above ₹5 crore annual turnover) is explicitly
  **out of scope** for the WhatsApp feature — the PDF sent is the existing
  analytics report, not a compliance document, and most SENOVA users are
  below that threshold.
