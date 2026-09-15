# ADR-0002: Corpora never performs retrieval

**Status:** accepted

## Decision
No index, no embeddings, no vector store, no ranking, no reranking, no chunking-for-search.
The only interface to the system under test is the `Target` protocol.

## Why
Retrieval is a crowded, well-funded, commoditized category with incumbents at every layer.
Grading someone else's retrieval is not. The moment this repo contains a retriever, the
product is a search engine competing with Glean, Elastic, Vespa, and every RAG framework,
and the differentiator is gone.

It also keeps us model-agnostic and platform-neutral, which is the structural defense
against a platform vendor shipping this natively for their own data only.

## Rejected
- A "reference retriever" for comparison. Tempting, and it would immediately become the
  product. If a customer wants a baseline, they can point a second `Target` at one.

## Reverses if
Never, while the thesis holds. If this is reversed, the company has changed.
