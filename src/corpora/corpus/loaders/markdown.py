"""Markdown loader.

First of the loaders, in the priority order set by docs/architecture.md: Markdown, plain
text, XLSX/CSV, PDF.

The heading parser here is small and it is load-bearing. `anchors/resolve.py` depends on
the exact shape it produces — `heading_path_at` only works because ranges are flat and
non-overlapping, and `_heading_span` compares full ancestry with list equality. Changing
any of that does not raise; it silently reclassifies anchors. `tests/test_corpus_loader.py`
pins the offsets with explicit numbers for that reason.
"""

from __future__ import annotations

import re

from ...models import Document, HeadingSpan
from ..normalize import content_hash, normalize

MARKDOWN_LOADER = "markdown"

MARKDOWN_LOADER_VERSION = "builtin-markdown-1.1.0"
"""Version of THIS parser, not of a third-party library — there isn't one.

Anchors are only valid within a loader version, because `heading_path` resolution depends
on how this file assigns ranges and ancestry. Changing the parser's behaviour is a
breaking change and needs a bump here plus an ADR, for the same reason
`NORMALIZER_VERSION` exists.
"""

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

# ATX headings only. Setext (underlined) headings and trailing closing sequences
# (`## Title ##`) are known gaps — see ADR-0013 and ADR-0015.
#
# The whitespace class is `[ \t]`, NOT `\s`. `\s` matches newlines, so on a hashes-only
# line — `#` alone is a valid CommonMark heading, and normalize() strips a trailing space
# so `"# "` arrives as `"#"` — `\s+` consumed the blank line and `(.+)$` captured the NEXT
# line as the title. A real heading on that line vanished from the output, its own hashes
# ended up inside a phantom title, and every heading below inherited the phantom as root
# ancestor. See ADR-0015; it flipped STALE to DESTROYED end to end.
#
# The title group is optional so an empty heading stays a heading. It is one in CommonMark,
# and it still terminates the previous section, so dropping it would silently merge its
# body into the heading above.
_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.+))?$", re.MULTILINE)

# Fenced code blocks, which must be excluded before headings are matched. Technical
# documentation is full of shell and YAML whose comments start with `#`; parsed as
# headings they invent sections that do not exist AND corrupt the ancestry of the real
# heading that follows, which is what `heading_path` resolution depends on.
_FENCE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)$", re.MULTILINE)


def _fenced_regions(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by fenced code blocks.

    Follows the CommonMark rules that matter here: a closing fence uses the same character,
    is at least as long as the opener, and carries no info string. A backtick opener may not
    have backticks in its info string. An unclosed fence runs to the end of the document —
    the conservative reading, since the alternative is to start finding headings in code.
    """
    regions: list[tuple[int, int]] = []
    start: int | None = None
    char = ""
    length = 0

    for m in _FENCE.finditer(text):
        fence = m.group("fence")
        info = m.group("info").strip()
        if start is None:
            if fence[0] == "`" and "`" in info:
                continue
            start, char, length = m.start(), fence[0], len(fence)
        elif fence[0] == char and len(fence) >= length and not info:
            regions.append((start, m.end()))
            start = None

    if start is not None:
        regions.append((start, len(text)))
    return regions


def parse_headings(text: str) -> list[HeadingSpan]:
    """Heading structure of already-normalized Markdown.

    Three properties the rest of the system relies on:

    - a heading's body starts one character past the end of its own line, so the heading
      text is never inside its own range
    - a heading's body ends where the NEXT heading begins, whatever that heading's level.
      Ranges are therefore flat and non-overlapping; a parent does not enclose its children
    - `path` is the full ancestry including the heading itself

    Headings inside fenced code blocks are skipped; a fenced block remains part of the
    enclosing heading's body range, because it is content.
    """
    fenced = _fenced_regions(text)
    matches = [
        m
        for m in _HEADING.finditer(text)
        if not any(lo <= m.start() < hi for lo, hi in fenced)
    ]
    spans: list[HeadingSpan] = []
    stack: list[tuple[int, str]] = []

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = (m.group(2) or "").strip()
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


def load_markdown(
    doc_key: str,
    raw: str,
    *,
    source_path: str | None = None,
) -> Document:
    """Build a `Document` from raw Markdown.

    `doc_key` is a locator — the normalized path relative to the corpus root — not
    identity. See ADR-0010. Identity is `Anchor.span_hash`.
    """
    text = normalize(raw)
    return Document(
        doc_key=doc_key,
        source_path=source_path if source_path is not None else doc_key,
        content_hash=content_hash(text),
        normalized_text=text,
        headings=parse_headings(text),
        loader=MARKDOWN_LOADER,
        loader_version=MARKDOWN_LOADER_VERSION,
    )
