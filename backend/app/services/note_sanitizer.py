"""
Phase 4.2 — sanitisation for the user-entered custom note per column.

A note is the one piece of free text in this whole feature that a user types
with the explicit intent of influencing an AI call, which makes it the
highest-risk string in the request. Two separate defences apply to it, and
they live in two different places on purpose:

1. **Shape** (this module) — strip control characters and hard-truncate to
   200 characters, before the note is stored, displayed, or sent anywhere.
   This is a data-hygiene rule, independent of whether AI is even enabled.
2. **Prompt framing** (``tier2_gemini._build_note_prompt``) — the sanitised
   text is placed inside an explicit, delimited field and the model is told
   in the system instruction to treat it as *data describing a column*, never
   as an instruction to itself. That is a prompt-injection defence and
   belongs beside the prompt it defends, not here.

Neither defence trusts the other to be sufficient alone.
"""

from __future__ import annotations

import re
import unicodedata

#: Hard cap, matching Phase 4.2 requirement 1. Enforced by slicing, not by
#: rejecting — a 500-character paste is truncated, not an error, because
#: trimming a shop owner's over-long note is friendlier than bouncing it.
MAX_NOTE_LENGTH = 200

#: Every Unicode control/format character except the three whitespace forms
#: (tab, newline, carriage return) we fold to a single space below. This
#: catches null bytes, escape sequences, and other characters that have no
#: business in a one-line note and could otherwise confuse a downstream
#: renderer or log line.
_CONTROL_CHAR_RE = re.compile(
    "[" + "".join(
        chr(code) for code in range(0x00, 0x20) if chr(code) not in "\t\n\r"
    ) + "\x7f" + "]"
)

_WHITESPACE_RUN_RE = re.compile(r"\s+")


def sanitize_note(raw: str | None) -> str:
    """
    Produce the exact string that may be stored/displayed/sent for a note.

    Order matters: Unicode-normalise first (so a combining-character trick
    can't smuggle a control character past the regex below), strip control
    characters, collapse all whitespace (including the newlines/tabs the
    regex deliberately let through) to single spaces, trim, then truncate.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    text = _CONTROL_CHAR_RE.sub("", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip()
    return text[:MAX_NOTE_LENGTH]
