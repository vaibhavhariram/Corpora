# ADR-0017: Cohort starts are stratified over calendar quarters

**Status:** accepted
**Amends:** `docs/study-protocol.md` section 4, **pre-run**, before any anchor was resolved

## Decision
One cohort start per calendar quarter, drawn uniformly at random from the commits in that
quarter, for every quarter from 2021Q1 through the last quarter containing a commit on or
before the cutoff. M becomes the number of eligible quarters (21) rather than a fixed 24.

Superseded: 24 cohort starts drawn uniformly over the commit population.

## The defect
The headline is a calendar-time half-life (ADR-0012). The sampling frame was commit-space.
**Reporting in one unit while sampling in another is the defect** — the same error class as
the study-unit decision, one layer down. ADR-0012 chose calendar time because it transfers
to a buyer, and then the frame underneath it stayed where it was.

Uniform-over-commits weights cohorts by churn, and churn on this corpus is not flat:

| year | commits touching the corpus | cohorts drawn | expected |
|---|---|---|---|
| 2021 | 2222 | 9 | 5.0 |
| 2022 | 2695 | 7 | 6.1 |
| 2023 | 2278 | 4 | 5.2 |
| 2024 | 1697 | 3 | 3.8 |
| 2025 | 1437 | 1 | 3.3 |
| 2026 | 282 | **0** | 0.6 |

Three reasons this is fixed rather than footnoted:

1. **The bias is self-serving and structural.** Editing activity fell roughly 2x between
   2022 and 2025. Weighting by churn over-represents the high-churn era, and if churn
   correlates with decay — it almost certainly does — the calendar-time headline overstates
   staleness **by construction**. That is the direction that must never ship unexamined.
2. **2026 had zero cohorts.** The claim is about how fast documentation goes stale *now*.
   A sample with nine cohorts in 2021 and one in 2025 invites a reader to discount the
   number, correctly, and a limitations paragraph does not repair it.
3. **The long-median downside gets worse, not better.** If the median comes back near two
   years — the scenario that changes the pitch, the ICP, and the first email — the
   structural bias means the true number is longer still. That case would have been read
   through a lens tilted the wrong way.

## Why this amendment is legitimate
Section 8b permits bias-grounds amendments pre-run. The test separating a legitimate
protocol edit from a self-serving one is whether the direction of the effect on the headline
can be predicted **before** running it.

It can, and **it goes against us**: fewer high-churn cohorts, more recent low-churn ones,
expected staleness down. An amendment that lowers the author's own headline, made before any
outcome was observed, on a bias the author identified and published.

It was found by a feasibility check that is structurally incapable of seeing outcomes —
`scripts/study_feasibility.py` does not import `corpora.anchors` or `corpora.diff`, enforced
by `check_invariants.py` (`study_firewall`) and negative-tested in both directions. The
finding came from commit dates and counts alone.

"Marking my own homework" is the right worry. The answer is the record, not abstention.

## New seed
The quarter-stratified draw uses seed **20260917**. The superseded commit-uniform draw used
**20260916** and its results are known to the author, so reusing it under a new frame would
be a free degree of freedom. Both seeds are recorded, and the superseded output is kept at
`docs/study/feasibility-commit-uniform.{txt,json}` so the change is inspectable without git
archaeology.

## What it costs
| | before | after |
|---|---|---|
| cohorts | 24 | 21 (one per quarter) |
| realised N | 1200 | **1050** |
| censoring at +365d | 4.2% | **14.3%** |
| censoring at +7..+180d | 0% | 0% |

N falls 12.5% and long-horizon censoring triples, because calendar-uniform sampling places
more cohorts near the present where the 365-day horizon is not yet reachable. Kaplan–Meier
handles that correctly; it is the honest price of a neutral frame, and it is paid in
precision rather than in bias. Per section 8b the permitted response, if precision proves
insufficient, is a larger K — never a looser eligibility rule.

## Churn becomes a covariate
With the frame neutral, each cohort's trailing 90-day commit count is reportable rather than
confounding. "Anchors captured in high-churn periods decay faster" becomes a finding the
study can state, and a per-stratum-style cut obtained for free. The measured series runs
from ~606 commits per 90 days in 2021–2022 to ~295 by 2026Q1.

The first implementation counted churn against the *windowed* population and reported 24
commits for 2021Q1 where its neighbours had ~500 — an artifact of the window edge, not a
quiet quarter. Now counted against full history. Caught by the number looking impossible
next to its neighbours, which is the same way three earlier defects in this project were
caught.

## Rejected
- **Footnote the bias in limitations.** Ships a known self-serving distortion and asks the
  reader to discount by an unstated amount.
- **Keep M = 24 by doubling up some quarters.** Reintroduces unequal calendar weighting,
  which is the thing being fixed.
- **Raise K to hold N at 1200.** Available under 8b, deliberately not taken: adjusting a
  second parameter to preserve a round number is how a frame change quietly becomes a yield
  change. If precision turns out to be short, that is a separate decision made on its own
  evidence.
- **Reuse seed 20260916.** Its draw is known.

## Reverses if
Nothing about the frame. If the realised precision at 1050 proves too low for the
per-stratum cuts, K rises — on its own ADR, argued on power rather than on the headline.
