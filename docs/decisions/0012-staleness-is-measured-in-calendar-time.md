# ADR-0012: The study's headline unit is calendar time

**Status:** accepted

## Decision
The Kubernetes staleness study measures per-commit, because that is the ground truth, and
reports in three layers:

- **Headline: calendar time.** "A golden set has a half-life of roughly N weeks."
- **Secondary: releases.** A supporting cut, not the number.
- **Raw: commits.** The measurement everything else aggregates from.

## Why
The sentence the study exists to produce is *"your golden set has a half-life, and here it
is."* A half-life in weeks transfers to every buyer regardless of how they version anything.

Releases do not transfer. They are a Kubernetes artifact. The customers this is aimed at —
construction firms with jurisdictional standards, pharma with regional product docs — do not
cut releases of their internal documentation. They edit it. Reporting staleness per release
would express the finding in a unit most of the audience does not have, which makes a
transferable result look domain-specific.

Commits are the honest unit for the measurement and the wrong unit for the claim. Commit
frequency is a property of how a project works, not of how fast its documentation decays; a
repo with ten times the commit rate has not got ten times the staleness problem. Aggregating
to days normalizes that away.

This is a customer-facing choice rather than an engineering one, which is why it is decided
here rather than left to whoever writes the analysis.

## Consequence
The diff layer must retain enough to aggregate either way: each resolution needs the commit
it was observed at and the timestamp of that commit. `Diff.computed_at` (ADR-0008) is the
timestamp seam; `from_snapshot_id` / `to_snapshot_id` carry the commit SHAs.

## Rejected
- **Releases as the headline.** Cleanest-looking chart, narrowest transfer.
- **Commits as the headline.** Confounds documentation decay with project velocity.
- **Deciding later, from the data.** Picking the unit after seeing which produces the most
  striking number is how a measurement becomes a marketing artifact. The sampling constraint
  in ADR-0009 exists for the same reason, and it would be undone by choosing the axis to fit
  the result.

## Reverses if
The half-life turns out to vary so much by document class that a single corpus-wide number
misleads. Then the headline becomes a distribution rather than a scalar — still in calendar
time.
