# Study protocol: the staleness half-life of a golden set

**Status: pre-registered. Committed before any corpus is sampled or any anchor is captured.**

This document exists so that "we sampled without curation" is checkable rather than
asserted. From outside, a curated study and an honest one look identical; the only evidence
that survives is a protocol whose commit predates the data. Git provides the timestamp. If
this file is edited after the first data commit, the amendment section below must say so, and
a reader is entitled to discount anything it changed.

It also protects the study from its author. The run will produce a number, there will be an
obvious reason to adjust one parameter, and that is the moment the study dies. Every
parameter is fixed here, in advance, including the ones that will look wrong later.

Design decisions are marked with the direction of bias they introduce, where one exists.

---

## 1. The question

Across real documentation history, **how long does an anchored answer span remain correct?**

Reported as a survival curve with a median — the half-life. Calendar time is the headline
unit, releases a secondary cut, commits the raw measurement (ADR-0012).

The claim being tested is not "we classify mutations correctly." That is the mutation
table, and it is a unit test. The claim is **a golden set decays at a measurable rate, and
nobody currently measures it.**

## 2. Corpus

`kubernetes/website`, path `content/en/docs/**`, Markdown only.

Chosen before the protocol was written and not after inspecting results: it is Markdown in
Git with thousands of commits, real heading structure, versioned API references, heavy
cross-linking, and it is structurally similar to the internal documentation this product
targets.

The exact commit SHA of the corpus at analysis time, and of Corpora itself, are recorded in
the results artifact.

## 3. Unit of analysis

**One anchor.** Anchors are the unit for every rate; documents and commits are not.

At most **one anchor per document per cohort**. Documents vary enormously in length, and
sampling spans uniformly would let a handful of long pages dominate. One-per-document also
avoids intra-document correlation inflating the apparent precision of the estimate.

## 4. Cohort and commit-pair sampling

Anchors are captured at commit A and re-resolved at later commits. Neither is chosen for
convenience (ADR-0009).

1. **Population.** All commits on `main` touching `content/en/docs/**` between
   **2021-01-01** and a cutoff **180 days before the analysis date**. The trailing gap
   exists so that short offsets are observable for every cohort rather than only for old
   ones.
2. **Cohort starts (amended — ADR-0017).** **One cohort start per calendar quarter**, drawn
   uniformly at random from the commits in that quarter, for every quarter from 2021Q1
   through the last quarter containing a commit on or before the cutoff. M is therefore the
   number of eligible quarters (**21**), not a fixed number. Seed **20260917**, recorded.

   The headline is a calendar-time half-life, so the sampling frame is calendar time.
   Drawing uniformly over *commits* instead weights cohorts by churn — and editing activity
   on this corpus fell roughly 2x between 2022 and 2025, which over-represents the high-churn
   era and biases the headline toward **more** staleness. Superseded design and its output are
   kept at `docs/study/feasibility-commit-uniform.{txt,json}`.
3. **Observation grid.** Each cohort is re-resolved at **+7, +14, +30, +60, +90, +180, +365
   days** after its start. For each offset, the snapshot used is the corpus at the **last
   commit on or before** that timestamp.
4. **Censoring.** An offset falling after the analysis date is not observed. Those anchors
   are right-censored at their last observed offset. Censoring is handled by the estimator,
   not by dropping the anchor.

No commit pair is inspected before being drawn. The RNG seed is fixed before the first draw
and recorded.

## 5. Anchor selection — the larger lever

The ADR-0009 sampling constraints cover commit pairs and say nothing about **which spans get
anchored**, which moves the headline further than pair selection does. Anchor only
well-formed prose under stable headings and staleness looks low; anchor version numbers and
command flags and it looks enormous. Same corpus, same commits, and both are
defensible-sounding.

The rule is therefore mechanical, fixed here, and applied with **no manual inspection of any
candidate before capture**.

Within each cohort:

1. Enumerate **eligible documents** (section 6).
2. Draw **K = 50** documents uniformly at random without replacement.
3. Within each drawn document, enumerate **eligible spans** and draw **exactly one**
   uniformly at random.

**Eligible span.** A sentence, where sentences are produced by splitting the document's
normalized text on `(?<=[.!?])\s+`, that satisfies all of:

- length between **40 and 400 characters** inclusive
- **occurs exactly once** in the document's normalized text — a span that is already
  ambiguous at capture starts in a degenerate state and would measure duplication, not decay
- lies **under at least one heading** — `heading_path` is a load-bearing resolution signal
  and a preamble span has none
- lies **outside every fenced code block**, using the loader's own fence detection

Target N = 21 × 50 = **1050 anchors**, less any cohort where fewer than 50 eligible
documents exist. The realised N is reported.

**On the 40-character floor.** Uniqueness is enforced separately, so the floor is not doing
that work. Its job is to reject sentence-split artifacts and fragments that are not
answer-shaped. The splitter is a regex and mis-handles abbreviations — `"Use a probe, e.g.
an HTTP check"` splits at `e.g.` — while correctly leaving `v1.28.0` and `0.5` intact, both
verified before this number was chosen.

The floor is a **stratum-biasing parameter and was nearly set wrong.** A spot check at 60
characters rejected two of three realistic technical sentences, and both rejected ones were
the short dense ones — `"Set restartPolicy=Always to keep it running."` (44) and `"The
kubelet restarts the container after 10 seconds."` (52) — while the long prose sentence
passed. A higher floor systematically drops `identifier` and `numeric` spans and keeps
`prose`, which **understates staleness**. 40 admits both. Because this parameter can skew
the sample invisibly, the **realised stratum distribution is reported** alongside the
results so a reader can check the sample rather than trust it.

**Bias, stated:** excluding fenced code blocks lowers measured staleness, because example
YAML and command flags churn faster than prose. The exclusion is deliberate — an anchor is
meant to model an answer span a generator would quote — and its direction is
**conservative**, understating the headline. It is listed again in section 11.

## 6. Exclusions, and why

| excluded | reason | bias direction |
|---|---|---|
| everything outside `content/en/docs/**` | the rest of the repo is site machinery, not documentation | none |
| all non-`en` locales (`zh-cn`, `ja`, `de`, … — 16 of them) | translations churn on sync commits, which measures translation lag, not documentation decay | none |
| files with `auto_generated: true` in front matter | machine-generated from Kubernetes source; their churn measures a code-generation pipeline's release cadence, not human editing | **lowers** measured staleness |
| non-Markdown files | no loader (ADR-0013) | none |
| documents with no eligible span | nothing to anchor | none |
| anchors whose span is non-unique at capture | degenerate start state | slight, direction unknown |

`auto_generated: true` is a real front-matter key in this corpus, verified before writing
this rule rather than assumed. It is preferred to a path allowlist because it is mechanical
and survives directory restructuring.

## 7. What is measured

For each anchor, at each observed offset, `resolve()` returns one observation.

**Primary event: the first `STALE` observation.**

`STALE` is the product's claim made concrete — the test still looks runnable and its expected
answer is now wrong. `VALID`, `VALID_REPAIRED` and `VALID_RELOCATED` are survival: the
evidence is intact and the anchor was repaired without human cost.

Secondary events, reported separately and never folded into the headline:

- **first `AMBIGUOUS`** — evidence duplicated, review required
- **first `DESTROYED`** — evidence not visible in that snapshot. Reported as an observation,
  never as a retirement (invariant 7). An anchor that is `DESTROYED` at one offset and
  resolvable at a later one is *not* treated as having failed, and that recovery rate is
  itself reported, because it is the empirical basis for tuning `RetirementPolicy`.

**Excluded from every numerator and denominator:** anchors appearing in `Diff.unresolvable`.
An anchor that cannot be resolved for infrastructural reasons is a fact about our tooling,
not about the corpus. Counting it would report our own version bumps as documentation decay
in the artifact whose purpose is to show that we catch exactly that.

## 8. Strata, classified mechanically at capture

Reporting one aggregate invites argument. "Staleness is 30%" is a number people dispute;
"the median anchor survives N weeks, and version-bearing content survives 3 while prose
survives 20" is diagnostic and harder to dismiss. It is also the same
aggregate-versus-per-failure-mode argument the product makes about retrieval scores, applied
to ourselves.

Each anchor is assigned exactly one stratum at capture time, from the span text alone, and
the assignment is frozen:

| stratum | rule |
|---|---|
| `numeric` | the span contains at least one digit |
| `identifier` | not `numeric`, and `corpus.normalize.technical_tokens(span)` is non-empty |
| `prose` | neither |

Crude on purpose. Every rule is computable from existing code with no judgement, so no
anchor's stratum can be adjusted after its outcome is known.

## 8d. Churn as a covariate

Each cohort records the number of commits touching the corpus in the **trailing 90 days**
before its start. With the sampling frame calendar-uniform (ADR-0017) this is a covariate
rather than a confound, so *"anchors captured in high-churn periods decay faster"* becomes a
finding the study can report — a per-stratum-style cut obtained for free, and the kind of
diagnostic detail that gets a study cited rather than nodded at.

Counted against full history, not the windowed population: counting against the population
truncates the trailing window at `WINDOW_START` and reported 24 commits for 2021Q1 where its
neighbours had ~500.

## 8a. Sampling stays uniform regardless of what the strata look like

**Pre-committed before the feasibility check runs.**

If the realised distribution comes back thin in one stratum — say 90% `prose`, 10%
`identifier` — the obvious move is to oversample `identifier` so the per-stratum estimate is
powered. That adjustment would **inflate the headline**, because identifier-bearing spans
almost certainly go stale faster than prose, and it would feel like a methods improvement
while being made.

So: **sampling is uniform over eligible spans, whatever the strata turn out to be.** A thin
stratum is reported as underpowered. It is never corrected for by oversampling, reweighting,
or quota. This turns the stratum numbers into pure information and removes the lever.

## 8b. Frozen parameters

The span floor moved once, from 60 to 40 characters, on the grounds that the higher value
systematically dropped short technical sentences and biased the sample toward prose. That
was a bias-direction argument made against three hand-written sentences, not against
corpus-drawn data, and it is the legitimate kind of parameter change.

**It has now moved. It is frozen.** Further changes to the span floor, the sentence
splitter, or any eligibility rule require an ADR and must be justified on **bias grounds
only** — never on realised yield.

If the feasibility check says N is too small, the permitted fixes are **more cohorts (M) or
more documents per cohort (K)**. Loosening eligibility to manufacture sample size is not
available, because it trades a known bias for a larger number.

## 8c. The feasibility firewall

A feasibility check may run before the study, and its script and output are committed
alongside this protocol so a reader can see exactly what was inspected in advance.

The distinction is the one a power analysis draws: confirming the design **can** detect an
effect is legitimate; looking at the effect is not.

**The check may compute:** eligible documents per cohort, eligible sentences per document,
realised N after the one-anchor-per-document rule, the censoring rate implied by the date
grid, which horizons are observable for each cohort, and the stratum distribution at
capture.

**The check may not resolve anchors.** No classifications, no staleness counts, nothing
downstream of capture — and not "computed then discarded". *The code path must not exist.*

`scripts/study_feasibility.py` therefore does not import `corpora.anchors` or `corpora.diff`
at all. It needs neither: stratum assignment is a function of span text alone. This is
enforced mechanically by `check_invariants.py` (`study_firewall`), not by discipline,
because a documented promise is exactly the kind of guarantee this project has now watched
fail five times.

## 9. Estimator

Kaplan–Meier, which is what right-censored time-to-event data requires. A naive "percentage
stale after 90 days" silently drops every anchor not yet observed that long and biases the
result.

**Headline:** median calendar time from capture to first `STALE`, over all anchors.
**Also reported:** the full survival curve, per-stratum curves and medians, the realised N,
the censoring rate, and the same in units of intervening commits and of releases.

## 10. Pre-committed interpretation

Fixed now so that the result cannot be reframed after it is seen:

- **Median survival under ~6 months** — the golden-set half-life claim holds; this is the
  headline and the study is the artifact.
- **Roughly 6 months to 2 years** — real but slower than assumed. Reported as-is, and the
  product's framing moves from "your tests are already wrong" to "your tests have a
  measurable shelf life."
- **Over ~2 years, or a censoring rate so high the median is unreachable** — the staleness
  problem is smaller than this project assumed. **That result gets published too.** It is
  ADR-0009's reverses-if condition and the reason the study runs before phase 3 rather than
  after.

The per-stratum breakdown is reported in all three cases, including when the aggregate is
uninteresting.

**What a long median would mean, priced now rather than at results time.** If the median
lands near or above two years, the staleness wedge is weak: detection stops being the
differentiator and the product falls back to the accept gate, which is more contested, has
real competitors closing on it, and is a materially worse position. That outcome does not
end the project, but it changes the pitch, the ICP, and the first outreach email. Publishing
it anyway is still correct — and it is the only reason anyone will believe the number in the
case where it is large.

## 11. Limitations we state ourselves

Listed here so they appear in the writeup rather than in someone's reply:

- **Fenced code blocks are excluded**, which understates staleness for exactly the content
  that churns fastest. Conservative.
- **`auto_generated` content is excluded**, which understates it further. Conservative.
- **One corpus.** Kubernetes documentation is unusually well maintained and unusually
  high-churn. Neither direction is obviously dominant, and generalisation to internal
  enterprise corpora is an assumption, not a finding.
- **Kubernetes documentation is saturated in pretraining data.** Irrelevant here — this study
  runs no model — but it matters the moment generation is layered on, and the verbatim-span
  grounding check is not optional on a public corpus.
- **An ancestor rename plus a rewording was reported `DESTROYED` until ADR-0016.** Fixed
  before the run; noted because it would have biased the headline downward.
- **Markdown parser gaps** (Setext headings, trailing closing sequences, HTML blocks) per
  ADR-0013 and ADR-0015.
- **Sentence splitting is a regex** and splits on abbreviations such as `e.g.`. Version
  numbers and decimals are unaffected. Short artifacts are removed by the length floor;
  surviving fragments are still valid anchors, since an anchor is content-addressed and does
  not need to be a grammatical sentence.

## 11a. Feasibility check — results

Run before any anchor was resolved. Script `scripts/study_feasibility.py`, full output
`docs/study/feasibility.txt`, machine-readable `docs/study/feasibility.json`. The script
cannot resolve anchors: it does not import `corpora.anchors` or `corpora.diff`, enforced by
`check_invariants.py` (`study_firewall`), which was negative-tested in both directions.

**The design runs as specified under the amended frame (ADR-0017).**

| quantity | commit-uniform (superseded) | quarter-stratified (adopted) |
|---|---|---|
| cohorts | 24 | **21**, one per quarter, 2021Q1–2026Q1 |
| realised N | 1200 / 1200 | **1050 / 1050** |
| eligible spans per document | median 19 | median 19 (min 1, max 317) |
| censoring +7..+180d | 0% | 0% |
| censoring +365d | 4.2% | **14.3%** |
| `prose` | 52.1% | 57.4% |
| `identifier` | 27.2% | 24.1% |
| `numeric` | 20.7% | 18.5% |
| trailing-90d churn | not recorded | 606 (2021Q1) → 295 (2026Q1) |

Every cohort reached its full 50 anchors under both frames. No stratum is thin, so the
oversampling temptation section 8a pre-commits against does not arise. **8a stands
regardless** — it is a rule about what may be done, not a prediction about what would have
been needed.

The stratum mix shifting toward `prose` under the neutral frame is consistent with the
predicted direction of ADR-0017: fewer high-churn cohorts, less churn-heavy content, expected
staleness down. That is a property of the *sample*, not an outcome.

### The open question this surfaced — now resolved by ADR-0017

Cohort starts are drawn uniformly **over commits**, while the headline is reported in
**calendar time**. Those are not the same frame, and editing activity is not flat:

| year | commits | % of population | cohorts drawn | expected |
|---|---|---|---|---|
| 2021 | 2222 | 20.9% | 9 | 5.0 |
| 2022 | 2695 | 25.4% | 7 | 6.1 |
| 2023 | 2278 | 21.5% | 4 | 5.2 |
| 2024 | 1697 | 16.0% | 3 | 3.8 |
| 2025 | 1437 | 13.5% | 1 | 3.3 |
| 2026 | 282 | 2.7% | 0 | 0.6 |

Two separate effects, both computed from dates and commit counts alone — no anchor was
resolved to find them:

1. **Structural.** Uniform-over-commits weights cohorts by churn. Activity fell roughly 2x
   from 2022 to 2025, so the high-churn era is over-represented by construction. If
   high-churn periods also decay faster, the calendar-time headline is biased toward *more*
   staleness — the self-serving direction, and therefore the one to be most suspicious of.
2. **This draw.** 9 cohorts landed in 2021 against 5.0 expected and 1 in 2025 against 3.3.
   That is chance on n = 24, but it compounds the structural effect and leaves the recent
   era thinly covered.

**Resolved by ADR-0017**, on the record rather than on the author's judgement. The amendment
passes the test that separates a legitimate protocol edit from a self-serving one: the
direction of its effect on the headline was predictable before running it, and **it goes
against us** — fewer high-churn cohorts, expected staleness down. An edit that lowers the
author's own headline, made pre-run, on a bias the author identified and published.

## 12. Amendments

The study runs **once**. Any change to this file after the first data commit is recorded
below with the date, what changed, why, and explicitly whether it was decided **before or
after** results were seen. `docs/study-protocol.md` is `CODEOWNERS`-protected so an
amendment cannot land without review.

**2026-09-16 — ADR-0017, cohort sampling frame. Decided BEFORE any anchor was resolved.**
Cohort starts changed from uniform-over-commits to one per calendar quarter. Reason: the
headline is calendar time and the frame was commit-space, which weights cohorts by churn and
biases the headline toward more staleness. Found by the pre-run feasibility check, which is
structurally unable to observe outcomes (`study_firewall`). Predicted direction of the
effect: **against the headline**. Costs: N 1200 → 1050, censoring at +365d 4.2% → 14.3%. New
seed 20260917; the superseded draw used 20260916 and its output is retained.

## 13. Reporting

- **Lead with one worked example, not a list.** The heading-regex defect — a full green
  suite, `mypy --strict`, ruff across `src` and `tests`, seven deterministic invariants, and
  the money case still silently routed from `STALE` to `DESTROYED` by one character in a
  regex, because no fixture contained an empty heading. One reproduction with a diff and a
  classification flip is evidence. Five bullets is a changelog, and a changelog about your
  own broken code reads as inexperience however it is framed. The frame is: *this is what
  the method catches, demonstrated where the stakes were ours.*
- **State the sampling method in the writeup**, not merely follow it. A reader who suspects
  curation discounts the entire number and cannot tell from outside. Link this file and its
  commit date.
- **Report the breakdown alongside the aggregate**, per section 8.
- **One line on what the protocol caught, not as process narration.** Three sessions, three
  self-serving parameters caught before they shipped: a span floor that silently dropped
  short technical sentences, an oversampling temptation pre-committed against before the
  strata were known, and a sampling frame in commit-space under a calendar-time headline.
  All three were invisible from inside the result and each would have moved the number in our
  own favour. That is the argument that a pre-registered protocol is the mechanism, not the
  ceremony.
- **Include the asymmetry of verification.** Of the defects this project found in itself,
  most were caught by a deterministic gate, one by an adversarial review *of* that gate, and
  one by a human reading an issue and disagreeing with its framing. A deterministic gate
  catches what you thought to encode; it cannot catch what you did not. The residue needs a
  different method, and some of it needs a person. That is the argument for a human accept
  gate in the product, made from our own experience rather than from a citation.
