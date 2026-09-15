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

The prior art this replaces: an internal spec-search system at a semiconductor company
identified evidence by `split_id`, a positional chunk index. Insert a paragraph near the top
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

## Build order — do not reorder

Phase 1 and 2 are the differentiator and have no prior art. Phases 3–5 are commodity and
were built elsewhere in five days. Building them first is the classic mistake.

1. **Anchors + diff.** No LLM, no metrics, no generation. Prove that given corpus v1 and v2,
   every anchor classifies correctly. `tests/test_anchors.py` is the spec; make it pass.
2. **Mutation harness.** Synthetic corpus + known edits + known correct classifications.
   This is simultaneously the test suite, the validation strategy with zero customers, and
   the artifact for the public study.
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

| outcome             | condition                                | action                    |
|---------------------|------------------------------------------|---------------------------|
| `VALID`             | span hash hits, same location            | none                      |
| `VALID_MOVED`       | span hash hits, position shifted         | silent repair             |
| `VALID_RELOCATED`   | heading changed/gone, span hash hits     | repair, low-priority note |
| `STALE`             | heading hits, span hash misses           | **flag for review**       |
| `AMBIGUOUS`         | span hash hits in 2+ locations           | **flag for review**       |
| `DESTROYED`         | nothing resolves                         | retire the test           |

`STALE` is the money case: the test still looks runnable but its expected answer is now
wrong. A suite full of `STALE` tests reports green while lying.

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

## Decision records

Any non-obvious choice gets a short ADR in `docs/decisions/NNNN-title.md`: what was decided,
why, what was rejected, what would reverse it. Write it at the moment of the decision, not
later. These are how the reasoning survives into future sessions and future engineers.

If a decision changes what we can promise a customer — not just how the code works — flag it
so it reaches the strategy side. Example: if PDF text extraction proves non-deterministic
across library versions, that changes the product contract, not just an implementation
detail.

## Context that is not in the code

- The prior system's failure: 29 of 59 real queries returned literally nothing. Pipeline
  trace read prefilter 0 → keyword 0 → embedding 0 → RRF 0. A five-question pilot two days
  earlier had scored recall@5 = 1.000. Nobody had filed a bug, because a plausible answer
  does not look like a failure. This is the class of bug Corpora exists to catch.
- The failure was lexical, not semantic: technical identifiers like `SLP_A_VAL=0`, `be=0`,
  `F:PCH_SOC_SYNC`, and Unicode dash variants broke tokenization before retrieval ever ran.
  Hence invariant 3 and the verbatim-token triage rule.
- Half the ground truth lived in spreadsheets nobody had indexed. Tables are first-class,
  ahead of PDF.
