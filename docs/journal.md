# Journal

Accumulated history: what was built, what broke, and why each decision went the way it did.
Append-only in spirit — nothing here is pruned to stay short.

**This is not the bridge.** `docs/status.md` is, and it is the one to read first. This file
exists so that status.md can stay at ninety seconds without losing the record, which is the
failure it drifted into over three sessions before being split.

## Where things stand

**Phase 1 is complete and the study is pre-registered.** Anchors, policy, corpus loader,
`diff/`, and a protocol committed before any anchor is resolved. 107 tests green,
`mypy --strict` clean, `ruff` clean across `src` `scripts` `tests`, eight deterministic
invariants holding.

## The remaining path

```
run the study once  ->  write it up
```

Two items. Nothing else is on it.

## Blocked

Nothing on the critical path. `ANTHROPIC_API_KEY` is still unset, which only affects the
parked agent loop — the CI reviewer fails loudly rather than reporting a false green, which
is the correct behaviour while it has nothing to run with.

## This session: the study protocol

`docs/study-protocol.md`, committed **2026-09-16, before any pair was sampled**. Git's
timestamp is the evidence; "we sampled without curation" is unfalsifiable from outside
without it.

**A firewall, enforced not promised.** `scripts/study_feasibility.py` may confirm the design
can detect an effect and may not look at the effect — the line a power analysis draws. It
does not import `corpora.anchors` or `corpora.diff` and does not need to, since stratum
assignment is a function of span text alone. `check_invariants.py` (`study_firewall`)
enforces it, negative-tested in both directions.

**Feasibility, run pre-registration:**

| | result |
|---|---|
| population | 10,611 commits touching `content/en/docs` since 2021-01-01 |
| cohorts | 21, one per calendar quarter, 2021Q1–2026Q1 |
| realised N | 1050 / 1050 — every cohort reached its full 50 |
| censoring | 0% at +7..+180d, 14.3% at +365d |
| strata | `prose` 57.4%, `identifier` 24.1%, `numeric` 18.5% |
| churn covariate | 606 commits/90d (2021Q1) → 295 (2026Q1) |

**Amended pre-run (ADR-0017): cohort starts stratified over calendar quarters.** The
headline is a calendar-time half-life and the frame was commit-space. Reporting in one unit
while sampling in another is the defect — the ADR-0012 unit decision, one layer down.
Uniform-over-commits weights cohorts by churn; activity fell ~2x from 2022 to 2025, so the
high-churn era was over-represented, biasing the headline toward **more** staleness. The
superseded draw also put **zero cohorts in 2026**, while the claim is about how documentation
decays *now*.

The amendment passes the test that separates a legitimate protocol edit from a self-serving
one: **the direction was predictable before running it, and it goes against us.** Cost: N
1200 → 1050, censoring at +365d 4.2% → 14.3% — paid in precision, not bias. New seed 20260917;
the superseded draw's output is retained for inspection.

**Pre-committed before the numbers existed:** sampling stays uniform whatever the strata turn
out to be (no oversampling a thin stratum); the span floor and eligibility rules are frozen
and may move only on bias grounds, never on yield; and a long median is priced now — if it
lands near two years the staleness wedge is weak, the product falls back to the accept gate,
and **that result gets published anyway**.

## What Phase 1 shipped

| | |
|---|---|
| `anchors/resolve.py` | the cascade; 15/15 mutation rows classify correctly |
| `anchors/policy.py` | observation/action split; `RETIRE` unreachable from one resolution |
| `corpus/loaders/markdown.py`, `corpus/snapshot.py` | real loader; snapshot construction out of test code |
| `diff/snapshots.py` | set-diff plus the compatibility guard |
| `diff/build.py` | `Diff` assembly; three traps closed |
| `scripts/check_invariants.py` | eight checks, ~2s, zero tokens, each negative-tested |

## The five false greens — the study's opening paragraph

Not a confession. The argument.

1. `normalizer_versioned` was line-based, so `make invariants` went blind on uncommitted work
2. a negative test passed when it should have failed — which is how #1 was found
3. a test asserted nothing and passed green, in the directory that holds the verifier
4. the CI reviewer reported green having skipped — no API key, and the action's own refusal
   to run when `pr.yml` differs from `main`: a guardrail that switches itself off in exactly
   the PR that modifies it
5. **92 tests passing over a loader that corrupted `heading_path` for every heading below a
   stray `#`**

The fifth makes the case. A full green suite, `mypy --strict`, ruff across `src` and `tests`,
deterministic invariants — and the money case was still silently routed from `STALE` to
`DESTROYED` by one character in a regex, because no fixture contained an empty heading.

That is the product thesis demonstrated on ourselves, with a diff and a classification flip,
before any customer data exists. *Your tests are green and your answer key is wrong.*

All five are the same shape: **a check that failed to fail.**

**And the honest asymmetry:** most were caught by the deterministic gate, one by an
adversarial review *of* that gate, one by a human reading an issue and disagreeing with its
framing. A gate catches what you thought to encode; it cannot catch what you didn't. The
residue needs a different method, and some of it needs a person. That is the argument for a
human accept gate in the product, from our own experience rather than a citation.

**Three self-serving parameters caught before shipping**, each invisible from inside the
result and each moving the number in our favour: a span floor that dropped short technical
sentences, an oversampling temptation, and a sampling frame in the wrong unit. That is the
argument that a pre-registered protocol is the mechanism, not the ceremony.

## Decisions (ADRs 0005–0017)

- **0007** enum names must be literally true — `VALID_MOVED` fired when nothing moved
- **0008** observation split from action; retirement never automatic, never from one observation
- **0009** the study is a rate, not the 13 rows; it runs before phase 3
- **0010** `doc_key` is a locator, not identity
- **0012** headline unit is calendar time; releases secondary, commits raw
- **0013**, **0015** loader boundaries; fenced code and the `\s` heading defect
- **0014** `tests/` is linted in CI — a false-green verifier lived in the verifier's directory
- **0016** heading paths resolve by suffix, not full ancestry; the leaf is the address
- **0017** cohort starts stratified over calendar quarters

## Loop: parked

The stopping rule is answered. #1, #2 and #3 were written by hand and are green; the loop
produced zero lines and never executed. Infrastructure stays committed and dormant —
`make invariants` runs regardless and has earned its place five times. The agent loop
specifically solves a throughput problem that does not exist here: one serial critical path,
one reviewer. Revisit with a cofounder, or when the work is genuinely parallel.

## Decisions needing a strategy call

None outstanding.

## Open questions

- **"Run once" is load-bearing.** M is now set by quarter count, so the frame self-adjusts —
  a run in 2027 would have 25 quarters and a different N. That is correct behaviour, and it
  means a second run is a *new* protocol with its own registration, not a re-run of this one.
- `RetirementPolicy` thresholds remain unmeasured placeholders. The study's `DESTROYED`
  recovery rate is the empirical basis that should replace them.
- `enforce_admins` is `false` because a sole code owner cannot approve their own PR. Flip it
  the day a second reviewer exists (recorded in ADR-0011).
