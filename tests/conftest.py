"""Test helpers. Builds Snapshots from plain dicts so fixtures stay readable.

Both functions delegate to the real loader in `src/`. They used to be independent
reimplementations, which is how `doc_key = filesystem path` lived here for weeks while
`models.py` asserted the opposite. A fixture that reimplements the thing under test can
agree with itself forever while disagreeing with production.
"""

from __future__ import annotations

from datetime import UTC, datetime

from corpora.corpus.loaders.markdown import load_markdown, parse_headings
from corpora.corpus.snapshot import build_snapshot as _build_snapshot
from corpora.models import Document, Snapshot

# `parse_headings` is re-exported, not reimplemented — listing it in __all__ is what
# keeps `from .conftest import parse_headings` working for any test that wants it.
__all__ = ["build_snapshot", "parse_headings"]

_FIXTURE_CAPTURED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def build_snapshot(files: dict[str, str], snapshot_id: str) -> Snapshot:
    """Snapshot from `path -> raw text`, with a caller-supplied id.

    The explicit `snapshot_id` is a fixture affordance: tests want to say "v1" and "v2"
    rather than compare hashes. The real loader computes it from content.
    """
    documents: dict[str, Document] = {
        path: load_markdown(path, raw) for path, raw in files.items()
    }
    return _build_snapshot(
        documents,
        source="fixture://",
        captured_at=_FIXTURE_CAPTURED_AT,
        snapshot_id=snapshot_id,
    )
