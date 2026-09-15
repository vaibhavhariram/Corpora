# ADR-0013: What the Markdown loader does, and what it deliberately does not

**Status:** accepted

## Context
`parse_headings` and `build_snapshot` lived in `tests/conftest.py` — the only
snapshot-construction code in the repository was test code. This ADR records the decisions
made moving them into `src/corpora/corpus/`.

## Decisions

### Fenced code blocks are excluded before headings are matched
The fixture parser matched `^#{1,6}\s+(.+)$` against the whole document. On the fixture
corpus that is fine, because it contains no code fences. On the study corpus it is not:

```
# Pods                     -> heading        (correct)
```bash
# Create a pod             -> heading        (WRONG — it is a shell comment)
# Delete it again          -> heading        (WRONG)
```
## Pod lifecycle           -> path ["Delete it again", "Pod lifecycle"]   (WRONG ancestry)
```

Two kinds of damage, and the second is worse. Invented headings are noise; a corrupted
ancestry silently changes `heading_path` on a *real* heading, and `heading_path` resolution
is exactly what separates `STALE` from `DESTROYED`. Kubernetes documentation is dense with
shell and YAML blocks, so this would have moved the study's headline numbers in a way no
test would have caught — the fixture corpus has no fences, so every existing test passed.

Caught by running the parser against realistic input rather than by reading it. That is the
third time this project has found a defect that way and the second time the defect was
invisible to a green suite.

Handled: backtick and tilde fences, openers of any length ≥3, up to three spaces of indent,
info strings, and a closing fence that must match the opener's character and be at least as
long. An unclosed fence runs to end of document — the conservative reading, since the
alternative is to resume finding headings inside code. A fenced block stays inside the
enclosing heading's body range, because it is content.

### Setext headings are not supported
`Title\n=====` is not recognised. Known gap, not an oversight. Kubernetes documentation is
ATX throughout, and adding Setext support later changes heading offsets, which is a
`MARKDOWN_LOADER_VERSION` bump rather than a bug fix.

### `snapshot_id` is content, not capture time
SHA-256 over each `doc_key` and its `content_hash` in sorted order, plus
`NORMALIZER_VERSION`.

- **Excludes `captured_at`.** Two captures of an unchanged corpus are the same snapshot
  whenever they happened. Including the clock would mean re-running the loader invalidates a
  frozen benchmark.
- **Includes `doc_key`.** Moving a file changes the snapshot even though it does not change
  any document (ADR-0010). The corpus is genuinely different.
- **Includes the normalizer version.** Invariant 3 makes it part of what a snapshot *means*:
  the same bytes under a different normalizer produce different anchors, so they are a
  different snapshot.

### Undecodable bytes raise
`encoding="utf-8"` with default strict errors. `errors="replace"` would substitute U+FFFD,
changing that document's content hash and every anchor inside it, with no error anywhere.
A silently wrong answer that looks healthy is the failure this product exists to catch; we
do not get to ship one.

The cost is that a single malformed file aborts a whole snapshot. Accepted for now. If real
corpora turn out to contain such files routinely, the fix is to report them as a per-document
load failure carried on the `Snapshot`, not to paper over the bytes.

### Dot-prefixed paths and symlinks are skipped
Walking a documentation repository means walking `.git`. Symlinks otherwise yield the same
content under two `doc_key`s — which would show up as a spurious `AMBIGUOUS` — or cycles.

### `MARKDOWN_LOADER_VERSION` names this parser
`"builtin-markdown-1.0.0"`, not a third-party version, because there is no third party.
Anchors are only valid within a loader version and `heading_path` resolution depends on how
this file assigns ranges and ancestry, so a behavioural change here needs a bump and an ADR
for the same reason `NORMALIZER_VERSION` does.

### `tests/conftest.py` delegates instead of reimplementing
It now calls the real loader and keeps only the fixture affordance of a caller-supplied
`snapshot_id`. The previous arrangement — an independent reimplementation in test code — is
precisely how `doc_key = filesystem path` survived in the fixtures while `models.py`
asserted the opposite (ADR-0010). A fixture that reimplements the thing under test can agree
with itself indefinitely while disagreeing with production.

## Rejected
- **A Markdown library.** Adding a dependency to parse six characters is scope creep, and
  `dependency_allowlist` would rightly have blocked it. We need offsets into normalized
  text, which most libraries do not expose.
- **Nesting heading ranges so a parent encloses its children.** `heading_path_at` picks the
  deepest heading containing a position; flat ranges make that unambiguous. Nesting would
  make the level tiebreak do the real work and is a larger change to resolution than it
  looks.
- **Computing `snapshot_id` over raw bytes.** Would make a snapshot's identity depend on
  line endings, which the normalizer exists to erase.

## Reverses if
A corpus needs Setext headings, or per-document load failures turn out to be common enough
that aborting a snapshot is worse than reporting them. Both are additive; neither changes
what is recorded here.
