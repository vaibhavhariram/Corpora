# Status

Update at the end of each working session. This is the bridge to the strategy side —
short, factual, no narrative.

## Loop: parked
The stopping rule is answered. #1 and #2 were written by hand in one session, both green;
the loop produced zero lines and never executed. Finish #3 and the study by hand.

The infrastructure stays committed and dormant. `make invariants` runs regardless and has
earned its place three times over — it is not the part that was speculative. The agent loop
specifically solves a throughput problem that does not exist here: one serial critical path,
one reviewer. Revisit when there is a cofounder, or when the work is genuinely parallel.

Issue #4 (cli) stays open and unlabelled.

## Current phase
Phase 1 complete: anchors, policy, corpus loader (#1), `diff/` (#2, #3). **The study is
next** — nothing else stands between here and it.

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
- nothing. Next is `diff/build.py` (#3), the last item before the study.

## diff set-diff (issue #2, done by hand)
`src/corpora/diff/snapshots.py` — `diff_snapshots()` and `assert_comparable()`. 79/79 green.

The set arithmetic is four lines. The guard is the part that earns its place: a normalizer
or loader version change invalidates every anchor captured under the old version, so a diff
across one reports **our own version bump as corpus staleness** — a confident pile of STALE
and DESTROYED that describes nothing that happened to the customer's documents. It raises;
there is deliberately no permissive mode, because shipping a warning there would mean
shipping the exact failure we sell against.

Loader versions are compared **per loader, where both snapshots use it**, not as whole
dicts. Adding spreadsheets to a corpus introduces an `xlsx` entry on one side only; failing
on that would make growing a corpus impossible while saying nothing about whether the
Markdown anchors still hold.

A rename reads as one removal plus one addition, and that is correct rather than a gap —
`doc_key` is a locator (ADR-0010), and the anchors inside a renamed file resolve to
VALID_RELOCATED via the cascade. The document diff is report metadata; `resolutions` carries
the meaning.

## Corpus loader (issue #1, done by hand)
`src/corpora/corpus/loaders/markdown.py` and `src/corpora/corpus/snapshot.py`. Snapshot
construction is no longer test code. 65/65 green, `mypy --strict` clean.

**It found a bug that would have corrupted the study.** The fixture parser matched
headings across the whole document, so a shell comment inside a fenced code block parsed
as an H1:

    # Pods              -> heading (right)
    ```bash
    # Create a pod      -> heading (WRONG)
    ```
    ## Pod lifecycle    -> path ["Create a pod", "Pod lifecycle"]  (WRONG ancestry)

The invented headings are noise. The corrupted ancestry is the damage: it silently changes
`heading_path` on a *real* heading, and `heading_path` resolution is what separates `STALE`
from `DESTROYED`. Kubernetes docs are dense with shell and YAML blocks, so this would have
moved the headline numbers — and no test would have caught it, because the fixture corpus
contains no fences and all 39 tests passed either way.

Found by running the parser against realistic input instead of reading it. Third time this
project has found a defect that way, second time it was invisible to a green suite.

Fixed with fence awareness (backtick and tilde, any length, indented, info strings, unclosed
runs to EOF) and five tests. ADR-0013 records that and the rest of the loader's boundaries:
`snapshot_id` is content not clock, undecodable bytes raise rather than substituting U+FFFD,
dotted paths and symlinks are skipped, Setext headings are a known gap.

`tests/conftest.py` now delegates to the real loader rather than reimplementing it — which
is how `doc_key = filesystem path` survived in fixtures for weeks while `models.py` asserted
the opposite. A fixture that reimplements the thing under test agrees with itself forever.

## Blocked
- **One action, yours: `gh secret set ANTHROPIC_API_KEY`** (or `/install-github-app`).
  Note the first docs PR needs `gh pr merge N --squash --admin` — its author is also its only
  eligible reviewer, and GitHub forbids self-approval. Agent PRs are authored by the GitHub
  App, so they can be approved normally; this only affects PRs opened under your own account.
  Issue #4 is created and deliberately **not** labelled `agent:ready` — labelling it now
  would fire a run that dies immediately on the missing key. Label it the moment the secret
  exists; that is the first live test of the loop.

  GitHub Pro is active (the protection endpoint went 403 → 404) and branch protection is
  applied, so CODEOWNERS now has force.

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

## diff build (issue #3, done by hand)
`src/corpora/diff/build.py`. 92/92 green. Three traps, each of which ships a wrong number
rather than an error:

1. **No pre-filtering to `changed_docs`.** An anchor in an *unchanged* document whose span
   was duplicated into a changed one must still be `AMBIGUOUS`. Filtering by `doc_key`
   never looks at it and reports `VALID` — silently, toward a false green.
2. **Per-anchor isolation, narrow on purpose.** `ValueError` only. A bare `except Exception`
   would turn every future defect in `resolve()` into a silently shrinking denominator.
3. **`Diff.unresolvable`, separate from `resolutions`.** Your addition, and the one that
   would have shipped a wrong number. An anchor captured under an older
   `NORMALIZER_VERSION` is a fact about our tooling, not the customer's documents — not
   `DESTROYED`, not `STALE`, never in a denominator. Given a different *shape* from
   `resolutions` rather than a seventh enum case, so the two cannot be pooled by accident.

## Fourth false-green, found this session
PR #6's `review` job reported **pass in 9 seconds having done nothing.** Two independent
skip paths, both green:

- `anthropic_api_key: ""` — secret unset
- `Skipping action due to workflow validation: the workflow file must have identical
  content to the version on the default branch`

The second is the dangerous one. The action refuses to run whenever `pr.yml` differs from
`main` — a deliberate protection against a PR rewriting the workflow that reviews it.
Correct of the action. Dangerous of us: **any PR editing `pr.yml` silently disables the
reviewer for itself and still shows green.** `CODEOWNERS` guarantees a human looks at the
change; it does nothing about the reviewer quietly not running, and the green tick actively
argues that it did.

Now fails loudly with the reason in the annotation. Verified: `review` is red on PR #6 and
says why.

That is four self-directed defects, all the same shape — **a check that failed to fail.**
The line-based normalizer check that went quiet on uncommitted work. The negative test that
passed when it should have failed. The test that asserted nothing. The reviewer that
reported green having skipped. Worth a line in the study writeup: the discipline that finds
these is the same one we are selling.

## The critical path

```
#1 loader  ->  #2 #3 diff  ->  k8s study  ->  outreach with a real number
```

Four items. Everything else in the repo — cli, report rendering, targets, metrics,
generation — is **off** this path and waits.

The study is the only artifact that changes a stranger's behavior. The repo alone does not;
it is a scaffold with one implemented module. "Your golden set has a half-life of N weeks,
here is the data" does.

Issue #4 (cli) is deliberately off the critical path. It exists to test the loop, not to
advance the product.

## Decision rule for the loop

The gate is good and has now caught two bugs in itself, both because a negative test failed
to fail. But **the loop has not yet written a single line of product code.** Three sessions
of infrastructure, zero output. Acceptable now; a problem if it continues.

So, a stopping rule decided in advance rather than in the moment:

- **#4 produces a working CLI in one run** → the loop works. Label #2 and move.
- **#4 takes more than one more session of debugging triggers, permissions, or payloads**
  → kill the loop and write #1, #2, #3 by hand.

`resolve()` shipped by hand in a single session. The loop is supposed to save time, not
become the project. Write the rule down now, because the sunk-cost argument is much more
persuasive after another session of near-misses.

## Loop state
- **Branch protection on `main`:** required check `invariants`, code-owner review required,
  force-push and deletion blocked, conversation resolution required.
- `enforce_admins` is deliberately **false**. As the sole code owner you cannot approve your
  own PR, so enforcing on admins would deadlock you on anything you open yourself. The agent
  is not an admin and is fully blocked; for you it turns a silent merge into an explicit
  override, which is the deliberate second action that was wanted.
- **Labels:** `agent:ready` (input), `agent` (counts against the WIP cap), `verifier-change`.
- **Issues:** #1 loader, #2 diff set-diff, #3 diff build, #4 cli. None labelled yet.
- **First labelled issue is #4, not #1.** The loop is untested: `issues: [labeled]` is not in
  the action's documented event list, the WIP cap has never declined anything, and the
  reviewer has never gated on `needs: invariants` in a real run. The first labelled issue is
  not "build the loader" — it is "does any of this fire." #4 is small, real, off the critical
  path, and already gated by `library_first`. Label #2 only after watching the loop work end
  to end. **#1 was built by hand** rather than waiting on the loop, because it is first on
  the critical path and the loop is blocked on a secret only you can set.

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

A second refinement, found the same way: `normalizer_versioned` was line-based, so a
comment or docstring edit would have demanded a `NORMALIZER_VERSION` bump — invalidating
every anchor ever captured in exchange for rewording prose. It now compares parsed ASTs with
bare string statements stripped, so only changes that could alter normalization trip it.
Verified in all three directions: comment-only passes, docstring-only passes, a changed dash
mapping or regex still fails.

Also landed: `.github/CODEOWNERS` (including `/scripts/` and `/.github/` — your catch),
`pr.yml` with the reviewer gated behind `needs: invariants`, and `agent-dev.yml` with a real
WIP cap that counts open labelled PRs rather than relying on `concurrency:`.

**Scrub item 1 done (ADR-0011).** Fixture identifiers renamed to generic equivalents across
fixtures, tests, the normalizer's prose and the docs, while it was still free. The AST
refinement above is what made it possible to touch `normalize.py`'s docstrings without a
spurious version bump. 39/39 still green.

## Decisions needing a strategy call
- none outstanding. Two settled this session, both yours:
  - **ADR-0010: `doc_key` is a locator, not identity.** The docstring was wrong, not the
    code. Identity is `span_hash`; the cascade already searches other documents, so a rename
    resolves correctly today with no rename detection and no state. Unblocks the loader.
  - **ADR-0012: the study's headline unit is calendar time**, with releases as a secondary
    cut and commits as the raw measurement. "Your golden set has a half-life of roughly N
    weeks" transfers to every buyer; releases are a Kubernetes artifact that most of the
    audience does not have, and commit counts confound documentation decay with project
    velocity. Decided before the run rather than after, for the same reason ADR-0009 fixes
    the sampling method up front.
  - **ADR-0011: the repo publishes with the study, not before.** Pro instead of public. The
    pre-publish scrub is recorded there as a precondition so it survives the eight weeks —
    including that the fixture rename is the one item whose price goes up once branch
    protection lands.

## Open questions
- **`tests/` is not linted in CI.** `pr.yml` runs `ruff check src scripts`. Writing #2's
  tests, ruff caught `assert_comparable(...) is None` with no `assert` — a test that
  verified nothing and passed. That is the exact class of defect this project exists to
  catch, and CI would not have seen it. Adding `tests` to the lint step means first fixing
  three pre-existing findings, two of which are in verifier files and so need a
  `verifier-change` label plus an ADR. Small, deliberate, worth doing.
- `RetirementPolicy` thresholds are unmeasured placeholders. First real output of the k8s
  study should be the distribution that replaces them.
- Four pre-existing `ruff` findings remain in scaffold files (import ordering in
  `models.py` and `test_anchors.py`, `Callable` import in `mutations.py`, `datetime.UTC`
  in `conftest.py`). Cosmetic, untouched, not worth a commit of their own.
