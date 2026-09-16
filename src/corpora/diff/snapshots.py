"""Snapshot-to-snapshot document diff, and the guard that decides whether a diff is
meaningful at all.

A `Snapshot` is already a map of `doc_key -> content_hash`, so identifying which documents
changed is set arithmetic and nearly free. The expensive part — re-resolving anchors — lives
in `diff/build.py`.

Generic snapshot diffing is the engine; Git is a convenience layer added later. Generic
works for any source: a SharePoint export, a network drive, an S3 bucket, PDFs emailed by a
standards body.
"""

from __future__ import annotations

from typing import NamedTuple

from ..models import Snapshot


class IncompatibleSnapshots(ValueError):
    """Two snapshots cannot be meaningfully compared.

    A `ValueError` subclass so it reads like the rest of the codebase's loud failures
    (`capture()` on a missing span, `resolve()` on normalizer skew), and a distinct type so
    callers can tell "this comparison is invalid" apart from "this input is malformed".
    """


class DocumentChanges(NamedTuple):
    """Which documents were added, removed, or edited between two snapshots.

    A `NamedTuple` so it unpacks like the tuple the caller expects while still having
    readable attribute access. Not a domain noun — the nine live in `models.py`.
    """

    added: list[str]
    removed: list[str]
    changed: list[str]


def assert_comparable(from_snapshot: Snapshot, to_snapshot: Snapshot) -> None:
    """Raise unless anchors captured against one snapshot mean anything in the other.

    There is deliberately no permissive mode. A normalizer or loader version change
    invalidates every anchor captured under the old version, so a diff across one produces
    a confident pile of STALE and DESTROYED describing our own version bump rather than
    anything that happened to the customer's documents. That is precisely the shape of
    failure this product exists to catch in other people's systems, and shipping a warning
    instead of an error would mean shipping it in ours.

    Loader versions are compared **per loader, where both snapshots use it** rather than as
    whole dicts. Adding spreadsheets to a corpus introduces an `xlsx` entry on one side
    only; that says nothing about whether the Markdown anchors are still valid, and failing
    on it would make growing a corpus impossible.
    """
    if from_snapshot.normalizer_version != to_snapshot.normalizer_version:
        raise IncompatibleSnapshots(
            f"normalizer version changed between snapshots "
            f"({from_snapshot.normalizer_version!r} -> {to_snapshot.normalizer_version!r}). "
            f"Invariant 3: this invalidates every anchor captured under the old version, so "
            f"any diff across it would report our own version bump as corpus staleness. "
            f"Recapture the benchmark's anchors against the new normalizer."
        )

    shared = from_snapshot.loader_versions.keys() & to_snapshot.loader_versions.keys()
    mismatched = sorted(
        loader
        for loader in shared
        if from_snapshot.loader_versions[loader] != to_snapshot.loader_versions[loader]
    )
    if mismatched:
        detail = ", ".join(
            f"{loader}: {from_snapshot.loader_versions[loader]!r} -> "
            f"{to_snapshot.loader_versions[loader]!r}"
            for loader in mismatched
        )
        raise IncompatibleSnapshots(
            f"loader version changed between snapshots ({detail}). Anchors are only valid "
            f"within a loader version — extraction differences move heading offsets and "
            f"change content hashes. Recapture the affected anchors, or pin the loader."
        )


def diff_snapshots(
    from_snapshot: Snapshot, to_snapshot: Snapshot
) -> DocumentChanges:
    """Which documents were added, removed, or edited.

    Guards first: an incomparable pair raises rather than returning a plausible answer.

    A renamed file reads as one removal plus one addition, because `doc_key` is a locator
    and not identity (ADR-0010). That is not a gap to be closed here — the anchor cascade
    searches other documents, so anchors inside a renamed file resolve to VALID_RELOCATED.
    This function reports document churn; `resolutions` carries the meaning.
    """
    assert_comparable(from_snapshot, to_snapshot)

    before = from_snapshot.documents
    after = to_snapshot.documents

    return DocumentChanges(
        added=sorted(after.keys() - before.keys()),
        removed=sorted(before.keys() - after.keys()),
        changed=sorted(
            doc_key
            for doc_key in before.keys() & after.keys()
            if before[doc_key].content_hash != after[doc_key].content_hash
        ),
    )
