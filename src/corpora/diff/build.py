"""Assemble a `Diff`: two snapshots plus a set of anchors in, one observation per anchor out.

This module is three guards wearing a thin layer of assembly. Each of the three, if got
wrong, produces a confident wrong number rather than an error — which is the only failure
mode that matters here, because the Kubernetes study reads its headline straight off this
output.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..anchors.resolve import resolve
from ..models import Anchor, Diff, ResolutionResult, Snapshot
from .snapshots import diff_snapshots


def build_diff(
    from_snapshot: Snapshot,
    to_snapshot: Snapshot,
    anchors: Sequence[Anchor],
    *,
    computed_at: datetime,
) -> Diff:
    """Re-resolve every anchor against `to_snapshot` and record what changed.

    Three things this deliberately does not do:

    **It does not pre-filter anchors to changed documents.** `docs/architecture.md` calls
    re-resolving anchors in changed documents "the real work", and read as a work list that
    is wrong. `resolve()` searches the whole snapshot by design — that is what makes a
    section moving between files VALID_RELOCATED. Consider an anchor in a document that did
    *not* change, whose span was duplicated into one that did: the correct observation is
    AMBIGUOUS, because the evidence is no longer uniquely located. An implementation that
    only visits anchors whose `doc_key` is in `changed_docs` never looks at that anchor and
    reports VALID. Silently, and in the direction of a false green. `changed_docs` is a
    report field. If profiling ever makes this matter, optimise then — with the duplication
    case pinned by a test first.

    **It does not let one bad anchor abort the batch.** `resolve()` raises `ValueError` on
    an anchor whose `span_text` no longer hashes to its `span_hash`, which is what an
    anchor captured under an older `NORMALIZER_VERSION` looks like from here. Left
    unhandled, one such anchor in a benchmark of nine hundred turns the whole diff into a
    traceback.

    **It does not count those anchors as findings.** They go to `Diff.unresolvable`, never
    to `resolutions`. See below.

    `computed_at` is required rather than defaulted: it is the seam the retirement history
    will be built on (ADR-0008), and a default would silently stamp the wrong time on a
    diff replayed from stored snapshots.
    """
    changes = diff_snapshots(from_snapshot, to_snapshot)

    resolutions: list[ResolutionResult] = []
    unresolvable: list[tuple[Anchor, str]] = []

    for anchor in anchors:
        try:
            resolutions.append(resolve(anchor, to_snapshot))
        except ValueError as exc:
            # Narrow on purpose. `ValueError` is the documented signal that an anchor
            # cannot be resolved for infrastructural reasons; anything else is a bug in
            # the cascade and must surface as a crash rather than as a quiet entry in a
            # list nobody reads. A bare `except Exception` here would convert every future
            # defect in resolve() into a silently shrinking denominator.
            unresolvable.append((anchor, str(exc)))

    return Diff(
        from_snapshot_id=from_snapshot.snapshot_id,
        to_snapshot_id=to_snapshot.snapshot_id,
        computed_at=computed_at,
        added_docs=changes.added,
        removed_docs=changes.removed,
        changed_docs=changes.changed,
        resolutions=resolutions,
        unresolvable=unresolvable,
    )
