"""Anchor capture and resolution.

THIS IS THE CORE OF THE PRODUCT. Read docs/architecture.md before editing.

`resolve()` is deliberately unimplemented. `tests/test_anchors.py` is its specification —
every mutation in the table has exactly one correct classification. Make the tests pass;
do not change the tests to match an implementation.
"""

from __future__ import annotations

from ..corpus.normalize import content_hash, normalize
from ..models import (
    Anchor,
    Document,
    Resolution,
    ResolutionResult,
    Snapshot,
)

CONTEXT_WINDOW = 400
"""Characters on each side of the span captured into context_hash. Large enough to be
distinctive, small enough that an edit two paragraphs away doesn't disturb it."""


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #


def capture(
    document: Document,
    span_text: str,
    snapshot_id: str,
    *,
    occurrence: int = 0,
) -> Anchor:
    """Create an anchor pointing at `span_text` inside `document`.

    Raises ValueError if the span is not present — an anchor to text that isn't there is
    the bug we exist to prevent, so fail loudly at capture time rather than silently
    producing a DESTROYED anchor later.
    """
    text = document.normalized_text
    span = normalize(span_text)

    starts = _all_occurrences(text, span)
    if not starts:
        raise ValueError(
            f"span not found in {document.doc_key!r}; refusing to create a dangling anchor"
        )
    if occurrence >= len(starts):
        raise ValueError(
            f"occurrence {occurrence} requested but span appears {len(starts)} time(s)"
        )

    start = starts[occurrence]
    end = start + len(span)

    return Anchor(
        doc_key=document.doc_key,
        heading_path=heading_path_at(document, start),
        span_hash=content_hash(span),
        context_hash=context_hash_at(text, start, end),
        char_range=(start, end),
        snapshot_id=snapshot_id,
        span_text=span,
    )


def heading_path_at(document: Document, position: int) -> list[str]:
    """Deepest heading whose body range contains `position`."""
    best: list[str] = []
    best_depth = -1
    for h in document.headings:
        if h.start <= position < h.end and h.level > best_depth:
            best, best_depth = list(h.path), h.level
    return best


def context_hash_at(text: str, start: int, end: int) -> str:
    """Hash of the window around a span, excluding the span itself.

    Excluding the span matters: if the span changes but its surroundings don't, we want
    context_hash to still match so we can locate where the answer USED to be and report
    what it says now.
    """
    before = text[max(0, start - CONTEXT_WINDOW) : start]
    after = text[end : end + CONTEXT_WINDOW]
    return content_hash(before + "\x00" + after)


def _all_occurrences(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    i = haystack.find(needle)
    while i != -1:
        out.append(i)
        i = haystack.find(needle, i + 1)
    return out


# --------------------------------------------------------------------------- #
# Resolution — implement me
# --------------------------------------------------------------------------- #


def resolve(anchor: Anchor, snapshot: Snapshot) -> ResolutionResult:
    """Re-resolve `anchor` against a later snapshot.

    The return value IS the staleness signal. Get this right and the product works;
    get it wrong and everything above it is noise.

    Cascade — first matching rule wins:

      1. span_hash found exactly once, at anchor.char_range
             -> VALID
      2. span_hash found exactly once, elsewhere in the same document
             -> VALID_MOVED            (document edited above/below; silent repair)
      3. span_hash found exactly once, under a different or missing heading_path
             -> VALID_RELOCATED        (section renamed/moved/split; repair + note)
      4. span_hash found in 2+ locations
             -> AMBIGUOUS              (content duplicated; flag for review)
      5. heading_path resolves but span_hash absent beneath it
             -> STALE                  (THE ANSWER TEXT CHANGED; flag for review)
      6. nothing resolves
             -> DESTROYED              (retire the test)

    Notes for the implementer:

    - Rules 2 and 3 both find the span exactly once. They differ only in whether the
      heading path at the new position matches the anchor's. Check the heading first,
      then decide between MOVED and RELOCATED.

    - Rule 5 is the money case and the easiest to get wrong. Resolve heading_path in the
      new snapshot; if the heading exists but the span is not inside its body range,
      that is STALE. Populate `candidate_spans` with what the text under that heading
      says NOW, so a reviewer can see the old answer (anchor.span_text) beside the new
      one without re-fetching the old snapshot.

    - If the document itself is gone from the snapshot, do NOT immediately return
      DESTROYED. Search other documents for span_hash first — a section moved to a
      different file is VALID_RELOCATED, not destroyed. Document splits and merges depend
      on this.

    - `context_hash` is a repair aid, not a validity signal. A context-only match (span
      changed, surroundings identical) is STALE with a suggested correction. It is never
      VALID. A human decides whether the reworded text still answers the question.

    - Never fall back to char_range as identity. Position is a tiebreaker for rule 1 and a
      hint for repair. Nothing else. Positional identity is the exact failure this design
      replaces.
    """
    raise NotImplementedError(
        "Implement the cascade. tests/test_anchors.py is the specification."
    )


def resolve_all(
    anchors: list[Anchor], snapshot: Snapshot
) -> list[ResolutionResult]:
    return [resolve(a, snapshot) for a in anchors]
