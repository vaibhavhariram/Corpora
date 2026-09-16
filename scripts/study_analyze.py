#!/usr/bin/env python3
"""Analyse the observations produced by study_run.py. Reads only; writes no data.

Separate from the runner on purpose. Analysis can be re-run and argued over without
re-running the study, and a runner that also reported a headline would invite adjusting a
parameter and re-running until the headline moved.

The headline event is **STALE** — the test still looks runnable and its expected answer is
now wrong. Fixed in the protocol before the run, not chosen after seeing the split.

DESTROYED is reported separately and never folded into the headline. It is an observation
about one snapshot, not a verdict (invariant 7): sections get emptied in one commit and
refilled in the next. Its recovery rate is reported for exactly that reason.

Usage:
    python scripts/study_analyze.py --observations docs/study/observations.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from corpora.study.survival import (
    Observation,
    kaplan_meier,
    median_survival,
    survival_at,
)

SURVIVES = {"valid", "valid_repaired", "valid_relocated"}
HEADLINE_EVENT = "stale"


def load(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    header: dict[str, Any] = {}
    observations: list[dict[str, Any]] = []
    unresolvable: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        kind = row.get("record")
        if kind == "run_header":
            header = row
        elif kind == "observation":
            observations.append(row)
        elif kind == "unresolvable":
            unresolvable.append(row)
    return header, observations, unresolvable


def to_survival(
    rows: list[dict[str, Any]], event_value: str
) -> tuple[list[Observation], dict[str, list[Observation]]]:
    """One Observation per anchor: first event horizon, else censored at the last seen.

    Anchors are keyed by (cohort, span_hash) rather than span_hash alone — the same sentence
    can legitimately be drawn in two different cohorts, and pooling them would silently
    merge two independent observations into one.
    """
    by_anchor: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_anchor[(row["cohort"], row["span_hash"])].append(row)

    overall: list[Observation] = []
    by_stratum: dict[str, list[Observation]] = defaultdict(list)

    for series in by_anchor.values():
        series.sort(key=lambda r: r["offset_days"])
        event_at = next(
            (r["offset_days"] for r in series if r["resolution"] == event_value), None
        )
        obs = Observation(
            time=float(event_at if event_at is not None else series[-1]["offset_days"]),
            event=event_at is not None,
        )
        overall.append(obs)
        by_stratum[series[0]["stratum"]].append(obs)
    return overall, dict(by_stratum)


def report_curve(label: str, observations: list[Observation], horizons: list[int]) -> None:
    curve = kaplan_meier(observations)
    median = median_survival(curve)
    events = sum(1 for o in observations if o.event)
    median_text = f"{median:.0f} days" if median is not None else "not reached"
    print(f"\n{label}  (n={len(observations)}, events={events})")
    print(f"  median survival: {median_text}")
    print("  " + "  ".join(f"+{h}d" for h in horizons))
    print("  " + "  ".join(f"{survival_at(curve, h):.3f}".rjust(len(f'+{h}d'))
                           for h in horizons))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True, type=Path)
    args = ap.parse_args()

    header, rows, unresolvable = load(args.observations)
    if not rows:
        print("no observations")
        return 1

    horizons = header.get("offsets_days", [7, 14, 30, 60, 90, 180, 365])
    anchors = {(r["cohort"], r["span_hash"]) for r in rows}

    print("=" * 66)
    print("STALENESS HALF-LIFE OF A GOLDEN SET")
    print("=" * 66)
    print(f"corpus         kubernetes/website @ {header.get('corpus_head', '?')[:12]}")
    print(f"corpora        {header.get('corpora_head', '?')[:12]}")
    print("protocol       docs/study-protocol.md (pre-registered)")
    print(f"seed           {header.get('seed')}")
    print(f"anchors        {len(anchors)} across {header.get('cohorts')} cohorts")
    print(f"observations   {len(rows)}")
    print(f"unresolvable   {len(unresolvable)}  (excluded from every denominator)")

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["resolution"]] += 1
    print("\nobservations by resolution")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<18} {count:>6}  {100 * count / len(rows):>5.1f}%")

    # ---- headline ----
    print("\n" + "=" * 66)
    print("HEADLINE — time to first STALE")
    print("=" * 66)
    overall, by_stratum = to_survival(rows, HEADLINE_EVENT)
    report_curve("all anchors", overall, horizons)
    for name in sorted(by_stratum, key=lambda s: -len(by_stratum[s])):
        report_curve(f"stratum: {name}", by_stratum[name], horizons)

    # ---- churn covariate ----
    churn_by_anchor = {
        (r["cohort"], r["span_hash"]): r["churn_90d"] for r in rows
    }
    median_churn = sorted(churn_by_anchor.values())[len(churn_by_anchor) // 2]
    high = [r for r in rows if r["churn_90d"] > median_churn]
    low = [r for r in rows if r["churn_90d"] <= median_churn]
    print("\n" + "=" * 66)
    print(f"COVARIATE — churn, split at the median of {median_churn} commits/90d")
    print("=" * 66)
    for label, subset in (("high churn", high), ("low churn", low)):
        if subset:
            report_curve(label, to_survival(subset, HEADLINE_EVENT)[0], horizons)

    # ---- destroyed, separately and caveated ----
    print("\n" + "=" * 66)
    print("SECONDARY — DESTROYED, reported separately")
    print("=" * 66)
    print("An observation about one snapshot, not a retirement (invariant 7). Sections get")
    print("emptied in one commit and refilled in the next, so the recovery rate below is the")
    print("reason a single DESTROYED must never retire a test.")

    destroyed_series: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        destroyed_series[(row["cohort"], row["span_hash"])].append(row)
    ever, recovered = 0, 0
    for series in destroyed_series.values():
        series.sort(key=lambda r: r["offset_days"])
        seen = [r["resolution"] for r in series]
        if "destroyed" in seen:
            ever += 1
            first = seen.index("destroyed")
            if any(r in SURVIVES for r in seen[first + 1:]):
                recovered += 1
    rate = 100 * recovered / ever if ever else 0.0
    print(f"\n  anchors ever DESTROYED         {ever}")
    print(f"  ...later resolvable again      {recovered}  ({rate:.1f}%)")
    print("\n  Every one of those recoveries would have been a test deleted from a")
    print("  customer's coverage, silently, had DESTROYED triggered retirement.")

    destroyed_obs, _ = to_survival(rows, "destroyed")
    report_curve("time to first DESTROYED", destroyed_obs, horizons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
