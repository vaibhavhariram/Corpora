# ADR-0010: `doc_key` is a locator, not identity

**Status:** accepted
**Amends:** the `Document.doc_key` docstring, which asserted the opposite

## Decision
`doc_key` is the normalized path of a document relative to the corpus root. It tells
resolution which document to search first. It is **not** identity and nothing in resolution
correctness may depend on it.

Identity is `Anchor.span_hash`.

## Why
`models.py` said "content-stable identity. NOT a filesystem path — paths move, documents
don't", and then `tests/conftest.py` set `doc_key = path`. One of the two was wrong. The
docstring was.

The cascade already does the right thing without any notion of stable document identity.
`_span_matches` searches the anchor's own document first and then every other document in
the snapshot. That is exactly why `move_section_to_other_file` resolves to
`VALID_RELOCATED` instead of `DESTROYED` — the `doc_key` misses, the search falls through,
and the span is found somewhere else. The behaviour we need from a renamed file already
exists:

| what happened | what resolves | correct? |
|---|---|---|
| file renamed, span unchanged | `doc_key` misses → found elsewhere → `VALID_RELOCATED` | yes |
| file renamed, span changed | nothing found → heading lookup → `STALE` | yes |
| file renamed and deleted | nothing found anywhere → `DESTROYED` | yes |

No git rename detection, no id mapping table, no persistent state. The only cost is
searching every document instead of one, which is what the cascade does anyway and is
irrelevant at any corpus size this product targets.

Treating `doc_key` as identity would have been actively worse: it would make a rename look
like a delete plus an add, which is the positional-identity failure (ADR-0001) wearing a
different hat.

## Consequence
Unblocks the corpus loader. There is no design question left to answer before moving
`build_snapshot` and `parse_headings` out of `tests/conftest.py` into `src/corpora/corpus/`.

## Rejected
- **Git rename detection.** Couples the generic snapshot engine to Git, which
  `docs/architecture.md` explicitly makes a convenience layer rather than a requirement.
  Also does not work at all for the sources that matter most — SharePoint exports, network
  drives, PDFs emailed by a standards body.
- **A content-hash document id.** A document whose content changes would change identity,
  so every edit would read as delete-plus-add. Strictly worse than the path.
- **A persisted path → id mapping.** State to maintain, migrate, and corrupt, bought
  nothing the cascade does not already do.

## Reverses if
A corpus turns up where the same span legitimately appears in many documents and the search
fallback produces `AMBIGUOUS` at a rate that drowns the signal. Then `doc_key` would need to
become a tiebreaker with real weight rather than a first-guess. Watch the `AMBIGUOUS` rate in
the Kubernetes study; it is the measurement that would show this.
