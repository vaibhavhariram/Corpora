"""Specification for the snapshot set-diff and the compatibility guard.

The set arithmetic is nearly free — a `Snapshot` is already a map of
`doc_key -> content_hash`. The guard is the part that earns its place: diffing across a
normalizer or loader version change produces confident, meaningless resolutions, and the
whole product is the claim that we do not do that.
"""

from __future__ import annotations

import pytest

from corpora.diff.snapshots import (
    IncompatibleSnapshots,
    assert_comparable,
    diff_snapshots,
)
from corpora.models import Snapshot

from .conftest import build_snapshot

V1 = {
    "a.md": "# A\n\nalpha\n",
    "b.md": "# B\n\nbeta\n",
    "c.md": "# C\n\ngamma\n",
}


def _snap(files: dict[str, str], snapshot_id: str = "v") -> Snapshot:
    return build_snapshot(files, snapshot_id=snapshot_id)


# --------------------------------------------------------------------------- #
# The set arithmetic
# --------------------------------------------------------------------------- #


def test_identical_snapshots_have_no_changes() -> None:
    changes = diff_snapshots(_snap(V1, "v1"), _snap(V1, "v2"))
    assert changes.added == []
    assert changes.removed == []
    assert changes.changed == []


def test_added_removed_and_changed_are_separated() -> None:
    v2 = {
        "a.md": "# A\n\nalpha\n",  # untouched
        "b.md": "# B\n\nbeta edited\n",  # changed
        "d.md": "# D\n\ndelta\n",  # added
    }  # c.md removed
    changes = diff_snapshots(_snap(V1, "v1"), _snap(v2, "v2"))
    assert changes.added == ["d.md"]
    assert changes.removed == ["c.md"]
    assert changes.changed == ["b.md"]


def test_an_unchanged_document_appears_in_no_bucket() -> None:
    changes = diff_snapshots(_snap(V1, "v1"), _snap(V1, "v2"))
    assert "a.md" not in changes.added + changes.removed + changes.changed


def test_results_are_sorted() -> None:
    """Stable order so a diff report does not churn between runs."""
    before = {"z.md": "# Z\n", "m.md": "# M\n"}
    after = {"q.md": "# Q\n", "b.md": "# B\n"}
    changes = diff_snapshots(_snap(before, "v1"), _snap(after, "v2"))
    assert changes.added == sorted(changes.added)
    assert changes.removed == sorted(changes.removed)


def test_a_rename_reads_as_removed_plus_added() -> None:
    """`doc_key` is a locator (ADR-0010), so the set-diff cannot see a rename as a rename.

    That is fine and deliberate: the anchor cascade searches other documents, so the
    anchors inside a renamed file resolve to VALID_RELOCATED. The document-level diff is
    report metadata; `resolutions` is what carries meaning.
    """
    renamed = {"a.md": "# A\n\nalpha\n", "b.md": "# B\n\nbeta\n", "c2.md": "# C\n\ngamma\n"}
    changes = diff_snapshots(_snap(V1, "v1"), _snap(renamed, "v2"))
    assert changes.added == ["c2.md"]
    assert changes.removed == ["c.md"]
    assert changes.changed == []


def test_empty_to_populated_is_all_added() -> None:
    changes = diff_snapshots(_snap({}, "v1"), _snap(V1, "v2"))
    assert changes.added == ["a.md", "b.md", "c.md"]
    assert changes.removed == []


def test_changes_unpack_as_a_tuple() -> None:
    added, removed, changed = diff_snapshots(_snap(V1, "v1"), _snap(V1, "v2"))
    assert (added, removed, changed) == ([], [], [])


# --------------------------------------------------------------------------- #
# The compatibility guard — invariant 3
# --------------------------------------------------------------------------- #


def test_normalizer_mismatch_raises() -> None:
    """Invariant 3: a normalizer change invalidates every anchor ever captured.

    Every document would read as changed, every anchor would fail to resolve, and the
    output would be a confident pile of STALE and DESTROYED that describes our own version
    bump rather than anything that happened to the corpus.
    """
    old = _snap(V1, "v1").model_copy(update={"normalizer_version": "0.9.0"})
    with pytest.raises(IncompatibleSnapshots) as exc:
        diff_snapshots(old, _snap(V1, "v2"))
    assert "0.9.0" in str(exc.value)


def test_the_guard_does_not_warn_and_continue() -> None:
    """There is no permissive mode. A silently wrong diff is the failure we sell against."""
    old = _snap(V1, "v1").model_copy(update={"normalizer_version": "0.9.0"})
    with pytest.raises(IncompatibleSnapshots):
        assert_comparable(old, _snap(V1, "v2"))


def test_same_loader_at_a_different_version_raises() -> None:
    """Anchors are only valid within a loader version; heading offsets can move."""
    old = _snap(V1, "v1").model_copy(
        update={"loader_versions": {"markdown": "builtin-markdown-0.9.0"}}
    )
    with pytest.raises(IncompatibleSnapshots) as exc:
        assert_comparable(old, _snap(V1, "v2"))
    assert "markdown" in str(exc.value)


def test_a_loader_present_in_only_one_snapshot_is_fine() -> None:
    """Adding spreadsheets to a corpus must not invalidate its Markdown anchors.

    The rule is per-loader agreement where both snapshots use it, not dict equality.
    """
    before = _snap(V1, "v1")
    after = _snap(V1, "v2").model_copy(
        update={
            "loader_versions": {
                **before.loader_versions,
                "xlsx": "openpyxl==3.1.5",
            }
        }
    )
    assert_comparable(before, after)


def test_one_mismatched_loader_among_several_raises() -> None:
    before = _snap(V1, "v1").model_copy(
        update={"loader_versions": {"markdown": "builtin-markdown-1.0.0", "pdf": "x==1"}}
    )
    after = _snap(V1, "v2").model_copy(
        update={"loader_versions": {"markdown": "builtin-markdown-1.0.0", "pdf": "x==2"}}
    )
    with pytest.raises(IncompatibleSnapshots) as exc:
        assert_comparable(before, after)
    assert "pdf" in str(exc.value)


def test_comparable_snapshots_pass_the_guard() -> None:
    """No exception is the pass condition; the guard returns nothing."""
    assert assert_comparable(_snap(V1, "v1"), _snap(V1, "v2")) is None


def test_the_error_names_both_versions_and_says_what_to_do() -> None:
    """A reviewer hitting this at 2am needs the fix in the message, not in an ADR."""
    old = _snap(V1, "v1").model_copy(update={"normalizer_version": "0.9.0"})
    with pytest.raises(IncompatibleSnapshots) as exc:
        assert_comparable(old, _snap(V1, "v2"))
    message = str(exc.value)
    assert "0.9.0" in message
    assert "recapture" in message.lower()
