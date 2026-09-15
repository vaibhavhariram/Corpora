# ADR-0001: Evidence identity is content-addressed, never positional

**Status:** accepted

## Decision
An `Anchor` identifies evidence by a hash of its normalized text, plus heading path and a
context hash. Character position is recorded but is never identity.

## Why
The system this design comes from identified evidence by `split_id`, a positional chunk
index. Inserting a paragraph near the top of a document shifted every downstream
`split_id`, silently repointing every test built on it. That system needed a dedicated
audit script to check whether expected chunks still existed, because they routinely did
not — a patch on a broken identity model.

Positional identity makes staleness detection impossible: you cannot distinguish "the
document was edited above this" from "this answer changed" when both look like a shifted
index.

## Rejected
- Chunk IDs from the target system's own indexer — not stable, and couples us to one target.
- Line numbers — break on reflow, reformat, and any conversion.
- XPath / heading path alone — breaks when a section is renamed, which is common.

## Reverses if
Someone demonstrates a content-addressing scheme that is both stable and cheaper. Note that
"cheaper" is not sufficient; stability is the requirement.
