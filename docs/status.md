# Status

Update at the end of each working session. This is the bridge to the strategy side —
short, factual, no narrative.

## Current phase
Phase 1 — anchors + diff.

## Done
- Domain model (nine nouns)
- Versioned normalizer, with technical-identifier handling. Tests green.
- Mutation harness: 13 mutations with known ground-truth classifications.
- Anchor capture.

## In progress
- `anchors/resolve()` — the cascade. 18 tests red.

## Blocked
- nothing

## Decisions needing a strategy call
- none

## Open questions
- Does context-only match ever warrant auto-repair, or always STALE? Currently always STALE.
