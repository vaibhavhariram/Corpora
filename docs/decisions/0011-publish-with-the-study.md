# ADR-0011: The repository goes public with the study, not before

**Status:** accepted

## Decision
Keep the repository private. Publish it at the moment the Kubernetes staleness study
publishes — repo and study land together. Until then, pay for GitHub Pro to get branch
protection on a private repo.

## Why
Going public early was considered specifically to obtain branch protection and CODEOWNERS
enforcement, which GitHub withholds from private repos on the free plan. That is buying a
$4/month feature with a one-time, irreversible strategic asset.

The distribution argument for open source is real, but it only pays when there is something
to distribute. This is phase 1 of 5. `resolve()` works and nothing else does. Nobody stars a
scaffold, and the attention spent announcing one is spent.

The study is the reason for a stranger to look; the repo is the evidence behind it. Landing
them together makes each one stronger. Landing the repo eight weeks early spends that moment
for nothing and commits every early mistake to permanent public history — git history is
published too, not just the working tree.

## Precondition: the scrub
This is a positioning problem, not a legal one. Corpora asks enterprises to trust it with
their crown-jewel documents. The repository is the first artifact a prospective customer
looks at. Finding a previous employer's production failure statistics there is disqualifying
in this market, independent of any NDA question.

Ranked by actual risk:

1. **`SLP_A_VAL`, `F:PCH_SOC_SYNC`, `PCH2`/`PCH3` in the fixtures.** Highest. PCH is Platform
   Controller Hub; these read as real signal names in a repo authored by a recent intern.
   Rename to something obviously generic — `PWR_SEQ_VAL`, `F:LINK_SYNC`, `DEV_A`/`DEV_B`.
   **Note:** this touches `tests/fixtures/mutations.py`, so after branch protection lands it
   requires a `verifier-change` label and an ADR. It is the one item whose price goes up.
2. **"29 of 59 real queries returned literally nothing"** and the pilot recall figures in
   CLAUDE.md. A named-adjacent company's internal quality failure, attributable in one click.
   Keep the lesson, delete the numbers.
3. **The named colleague with commercial intent attached**, `docs/status.md`. Remove.
4. **"a semiconductor company"** → "a prior enterprise deployment".
5. **One email** to the former manager. Verbal permission to *use* internal documentation is
   not permission to *publish* derived material publicly under one's own name. One line, gets
   a written yes, costs nothing.

## What is not a reason to stay private
The algorithm. The cascade is six rules and a hash; anyone could reimplement it from
`docs/architecture.md`. The moat is the accumulated per-customer calibration and the
provenance graph, neither of which is in this repository. When the publish decision is
revisited, do not re-argue it as though the algorithm were the asset.

The mutation table becoming public is fine and probably good — it is the credibility artifact
and the point of the study.

## Rejected
- **Public now, for branch protection.** Spends the launch moment on a scaffold to save $4.
- **Public now, no scrub.** See the precondition.
- **Free plan, advisory-only CI.** Workable, but nothing blocks merge, so the guardrail
  depends on noticing a red X rather than on being unable to proceed. The whole safety story
  is that the loop *cannot* edit its own scorer.

## Reverses if
The study does not happen, or lands somewhere that makes the repo irrelevant to it. Then
publishing becomes an ordinary decision about whether an open scaffold helps hiring or
credibility, and should be argued on those terms.
