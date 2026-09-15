# ADR-0008: `resolve()` observes, policy decides; retirement is never automatic

**Status:** accepted
**Amends:** ADR-0005 (dissolves its open question about emptied headings)

## Decision
Split the model in two.

- **`Resolution`** is an observation. It says what re-resolution found, and nothing about
  what to do. `resolve()` returns only this.
- **`Action`** is a decision, produced by `anchors/policy.py`. `action_for()` maps a single
  resolution to the action it warrants on its own.
- **`Action.RETIRE` is unreachable from `action_for()`.** Retirement requires
  `should_propose_retirement()` over an anchor's history *plus* a named human via
  `may_retire(..., confirmed_by=...)`. Neither half is sufficient alone.

Default mapping: `VALID`→`NONE`, `VALID_REPAIRED`→`REPAIR`, `VALID_RELOCATED`→
`REPAIR_AND_NOTE`, `STALE`/`AMBIGUOUS`→`REVIEW`, `DESTROYED`→`WATCH`.

Recorded as invariant 7 in CLAUDE.md.

## Why
The six outcomes were a mix of observations and implied actions, and the implied actions
are not equally reversible:

| action  | cost of being wrong                                          | reversible |
|---------|--------------------------------------------------------------|------------|
| repair  | an anchor points at the right text via a different route      | yes, silently |
| review  | someone spends ten minutes confirming nothing was wrong       | yes |
| retire  | a test leaves the customer's coverage, and nobody is told     | **no** |

Retirement is the only one where being wrong costs the customer something they cannot get
back, and it is the only one that is invisible after the fact — a shrinking benchmark looks
exactly like a benchmark that was always that size. Inferring it from a single observation
was the model's most dangerous property, and it was load-bearing in exactly the wrong
direction: `DESTROYED` meant "retire the test" in the enum's own docstring.

The refill case makes it concrete. A section emptied in one commit and refilled in the next
produces one `DESTROYED` observation. Under the old model that is a permanent retirement
for a transient state. Under the new one it is a `WATCH`, the next resolution finds the
span, and the run resets. `tests/test_policy.py::test_refill_resets_the_clock` pins this.

This also dissolves ADR-0005's open question rather than answering it. Whether an
emptied-but-surviving heading is `DESTROYED` or `STALE` mattered only because `DESTROYED`
triggered retirement. It is `DESTROYED` — a correct observation, since nothing resolved —
and it now costs nobody a test.

Keeping the two concepts separate also means a change in patience (how many observations,
over how long, before retirement is proposed) cannot be mistaken for a change in what the
cascade observed. The hysteresis thresholds will be tuned from the Kubernetes churn data;
the observations they are computed from will not move when they are.

## Provisional, and marked as such
`RetirementPolicy` defaults — 3 consecutive `DESTROYED` spanning at least 14 days — are
placeholders, not measurements. The real distribution of how long a section stays missing
before it returns comes out of the Kubernetes study. They are not to be quoted to a
customer as tuned.

## Rejected
- **`DESTROYED` → `REVIEW`.** Puts every missing anchor in front of a human immediately,
  spending the scarce resource on absences that resolve themselves. It also breaks
  `test_only_stale_and_ambiguous_need_review`, which pins the review queue to the two
  outcomes that genuinely block a valid measurement.
- **An `action` field on `ResolutionResult`.** Re-couples the two concepts on the object
  that crosses every module boundary, and makes a policy change look like a resolution
  change in every stored result.
- **A `Retirement` noun in the model.** CLAUDE.md caps v1 at nine nouns. Policy functions
  take plain `(datetime, Resolution)` history instead.

## Reverses if
Nothing reverses the split. The thresholds change once the study produces real numbers —
that is expected, and is the reason they live in a dataclass rather than in the cascade.
