# Architecture

## The problem in one paragraph

Companies build AI search and Q&A over their own private documents. Almost none of them can
tell whether it works. The minority who build a test set build it by hand, at enormous
expert cost, and then their documents change and the test set silently becomes wrong. The
suite keeps reporting green. Nobody notices, because noticing requires knowing which test
depended on which paragraph of which version of which document.

## What Corpora is not

Not a retriever. Not an index. Not a vector database. Not a RAG framework. Not an
observability dashboard. Corpora reads documents, makes durable pointers into them, asks
another system questions, scores the answers deterministically, and watches for the moment
a document change invalidates a pointer.

This boundary is the most important architectural fact in the project. Every temptation to
"just add a small retriever for X" ends with a search company that has no differentiator.

## Module map

```
corpus/      load + normalize + snapshot + content-hash
anchors/     capture and resolve durable evidence pointers   <- core
diff/        snapshot -> snapshot -> affected anchors -> affected tests
generate/    LLM candidate synthesis (documents and query logs)
triage/      deterministic bucketing rules
review/      accept gate, queue, promotion to benchmark
benchmark/   freeze, integrity audit, load
targets/     adapter protocol + http / subprocess / python
run/         execution, checkpointing, config binding, transport classification
metrics/     recall@k, MRR, MAP, nDCG, context precision, wrong-top-1, latency, empties, errors
report/      render, same-contract comparison gate, PR comment
ci/          GitHub Action
```

---

## corpus/

Loads documents from a source, normalizes text, hashes content, produces a `Snapshot`.

**Loaders, in priority order:** Markdown, plain text, XLSX/CSV, PDF.

Tables come before PDF deliberately. On the system this design is derived from, XLSX-heavy
documentation was identified as a major missing retrieval surface a week into the project,
and a row-level spreadsheet indexer with semantic header detection had to be built. Half
the ground truth lived in tables. Schedules, equipment lists, register maps, parameter
tables — this is where technical corpora keep their facts.

**PDF is a hazard.** Text extraction is non-deterministic across libraries and versions: two
extractors produce two different strings for the same page, which produces two different
hashes, which destroys anchors. Policy: one pinned extractor, version locked, extractor
version stamped into the `Snapshot`. Anchors are only valid within an extractor version.
State this contract explicitly to customers.

### normalize.py

The single most load-bearing small file in the repo.

On a prior deployment, query-side and index-side text went through different normalization,
which meant the same token could be looked up one way and stored another. The fix was
described internally as "a vocabulary migration that may require reindexing" — i.e. changing
normalization invalidates everything downstream. Same is true here, which is why
`NORMALIZER_VERSION` exists and is stamped into every snapshot.

What it must handle:

- Unicode normalization to NFC.
- Dash variants (en, em, figure, non-breaking hyphen, minus sign) collapsed to ASCII hyphen.
  A spec author typing an en dash instead of a hyphen broke real queries.
- Whitespace variants (non-breaking space, thin space, tab) collapsed to single ASCII space.
- Line endings normalized; trailing whitespace stripped; runs of 3+ blank lines collapsed.
- **Case preserved.** `PWR_SEQ_VAL` and `pwr_seq_val` are different identifiers. Do not lowercase.
- **Technical identifiers preserved byte-for-byte.** Tokens containing `=`, `:`, `_`, mixed
  case with digits, or hex-like patterns must not be split, spaced, or re-cased.

---

## anchors/

### Why not chunk IDs

See ADR-0001. Short version: positional identity shifts on edit, so a test pointing at
"chunk 47" silently points somewhere else after a paragraph is inserted above it. This is
the failure mode the entire product exists to fix; reproducing it internally would be fatal.

### Anchor fields

```python
doc_key           # content-stable document identity, not a filesystem path
heading_path      # ["3 Fire Protection", "3.2 Dampers", "3.2.1 Rated Assemblies"]
span_hash         # SHA-256 of the normalized answer text
context_hash      # SHA-256 of normalized surrounding window
char_range        # position at capture time — weakest signal, kept only for repair
snapshot_id       # which corpus revision this was captured against
```

Redundancy is deliberate. Any single signal can break; the cascade uses whichever survive,
and *which ones broke* is the diagnostic output.

### The cascade

Implemented in `anchors/resolve.py`. Order matters — the first matching rule wins.

1. `span_hash` found exactly once, at `char_range`, with `context_hash` intact → `VALID`
2. `span_hash` found exactly once under the same heading, position or context changed →
   `VALID_REPAIRED`
3. `span_hash` found exactly once, under a different `heading_path` or in a different
   document → `VALID_RELOCATED`
4. `span_hash` found in 2+ locations → `AMBIGUOUS`
5. `heading_path` resolves but `span_hash` is absent under it → `STALE`
6. Nothing resolves → `DESTROYED`

`STALE` is the product. The test still runs, still looks healthy, and its expected answer is
now wrong. Everything else is either a silent repair or an observation to record.

These six are **observations, not instructions.** `resolve()` reports what it found;
`anchors/policy.py` decides what to do about it. The names are chosen so that each is
literally true of every case that reaches it — rule 2 fires when a span sits at its old
offset inside edited surroundings, so it is `VALID_REPAIRED` rather than `VALID_MOVED`,
because nothing moved. See ADR-0007.

`DESTROYED` in particular is a statement about one snapshot, not a verdict on the test. It
never retires anything. Repair and review are cheap and reversible; retirement removes a
test from a customer's coverage permanently and silently, so it needs a sustained run of
`DESTROYED` observations plus a named human. See ADR-0008.

`context_hash` is used for fuzzy repair when the span changed only in whitespace or
punctuation that the normalizer did not absorb. Treat a context-only match as `STALE` with a
suggested correction, never as `VALID` — the answer text changed, and a human decides.

---

## diff/

Answers: what changed between corpus revision A and revision B, and which tests are affected.

A `Snapshot` is already a map of `doc_key -> content_hash`. Diffing two snapshots is a set
operation on that map, so identifying changed documents is nearly free. The real work is
re-resolving every anchor that lives inside a changed document.

**Generic snapshot diffing is the engine. Git is a convenience layer**, not a requirement:

- Generic works for any source — SharePoint export, network drive, S3 bucket, PDFs emailed
  by a standards body. Costs storage for snapshots.
- Git pre-filters candidate files faster and lets `snapshot_id` be a commit SHA, so a
  benchmark can be described as "frozen at `abc123`".

Build generic first. Add the Git layer as an optimization once generic is correct.

---

## generate/

Two sources, both required:

- `from_documents` — sample source documents, ask an LLM for a question plus a verbatim
  answer span plus the governing heading.
- `from_query_log` — if the customer has real queries, that is the most valuable generation
  source available. Real questions people actually asked, deduplicated. Do not skip this
  because synthetic is easier.

**Grounding check, free and deterministic:** the model must return the answer span quoted
exactly. If that string is not found byte-identical in the normalized source, reject the
candidate. No judge model needed. This also defends against a model answering from
pretraining memory rather than from the document — critical on any public corpus.

**Generation and evaluation data must be disjoint.** Documents sampled for generation are
excluded from the evaluation pool, or the benchmark measures memorization.

---

## triage/

Deterministic bucketing. No LLM. Buckets, derived from the prior system's scheme:
five primary categories, two exploratory, four reject, across three eligibility lanes. Only
`accepted` + `primary` records are promoted into a frozen benchmark.

Mandatory rules:

- **Verbatim technical token rule.** Every technical-looking token in the question must
  appear byte-identical in the anchored span. If the generator wrote `PWR_SEQ_VAL = 0` with
  spaces and the document says `PWR_SEQ_VAL=0`, the test is testing the wrong string. Reject.
- Answerability: the anchored span must actually contain the answer.
- Deduplication against existing benchmark questions.
- Applicability: the question must be answerable within a single applicability scope, or it
  must declare that it spans scopes.

---

## Benchmarks come in two kinds

The prior design specified both on day three and it is easy to forget one.

- **Frozen.** Curated, human-accepted, small (30–60 questions). This is what CI gates on.
- **Held-out.** Synthetic, uncurated, larger. This is what tells you the system is not
  overfitting to the frozen set.

`Benchmark.kind` distinguishes them.

---

## Applicability is first-class

A test is not "question → expected document". It is "question, *within this filter context*,
→ expected document".

On that prior deployment the context was customer/product applicability, enforced as a hard
binary gate. In construction it is jurisdiction and client firm. In pharma it is product and
region. Hence `TestCase.applicability: dict[str, str]`, and "correct document, wrong
applicability scope" is its own failure-mode tag rather than a plain miss.

---

## targets/

The entire interface to the system under test:

```python
class Target(Protocol):
    def search(self, query: str, top_k: int, **filters) -> list[Hit]: ...
```

`Hit` carries `doc_key`, `text`, `score`, optional `native_id`, and optional `trace: dict`.

The `trace` field matters. On the prior system, localizing a catastrophic failure required
per-stage candidate counts — prefilter, keyword branch, embedding branch, RRF. The trace
read `0 → 0 → 0 → 0`, which proved the failure was at the prefilter boundary and not in
ranking or reranking. If a target can expose stage counts, capture them; they turn "it
failed" into "it failed here."

Adapters: `HttpTarget`, `SubprocessTarget`, `PythonTarget`.

---

## run/

- Immutable run configuration, SHA-256 bound to both dataset and config.
- Atomic checkpoint writes with resume. Long runs against slow enterprise endpoints will be
  interrupted.
- **Transport error classification** — timeout, TLS, proxy, auth, DNS — kept separate from
  retrieval outcomes. On a prior deployment a run returned mostly empty results alongside a
  handful of transport errors; because errors were classified separately, that run was
  correctly reported as "workflow validated, quality not measured" rather than as a
  catastrophic quality regression.
- **`Run.identity`.** Results are only interpretable relative to the access scope of the
  identity that executed them. A run by a user who cannot see half the corpus is not a
  quality measurement. Record it. (Permission-aware *evaluation* is deferred; recording the
  identity is not.)
- Secret-safe reporting: never serialize tokens or credentials into a report.

---

## metrics/

Full set, all deterministic:

`context_precision`, `recall@1`, `recall@3`, `recall@5`, `recall@10`, `MRR`, `MAP`, `nDCG`,
`top-1 wrong-citation rate`, `median latency`, `p95 latency`, `empty_result_count`,
`error_count`.

The last two are not optional. On a prior deployment, the empty-result count is what exposed the entire failure. A metrics module that reports only ranking quality will
average a catastrophic outage into a mediocre-looking score.

**Cost tracking is a known gap in the prior work and should be in v1 here.** An eval that
scores quality but not cost or latency cannot adjudicate a change that trades one for the
other — and the single cleanest finding on the prior system (an embedding change rejected
despite *lower* latency) was exactly that kind of trade.

---

## report/

- Render a scorecard.
- **Same-contract comparison gate:** refuse to compare two runs unless dataset hash, config
  hash, target identity, and query ID set all match. This gate is what turns a comparison
  from an eyeball diff into evidence.
- Report aggregate deltas **and** per-query regressions. On the prior system the decisive
  finding was "three previously-passing queries regressed" — invisible in the aggregate.
- Integrity status: the result of re-resolving every anchor in the benchmark before scoring.
  A run whose benchmark has unresolved anchors is not a valid measurement.

---

## ci/

A GitHub Action is a v1 deliverable, not a nice-to-have. It is how a customer actually
consumes this.

Shape, from the prior system's working workflow: deployed preflight check → run the frozen
benchmark → upload artifacts → post or update a PR comment. **Marker-based update-in-place**
— the comment carries a hidden marker and is edited on each run, rather than appending a new
comment every time.

---

## Validation with zero customers

Two halves, proving different things. Both are required and they are not interchangeable.

### Half one — synthetic mutation (a unit test)

Author the corpus and the edits, so ground truth is free.

| mutation                              | correct classification |
|---------------------------------------|------------------------|
| no change                             | `VALID`                |
| whitespace-only edit                  | `VALID` (normalizer absorbs) |
| Unicode dash swapped for ASCII hyphen | `VALID` (normalizer absorbs) |
| insert paragraph above the anchor     | `VALID_REPAIRED`       |
| reword a neighboring sentence         | `VALID_REPAIRED`       |
| rename the heading                    | `VALID_RELOCATED`      |
| move the section to another file      | `VALID_RELOCATED`      |
| split one document into two           | `VALID_RELOCATED`      |
| merge two documents                   | `VALID_REPAIRED`       |
| **reword the answer sentence**        | **`STALE`**            |
| **change a number inside the answer** | **`STALE`**            |
| duplicate the section                 | `AMBIGUOUS`            |
| delete the section                    | `DESTROYED`            |

This yields precision and recall *on staleness detection itself*, with no expert and no
customer. It proves the cascade classifies correctly when a document changes in way X.

**It is not the study, and it is not the pitch.** Thirteen hand-written mutations will not
move a stranger — we authored both the corpus and the edits, so of course we classify them
correctly. Treat this as what it is: the unit test that has to pass before the study is
worth running.

### Half two — real churn (the study)

The saleable number is **a rate**, and it can only come from history nobody authored:
across N thousand real commits to a real corpus, what fraction of anchors went stale
within K revisions, and what does the distribution of how-fast look like?

That is the claim a stranger cares about: **your golden set has a half-life, and here it
is.** Not "we classify mutations correctly" but "the test set you paid an expert to build
is already N% wrong, and here is how fast it decayed."

Corpus: **Kubernetes documentation.** Markdown in Git, thousands of commits, real heading
structure, versioned API references, heavy cross-linking, and structurally similar to most
companies' internal docs.

Method constraints, both load-bearing:

- **Capture anchors at commit A, resolve at commit B, with neither chosen for
  convenience.** Sampling is random or exhaustive across history. Hand-picked commit pairs
  produce a demo, not a measurement, and a reader who suspects curation discounts the
  whole number.
- **Run it before phase 3.** The study needs only corpus loader + anchors + diff + Git
  history. No generation, no targets, no metrics, no LLM. Running it early also stress-
  tests the cascade against churn we did not author — the only way to find the class of
  bug that authored fixtures structurally cannot reach.

Caveat: Kubernetes docs are saturated in pretraining data. The verbatim-span grounding check
in `generate/` is not optional on a public corpus — it is what prevents a model from
answering from memory instead of from the document.
