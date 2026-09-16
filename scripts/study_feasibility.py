#!/usr/bin/env python3
"""Feasibility check for the study design in docs/study-protocol.md.

WHAT THIS MAY DO
----------------
Confirm the design can detect an effect: eligible documents per cohort, eligible sentences
per document, realised N after the one-anchor-per-document rule, which observation horizons
are reachable given the date grid, the implied censoring rate, and the stratum distribution
at capture.

WHAT THIS MAY NOT DO
--------------------
Resolve anchors. No classifications, no staleness counts, nothing downstream of capture —
and not "computed and then discarded". **The code path does not exist.** This module does
not import `corpora.anchors` or `corpora.diff`, and does not need to: stratum assignment is
a function of span text alone.

That is the same distinction a power analysis draws before a trial. Confirming the design
can detect an effect is legitimate; looking at the effect is not. Peeking would make the
pre-registration worthless, and a pre-registration is the only evidence of non-curation that
survives a sceptical reader.

The firewall is enforced by `check_invariants.py` (`study_firewall`) rather than by this
docstring, because a documented promise is exactly the kind of guarantee this project has
already watched fail five times.

Usage:
    python scripts/study_feasibility.py --repo <path-to-corpus-clone> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from corpora.corpus.loaders.markdown import (
    MARKDOWN_SUFFIXES,
    parse_headings,
)
from corpora.corpus.normalize import normalize, technical_tokens

# --------------------------------------------------------------------------- #
# Protocol parameters — frozen in docs/study-protocol.md sections 4, 5, 8b
# --------------------------------------------------------------------------- #

CORPUS_PATH = "content/en/docs"
DOCS_PER_COHORT = 50
MIN_SPAN = 40
MAX_SPAN = 400
OFFSETS_DAYS = (7, 14, 30, 60, 90, 180, 365)
WINDOW_START = "2021-01-01"
TRAILING_GAP_DAYS = 180
SEED = 20260917
"""Seed for the quarter-stratified draw (ADR-0017).

The superseded commit-uniform draw used 20260916. Its results are known to the author, so
reusing it under a new frame would be a degree of freedom with no benefit. Both seeds are
recorded; see docs/study/feasibility-commit-uniform.txt for the superseded output.
"""

CHURN_WINDOW_DAYS = 90
"""Trailing window over which each cohort's churn covariate is counted."""

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_DIGIT = re.compile(r"\d")


def stratum(span: str) -> str:
    """Protocol section 8. Computed from span text alone, frozen at capture."""
    if _DIGIT.search(span):
        return "numeric"
    return "identifier" if technical_tokens(span) else "prose"


def is_auto_generated(raw: str) -> bool:
    m = _FRONT_MATTER.match(raw)
    return bool(m) and "auto_generated: true" in m.group(1)


def eligible_spans(raw: str) -> list[str]:
    """Spans a capture could legally choose. Protocol section 5.

    Deliberately returns the spans themselves and nothing else — no anchors are built, so
    there is nothing here that could be resolved even by accident.
    """
    text = normalize(raw)
    headings = parse_headings(text)
    if not headings:
        return []

    # Fenced regions, recomputed here rather than imported, so this script depends on no
    # private loader internals. Same rule as the loader: see ADR-0013.
    fenced: list[tuple[int, int]] = []
    start: int | None = None
    char, length = "", 0
    for m in re.finditer(r"^([ ]{0,3})(`{3,}|~{3,})([^\n]*)$", text, re.MULTILINE):
        fence, info = m.group(2), m.group(3).strip()
        if start is None:
            if fence[0] == "`" and "`" in info:
                continue
            start, char, length = m.start(), fence[0], len(fence)
        elif fence[0] == char and len(fence) >= length and not info:
            fenced.append((start, m.end()))
            start = None
    if start is not None:
        fenced.append((start, len(text)))

    def under_heading(pos: int) -> bool:
        return any(h.start <= pos < h.end for h in headings)

    def in_fence(pos: int) -> bool:
        return any(lo <= pos < hi for lo, hi in fenced)

    out: list[str] = []
    for sentence in _SENTENCE.split(text):
        s = sentence.strip()
        if not (MIN_SPAN <= len(s) <= MAX_SPAN):
            continue
        first = text.find(s)
        if first == -1 or text.find(s, first + 1) != -1:  # must occur exactly once
            continue
        if not under_heading(first) or in_fence(first):
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Git
# --------------------------------------------------------------------------- #


def quarter_of(when: datetime) -> str:
    return f"{when.year}Q{(when.month - 1) // 3 + 1}"


def stratify_by_quarter(
    population: list[tuple[str, datetime]], rng: random.Random
) -> list[tuple[str, datetime]]:
    """One cohort start per calendar quarter, drawn uniformly within the quarter.

    ADR-0017. The headline is a calendar-time half-life, so the sampling frame is calendar
    time. Drawing uniformly over commits instead weights cohorts by churn, and editing
    activity on this corpus fell roughly 2x between 2022 and 2025 — which over-represents
    the high-churn era and biases the headline toward more staleness.
    """
    buckets: dict[str, list[tuple[str, datetime]]] = {}
    for sha, when in population:
        buckets.setdefault(quarter_of(when), []).append((sha, when))
    return [rng.choice(buckets[q]) for q in sorted(buckets)]


def churn_before(repo: Path, when: datetime) -> int:
    """Commits touching the corpus in the trailing window before a cohort start.

    A covariate, not a confound — once the frame is calendar-uniform, "anchors captured in
    high-churn periods decay faster" becomes a finding the study can report.

    Counted against FULL history rather than the windowed population. Counting against the
    population truncates the trailing window for cohorts near WINDOW_START and reported 24
    commits for 2021Q1 where its neighbours had ~500 — an artifact of the window edge, not
    a quiet quarter.
    """
    lo = (when - timedelta(days=CHURN_WINDOW_DAYS)).date().isoformat()
    out = git(
        repo, "log", "--format=%H", f"--since={lo}",
        f"--until={when.date().isoformat()}", "--", CORPUS_PATH,
    )
    return len([ln for ln in out.splitlines() if ln.strip()])


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def commits_touching_corpus(repo: Path, until: datetime) -> list[tuple[str, datetime]]:
    out = git(
        repo, "log", "--format=%H %cI", f"--since={WINDOW_START}",
        f"--until={until.date().isoformat()}", "--", CORPUS_PATH,
    )
    rows = []
    for line in out.splitlines():
        sha, _, iso = line.partition(" ")
        if sha and iso:
            rows.append((sha, datetime.fromisoformat(iso)))
    return rows


def docs_at(repo: Path, sha: str) -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", sha, "--", CORPUS_PATH)
    return [
        p for p in out.splitlines()
        if Path(p).suffix.lower() in MARKDOWN_SUFFIXES
    ]


def read_many(repo: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """Read many blobs in one `git cat-file --batch`.

    One subprocess per cohort rather than one per document. On a blobless partial clone
    each individual `git show` costs a network round trip (~0.3s measured), so 3600 of them
    is 18 minutes of latency; batching lets git fetch the whole set at once.
    """
    if not paths:
        return {}
    request = "".join(f"{sha}:{p}\n" for p in paths).encode()
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=request, capture_output=True, check=True,
    )
    out, pos, result = proc.stdout, 0, {}
    for path in paths:
        end = out.find(b"\n", pos)
        if end == -1:
            break
        header = out[pos:end].decode(errors="replace")
        pos = end + 1
        parts = header.rsplit(" ", 2)
        if len(parts) != 3 or parts[1] != "blob":
            continue  # missing or not a blob
        size = int(parts[2])
        result[path] = out[pos : pos + size].decode("utf-8", errors="replace")
        pos += size + 1
    return result


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--docs-per-cohort", type=int, default=DOCS_PER_COHORT)
    args = ap.parse_args()

    analysis_date = datetime.fromisoformat(
        git(args.repo, "log", "-1", "--format=%cI").strip()
    )
    cutoff = analysis_date - timedelta(days=TRAILING_GAP_DAYS)

    population = commits_touching_corpus(args.repo, cutoff)
    print(f"corpus            {CORPUS_PATH}")
    print(f"analysis date     {analysis_date.date()}")
    print(f"cutoff            {cutoff.date()}  ({TRAILING_GAP_DAYS}d trailing gap)")
    print(f"population        {len(population)} commits touching the corpus since {WINDOW_START}")
    if not population:
        print("EMPTY POPULATION — the design cannot run")
        return 1

    rng = random.Random(SEED)
    starts = stratify_by_quarter(population, rng)

    per_cohort: list[dict[str, Any]] = []
    strata: dict[str, int] = {"numeric": 0, "identifier": 0, "prose": 0}
    horizon_observable = dict.fromkeys(OFFSETS_DAYS, 0)
    realised_n = 0
    sentences_per_doc: list[int] = []

    quarters = sorted({quarter_of(w) for _, w in population})
    print(f"eligible quarters {len(quarters)}  ({quarters[0]} .. {quarters[-1]})")
    print(f"\ncohorts           {len(starts)}, one per quarter (seed {SEED})")
    print(f"{'quarter':<9} {'start date':<12} {'churn':>6} {'anchors':>8} {'horizons':>9}")
    print("-" * 50)

    for sha, when in starts:
        churn = churn_before(args.repo, when)
        all_docs = docs_at(args.repo, sha)
        sampled = rng.sample(all_docs, min(args.docs_per_cohort * 3, len(all_docs)))

        contents = read_many(args.repo, sha, sampled)
        anchors_here = 0
        eligible_docs = 0
        for path in sampled:
            if anchors_here >= args.docs_per_cohort:
                break
            raw = contents.get(path)
            if raw is None or is_auto_generated(raw):
                continue
            spans = eligible_spans(raw)
            if not spans:
                continue
            eligible_docs += 1
            sentences_per_doc.append(len(spans))
            strata[stratum(rng.choice(spans))] += 1  # one anchor per document
            anchors_here += 1

        realised_n += anchors_here
        reachable = [d for d in OFFSETS_DAYS if when + timedelta(days=d) <= analysis_date]
        for d in reachable:
            horizon_observable[d] += anchors_here

        per_cohort.append({
            "sha": sha, "date": when.date().isoformat(),
            "quarter": quarter_of(when), "churn_90d": churn,
            "eligible_docs_in_sample": eligible_docs, "anchors": anchors_here,
            "horizons_observable": reachable,
        })
        print(f"{quarter_of(when):<9} {when.date()!s:<12} {churn:>6} "
              f"{anchors_here:>8} {len(reachable):>9}")

    print(f"\nrealised N        {realised_n}  (target {len(starts) * args.docs_per_cohort})")
    if sentences_per_doc:
        ordered = sorted(sentences_per_doc)
        print(f"eligible spans/doc  median {ordered[len(ordered) // 2]}  "
              f"min {ordered[0]}  max {ordered[-1]}")

    print("\nhorizon    observable anchors   censoring")
    for d in OFFSETS_DAYS:
        obs = horizon_observable[d]
        pct = 100.0 * (1 - obs / realised_n) if realised_n else 100.0
        print(f"  +{d:>4}d   {obs:>17}   {pct:>7.1f}%")

    total = sum(strata.values()) or 1
    print("\nstratum distribution at capture (sampling stays uniform — protocol 8a)")
    for name, count in sorted(strata.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<12} {count:>5}  {100.0 * count / total:>5.1f}%")

    if args.json:
        args.json.write_text(json.dumps({
            "generated_from": "scripts/study_feasibility.py",
            "corpus_head": git(args.repo, "rev-parse", "HEAD").strip(),
            "analysis_date": analysis_date.isoformat(),
            "seed": SEED,
            "population_commits": len(population),
            "realised_n": realised_n,
            "target_n": len(starts) * args.docs_per_cohort,
            "frame": "quarter-stratified",
            "horizon_observable": {str(k): v for k, v in horizon_observable.items()},
            "strata": strata,
            "cohorts": per_cohort,
        }, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
