# Status

Update at the end of each working session. This is the bridge to the strategy side —
short, factual, no narrative.

## Current phase
Phase 1 — anchors. Complete. Loop infrastructure landed. Loader is next, then `diff/`.

## Done
- Domain model. Now split: `Resolution` observes, `Action` decides (ADR-0008).
- Versioned normalizer, with technical-identifier handling.
- Anchor capture.
- **`anchors/resolve()` — the cascade.** 13/13 mutation rows classify correctly. The two
  decisive rows verified the right way round: `change_number_in_answer` → `STALE`
  (reporting "18 milliseconds" as what the text says now), `insert_paragraph_above` →
  `VALID_REPAIRED` (span shifts 271 → 320, repaired silently, never flagged).
- **`anchors/policy.py`** — the observation/action seam. `Action.RETIRE` is structurally
  unreachable from a single resolution.
- 39/39 green, `mypy --strict` clean, `ruff` clean across `src/corpora/anchors` and the
  new tests.

## In progress
- nothing. Next is the corpus loader (issue #1), then `diff/`.

## Blocked
- **Two actions only you can take**, and the loop does not run until both are done:
  1. Upgrade to GitHub Pro. Branch protection and rulesets currently return
     `403 Upgrade to GitHub Pro or make this repository public`, so CODEOWNERS is
     inert until then — the file exists and enforces nothing.
  2. `gh secret set ANTHROPIC_API_KEY` (or `/install-github-app`).

  Everything else is written, tested, and committed.

## Both strategy calls landed

**1. Enum renamed (ADR-0007).** `VALID_MOVED` → `VALID_REPAIRED`. The name was false:
the widened bucket fires for `reword_neighbor`, where the span sits at offset 271 before
and after the edit. Nothing moved. Renamed before `diff/` and before the enum reaches
report rendering. The constraint is now written down for future members — each name must
be literally true of every case that reaches it.

Cost: this required touching `tests/test_anchors.py`, against the standing rule. One
identifier, no semantics — same assertion, same mutation, same outcome. An enum alias
would have kept the suite untouched and left the false name in the codebase, which is the
thing being fixed.

**2. Observation split from action (ADR-0008), and retirement defanged.** `resolve()`
returns an observation and cannot cause a retirement. `DESTROYED` maps to `WATCH`: record
it, carry the test forward unchanged. Retirement needs a sustained run of `DESTROYED`
over time *plus* a named human — `may_retire(..., confirmed_by=...)`, where neither half
alone is sufficient. Recorded as invariant 7.

The refill case is pinned by a test: emptied in one commit, refilled in the next, run
resets, nothing retires. Hysteresis defaults (3 observations spanning 14 days) are
**placeholders, not measurements** — they get tuned from the k8s churn data and are not to
be quoted to a customer as tuned.

This dissolved the emptied-heading open question rather than answering it. It only
mattered because `DESTROYED` retired things.

## The study is a rate, not the 13 rows (ADR-0009)
Correcting a conflation in the last status note.

- **13 synthetic mutations = a unit test.** Proves the cascade classifies correctly when a
  document changes in way X. Necessary. Not saleable — we authored both the corpus and the
  edits, so "you graded your own homework" is a fair reply.
- **The study = the rate.** Across real commits to a real corpus, what fraction of anchors
  go stale within K revisions, and the distribution of how fast. "Your golden set has a
  half-life, and here it is."

**Phase 2 is half done.** Synthetic half: complete. Real half: not started, and it is the
half that goes in an email to Brandon.

## Build order revised (ADR-0009)
`diff/` → **k8s study** → phase 3. Not straight to targets/runner/metrics.

The study needs only corpus loader + anchors + diff + Git history — no generation, no
targets, no metrics, no LLM. Shortest path from working code to an artifact that gets
replies, and it stress-tests the cascade against churn we did not author.

That second reason is doing real work. Every Phase 1 bug so far came from fixtures we
wrote, and three were wrong *because* we wrote them by reasoning instead of running. Real
history is the only source available that cannot reproduce our own mental model back to us.

Method constraint, recorded in CLAUDE.md and ADR-0009: **capture at commit A, resolve at
commit B, neither chosen for convenience.** Random or exhaustive sampling across history.
Hand-picked pairs make it a demo, and the sampling method has to be stated in the writeup —
a reader who suspects curation discounts the whole number and cannot tell from outside.

## Loop infrastructure (this session)
Deterministic gate first, one reviewer for the residue. The framing correction was yours and
it was right: most invariants are mechanically checkable, and putting a prose reviewer on a
mechanically checkable constraint is ADR-0004 violated in our own tooling.

`make invariants` — seven checks, pure stdlib, ~2s, zero tokens, never flaky. Each one
verified in both directions (planted a violation, confirmed the failure, reverted):

| check | invariant | negative test |
|---|---|---|
| `no_retrieval` | 1 | planted `import chromadb` → caught |
| `dependency_allowlist` | 1 | added `langchain` to pyproject → caught |
| `no_llm_in_grading` | 2 | planted `import anthropic` in `anchors/` → caught |
| `normalizer_versioned` | 3 | edited normalizer, left version → caught |
| `verifier_protected` | discipline | both branches tested: label+ADR passes, either missing fails |
| `library_first` | 6 | branching in `cli.py` → caught |
| `no_orphan_modules` | scope creep | untested module → caught |

One bug found by testing rather than reasoning: the change-sensitive checks originally used
`git diff base...HEAD`, which sees only *committed* work. `make invariants` run locally
before a commit was silently blind. Now diffs from the merge-base against the working tree.
A gate that goes quiet exactly when you are still editing is a gate you learn to ignore.

Also landed: `.github/CODEOWNERS` (including `/scripts/` and `/.github/` — your catch),
`pr.yml` with the reviewer gated behind `needs: invariants`, and `agent-dev.yml` with a real
WIP cap that counts open labelled PRs rather than relying on `concurrency:`.

## Decisions needing a strategy call
- none outstanding. Two settled this session, both yours:
  - **ADR-0010: `doc_key` is a locator, not identity.** The docstring was wrong, not the
    code. Identity is `span_hash`; the cascade already searches other documents, so a rename
    resolves correctly today with no rename detection and no state. Unblocks the loader.
  - **ADR-0011: the repo publishes with the study, not before.** Pro instead of public. The
    pre-publish scrub is recorded there as a precondition so it survives the eight weeks —
    including that the fixture rename is the one item whose price goes up once branch
    protection lands.

## Open questions
- **The fixture rename is cheaper today than later.** Renaming `SLP_A_VAL` /
  `F:PCH_SOC_SYNC` / `PCH2` touches `tests/fixtures/mutations.py`. Right now that is a free
  edit. Once branch protection is on it needs a `verifier-change` label and an ADR. Not
  urgent — the repo is staying private — but it is the only scrub item with a rising price.
- `RetirementPolicy` thresholds are unmeasured placeholders. First real output of the k8s
  study should be the distribution that replaces them.
- The study needs a defined unit for "K revisions" — commits touching the corpus, calendar
  time, or releases. Commits are easiest; releases are probably what a customer actually
  experiences. Worth deciding before the run, since it shapes the headline number.
- Four pre-existing `ruff` findings remain in scaffold files (import ordering in
  `models.py` and `test_anchors.py`, `Callable` import in `mutations.py`, `datetime.UTC`
  in `conftest.py`). Cosmetic, untouched, not worth a commit of their own.
