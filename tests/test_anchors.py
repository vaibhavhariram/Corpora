"""Specification for anchor resolution, expressed as tests.

These fail on a fresh clone. That is intended — `resolve()` is unimplemented and this file
is its spec. Make them pass. Do not weaken a test to match an implementation; if a
classification here seems wrong, argue it in an ADR first and change both together.
"""

from __future__ import annotations

import pytest

from corpora.anchors.resolve import capture, resolve
from corpora.models import NEEDS_REVIEW, Resolution

from .conftest import build_snapshot
from .fixtures.mutations import (
    CORPUS_V1,
    MUTATIONS,
    MUTATIONS_BY_NAME,
    SPAN_S3_ENTRY,
)

# --------------------------------------------------------------------------- #
# The mutation table
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.name)
def test_mutation_classifies_correctly(mutation) -> None:
    """Every mutation has exactly one correct classification.

    This single parametrized test is the product thesis. If it passes at high precision
    and recall, Corpora works. If it doesn't, nothing above it matters.
    """
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    doc = next(
        d for d in v1.documents.values() if mutation.anchored_span in d.normalized_text
    )
    anchor = capture(doc, mutation.anchored_span, snapshot_id="v1")

    v2 = build_snapshot(mutation.apply(CORPUS_V1), snapshot_id="v2")
    result = resolve(anchor, v2)

    assert result.resolution is mutation.expected, (
        f"{mutation.name}: expected {mutation.expected.value}, "
        f"got {result.resolution.value}. {mutation.note}"
    )


# --------------------------------------------------------------------------- #
# Properties that must hold regardless of mutation
# --------------------------------------------------------------------------- #


def test_stale_reports_what_the_text_says_now() -> None:
    """A STALE result must show the reviewer the new text.

    Without this the reviewer has to go diff the corpus by hand, which is the manual
    labor we are selling them out of.
    """
    m = MUTATIONS_BY_NAME["change_number_in_answer"]
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    doc = v1.documents["spec-a.md"]
    anchor = capture(doc, SPAN_S3_ENTRY, snapshot_id="v1")

    result = resolve(anchor, build_snapshot(m.apply(CORPUS_V1), snapshot_id="v2"))

    assert result.resolution is Resolution.STALE
    assert result.candidate_spans, "STALE must populate candidate_spans"
    assert any("18 milliseconds" in s for s in result.candidate_spans)
    assert "12 milliseconds" in anchor.span_text, "old answer must survive on the anchor"


def test_position_is_never_identity() -> None:
    """Inserting text above an anchor must not break it.

    This is the failure mode of positional chunk IDs and the reason the product exists.
    If this test ever fails, the implementation has regressed to positional identity.
    """
    m = MUTATIONS_BY_NAME["insert_paragraph_above"]
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    anchor = capture(v1.documents["spec-a.md"], SPAN_S3_ENTRY, snapshot_id="v1")

    result = resolve(anchor, build_snapshot(m.apply(CORPUS_V1), snapshot_id="v2"))

    assert result.resolution is Resolution.VALID_REPAIRED
    assert result.new_char_range is not None
    assert result.new_char_range[0] > anchor.char_range[0], "span should have shifted down"


def test_only_stale_and_ambiguous_need_review() -> None:
    """Review is the scarce resource. Everything repairable must repair silently."""
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")

    flagged: list[str] = []
    for m in MUTATIONS:
        doc = next(
            d for d in v1.documents.values() if m.anchored_span in d.normalized_text
        )
        anchor = capture(doc, m.anchored_span, snapshot_id="v1")
        result = resolve(anchor, build_snapshot(m.apply(CORPUS_V1), snapshot_id="v2"))
        if result.resolution in NEEDS_REVIEW:
            flagged.append(m.name)

    assert set(flagged) == {
        "reword_answer_sentence",
        "change_number_in_answer",
        "duplicate_section",
    }


def test_moved_to_another_document_is_not_destroyed() -> None:
    """A section moving files must be found, not retired.

    Naive implementations look only in anchor.doc_key, find nothing, and return DESTROYED —
    which silently deletes a perfectly good test.
    """
    m = MUTATIONS_BY_NAME["move_section_to_other_file"]
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    anchor = capture(v1.documents["spec-a.md"], m.anchored_span, snapshot_id="v1")

    result = resolve(anchor, build_snapshot(m.apply(CORPUS_V1), snapshot_id="v2"))

    assert result.resolution is Resolution.VALID_RELOCATED


def test_capture_refuses_dangling_anchor() -> None:
    """Fail loudly at capture rather than silently producing DESTROYED later."""
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    with pytest.raises(ValueError):
        capture(v1.documents["spec-a.md"], "text that does not exist", snapshot_id="v1")


def test_resolution_is_deterministic() -> None:
    """Same inputs, same answer, every time. No LLM, no randomness, no clock."""
    v1 = build_snapshot(CORPUS_V1, snapshot_id="v1")
    anchor = capture(v1.documents["spec-a.md"], SPAN_S3_ENTRY, snapshot_id="v1")
    v2 = build_snapshot(
        MUTATIONS_BY_NAME["rename_heading"].apply(CORPUS_V1), snapshot_id="v2"
    )

    first = resolve(anchor, v2)
    for _ in range(5):
        assert resolve(anchor, v2).resolution is first.resolution
