#!/usr/bin/env python3
"""Execute the study in docs/study-protocol.md. Append-only; no analysis.

This script produces observations and nothing else. It computes no rate, no median, no
survival curve — `scripts/study_analyze.py` does that, reading the file this writes. The
split is deliberate: analysis can be re-run and argued over without re-running the study,
and a runner that also reported a headline would invite adjusting a parameter and re-running
until the headline moved.

Output is JSONL, one line per (anchor, horizon) observation, appended and never rewritten.

Sampling is imported from `study_feasibility.py` rather than reimplemented, so the cohorts
and anchors are provably the ones the pre-registered feasibility check described. Same seed,
same functions, same draw.

Usage:
    python scripts/study_run.py --repo <clone> --out docs/study/observations.jsonl
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from corpora.anchors.resolve import capture
from corpora.corpus.snapshot import load_directory
from corpora.diff.build import build_diff


def _load_feasibility() -> Any:
    """Import the pre-registered sampling code by path, without editing it."""
    spec = importlib.util.spec_from_file_location(
        "study_feasibility", ROOT / "scripts" / "study_feasibility.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = _load_feasibility()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def commit_at_or_before(repo: Path, ref: str, when: datetime) -> str | None:
    """Newest commit touching the corpus at or before `when`, walking `ref`.

    `ref` is explicit and load-bearing. `git log` walks HEAD by default, and this runner
    detaches HEAD to each cohort's own commit — so the default would only ever find
    ANCESTORS of the cohort start, i.e. the cohort commit itself. Every "later" snapshot
    would equal its own base, every anchor would resolve VALID, and the study would report
    that documentation never goes stale. Observed: 2800/2800 observations with
    observed_sha == cohort_sha before this was fixed.
    """
    out = git(
        repo, "log", "--format=%H", "-1", f"--until={when.isoformat()}",
        ref, "--", F.CORPUS_PATH,
    ).strip()
    return out or None


def commits_touching_corpus(repo: Path, ref: str, until: datetime) -> list[Any]:
    """Population of candidate cohort starts, walking `ref`.

    Local rather than imported from the feasibility module for one reason: that version
    takes no ref and walks HEAD. The feasibility check never checks anything out, so HEAD is
    always the branch tip there and it is correct in that context. Here it is not — and the
    failure is silent, producing a truncated population and a smaller, differently-drawn
    sample rather than an error. See ADR-0018.
    """
    out = git(
        repo, "log", "--format=%H %cI", f"--since={F.WINDOW_START}",
        f"--until={until.date().isoformat()}", ref, "--", F.CORPUS_PATH,
    )
    rows = []
    for line in out.splitlines():
        sha, _, iso = line.partition(" ")
        if sha and iso:
            rows.append((sha, datetime.fromisoformat(iso)))
    return rows


def churn_before(repo: Path, ref: str, when: datetime) -> int:
    """Trailing-window churn, walking `ref` for the same reason as above."""
    lo = (when - timedelta(days=F.CHURN_WINDOW_DAYS)).date().isoformat()
    out = git(
        repo, "log", "--format=%H", f"--since={lo}",
        f"--until={when.date().isoformat()}", ref, "--", F.CORPUS_PATH,
    )
    return len([ln for ln in out.splitlines() if ln.strip()])


def snapshot_at(repo: Path, sha: str, when: datetime) -> Any:
    """Check out one revision and load it through the real loader."""
    git(repo, "clean", "-qfd")
    git(repo, "checkout", "-q", "--detach", "--force", sha)
    return load_directory(repo / F.CORPUS_PATH, source=f"git:{sha}", captured_at=when)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--feasibility", type=Path,
                    default=ROOT / "docs" / "study" / "feasibility.json")
    ap.add_argument("--limit-cohorts", type=int, default=None)
    args = ap.parse_args()

    # Never `rev-parse HEAD`: a previous run leaves the repo detached, and the whole
    # population would then be drawn from an old commit's ancestry without complaint.
    ref = git(args.repo, "rev-parse", args.ref).strip()
    analysis_date = datetime.fromisoformat(
        git(args.repo, "log", "-1", "--format=%cI", ref).strip()
    )
    cutoff = analysis_date - timedelta(days=F.TRAILING_GAP_DAYS)
    population = commits_touching_corpus(args.repo, ref, cutoff)

    # Cross-check against the pre-registered feasibility run. Two independently computed
    # values of the same quantity disagreeing is what caught ADR-0018; this makes that
    # check automatic rather than lucky.
    expected = json.loads(args.feasibility.read_text()) if args.feasibility.exists() else {}
    if expected.get("population_commits") not in (None, len(population)):
        raise RuntimeError(
            f"population is {len(population)} commits but the pre-registered feasibility "
            f"run measured {expected['population_commits']}. The sample would not be the "
            f"one the protocol describes. Refusing to run."
        )
    rng = random.Random(F.SEED)
    cohorts = F.stratify_by_quarter(population, rng)
    if args.limit_cohorts:
        cohorts = cohorts[: args.limit_cohorts]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with args.out.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps({
            "record": "run_header",
            "corpus_head": ref,
            "corpora_head": git(ROOT, "rev-parse", "HEAD").strip(),
            "analysis_date": analysis_date.isoformat(),
            "seed": F.SEED,
            "cohorts": len(cohorts),
            "offsets_days": list(F.OFFSETS_DAYS),
        }) + "\n")

        for index, (sha, when) in enumerate(cohorts, start=1):
            quarter = F.quarter_of(when)
            churn = churn_before(args.repo, ref, when)
            base = snapshot_at(args.repo, sha, when)

            # --- capture, exactly as the feasibility check described ---
            docs = sorted(base.documents)
            rng.shuffle(docs)
            anchors, meta = [], {}
            for doc_key in docs:
                if len(anchors) >= F.DOCS_PER_COHORT:
                    break
                document = base.documents[doc_key]
                raw = (args.repo / F.CORPUS_PATH / doc_key).read_text(encoding="utf-8")
                if F.is_auto_generated(raw):
                    continue
                spans = F.eligible_spans(raw)
                if not spans:
                    continue
                span = rng.choice(spans)
                try:
                    anchor = capture(document, span, base.snapshot_id)
                except ValueError:
                    continue  # non-unique after normalization; protocol section 6
                anchors.append(anchor)
                meta[anchor.span_hash] = {
                    "doc_key": doc_key, "stratum": F.stratum(span),
                }

            print(f"[{index}/{len(cohorts)}] {quarter} {when.date()} "
                  f"{len(anchors)} anchors churn={churn}", flush=True)

            # --- observe at each reachable horizon ---
            for offset in F.OFFSETS_DAYS:
                target = when + timedelta(days=offset)
                if target > analysis_date:
                    continue
                later_sha = commit_at_or_before(args.repo, ref, target)
                if later_sha is None:
                    continue
                if later_sha == sha:
                    # The corpus cannot be compared against itself. If this ever fires it
                    # is a bug in snapshot selection, not a quiet quarter with no commits,
                    # and recording it would manufacture a VALID observation out of thin
                    # air. Fail loudly rather than publish an artifact.
                    raise RuntimeError(
                        f"cohort {index} offset +{offset}d resolved to its own base commit "
                        f"{sha[:12]} — snapshot selection is broken"
                    )
                later = snapshot_at(args.repo, later_sha, target)
                diff = build_diff(base, later, anchors, computed_at=target)

                for result in diff.resolutions:
                    info = meta[result.anchor.span_hash]
                    sink.write(json.dumps({
                        "record": "observation",
                        "cohort": index, "quarter": quarter,
                        "cohort_sha": sha, "cohort_date": when.date().isoformat(),
                        "churn_90d": churn,
                        "span_hash": result.anchor.span_hash,
                        "doc_key": info["doc_key"], "stratum": info["stratum"],
                        "offset_days": offset, "observed_sha": later_sha,
                        "resolution": result.resolution.value,
                    }) + "\n")
                    written += 1

                for anchor, reason in diff.unresolvable:
                    sink.write(json.dumps({
                        "record": "unresolvable",
                        "cohort": index, "span_hash": anchor.span_hash,
                        "offset_days": offset, "reason": reason[:200],
                    }) + "\n")
                sink.flush()

    git(args.repo, "clean", "-qfd")
    git(args.repo, "checkout", "-q", "--force", "main")
    print(f"\nwrote {written} observations to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
