"""Test helpers. Builds Snapshots from plain dicts so fixtures stay readable."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from corpora.corpus.normalize import NORMALIZER_VERSION, content_hash, normalize
from corpora.models import Document, HeadingSpan, Snapshot

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_headings(text: str) -> list[HeadingSpan]:
    """Minimal Markdown heading parser. Real loaders live in corpus/loaders/."""
    matches = list(_HEADING.finditer(text))
    spans: list[HeadingSpan] = []
    stack: list[tuple[int, str]] = []

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        body_start = m.end() + 1
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

        spans.append(
            HeadingSpan(
                path=[t for _, t in stack],
                level=level,
                start=body_start,
                end=body_end,
            )
        )
    return spans


def build_snapshot(files: dict[str, str], snapshot_id: str) -> Snapshot:
    docs: dict[str, Document] = {}
    for path, raw in files.items():
        text = normalize(raw)
        docs[path] = Document(
            doc_key=path,
            source_path=path,
            content_hash=content_hash(text),
            normalized_text=text,
            headings=parse_headings(text),
            loader="markdown",
            loader_version="builtin-1",
        )
    return Snapshot(
        snapshot_id=snapshot_id,
        captured_at=datetime.now(timezone.utc),
        source="fixture://",
        documents=docs,
        normalizer_version=NORMALIZER_VERSION,
        loader_versions={"markdown": "builtin-1"},
    )
