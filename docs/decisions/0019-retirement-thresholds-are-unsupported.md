# ADR-0019: The retirement thresholds are unsupported, and say so

**Status:** accepted
**Amends:** ADR-0008's provisional numbers, now that the study has measured the quantity
they were waiting on

## Decision
`RetirementPolicy` keeps its defaults — 3 consecutive `DESTROYED` observations spanning at
least 14 days — but they are no longer described as placeholders awaiting the study. The
study has run. It measured the thing, and **it does not support the argument the defaults
were built on.**

The docstring now says that, rather than continuing to promise tuning that has already
happened.

## What the study measured
Of 36 anchors ever observed `DESTROYED` across 1012 anchors and 7200 observations,
**one** later resolved again. A 2.8% recovery rate on n = 36.

ADR-0008 justified never retiring on a single observation like this:

> Sections get emptied in one commit and refilled in the next; a model that retires on one
> `DESTROYED` deletes coverage for a transient state.

That mechanism is real — it happened once — but it is rare in this corpus, not routine. The
empirical case was overstated. On frequency alone, hysteresis buys little.

## Why the policy does not change
The decision was always resting on two legs and only one of them moved.

**Frequency** (weakened): transient `DESTROYED` is uncommon, at least here.

**Cost asymmetry** (unchanged): retiring a test wrongly removes coverage permanently and
tells nobody. Carrying a genuinely dead test for another observation cycle costs one line in
a report. Those are not comparable, and the asymmetry does not depend on how often the
mistake would occur — it depends on the mistake being invisible and unrecoverable when it
does.

So the conservative defaults stay, and invariant 7 stays. What changes is the story told
about them: this is a decision made on cost asymmetry, not on a measured recovery rate, and
the measured recovery rate is 1 in 36.

## Why not tune the numbers to the data
Because n = 36 on one corpus, and because tuning a safety threshold downward on the strength
of a single small sample is how a conservative default quietly becomes an aggressive one.
The direction the data points — "you could be less patient" — is also the direction that
would make the product delete more of a customer's coverage. That asymmetry is a reason to
leave it alone, not a reason to act.

If a corpus ever shows a high transient-`DESTROYED` rate, that is an argument for *more*
patience, and it can be made on its own evidence.

## Rejected
- **Quietly stop mentioning the recovery rate.** The argument was made in writing; the number
  that undercuts it should be too.
- **Lower the thresholds to match 2.8%.** See above.
- **Remove hysteresis entirely.** Frequency was never the load-bearing leg.

## Reverses if
A corpus shows transient `DESTROYED` at a rate high enough that the current thresholds retire
live tests. The symptom is a retirement proposal for an anchor that resolves again shortly
after — watch for it wherever the policy is first used against real history.
