# ADR-0003: One normalizer, versioned, stamped into every snapshot

**Status:** accepted

## Decision
All text passes through `corpus.normalize.normalize()`. `NORMALIZER_VERSION` is recorded on
every `Snapshot`. Changing the normalizer is a breaking change requiring a version bump.

## Why
On the prior system, query-side and index-side text were normalized differently. The same
token was stored one way and looked up another. Production queries returned literally
nothing: technical identifiers like `SLP_A_VAL=0`, `be=0`, `F:PCH_SOC_SYNC`, plus Unicode
dash variants, broke tokenization before retrieval ran. The remediation was correctly
described internally as a vocabulary migration requiring reindexing.

Anchors hash normalized text. If normalization changes, every anchor's `span_hash` changes,
and every benchmark silently becomes invalid. Versioning makes that detectable instead of
silent.

## Constraints the normalizer must honor
- Case is preserved. `SLP_A_VAL` != `slp_a_val`.
- Technical identifiers are never split, spaced, or re-cased.
- Dash, space, and quote variants collapse to ASCII.

## Reverses if
Nothing. The version may increment; the single-normalizer rule does not change.
