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
- **`anchors/resolve()` — the cascade. Implemented. 26/26 green, 13/13 mutation rows
  classify correctly.** `mypy --strict` clean. `tests/test_anchors.py` unmodified.
  The two decisive rows verified explicitly and the right way round:
  `change_number_in_answer` → `STALE` (reports "18 milliseconds" as what the text says
  now), `insert_paragraph_above` → `VALID_MOVED` (span shifts 271 → 320, repaired
  silently, never flagged).

## In progress
- nothing — Phase 1 resolution is complete. Next is `diff/`: snapshot → snapshot →
  affected anchors → affected tests. Generic snapshot diffing first, Git layer after.

## Blocked
- nothing

## Decisions needing a strategy call
- **Three of the thirteen mutation rows were not testing what the table claimed, and have
  been corrected (ADR-0006).** Two were provably unsatisfiable — they handed `resolve()` a
  signal vector identical to a row expecting a different answer, so no implementation could
  have separated them. The third never executed at all. Every `expected` classification is
  unchanged; the corpus and the edits changed so each row performs the mutation its own
  description claims.
  - `unicode_dash_swap` inserted a dash into a corpus that contained no hyphen, rather than
    swapping one. The normalizer cannot absorb an insertion, so the row contradicted both
    its own description and the architecture table.
  - `merge_documents` appended the second document *below* the anchor, so the span never
    moved — locally indistinguishable from `no_change`, while expecting `VALID_MOVED`.
  - `delete_section` had a precondition string that did not occur in the corpus, so the
    `DESTROYED` arm of the cascade had no coverage at all.

  Strategy relevance: the mutation table is the public-study artifact. Any staleness
  precision/recall number quoted before this commit covered 12 rows, one of them
  mislabeled. Nothing is published yet, so there is nothing to retract — but the corrected
  table is the one to quote from.

## Open questions
- ~~Does context-only match ever warrant auto-repair, or always STALE?~~ **Resolved:
  always STALE**, now implemented. A context-only match produces a *suggested correction*
  ordered first in `candidate_spans`, never an auto-repair. Verified reachable: a heading
  renamed out from under an anchor whose span was reworded resolves to `STALE` with the
  correct suggestion rather than `DESTROYED`.
- `VALID` now additionally requires a `context_hash` match, so a span sitting at its old
  offset inside edited surroundings reports `VALID_MOVED` (ADR-0005). Both are
  auto-repairable and neither costs review time, so this is free honesty — but it means
  `VALID` in a diff report means "nothing changed around this anchor," not merely "found
  it." Worth one line in customer-facing docs when they exist.
- An emptied-but-surviving heading resolves to `DESTROYED`, not `STALE` (ADR-0005).
  Revisit against real Git churn in the Kubernetes study: if sections are routinely emptied
  in one commit and refilled in the next, that is a transient state, not a retirement.
- Four pre-existing `ruff` findings remain in scaffold files (import ordering in
  `models.py` and `test_anchors.py`, `datetime.UTC` in `conftest.py`, `Callable` import in
  `mutations.py`). Left alone — one is in `test_anchors.py`, which is not to be modified.
  `src/corpora/anchors/resolve.py` is clean under both `ruff` and `mypy --strict`.
