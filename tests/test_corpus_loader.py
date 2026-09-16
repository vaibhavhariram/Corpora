"""Specification for the corpus loader.

`resolve.py` is coupled to the exact shape this loader produces. `heading_path_at` only
works because heading ranges are flat and non-overlapping; `_heading_span` compares full
ancestry with list equality. Getting any of it subtly wrong does not raise — it silently
reclassifies anchors, which is the failure this product exists to catch in other systems.

So the heading semantics are pinned here with explicit offsets rather than described.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from corpora.corpus.loaders.markdown import (
    MARKDOWN_LOADER,
    MARKDOWN_LOADER_VERSION,
    load_markdown,
    parse_headings,
)
from corpora.corpus.normalize import NORMALIZER_VERSION, content_hash, normalize
from corpora.corpus.snapshot import build_snapshot, load_directory, snapshot_id_for

T0 = datetime(2026, 1, 1, tzinfo=UTC)

# Two headings, a nested one, and bodies either side. Offsets below are hand-counted
# against the NORMALIZED text and are the contract.
DOC = "# A\n\nintro\n\n## B\n\nbody\n"


# --------------------------------------------------------------------------- #
# Heading semantics — the part resolve.py depends on
# --------------------------------------------------------------------------- #


def test_heading_offsets_are_exact() -> None:
    """The contract, spelled out. Change these numbers and every anchor moves."""
    text = normalize(DOC)
    assert text == "# A\n\nintro\n\n## B\n\nbody"

    spans = parse_headings(text)
    assert len(spans) == 2

    # body starts one character past the end of the heading line, so the heading
    # text itself is never inside its own body range
    assert (spans[0].path, spans[0].level, spans[0].start, spans[0].end) == (["A"], 1, 4, 12)
    assert (spans[1].path, spans[1].level, spans[1].start, spans[1].end) == (
        ["A", "B"],
        2,
        17,
        22,
    )
    assert text[spans[0].start : spans[0].end] == "\nintro\n\n"
    assert text[spans[1].start : spans[1].end] == "\nbody"


def test_heading_ranges_are_flat_and_non_overlapping() -> None:
    """A parent's range does NOT enclose its children.

    `heading_path_at` picks the deepest heading whose range contains a position. That is
    only correct because ranges never nest — if a parent enclosed its children, every
    position would match the parent too and the tiebreak would be doing the real work.
    """
    spans = parse_headings(normalize(DOC))
    for earlier, later in pairwise(spans):
        assert earlier.end <= later.start, "ranges must not overlap"

    parent, child = spans
    assert parent.level < child.level
    assert not (parent.start <= child.start and parent.end >= child.end), (
        "parent must not enclose child"
    )


def test_a_heading_ends_at_the_next_heading_of_any_level() -> None:
    """Not the next heading of the same or shallower level — the next one, full stop."""
    text = normalize("# A\n\nx\n\n### Deep\n\ny\n\n# B\n\nz\n")
    spans = parse_headings(text)
    paths = [s.path for s in spans]
    assert paths == [["A"], ["A", "Deep"], ["B"]]
    assert spans[0].end == text.index("### Deep")
    assert spans[1].end == text.index("# B")
    assert spans[2].end == len(text)


def test_path_is_full_ancestry_including_the_heading_itself() -> None:
    text = normalize("# One\n\n## Two\n\n### Three\n\n## Four\n\n# Five\n")
    assert [s.path for s in parse_headings(text)] == [
        ["One"],
        ["One", "Two"],
        ["One", "Two", "Three"],
        ["One", "Four"],
        ["Five"],
    ]


def test_hashes_inside_fenced_code_are_not_headings() -> None:
    """The bug that would have wrecked the Kubernetes study.

    Technical documentation is dense with shell and YAML blocks whose comments start with
    `#`. Parsed naively they become H1 headings, which does two kinds of damage: it invents
    headings that do not exist, and it corrupts the ancestry of the real heading that
    follows. `heading_path` resolution is what separates STALE from DESTROYED, so this
    would have moved the study's headline numbers.
    """
    text = normalize(
        "# Pods\n\nA Pod is the smallest deployable unit.\n\n"
        "```bash\n# Create a pod\nkubectl apply -f pod.yaml\n# Delete it\n"
        "kubectl delete pod nginx\n```\n\n"
        "## Pod lifecycle\n\nPods have a defined lifecycle.\n"
    )
    spans = parse_headings(text)
    assert [s.path for s in spans] == [["Pods"], ["Pods", "Pod lifecycle"]]


def test_fence_variants_are_all_recognised() -> None:
    cases = {
        "tilde": "~~~\n# not a heading\n~~~\n",
        "indented": "   ```\n# not a heading\n   ```\n",
        "long": "````\n# not a heading\n````\n",
        "info string": "```python\n# not a heading\n```\n",
    }
    for name, fence in cases.items():
        text = normalize(f"# Real\n\n{fence}\n## Also real\n")
        assert [s.path for s in parse_headings(text)] == [
            ["Real"],
            ["Real", "Also real"],
        ], f"{name} fence not handled"


def test_a_shorter_fence_does_not_close_a_longer_one() -> None:
    """A ``` line inside a ```` block is content, not the closing fence."""
    text = normalize("# Real\n\n````\n```\n# not a heading\n```\n````\n\n## Also real\n")
    assert [s.path for s in parse_headings(text)] == [["Real"], ["Real", "Also real"]]


def test_an_unclosed_fence_swallows_the_rest_of_the_document() -> None:
    """Malformed input should not resurrect the bug; treat the remainder as code."""
    text = normalize("# Real\n\n```\n# not a heading\n\n## also not\n")
    assert [s.path for s in parse_headings(text)] == [["Real"]]


def test_a_fenced_block_stays_inside_its_headings_body() -> None:
    """Skipping fenced headings must not shrink the enclosing heading's range."""
    text = normalize("# Real\n\n```\n# not a heading\n```\n")
    span = parse_headings(text)[0]
    assert "# not a heading" in text[span.start : span.end]


def test_offsets_are_into_normalized_text() -> None:
    """Normalization runs first, so offsets index the normalized string.

    Raw text here has CRLF line endings and a run of blank lines that the normalizer
    collapses. If offsets were computed against the raw text every span would be wrong.
    """
    raw = "# A\r\n\r\n\r\n\r\nbody with a – dash\r\n"
    doc = load_markdown("a.md", raw)
    span = doc.headings[0]
    assert doc.normalized_text[span.start : span.end] == "\nbody with a - dash"


def test_document_with_no_headings_has_no_spans() -> None:
    doc = load_markdown("a.md", "just a paragraph, no headings at all\n")
    assert doc.headings == []


# --------------------------------------------------------------------------- #
# Document identity
# --------------------------------------------------------------------------- #


def test_content_hash_is_of_normalized_text() -> None:
    doc = load_markdown("a.md", "# A\r\n\r\nbody   with  spaces\n")
    assert doc.content_hash == content_hash(doc.normalized_text)


def test_loader_version_is_stamped_truthfully() -> None:
    """Anchors are only valid within a loader version, so it must identify this parser."""
    doc = load_markdown("a.md", "# A\n")
    assert doc.loader == MARKDOWN_LOADER
    assert doc.loader_version == MARKDOWN_LOADER_VERSION
    assert doc.loader_version != "builtin-1", "the fixture placeholder must not survive"


# --------------------------------------------------------------------------- #
# Directory loading
# --------------------------------------------------------------------------- #


def _corpus(tmp_path: Path) -> Path:
    (tmp_path / "spec.md").write_text("# A\n\nalpha\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.md").write_text("# B\n\nbeta\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not markdown\n", encoding="utf-8")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "config.md").write_text("# Hidden\n", encoding="utf-8")
    return tmp_path


def test_doc_key_is_the_posix_relative_path(tmp_path: Path) -> None:
    """A locator, not identity (ADR-0010). Posix separators so it is stable across OSes."""
    snap = load_directory(_corpus(tmp_path), captured_at=T0)
    assert set(snap.documents) == {"spec.md", "nested/deep.md"}


def test_non_markdown_and_hidden_directories_are_skipped(tmp_path: Path) -> None:
    """Walking a real repo means walking .git. Skipping dotted paths is not optional."""
    snap = load_directory(_corpus(tmp_path), captured_at=T0)
    assert not any(k.endswith(".txt") for k in snap.documents)
    assert not any(".git" in k for k in snap.documents)


def test_empty_directory_loads_an_empty_snapshot(tmp_path: Path) -> None:
    snap = load_directory(tmp_path, captured_at=T0)
    assert snap.documents == {}
    assert snap.snapshot_id


def test_undecodable_bytes_raise_rather_than_being_replaced(tmp_path: Path) -> None:
    """Silently substituting U+FFFD would change the content hash of that document and
    every anchor inside it, with no error anywhere. Fail loudly instead."""
    (tmp_path / "bad.md").write_bytes(b"# A\n\n\xff\xfe not utf-8\n")
    with pytest.raises(UnicodeDecodeError):
        load_directory(tmp_path, captured_at=T0)


def test_captured_at_is_injectable(tmp_path: Path) -> None:
    snap = load_directory(_corpus(tmp_path), captured_at=T0)
    assert snap.captured_at == T0


def test_normalizer_version_is_stamped(tmp_path: Path) -> None:
    snap = load_directory(_corpus(tmp_path), captured_at=T0)
    assert snap.normalizer_version == NORMALIZER_VERSION
    assert snap.loader_versions == {MARKDOWN_LOADER: MARKDOWN_LOADER_VERSION}


# --------------------------------------------------------------------------- #
# snapshot_id
# --------------------------------------------------------------------------- #


def test_snapshot_id_is_deterministic(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    assert load_directory(root, captured_at=T0).snapshot_id == (
        load_directory(root, captured_at=T0).snapshot_id
    )


def test_snapshot_id_ignores_capture_time(tmp_path: Path) -> None:
    """Two captures of an unchanged corpus are the same snapshot, whenever they happened."""
    root = _corpus(tmp_path)
    later = datetime(2027, 6, 1, tzinfo=UTC)
    assert (
        load_directory(root, captured_at=T0).snapshot_id
        == load_directory(root, captured_at=later).snapshot_id
    )


def test_snapshot_id_changes_when_content_changes(tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    before = load_directory(root, captured_at=T0).snapshot_id
    (root / "spec.md").write_text("# A\n\nalpha edited\n", encoding="utf-8")
    assert load_directory(root, captured_at=T0).snapshot_id != before


def test_snapshot_id_changes_when_a_document_moves(tmp_path: Path) -> None:
    """doc_key is part of the snapshot's identity even though it is not a document's."""
    root = _corpus(tmp_path)
    before = load_directory(root, captured_at=T0).snapshot_id
    (root / "spec.md").rename(root / "renamed.md")
    assert load_directory(root, captured_at=T0).snapshot_id != before


def test_snapshot_id_binds_the_normalizer_version(tmp_path: Path) -> None:
    """Invariant 3: a normalizer change invalidates every anchor, so it is a different
    snapshot even if the bytes on disk are identical."""
    snap = load_directory(_corpus(tmp_path), captured_at=T0)
    assert snapshot_id_for(snap.documents, "9.9.9") != snap.snapshot_id


# --------------------------------------------------------------------------- #
# Round trip with the anchor cascade
# --------------------------------------------------------------------------- #


def test_anchors_captured_through_the_loader_resolve(tmp_path: Path) -> None:
    """The loader's output must be usable by the cascade unchanged."""
    from corpora.anchors.resolve import capture, resolve
    from corpora.models import Resolution

    (tmp_path / "s.md").write_text(
        "# 1 Top\n\n## 1.1 Inner\n\nThe limit is 12 volts.\n", encoding="utf-8"
    )
    v1 = load_directory(tmp_path, captured_at=T0)
    anchor = capture(v1.documents["s.md"], "The limit is 12 volts.", v1.snapshot_id)
    assert anchor.heading_path == ["1 Top", "1.1 Inner"]

    assert resolve(anchor, v1).resolution is Resolution.VALID

    (tmp_path / "s.md").write_text(
        "# 1 Top\n\n## 1.1 Inner\n\nThe limit is 19 volts.\n", encoding="utf-8"
    )
    v2 = load_directory(tmp_path, captured_at=T0)
    result = resolve(anchor, v2)
    assert result.resolution is Resolution.STALE
    assert any("19 volts" in s for s in result.candidate_spans)


def test_build_snapshot_accepts_documents_directly(tmp_path: Path) -> None:
    """The in-memory path tests/conftest.py uses, so fixtures and the real loader cannot
    drift apart."""
    docs = {"a.md": load_markdown("a.md", "# A\n\nbody\n")}
    snap = build_snapshot(docs, source="memory://", captured_at=T0)
    assert snap.documents["a.md"].normalized_text == "# A\n\nbody"
    assert snap.snapshot_id == snapshot_id_for(docs, NORMALIZER_VERSION)
