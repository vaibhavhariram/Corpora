# ADR-0001: Evidence identity is content-addressed, never positional

**Status:** accepted

## Decision
An `Anchor` identifies evidence by a hash of its normalized text, plus heading path and a
context hash. Character position is recorded but is never identity.

## Why
The system this design comes from identified evidence by `split_id`, a positional chunk
index. Inserting a paragraph near the top of a document shifted every downstream
`split_id`, silently repointing every test built on it. That system carried a dedicated
audit script whose job was checking whether expected chunks still existed — a patch on a
broken identity model. (How often they did not still exist is inferred rather than
confirmed; see the next section.)

Positional identity makes staleness detection impossible: you cannot distinguish "the
document was edited above this" from "this answer changed" when both look like a shifted
index.

## What is observed, and what is inferred

Stated precisely, because this ADR is the foundation the product rests on and a product
whose pitch is "we catch the small lie your dashboard is telling" cannot cite an inference
as a fact in its own decision record.

**Logically certain, independent of any system.** If identity is "chunk 47", inserting a
paragraph above chunk 47 changes what chunk 47 contains. That is definitional. The decision
below rests on this and needs no field evidence.

**Observed.** A `corpus_audit.py` existed whose job was checking whether expected chunks
still resolved. A stale-prune shipped. A re-index carried an explicit warning.

**Inferred, not confirmed.** That expected chunks "routinely did not" still exist, and that
`split_id` is unstable across re-indexing. Both were reasoned from the four signals above —
an audit script existing implies something it was auditing for — not from a measurement or
a statement by anyone who ran that system.

The distinction matters in one direction only. The design does not change if the inference
is wrong: content-addressing is still correct, because the insert-a-paragraph case is
logical rather than empirical. What changes is how the motivating story may be told. "Their
chunk IDs churned in production" is not ours to claim until someone who maintained that
system confirms it; "positional identity cannot survive an edit above it" always is.

**The question that settles it:** is `split_id` stable across a re-index? One person can
answer that in ten seconds. Until they do, treat the churn claim as an assumption of this
repository rather than a finding.

## Rejected
- Chunk IDs from the target system's own indexer — not stable, and couples us to one target.
- Line numbers — break on reflow, reformat, and any conversion.
- XPath / heading path alone — breaks when a section is renamed, which is common.

## Reverses if
Someone demonstrates a content-addressing scheme that is both stable and cheaper. Note that
"cheaper" is not sufficient; stability is the requirement.
