# A green suite over a wrong answer key

*Measuring how fast a documentation benchmark decays, and what it took to get a number
worth believing.*

---

## The result I nearly published

The first execution of this study produced a clean artifact. A full Kaplan–Meier survival
curve. A per-stratum breakdown. 2800 observations across four cohorts, no errors, no
warnings. The resolution mix looked entirely plausible — 87% of observations `VALID`, 13%
`AMBIGUOUS`. Every test in the repository passed. `mypy --strict` was clean. Eight
deterministic invariant checks passed. An adversarial multi-agent review of the diff engine
had already run and been acted on.

The finding was that documentation never goes stale.

Every one of those 2800 observations had compared the corpus against itself.

`git log` walks `HEAD` unless you give it an explicit ref. The runner checks out each
cohort's commit with `--detach` before loading its snapshot. So by the time it asked for
"the newest commit at or before cohort start + 90 days", `HEAD` *was* the cohort commit —
and `git log` only walks ancestors. The newest ancestor at or before a later date is the
cohort commit itself. One missing argument, and every downstream number followed from it
correctly.

Nothing in the project could see it. The test suite doesn't exercise the runner against real
git history. The invariant gate models imports and versioning, not snapshot selection. A type
checker cannot know that two SHAs should differ.

What caught it was a covariate that exists only as a reporting nicety, computed twice, and
disagreeing with itself. The runner printed `churn=0` for a quarter where the pre-registered
feasibility check had independently measured 518.

---

## The fourth verification method

Four things found defects in this project. They are not interchangeable, and only one of
them could have caught the bug above.

| method | catches | found here |
|---|---|---|
| deterministic gate | what you thought to encode | invariant violations, an unversioned normalizer change, verifier edits |
| adversarial review | what you thought to look for | a regex that swallowed the following heading |
| a person | a wrong framing | the resolution cascade's ancestry semantics |
| **redundant independent computation** | **a single implementation being uniformly wrong** | **the self-comparison** |

The first three all share a blind spot. A gate checks the properties you enumerated. A
reviewer checks the questions you posed. A person catches the framing you got wrong — but
only if they are looking at the framing, not the output. None of them can tell you that your
one implementation of a quantity is confidently and consistently incorrect, **because there
is nothing inside a single implementation to compare against.**

Redundancy is the only method that catches that class, and it is the one nobody builds on
purpose. The churn covariate wasn't a check. It was a nice-to-have that happened to be
computed in two places by two pieces of code written a day apart.

It is now a real check: the runner cross-references its commit population against the
pre-registered feasibility artifact and refuses to run on a mismatch, and raises immediately
if any observation horizon resolves to its own base commit. Both negative-tested by
deliberately breaking them.

Worth stating plainly: the same bug bit twice. I fixed two of its three call sites, and the
next run silently drew its sample from two quarters instead of twenty-one. That is what
converted "fix the call sites" into "add a guard that cannot be bypassed."

---

## The number

With that fixed, the study ran as pre-registered: 21 cohorts, one per calendar quarter from
2021Q1 to 2026Q1, 1050 anchors drawn uniformly from Kubernetes documentation, 7200
observations, zero unresolvable.

**Survival of an anchored answer span:**

| horizon | 7d | 14d | 30d | 60d | 90d | 180d | 365d |
|---|---|---|---|---|---|---|---|
| still correct | 0.997 | 0.989 | 0.981 | 0.973 | 0.965 | 0.941 | **0.901** |

**The median is not reached.** Roughly 10% of anchors go stale within a year. There is no
half-life inside the observable window, and I am not going to manufacture one by
extrapolation.

That is a negative result for the hypothesis I started with.

### What it does support

**At 90 days, 3.5% of a benchmark's answer keys are wrong, and the suite reports green.**

That is not a decay story. It is a measurement-floor story, and it is the more useful claim.

If you evaluate a retrieval system quarterly against a frozen golden set, roughly 3.5% of
your denominator has silently changed meaning between runs. A stale test does not error — it
scores, against an expectation that no longer matches the document. So a change that moves
recall by two points cannot be distinguished from the corpus having moved underneath you.
**Your eval cannot resolve the changes you are using it to decide.**

That is the same argument as gating comparisons on identical dataset and config hashes,
extended one layer out: a comparison is only meaningful if both sides measured the same
thing, and an un-audited golden set silently violates that between every pair of runs.

### The breakdown

Every effect is directionally as predicted and all of them are small.

| cut | n | events | survival at 365d |
|---|---|---|---|
| prose | 554 | 47 | 0.909 |
| numeric | 224 | 23 | 0.894 |
| identifier | 234 | 25 | 0.888 |
| high churn (>511 commits/90d) | 488 | 55 | 0.887 |
| low churn | 524 | 40 | 0.914 |

Identifier-bearing spans decay faster than prose. High-churn periods decay faster than quiet
ones. Both were predicted in advance; both are about two percentage points at one year. I
would not build an argument on either.

### A secondary result that surprised me

Of 36 anchors ever observed `DESTROYED`, **one** later resolved again. I had argued from
first principles that sections get emptied in one commit and refilled in the next, and used
that to justify never retiring a test on a single observation. The data says recovery is rare
in this corpus — 2.8%, on n=36.

The design decision still stands, on cost asymmetry rather than frequency: retiring a test
wrongly removes coverage permanently and tells nobody. But the empirical case I made for it
is weaker than I made it, and it is more honest to say so than to quietly stop mentioning
the number.

---

## Finding versus hypothesis

**Finding.** Kubernetes documentation anchors go stale at approximately 10% per year.
Identifier-bearing content slightly faster than prose, high-churn periods slightly faster
than quiet ones, all effects small.

**Hypothesis, unmeasured.** That regulated technical corpora behave the same way.

The gap is not rhetorical. This corpus is 57% prose by the study's own classification,
community-reviewed, and describes concepts that are deliberately stable. It has **no
applicability dimension at all** — no customer field, no jurisdiction, no active/legacy
window, no addenda arriving mid-project. A building-code corpus on a three-year cycle plus
local amendments plus project addenda is a structurally different object, and so is hardware
documentation where version applicability is a first-class field.

That gap might be large. It is also precisely the escape hatch a pre-registration exists to
deny. Running corpus after corpus until one produces a satisfying number is p-hacking with
extra steps, and a reader will see it from a long way off.

So: a second study is legitimate only if it is pre-registered before the data is touched,
published regardless of outcome, and chosen for a stated structural reason rather than
because it looks promising. And it should follow conversations with practitioners rather than
precede them.

---

## What the method cost

The protocol was committed before any commit pair was sampled. Git's timestamp is the
evidence; "we sampled without curation" is unfalsifiable from outside without it.

A feasibility check ran before the study to confirm the design could detect an effect. It is
structurally incapable of looking at the effect: it does not import the resolution engine at
all, and a check in the invariant gate fails the build if it ever does. That is the
distinction a power analysis draws — confirming the design can detect an effect is
legitimate, looking at the effect is not.

**Three parameters were caught moving the number in my own favour**, each before the run and
each invisible from inside the result:

1. A 60-character minimum span length, chosen for an unrelated reason, rejected two of three
   realistic technical sentences in a spot check — and both rejected were the short, dense,
   identifier-bearing ones. It biased the sample toward prose, which understates staleness.
   Lowered to 40.
2. A pre-commitment, made before the strata were known, never to oversample a thin stratum.
   Had the feasibility check returned 90% prose, the obvious move would have been to
   oversample identifiers "so the per-stratum estimate is powered" — which would have
   inflated the headline while feeling like a methods improvement.
3. Cohort starts were drawn uniformly over *commits* while the headline was reported in
   *calendar time*. Editing activity on this corpus fell roughly 2× between 2022 and 2025, so
   the high-churn era was over-represented by construction. The superseded draw also put zero
   cohorts in 2026, while the claim is about how documentation decays now.

That third one became an amendment, and it is the one I would point a sceptical reader at:
its effect on the headline was predictable before running it, and **it went against me** —
fewer high-churn cohorts, expected staleness down. It cost N (1200 → 1050) and tripled
long-horizon censoring, paid in precision rather than bias.

One gap was found after the run and **reported rather than corrected**. The protocol excludes
spans that are non-unique at capture; the implementation enforced uniqueness only within a
document, not across the corpus, so 112 anchors were already `AMBIGUOUS` at the first
observation. Applying the exclusion the protocol already specifies moves the headline from
9.9% to 9.8% — in my favour. The as-run figure is the headline and the correction is a
sensitivity, because the alternative is adjusting analysis after seeing results, which is
where studies go to die.

---

## What I would tell someone evaluating a retrieval system

Three things, only one of which is about this study.

**Your golden set is a measurement instrument and it is drifting.** Not fast, on evidence
from one corpus — but fast enough that a quarterly comparison of two-point changes is
measuring your corpus as much as your system. Audit the answer keys, or stop reporting
deltas smaller than the drift.

**A green suite is evidence about your tests, not about your system.** This one produced a
complete, plausible, internally consistent, entirely fictional result while every check in
the repository passed. That failure mode does not announce itself, and it is not rare — it
is what happens whenever the thing that is wrong is not the thing anything checks.

**Compute your important numbers twice, by different means.** It is the only method that
catches the case where your single implementation is uniformly wrong, and it is the one
almost nobody builds deliberately. Mine was an accident that happened to save the study.

---

## Reproducing this

Everything is in the repository: the pre-registered protocol and its amendment history, the
feasibility check and its output, the runner, the analysis, the raw observations, and the
decision records for every non-obvious choice — including the ones that went badly.

- `docs/study-protocol.md` — pre-registration, committed before any sampling
- `docs/study/feasibility.txt` — the design check, and the superseded draw beside it
- `docs/study/observations.jsonl` — 7200 raw observations
- `docs/study/results.txt` — the analysis output, including the sensitivity
- `docs/decisions/0018-*` — the self-comparison defect, in full

One corpus, measured honestly, published against interest.
