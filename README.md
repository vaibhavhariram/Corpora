# Corpora

**Unit tests for AI that reads your company's documents.**

Companies build AI search and Q&A over their own private documents and have no way to know
whether it works. The few who build a test set build it by hand at high expert cost — and
then the documents change, the expected answers silently become wrong, and the suite keeps
reporting green.

Corpora generates questions whose correct source is known, freezes them into a benchmark,
runs them against your retrieval system, scores deterministically, and detects when a
document change has invalidated a test.

## Status

Pre-alpha. Phase 1 of 5. `anchors/resolve()` is unimplemented and `tests/test_anchors.py`
is its specification.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # normalizer green, anchor tests red — that's correct
```

## What this is not

Not a retriever, not an index, not a vector database, not a RAG framework, not a dashboard.
See `docs/decisions/0002-no-retrieval-in-scope.md`.

## Where to start reading

1. `CLAUDE.md` — operating rules and invariants
2. `docs/architecture.md` — the plan and the reasoning behind it
3. `src/corpora/models.py` — the nine domain nouns
4. `tests/fixtures/mutations.py` — the mutation table, which is the product thesis

## License

MIT
