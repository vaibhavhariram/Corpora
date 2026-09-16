# CLAUDE.md

Operating instructions for this repository. Read fully before the first edit of any session.

## What this is

Corpora is a test suite for AI systems that read private document corpora. It generates
questions whose correct source is known, freezes them into a benchmark, runs them against
someone else's retrieval system, scores the result deterministically, and — the part that
makes this a product — detects when a document change has invalidated a test.

One sentence: **unit tests for AI that reads your company's documents.**

## The single most important thing in this repo

`src/corpora/anchors/` — a re-resolvable pointer to evidence inside a document.

The prior art this replaces: a prior enterprise deployment identified evidence by
`split_id`, a positional chunk index. Insert a paragraph near the top
of a document and every downstream `split_id` shifts. That system needed a dedicated audit
script to check whether expected chunks still existed, because they routinely did not.
That script was a patch on a broken identity model.

If evidence identity is positional, staleness detection is impossible and there is no product.
Anchors are content-addressed and resolve through a cascade. **Do not introduce positional
identity anywhere in the evidence path.**

## Invariants — never break these without an ADR

1. **Corpora never does retrieval.** No index, no embeddings, no vector store, no ranking,
   no reranking, no chunking-for-search. We grade someone else's retrieval. The moment this
   repo contains a retriever, the product has become a search engine and lost.

2. **No LLM in grading.** An LLM may generate candidate questions. It may never accept a
   test into a benchmark and may never influence a pass/fail. All scoring is deterministic.
   This constraint came from a validation architect who would not accept anything else, and
   it is a selling point in every regulated industry.

3. **One normalizer, versioned.** Every byte of text that gets hashed or shown to a
   generator passes through `corpus.normalize.normalize()`. `NORMALIZER_VERSION` is stamped
   into every `Snapshot`. Changing the normalizer invalidates every existing anchor —
   that is a breaking change and requires a version bump plus an ADR.

4. **Transport errors are not retrieval misses.** A timeout, TLS failure, proxy error, or
   auth rejection is classified as a `TransportError`, excluded from retrieval metrics, and
   reported separately. Counting a timeout as a miss makes recall lie.

5. **Comparisons are gated.** Two runs may only be compared if dataset hash, config hash,
   target identity, and query ID set all match. Every comparison reports aggregate deltas
   **and** per-query regressions. Aggregate-only hides the case where three specific queries
   broke while the mean held.

6. **Library first.** All logic lives in importable functions. `cli.py` contains argument
   parsing and nothing else. If there is logic in `cli.py`, it is in the wrong file.

7. **Retirement is never automatic, and never inferred from one observation.** `resolve()`
   observes; `anchors/policy.py` decides. Repair and review may be derived from a single
   resolution — they are cheap and reversible. Retirement is neither: it removes a test
   from the customer's coverage permanently and tells nobody. It requires a sustained run
   of `DESTROYED` observations over time *plus* a named human confirming. Sections get
   emptied in one commit and refilled in the next; a model that retires on one `DESTROYED`
   deletes coverage for a transient state. `Action.RETIRE` must stay unreachable from
   `action_for()`.

## Build order — do not reorder

Phase 1 and 2 are the differentiator and have no prior art. Phases 3–5 are commodity and
were built elsewhere in five days. Building them first is the classic mistake.

**The study runs before phase 3.** Order is: `diff/` → Kubernetes study → phase 3. The
study needs only corpus loader + anchors + diff + real Git history — no generation, no
targets, no metrics, no LLM. It is the shortest path from working code to the artifact
that gets replies, and it stress-tests the cascade against churn we did not author, which
is the only way to find the next class of bug that authored fixtures cannot reach.

1. **Anchors + diff.** No LLM, no metrics, no generation. Prove that given corpus v1 and v2,
   every anchor classifies correctly. `tests/test_anchors.py` is the spec; make it pass.
2. **Validation, in two halves. Both are required; they prove different things.**
   a. *Synthetic mutations.* Authored corpus + known edits + known classifications. This
      is a **unit test**: it proves the cascade classifies correctly when a document
      changes in way X. Necessary, and not saleable — nobody outside is moved by thirteen
      hand-written mutations.
   b. *Real churn — the Kubernetes study.* Capture anchors at commit A, resolve at commit
      B, across real history at volume. This produces **the rate**: what fraction of a
      golden set goes stale within K revisions, and how fast. That is the number a
      stranger cares about — "your golden set has a half-life, and here it is." It is the
      artifact that gets replies, and it cannot come from authored edits.
      Sampling must be random or exhaustive across history. **Never hand-pick the commit
      pairs** — curated pairs make it a demo, not a measurement.
3. **Targets + runner + metrics.** Adapter protocol, checkpointed execution, the full metric
   set including empty-result and error counts.
4. **Generation.** Direct LLM API call. Structured output: question, verbatim answer span,
   source heading. Reject any candidate whose quoted span is not found byte-identical in the
   source — a free grounding check with no judge model.
5. **Triage + accept gate.** Deterministic rules plus a CLI review queue. The learned gate
   comes after real accept/reject labels exist, which come from customers, not from us.

## Do not build

Web UI. Auth. Multi-tenancy. Hosting. Connectors beyond local directory and Git.
Observability. A plugin system. A learned accept gate. Anything with "agent" in the name.
Anything that scales past one corpus, one target, one reviewer.

## Domain model

Nine nouns. If a thing being built is not one of these or a function between them, it is
not v1. See `src/corpora/models.py`.

```
Document   raw file + normalized text + content hash
Snapshot   immutable capture of a whole corpus at one revision
Anchor     re-resolvable pointer into a snapshot          <- the core
Candidate  generated question + anchor + provenance + triage bucket
TestCase   promoted candidate, frozen, with review metadata
Benchmark  set of TestCases + snapshot ref + config hash
Run        benchmark x target x config -> outcomes
Report     metrics + per-test results + integrity status
Diff       snapshot A -> snapshot B -> affected anchors -> affected tests
```

## Resolution cascade

The output of anchor resolution *is* the staleness signal.

`resolve()` returns an **observation**. What to do about it is a separate decision, made
by `anchors/policy.py`. Never collapse the two columns — see invariant 7 and ADR-0008.

| observation (`Resolution`) | condition                            | default action (`Action`)   |
|----------------------------|--------------------------------------|-----------------------------|
| `VALID`                    | span hits, same place, context intact | `NONE`                     |
| `VALID_REPAIRED`           | span hits, position or context shifted | `REPAIR` (silent)         |
| `VALID_RELOCATED`          | span hits under a different heading or document | `REPAIR_AND_NOTE` |
| `STALE`                    | heading hits, span misses             | `REVIEW`                   |
| `AMBIGUOUS`                | span hits in 2+ locations             | `REVIEW`                   |
| `DESTROYED`                | nothing resolves                      | `WATCH` — **never retire**  |

Every name must be literally true of every case that reaches it. `VALID_REPAIRED` fires
when a span sits at its old offset inside edited surroundings, so it is not called
`VALID_MOVED` — nothing moved. The enum is customer-facing in the diff report, and a
product that sells "we catch the small lie your green dashboard is telling" cannot ship a
small lie in its own output. See ADR-0007.

`STALE` is the money case: the test still looks runnable but its expected answer is now
wrong. A suite full of `STALE` tests reports green while lying.

**A heading path resolves by suffix, not by full-ancestry equality.** The leaf is the
address; ancestors are context. Renaming `# Guide` to `# Handbook` leaves `## Termination`
addressing the same section, so an anchor beneath it is `VALID_REPAIRED` when its span is
intact and `STALE` when its span changed — not `DESTROYED`. Requiring exact ancestry made a
renamed root corrupt every anchor below it in the file, and biased the staleness rate
downward. See ADR-0016.

## Code rules

- Python 3.11+. Pydantic v2 for models. Typer for CLI. Pytest. No framework beyond these.
- **No Haystack.** It is a framework for building search. We do not build search.
- **No Ragas or DeepEval as core dependencies.** They carry metric opinions we do not want
  and they are adjacent competitors. Generation calls an LLM API directly.
- SQLite for storage, not Postgres. Single file, portable, zero ops, trivial self-hosting.
- Content hashing: SHA-256. Stable, boring, available everywhere.
- Type hints everywhere. `mypy --strict` should pass.
- **Never commit generated caches, build artifacts, or model outputs.** A PR was closed on
  the prior project for exactly this.

## Test discipline

- TDD for `anchors/` and `diff/`. The mutation table is the spec; tests come before code.
- Every mutation in `tests/fixtures/mutations.py` has exactly one correct classification.
- Deterministic tests only. Any test that calls an LLM is marked `@pytest.mark.llm` and is
  excluded from the default run.

## The loop

Work arrives as a GitHub issue labelled `agent:ready` and leaves as one PR. At most two
agent PRs are open at once — review capacity is the binding constraint, not throughput.

Before opening a PR, all four must be clean:

```bash
make invariants   # deterministic gate — scripts/check_invariants.py
pytest
mypy
ruff check src scripts
```

**Never open a red PR.** If it will not go green, comment on the issue saying exactly what
blocked you and stop. A red PR converts review time into debugging time.

`make invariants` mechanically enforces invariants 1, 2, 3, and 6 plus verifier protection
and orphan modules. It is deterministic on purpose: an LLM asked "does this add retrieval?"
is right most of the time and silently wrong occasionally, and ADR-0004 applies to our own
tooling before it applies to anyone else's. Invariants 4 and 5 are not greppable and belong
in `tests/` once `run/` and `report/` exist.

### Do not loop on these

Everything in `.github/CODEOWNERS` requires human review, and the list is not arbitrary —
these are the things where no test can state what "right" means:

- `tests/test_anchors.py`, `tests/fixtures/mutations.py` — the scorer
- `src/corpora/models.py` — enum names and semantics, which are customer-facing
- `CLAUDE.md`, `docs/architecture.md`, `docs/decisions/` — the rules themselves
- `scripts/`, `.github/`, `Makefile` — the loop's own machinery

That last group matters most. An agent that can edit `check_invariants.py` or a workflow
disables every guardrail in one PR, which is reward hacking one level up from editing tests.

Rule of thumb: **if you cannot state the test that proves it right, it is not loopable yet.**

## The bridge

`docs/status.md` is the bridge to the strategy side: current state, the number, what is next.
Ninety seconds, no diff required. Update it at the end of every session and keep it short —
it drifted to twenty-two sections before being split, which is the failure it exists to
prevent.

`docs/journal.md` holds the accumulated history. Nothing is pruned there.

## Decision records

Any non-obvious choice gets a short ADR in `docs/decisions/NNNN-title.md`: what was decided,
why, what was rejected, what would reverse it. Write it at the moment of the decision, not
later. These are how the reasoning survives into future sessions and future engineers.

If a decision changes what we can promise a customer — not just how the code works — flag it
so it reaches the strategy side. Example: if PDF text extraction proves non-deterministic
across library versions, that changes the product contract, not just an implementation
detail.

## Context that is not in the code

- The prior system's failure: a large fraction of real queries returned literally nothing,
  while a handful-of-questions pilot days earlier had scored perfectly. The pipeline trace
  showed zero candidates at every stage, which located the fault at the prefilter boundary
  rather than in ranking. Nobody had filed a bug, because a plausible answer does not look
  like a failure. This is the class of bug Corpora exists to catch.
- The failure was lexical, not semantic: technical identifiers like `PWR_SEQ_VAL=0`, `be=0`,
  `F:LINK_SYNC`, and Unicode dash variants broke tokenization before retrieval ever ran.
  Hence invariant 3 and the verbatim-token triage rule.
- Half the ground truth lived in spreadsheets nobody had indexed. Tables are first-class,
  ahead of PDF.
