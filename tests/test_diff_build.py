"""Specification for assembling a Diff from two snapshots and a set of anchors.

Three traps, each of which ships a wrong number rather than an error:

1. pre-filtering anchors to changed documents silently misses AMBIGUOUS
2. no error isolation, so one stale anchor aborts nine hundred good resolutions
3. pooling unresolvable anchors into the resolution counts, which reports our own
   version bumps as documentation decay
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from corpora.anchors.resolve import capture
from corpora.corpus.normalize import content_hash
from corpora.diff.build import build_diff
from corpora.diff.snapshots import IncompatibleSnapshots
from corpora.models import Anchor, Resolution

from .conftest import build_snapshot

T0 = datetime(2026, 1, 1, tzinfo=UTC)

SPAN = "The limit is 12 volts."

V1 = {
    "stable.md": f"# Stable\n\n## Inner\n\n{SPAN}\n",
    "churn.md": "# Churn\n\n## Other\n\nUnrelated prose.\n",
}


def _anchor_on(files: dict[str, str], doc_key: str, span: str) -> Anchor:
    snap = build_snapshot(files, snapshot_id="v1")
    return capture(snap.documents[doc_key], span, snapshot_id="v1")


# --------------------------------------------------------------------------- #
# Trap 1 — every anchor is resolved, not only those in changed documents
# --------------------------------------------------------------------------- #


def test_an_anchor_in_an_unchanged_document_is_still_resolved() -> None:
    """`changed_docs` is a report field, not a work list."""
    v2 = dict(V1)
    v2["churn.md"] = "# Churn\n\n## Other\n\nUnrelated prose, reworded.\n"

    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(v2, "v2"),
        [_anchor_on(V1, "stable.md", SPAN)],
        computed_at=T0,
    )
    assert diff.changed_docs == ["churn.md"]
    assert len(diff.resolutions) == 1, "the anchor lives in an unchanged doc; resolve it anyway"


def test_a_span_duplicated_into_a_changed_document_is_ambiguous() -> None:
    """THE trap. An implementation that re-resolves only anchors whose doc_key is in
    `changed_docs` never looks at this anchor and reports VALID. Silently.

    The anchor's own document is untouched. Another document grew a copy of its span, so
    the evidence is no longer uniquely located and no longer means what the test assumed.
    """
    v2 = dict(V1)
    v2["churn.md"] = f"# Churn\n\n## Other\n\nUnrelated prose.\n\n## Copy\n\n{SPAN}\n"

    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(v2, "v2"),
        [_anchor_on(V1, "stable.md", SPAN)],
        computed_at=T0,
    )
    assert diff.changed_docs == ["churn.md"], "the anchor's own document did not change"
    assert diff.resolutions[0].resolution is Resolution.AMBIGUOUS
    assert diff.needs_review, "AMBIGUOUS must reach a human"


# --------------------------------------------------------------------------- #
# Trap 2 — one bad anchor must not abort the diff
# --------------------------------------------------------------------------- #


def _skewed_anchor() -> Anchor:
    """An anchor whose span_text no longer hashes to its span_hash.

    That is what an anchor captured under an older NORMALIZER_VERSION looks like from
    here, and `resolve()` raises ValueError on it before doing any work.
    """
    good = _anchor_on(V1, "stable.md", SPAN)
    return good.model_copy(update={"span_hash": content_hash("something else entirely")})


def test_one_unresolvable_anchor_does_not_abort_the_diff() -> None:
    good = _anchor_on(V1, "stable.md", SPAN)
    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(V1, "v2"),
        [_skewed_anchor(), good, _skewed_anchor()],
        computed_at=T0,
    )
    assert len(diff.resolutions) == 1
    assert len(diff.unresolvable) == 2


def test_an_unexpected_error_is_not_swallowed() -> None:
    """Isolation is for the known infrastructural case, not a blanket except.

    A bug in the cascade must surface as a crash, not as two quiet entries in a list
    nobody reads.
    """
    with pytest.raises(AttributeError):
        build_diff(
            build_snapshot(V1, "v1"),
            build_snapshot(V1, "v2"),
            ["not an anchor"],  # type: ignore[list-item]
            computed_at=T0,
        )


# --------------------------------------------------------------------------- #
# Trap 3 — unresolvable is not a corpus finding
# --------------------------------------------------------------------------- #


def test_unresolvable_anchors_are_absent_from_every_resolution_bucket() -> None:
    """Not DESTROYED, not STALE, not counted. Invariant 4 one level up."""
    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(V1, "v2"),
        [_skewed_anchor()],
        computed_at=T0,
    )
    assert diff.resolutions == []
    assert diff.needs_review == []
    assert diff.unresolved == []
    assert diff.repaired == []
    assert len(diff.unresolvable) == 1


def test_unresolvable_carries_the_anchor_and_a_reason() -> None:
    skewed = _skewed_anchor()
    diff = build_diff(
        build_snapshot(V1, "v1"), build_snapshot(V1, "v2"), [skewed], computed_at=T0
    )
    anchor, reason = diff.unresolvable[0]
    assert anchor.span_hash == skewed.span_hash
    assert "NORMALIZER_VERSION" in reason or "span_hash" in reason


def test_a_staleness_rate_over_resolutions_ignores_unresolvable() -> None:
    """The number the study reports. If unresolvable anchors were pooled in, a version
    bump on our side would read as documentation decay on the customer's."""
    v2 = dict(V1)
    v2["stable.md"] = "# Stable\n\n## Inner\n\nThe limit is 19 volts.\n"

    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(v2, "v2"),
        [_anchor_on(V1, "stable.md", SPAN), _skewed_anchor(), _skewed_anchor()],
        computed_at=T0,
    )
    stale = [r for r in diff.resolutions if r.resolution is Resolution.STALE]
    assert len(diff.resolutions) == 1
    assert len(stale) / len(diff.resolutions) == 1.0, "1 of 1 resolvable anchors went stale"
    assert len(diff.unresolvable) == 2, "reported separately, never in the denominator"


def test_a_genuine_destroyed_stays_in_resolutions() -> None:
    """The distinction that matters: evidence gone is a finding; tooling skew is not."""
    v2 = {"stable.md": "# Stable\n\n## Inner\n\n", "churn.md": V1["churn.md"]}
    diff = build_diff(
        build_snapshot(V1, "v1"),
        build_snapshot(v2, "v2"),
        [_anchor_on(V1, "stable.md", SPAN)],
        computed_at=T0,
    )
    assert diff.resolutions[0].resolution is Resolution.DESTROYED
    assert diff.unresolvable == []


# --------------------------------------------------------------------------- #
# The rest of the Diff
# --------------------------------------------------------------------------- #


def test_document_level_changes_are_populated() -> None:
    v2 = {
        "stable.md": V1["stable.md"],
        "churn.md": "# Churn\n\n## Other\n\nReworded.\n",
        "added.md": "# New\n",
    }
    diff = build_diff(build_snapshot(V1, "v1"), build_snapshot(v2, "v2"), [], computed_at=T0)
    assert diff.added_docs == ["added.md"]
    assert diff.changed_docs == ["churn.md"]
    assert diff.removed_docs == []
    assert diff.from_snapshot_id == "v1"
    assert diff.to_snapshot_id == "v2"


def test_computed_at_is_recorded() -> None:
    diff = build_diff(build_snapshot(V1, "v1"), build_snapshot(V1, "v2"), [], computed_at=T0)
    assert diff.computed_at == T0


def test_no_anchors_is_a_valid_diff() -> None:
    diff = build_diff(build_snapshot(V1, "v1"), build_snapshot(V1, "v2"), [], computed_at=T0)
    assert diff.resolutions == []
    assert diff.unresolvable == []


def test_incompatible_snapshots_raise_before_any_anchor_resolves() -> None:
    """The snapshot-level guard fires first; per-anchor isolation must not mask it."""
    old = build_snapshot(V1, "v1").model_copy(update={"normalizer_version": "0.9.0"})
    with pytest.raises(IncompatibleSnapshots):
        build_diff(old, build_snapshot(V1, "v2"), [_anchor_on(V1, "stable.md", SPAN)],
                   computed_at=T0)


def test_resolution_order_follows_the_anchors_given() -> None:
    """Stable output so a diff report does not churn between runs."""
    a1 = _anchor_on(V1, "stable.md", SPAN)
    a2 = _anchor_on(V1, "churn.md", "Unrelated prose.")
    diff = build_diff(
        build_snapshot(V1, "v1"), build_snapshot(V1, "v2"), [a1, a2], computed_at=T0
    )
    assert [r.anchor.doc_key for r in diff.resolutions] == ["stable.md", "churn.md"]
