"""Anchor capture and resolution.

THIS IS THE CORE OF THE PRODUCT. Read docs/architecture.md before editing.

`tests/test_anchors.py` is the specification for `resolve()` — every mutation in the table
has exactly one correct classification. Do not change the tests to match an implementation;
if a classification looks wrong, argue it in an ADR and change both together.
"""

from __future__ import annotations

from ..corpus.normalize import content_hash, normalize
from ..models import (
    Anchor,
    Document,
    HeadingSpan,
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
# Resolution
# --------------------------------------------------------------------------- #


def _span_matches(
    anchor: Anchor, snapshot: Snapshot
) -> list[tuple[Document, int, int]]:
    """Every place the anchored span still occurs, anywhere in the snapshot.

    Searching the whole snapshot rather than only `anchor.doc_key` is what makes a
    section that moved between files VALID_RELOCATED instead of DESTROYED. Document
    splits and merges depend on it.

    The anchor's own document is searched first, then the rest in sorted key order, so
    the result is stable regardless of how the snapshot's dict was built.
    """
    own = snapshot.documents.get(anchor.doc_key)
    others = [snapshot.documents[k] for k in sorted(snapshot.documents) if k != anchor.doc_key]
    ordered = ([own] if own is not None else []) + others

    out: list[tuple[Document, int, int]] = []
    for doc in ordered:
        for start in _all_occurrences(doc.normalized_text, anchor.span_text):
            out.append((doc, start, start + len(anchor.span_text)))
    return out


def _common_suffix_length(a: list[str], b: list[str]) -> int:
    """How many trailing elements two heading paths share."""
    shared = 0
    for x, y in zip(reversed(a), reversed(b), strict=False):
        if x != y:
            break
        shared += 1
    return shared


def heading_paths_resolve(anchor_path: list[str], candidate_path: list[str]) -> bool:
    """Whether `candidate_path` still addresses what `anchor_path` addressed.

    Suffix matching, not full-ancestry equality: the paths resolve to each other if their
    tails agree. Renaming `# Guide` to `# Handbook` leaves `## Termination` addressing the
    same section; renaming `## Termination` itself does not.

    ADR-0016. The cascade already made this call once — rule 3 exists precisely because a
    renamed heading is not a reason to lose an anchor. Requiring exact ancestry honoured
    that at the leaf and contradicted it at the parent: same event, two answers, and only
    the arbitrary one was implemented.
    """
    if not anchor_path and not candidate_path:
        return True
    return _common_suffix_length(anchor_path, candidate_path) > 0


def _heading_span(document: Document, heading_path: list[str]) -> HeadingSpan | None:
    """The heading that still addresses `heading_path`, if any.

    An exact full-ancestry match wins outright. Otherwise the heading sharing the longest
    suffix, which recovers a section whose ancestors were renamed or re-parented — the
    common case in real documentation, and the one that used to report DESTROYED.

    Ties break on document order so the result is deterministic. A repeated leaf name
    cannot mislead about *whether the evidence is intact*: this function is reached only
    after the span was found nowhere, so the span-hash count has already spoken.
    """
    if not heading_path:
        return None

    best: HeadingSpan | None = None
    best_shared = 0
    for h in document.headings:
        path = list(h.path)
        if path == list(heading_path):
            return h
        shared = _common_suffix_length(path, list(heading_path))
        if shared > best_shared:
            best, best_shared = h, shared
    return best


def _lines(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        nl = text.find("\n", pos, end)
        stop = end if nl == -1 else nl
        out.append((pos, stop))
        pos = stop + 1
    return out


def _paragraphs(text: str, start: int, end: int) -> list[tuple[str, int, int]]:
    """Non-empty blocks of consecutive non-blank lines in a range, with their offsets.

    Offsets are kept because a candidate is only useful to a reviewer if we can also
    ask whether its surroundings match `context_hash` — that is what turns a list of
    paragraphs into a suggested correction.
    """
    out: list[tuple[str, int, int]] = []
    block: tuple[int, int] | None = None
    for a, b in _lines(text, start, end):
        if text[a:b].strip():
            block = (a, b) if block is None else (block[0], b)
        elif block is not None:
            out.append((text[block[0] : block[1]], block[0], block[1]))
            block = None
    if block is not None:
        out.append((text[block[0] : block[1]], block[0], block[1]))
    return out


def resolve(anchor: Anchor, snapshot: Snapshot) -> ResolutionResult:
    """Re-resolve `anchor` against a later snapshot.

    The return value IS the staleness signal. Get this right and the product works;
    get it wrong and everything above it is noise.

    Cascade — first matching rule wins:

      1. span found exactly once, same document, same position, context intact
             -> VALID
      2. span found exactly once, elsewhere in the same document
             -> VALID_REPAIRED         (document edited around it; anchor updated)
      3. span found exactly once, in another document or under a different heading
             -> VALID_RELOCATED        (section renamed/moved/split; update + note)
      4. span found in 2+ locations
             -> AMBIGUOUS              (content duplicated; flag for review)
      5. heading_path resolves to text that is no longer the span
             -> STALE                  (THE ANSWER TEXT CHANGED; flag for review)
      6. nothing resolves
             -> DESTROYED              (evidence not visible in THIS snapshot)

    Design notes:

    - Rule 1 requires `context_hash` to match as well as the position. A span sitting at
      the same offset inside edited surroundings has not been re-verified by anything;
      calling that VALID would report "nothing happened" about a document that changed.
      It is a silent repair either way, so it costs no review time to be honest and call
      it VALID_REPAIRED.

    - Rule 5 is the money case. Populate `candidate_spans` with what the text under that
      heading says NOW, so a reviewer sees the old answer (`anchor.span_text`) beside the
      new one without re-fetching the old snapshot.

    - A heading that survives with an empty body is DESTROYED, not STALE. STALE means
      "there is new text here and a human must judge it"; with nothing left to judge,
      there is no review to do. DESTROYED is not a retirement — see `anchors.policy`.

    - `context_hash` is a repair aid, never a validity signal. A context-only match
      (span changed, surroundings identical) is STALE with a suggested correction. A
      human decides whether the reworded text still answers the question.

    - DESTROYED is an observation about one snapshot, never a verdict on the test. This
      function must not be able to cause a retirement; that decision needs history and a
      human, and lives in `anchors.policy`. See ADR-0008.

    - Never fall back to char_range as identity. Position is a tiebreaker for rule 1 and
      a hint for repair. Nothing else. Positional identity is the exact failure this
      design replaces.
    """
    if content_hash(anchor.span_text) != anchor.span_hash:
        raise ValueError(
            f"anchor span_text does not hash to span_hash for {anchor.doc_key!r}; "
            "the anchor was captured under a different NORMALIZER_VERSION and cannot "
            "be resolved against this snapshot"
        )

    matches = _span_matches(anchor, snapshot)

    # Rule 4 — duplicated content. Checked before the single-match rules because
    # "found it, twice" is not a repair, it is a question only a human can answer.
    if len(matches) > 1:
        return ResolutionResult(
            anchor=anchor,
            resolution=Resolution.AMBIGUOUS,
            candidate_spans=[
                _locate(doc, start, end) for doc, start, end in matches
            ],
            note=(
                f"span occurs in {len(matches)} locations; cannot decide which one the "
                "test meant"
            ),
        )

    # Rules 1-3 — the span survived exactly once.
    if len(matches) == 1:
        doc, start, end = matches[0]
        new_heading = heading_path_at(doc, start)

        if doc.doc_key != anchor.doc_key:
            return ResolutionResult(
                anchor=anchor,
                resolution=Resolution.VALID_RELOCATED,
                new_char_range=(start, end),
                new_heading_path=new_heading,
                note=(
                    f"span moved from {anchor.doc_key!r} to {doc.doc_key!r}; "
                    "repaired, no review needed"
                ),
            )

        if not heading_paths_resolve(anchor.heading_path, new_heading):
            return ResolutionResult(
                anchor=anchor,
                resolution=Resolution.VALID_RELOCATED,
                new_char_range=(start, end),
                new_heading_path=new_heading,
                note=(
                    f"heading changed from {anchor.heading_path} to {new_heading}; "
                    "span unchanged, repaired"
                ),
            )

        same_place = start == anchor.char_range[0]
        same_context = (
            context_hash_at(doc.normalized_text, start, end) == anchor.context_hash
        )
        if same_place and same_context:
            return ResolutionResult(
                anchor=anchor,
                resolution=Resolution.VALID,
                new_char_range=(start, end),
                new_heading_path=new_heading,
            )

        return ResolutionResult(
            anchor=anchor,
            resolution=Resolution.VALID_REPAIRED,
            new_char_range=(start, end),
            new_heading_path=new_heading,
            note=(
                "span intact but its surroundings changed; repaired silently"
                if same_place
                else f"span shifted from offset {anchor.char_range[0]} to {start}; "
                "repaired silently"
            ),
        )

    # Rules 5-6 — the span is gone. Which one depends on whether anything is left to review.
    return _resolve_missing_span(anchor, snapshot)


def _resolve_missing_span(anchor: Anchor, snapshot: Snapshot) -> ResolutionResult:
    """The span no longer exists anywhere. Decide between STALE and DESTROYED.

    STALE means a reviewer has something to look at: the heading the answer lived under
    still exists and still has text in it. That text is what the document now says, and
    the test's expected answer is now wrong. DESTROYED means there is nothing left.
    """
    doc = snapshot.documents.get(anchor.doc_key)
    heading = _heading_span(doc, anchor.heading_path) if doc is not None else None

    # The document is gone, but the heading may have survived inside another file.
    if heading is None:
        for key in sorted(snapshot.documents):
            found = _heading_span(snapshot.documents[key], anchor.heading_path)
            if found is not None:
                doc, heading = snapshot.documents[key], found
                break

    if doc is not None and heading is not None:
        candidates = _paragraphs(doc.normalized_text, heading.start, heading.end)
        if candidates:
            return _stale(anchor, doc, candidates)

    # Last resort before retiring the test: the section may have lost its heading while
    # the surrounding text stayed put. A context-only match is still STALE, never VALID.
    if doc is not None:
        whole = _paragraphs(doc.normalized_text, 0, len(doc.normalized_text))
        by_context = [
            (t, s, e)
            for t, s, e in whole
            if context_hash_at(doc.normalized_text, s, e) == anchor.context_hash
        ]
        if by_context:
            return _stale(anchor, doc, by_context)

    return ResolutionResult(
        anchor=anchor,
        resolution=Resolution.DESTROYED,
        note=(
            "span, heading, and context all failed to resolve in this snapshot; the test "
            "is carried forward unchanged and the observation recorded"
        ),
    )


def _stale(
    anchor: Anchor, document: Document, candidates: list[tuple[str, int, int]]
) -> ResolutionResult:
    """Build a STALE result, putting the best-supported correction first.

    A candidate whose surroundings hash to the anchor's `context_hash` is sitting exactly
    where the old answer was, so it is the most likely replacement. It is still only a
    suggestion — the answer text changed and a human decides.
    """
    suggestion = next(
        (
            text
            for text, start, end in candidates
            if context_hash_at(document.normalized_text, start, end)
            == anchor.context_hash
        ),
        None,
    )
    spans = [t for t, _, _ in candidates]
    if suggestion is not None:
        spans = [suggestion] + [t for t in spans if t != suggestion]

    return ResolutionResult(
        anchor=anchor,
        resolution=Resolution.STALE,
        new_heading_path=anchor.heading_path,
        candidate_spans=spans,
        note=(
            "the answer text changed; the first candidate sits where the old answer was "
            "and is the suggested correction, but a human decides whether it still "
            "answers the question"
            if suggestion is not None
            else "the answer text under this heading changed"
        ),
    )


def _locate(document: Document, start: int, end: int) -> str:
    """Human-readable locator for one match, used to describe AMBIGUOUS results."""
    path = " > ".join(heading_path_at(document, start)) or "(no heading)"
    return f"{document.doc_key} [{path}] @{start}-{end}: {document.normalized_text[start:end]}"


def resolve_all(
    anchors: list[Anchor], snapshot: Snapshot
) -> list[ResolutionResult]:
    return [resolve(a, snapshot) for a in anchors]
