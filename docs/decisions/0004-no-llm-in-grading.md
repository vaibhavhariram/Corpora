# ADR-0004: An LLM may generate, never judge

**Status:** accepted

## Decision
LLMs are used for candidate question generation only. No LLM may accept a test into a
benchmark, and no LLM may influence a pass/fail outcome. All grading is deterministic.

## Why
Three reasons, in order of weight:

1. **Buyer requirement.** The validation architect on the prior project approved the eval
   design only with "no LLM-as-judge in routine PR evaluation" as an explicit condition.
   Regulated buyers — pharma, finance, defense, semiconductors — hold the same line. Every
   competing eval vendor pushes judge models; refusing to is a differentiator, not a
   limitation.
2. **Reproducibility.** A gate that returns different answers on identical input cannot
   block a merge.
3. **Trust.** "Who validates the validators" is an open research problem. We do not need
   to solve it to ship, so we route around it.

## Consequence
Generation gets a free, deterministic grounding check instead: the model must return the
answer span quoted verbatim, and we reject any candidate whose quoted span is not found
byte-identical in the source. This also defends against a model answering from pretraining
memory rather than from the document — essential on any public corpus.

## Reverses if
A customer demands judge-based scoring for a subjective criterion retrieval metrics cannot
express. Even then it belongs in a separate, clearly labeled, non-gating lane.
