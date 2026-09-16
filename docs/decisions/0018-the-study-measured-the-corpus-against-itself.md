# ADR-0018: The runner compared every snapshot to itself, and nothing caught it

**Status:** accepted
**Scope:** `scripts/study_run.py`, found and fixed before any result was published

## What happened
The first execution of the study produced this:

```
{'valid': 2436, 'ambiguous': 364}          <- zero stale, across 2800 observations
observations where later_sha == cohort_sha: 2800/2800
```

Every "later" snapshot was the cohort's own snapshot. The study measured the corpus against
itself and would have reported, with a clean survival curve and a plausible-looking
per-stratum breakdown, that **documentation never goes stale.**

## Cause
`git log` walks `HEAD` unless given an explicit ref. The runner checks out each cohort's
commit with `--detach` before loading its snapshot, so by the time it asked for "the newest
commit at or before cohort_start + 90 days", `HEAD` was the cohort commit — and `git log`
only walks *ancestors*. The newest ancestor at or before a later date is the cohort commit
itself.

One missing argument. Every downstream number followed from it correctly.

## Why this is the most dangerous defect in the project so far
The previous five false greens produced a wrong classification, a silent skip, or a test
that verified nothing. This one produced **a complete, internally consistent, publishable
result that was entirely an artifact.** It had:

- a full survival curve
- a per-stratum breakdown
- a sensible-looking resolution mix (87% `valid`, 13% `ambiguous`)
- 2800 observations, no errors, no warnings

Nothing about the output said "broken". The only tell was that `stale` was absent — and a
zero would have been reported as the finding, not as a bug. Under the pre-committed
interpretation in protocol section 10, "median not reached" is a legitimate outcome that
gets published. This would have walked straight through that door.

## What caught it, and what did not
**Not** the test suite: 107 tests green throughout, and none of them exercise the runner
against real git history.
**Not** `make invariants`: eight checks, all passing, none of which model snapshot selection.
**Not** the type checker, the linter, or the adversarial review.

What caught it was a **disagreement between two independent computations of the same
quantity.** The runner printed `churn=0` for 2021Q2; the pre-registered feasibility check had
independently measured 518 for that quarter. Two numbers that should have matched did not,
and the churn covariate — which is not part of the headline and exists only as a reporting
nicety — was the thread that unravelled it.

That is a fourth verification method, distinct from the three already recorded:

| method | what it caught |
|---|---|
| deterministic gate | invariants, normalizer versioning, verifier edits |
| adversarial review of the gate | the `\s` heading-regex defect |
| a human reading an issue | the cascade's ancestry semantics (ADR-0016) |
| **redundant independent computation** | **this** |

A gate catches what you thought to encode. A review catches what you thought to look for.
Only a second, independently written computation of the same number catches the case where
your single implementation is confidently and consistently wrong — because there is nothing
to compare against inside one implementation.

**This belongs in the writeup.** It is the strongest available evidence for the product's own
thesis: a green suite, a strict type checker, a lint pass, seven invariants, and an
adversarial review, and the headline number was still an artifact. Not because anyone was
careless, but because *no check existed that could observe the thing that was wrong*.

## The fix
1. Every `git log` call takes an explicit ref, captured before the first checkout.
2. Checkouts are `--force` and preceded by `git clean -qfd`, because a killed run leaves a
   mixed tree that silently blocks later checkouts.
3. **A guard that raises.** If any offset resolves to the cohort's own base commit, the
   runner aborts:

   > `cohort N offset +Md resolved to its own base commit <sha> — snapshot selection is broken`

The guard is the durable part. Documenting "remember to pass a ref" would have been worth
nothing; the codebase now cannot record a self-comparison even if the ref handling regresses
again. Consistent with every other guard here: make the check fail, do not write down that it
should not happen.

## Verified
After the fix, on the first two cohorts: churn reads 606 and 518, matching the feasibility
check exactly, and **0 / 700** observations are self-comparisons. The resolution mix becomes
`valid` 393, `valid_repaired` 142, `ambiguous` 113, `stale` 30, `destroyed` 20,
`valid_relocated` 2 — six distinct outcomes where there had been two.

## Reverses if
Nothing. The guard stays regardless of how snapshot selection is implemented later.
