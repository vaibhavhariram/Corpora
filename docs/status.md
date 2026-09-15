# Status

Update at the end of each working session. This is the bridge to the strategy side —
short, factual, no narrative.

## Current phase
Phase 1 — anchors. Complete. `diff/` is next.

## Done
- Domain model. Now split: `Resolution` observes, `Action` decides (ADR-0008).
- Versioned normalizer, with technical-identifier handling.
- Anchor capture.
- **`anchors/resolve()` — the cascade.** 13/13 mutation rows classify correctly. The two
  decisive rows verified the right way round: `change_number_in_answer` → `STALE`
  (reporting "18 milliseconds" as what the text says now), `insert_paragraph_above` →
  `VALID_REPAIRED` (span shifts 271 → 320, repaired silently, never flagged).
- **`anchors/policy.py`** — the observation/action seam. `Action.RETIRE` is structurally
  unreachable from a single resolution.
- 39/39 green, `mypy --strict` clean, `ruff` clean across `src/corpora/anchors` and the
  new tests.

## In progress
- nothing. Next is `diff/`: snapshot → snapshot → affected anchors → affected tests.
  Generic snapshot diffing first, Git layer after.

## Blocked
- nothing

## Both strategy calls landed

**1. Enum renamed (ADR-0007).** `VALID_MOVED` → `VALID_REPAIRED`. The name was false:
the widened bucket fires for `reword_neighbor`, where the span sits at offset 271 before
and after the edit. Nothing moved. Renamed before `diff/` and before the enum reaches
report rendering. The constraint is now written down for future members — each name must
be literally true of every case that reaches it.

Cost: this required touching `tests/test_anchors.py`, against the standing rule. One
identifier, no semantics — same assertion, same mutation, same outcome. An enum alias
would have kept the suite untouched and left the false name in the codebase, which is the
thing being fixed.

**2. Observation split from action (ADR-0008), and retirement defanged.** `resolve()`
returns an observation and cannot cause a retirement. `DESTROYED` maps to `WATCH`: record
it, carry the test forward unchanged. Retirement needs a sustained run of `DESTROYED`
over time *plus* a named human — `may_retire(..., confirmed_by=...)`, where neither half
alone is sufficient. Recorded as invariant 7.

The refill case is pinned by a test: emptied in one commit, refilled in the next, run
resets, nothing retires. Hysteresis defaults (3 observations spanning 14 days) are
**placeholders, not measurements** — they get tuned from the k8s churn data and are not to
be quoted to a customer as tuned.

This dissolved the emptied-heading open question rather than answering it. It only
mattered because `DESTROYED` retired things.

## The study is a rate, not the 13 rows (ADR-0009)
Correcting a conflation in the last status note.

- **13 synthetic mutations = a unit test.** Proves the cascade classifies correctly when a
  document changes in way X. Necessary. Not saleable — we authored both the corpus and the
  edits, so "you graded your own homework" is a fair reply.
- **The study = the rate.** Across real commits to a real corpus, what fraction of anchors
  go stale within K revisions, and the distribution of how fast. "Your golden set has a
  half-life, and here it is."

**Phase 2 is half done.** Synthetic half: complete. Real half: not started, and it is the
half that goes in an email to Brandon.

## Build order revised (ADR-0009)
`diff/` → **k8s study** → phase 3. Not straight to targets/runner/metrics.

The study needs only corpus loader + anchors + diff + Git history — no generation, no
targets, no metrics, no LLM. Shortest path from working code to an artifact that gets
replies, and it stress-tests the cascade against churn we did not author.

That second reason is doing real work. Every Phase 1 bug so far came from fixtures we
wrote, and three were wrong *because* we wrote them by reasoning instead of running. Real
history is the only source available that cannot reproduce our own mental model back to us.

Method constraint, recorded in CLAUDE.md and ADR-0009: **capture at commit A, resolve at
commit B, neither chosen for convenience.** Random or exhaustive sampling across history.
Hand-picked pairs make it a demo, and the sampling method has to be stated in the writeup —
a reader who suspects curation discounts the whole number and cannot tell from outside.

## Decisions needing a strategy call
- none outstanding.

## Open questions
- `RetirementPolicy` thresholds are unmeasured placeholders. First real output of the k8s
  study should be the distribution that replaces them.
- The study needs a defined unit for "K revisions" — commits touching the corpus, calendar
  time, or releases. Commits are easiest; releases are probably what a customer actually
  experiences. Worth deciding before the run, since it shapes the headline number.
- Four pre-existing `ruff` findings remain in scaffold files (import ordering in
  `models.py` and `test_anchors.py`, `Callable` import in `mutations.py`, `datetime.UTC`
  in `conftest.py`). Cosmetic, untouched, not worth a commit of their own.
