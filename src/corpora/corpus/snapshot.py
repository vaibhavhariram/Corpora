"""Snapshot construction: walk a corpus, load every document, freeze the result.

A `Snapshot` is an immutable capture of a whole corpus at one revision. Diffing two of
them is a set operation over `doc_key -> content_hash`, which is why identifying changed
documents is nearly free and why this module keeps that map honest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from ..models import Document, Snapshot
from .loaders.markdown import (
    MARKDOWN_LOADER,
    MARKDOWN_LOADER_VERSION,
    MARKDOWN_SUFFIXES,
    load_markdown,
)
from .normalize import NORMALIZER_VERSION


def snapshot_id_for(
    documents: Mapping[str, Document],
    normalizer_version: str = NORMALIZER_VERSION,
) -> str:
    """Content hash of a whole corpus.

    Covers each `doc_key` and its `content_hash`, in sorted order, plus the normalizer
    version. Deliberately excludes `captured_at`: two captures of an unchanged corpus are
    the same snapshot, whenever they happened, and a benchmark frozen against one should
    not be invalidated by re-running the loader.

    The normalizer version is bound in because invariant 3 makes it part of what a
    snapshot *means* — a normalizer change invalidates every anchor captured under the old
    one, so the same bytes under a different normalizer are a different snapshot.
    """
    digest = hashlib.sha256()
    digest.update(normalizer_version.encode("utf-8"))
    digest.update(b"\x00")
    for doc_key in sorted(documents):
        digest.update(doc_key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(documents[doc_key].content_hash.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_snapshot(
    documents: Mapping[str, Document],
    *,
    source: str,
    captured_at: datetime | None = None,
    snapshot_id: str | None = None,
) -> Snapshot:
    """Freeze a set of already-loaded documents into a `Snapshot`.

    `snapshot_id` is computed unless supplied. Supplying it is for the Git layer, where the
    id is a commit SHA so a benchmark can be described as "frozen at abc123". That layer is
    not built yet; build generic first.
    """
    loader_versions = {
        doc.loader: doc.loader_version for doc in documents.values()
    } or {MARKDOWN_LOADER: MARKDOWN_LOADER_VERSION}

    return Snapshot(
        snapshot_id=snapshot_id or snapshot_id_for(documents),
        captured_at=captured_at if captured_at is not None else datetime.now(UTC),
        source=source,
        documents=dict(documents),
        normalizer_version=NORMALIZER_VERSION,
        loader_versions=loader_versions,
    )


def load_directory(
    root: Path,
    *,
    source: str | None = None,
    captured_at: datetime | None = None,
) -> Snapshot:
    """Load every supported document beneath `root` into a `Snapshot`.

    Skipped, deliberately:

    - any path with a dot-prefixed component. Walking a real documentation repo means
      walking `.git`, and a few thousand objects in there are not the corpus.
    - symlinks, which otherwise produce duplicate content under two doc_keys, or cycles.

    Undecodable bytes raise. Decoding with `errors="replace"` would substitute U+FFFD,
    silently changing that document's content hash and every anchor inside it — a wrong
    answer with no error anywhere, which is the exact failure this product exists to catch.
    """
    documents: dict[str, Document] = {}

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in MARKDOWN_SUFFIXES:
            continue

        doc_key = relative.as_posix()
        documents[doc_key] = load_markdown(
            doc_key,
            path.read_text(encoding="utf-8"),
            source_path=str(path),
        )

    return build_snapshot(
        documents,
        source=source if source is not None else str(root),
        captured_at=captured_at,
    )
