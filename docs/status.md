# Status

The bridge. Ninety seconds, no diff required. History lives in `docs/journal.md`.

## Where things stand

**The study has run and the result is negative.** Phase 1 complete, protocol pre-registered
and honoured, 1050 anchors across 21 quarterly cohorts, 7200 observations. 107 tests green,
`mypy --strict` clean, `ruff` clean, eight invariants holding.

## The number

| horizon | 7d | 30d | 90d | 180d | 365d |
|---|---|---|---|---|---|
| answer span still correct | 0.997 | 0.981 | 0.965 | 0.941 | **0.901** |

**Median not reached.** ~10% of anchors go stale within a year. There is no half-life inside
the observable window, and **that sentence is retired** — it is not what 1012 anchors say.

**What the data does support:** at 90 days, **3.5% of a benchmark's answer keys are wrong
while the suite reports green.** That is a measurement-floor claim, not a decay claim: a
quarterly comparison of two-point changes is measuring the corpus as much as the system.
Weaker urgency, same buyer, and it is what the evidence actually carries.

Finding: *Kubernetes documentation* decays at ~10%/year. Hypothesis, unmeasured: that
regulated corpora behave the same. That corpus is 57% prose, community-reviewed, and has no
applicability dimension at all — no jurisdiction, no active/legacy window, no addenda
mid-project. The gap may be large, and it is exactly the escape hatch a pre-registration
exists to deny.

## Next

1. **Publish the writeup** (`docs/study/writeup.md`) — methodology-led, ADR-0018 as the lead.
2. **Five conversations, one question:** *when a source document changes, what downstream
   thing becomes wrong, and how do you currently find out?* This is the first point in the
   project where the next move requires talking to someone; everything before it was
   buildable alone. The answer decides whether a second study is worth pre-registering.

A second study is legitimate only if pre-registered, published regardless of outcome, and
chosen for a stated structural reason — not because it looks promising.

## The fork, stated plainly

Staleness detection is not the differentiator the teardown hoped for. What remains is the
accept gate: more contested, with real competitors closing. That is a worse position and is
worth holding as such rather than being talked out of.

**Do not decide the pivot this week.** The writeup is worth publishing either way, it is the
artifact that makes anyone reply, and two weeks of conversations will settle more than
reasoning can.

## Blocked

Nothing on the critical path. `ANTHROPIC_API_KEY` is unset, which only affects the parked
agent loop.

## Open

- **Second corpus**: only under pre-registration, and only after the interviews.
- **`RetirementPolicy` thresholds** (ADR-0019): now explicitly *unsupported* rather than
  provisional. The study measured 1-in-36 `DESTROYED` recovery, which weakens the frequency
  argument for hysteresis. Defaults stay on cost asymmetry.
- **Protocol §6 uniqueness gap**: reported as a sensitivity, not corrected — 9.9% → 9.8%,
  in our own favour. Recorded in the writeup.
- **"Run once" is load-bearing**: M is set by quarter count, so a later run has a different
  N. A second run is a new protocol with its own registration.
- `enforce_admins` is `false` while there is one code owner (ADR-0011).
