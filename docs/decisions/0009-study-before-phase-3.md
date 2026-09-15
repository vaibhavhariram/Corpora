# ADR-0009: The study is a rate, and it runs before phase 3

**Status:** accepted
**Amends:** CLAUDE.md "Build order — do not reorder"

## Decision
Two things, one sequencing and one framing.

**Sequencing.** After `diff/` lands, the Kubernetes churn study runs next. Phase 3
(targets + runner + metrics) comes after it. New order: `diff/` → study → phase 3.

**Framing.** The synthetic mutation table and the study are different artifacts proving
different claims, and must stop being described as one thing:

- **13 synthetic mutations = a unit test.** It proves the cascade classifies correctly
  when a document changes in way X. Necessary. Not saleable.
- **The study = a rate.** Across real commits to a real corpus, what fraction of anchors
  go stale within K revisions, and how fast. This is the number that makes a stranger
  care.

## Why the framing matters
We authored both the corpus and the edits in the synthetic table, so classifying them
correctly is table stakes, not evidence. Nobody outside is moved by thirteen hand-written
mutations — the obvious response is "you graded your own homework," and it is fair.

The claim that lands is **"your golden set has a half-life, and here it is."** Not "we
classify mutations correctly" but "the test set you paid an expert to build is already N%
wrong, and here is how fast it decayed." That requires real churn at volume. It cannot be
produced by authored edits at any quantity.

By this framing phase 2 is half done: the synthetic half is complete, the real half is not
started, and the real half is the one that goes in an email.

## Why the sequencing
The study needs corpus loader + anchors + diff + real Git history. Nothing else — no
generation, no targets, no metrics, no LLM, no API key. It is the shortest path from the
code that exists today to the artifact that gets replies.

Phase 3 is commodity work that was built elsewhere in five days. Doing it first spends the
project's most expensive resource — time before anyone outside has seen anything — on the
part that is least differentiated.

The second reason is technical and matters as much. Every bug found in Phase 1 so far came
from fixtures we wrote, and three of them were wrong *because* we wrote them by reasoning
rather than running. Real commit history is churn nobody authored: no shared assumptions
with the implementation, and no way for an error in our mental model to be reproduced
identically in both the test and the code. It is the only available source of the next
class of bug.

## Method constraint, non-negotiable
Anchors are captured at commit A and resolved at commit B where **neither commit was
chosen for convenience.** Sampling is random or exhaustive across history.

Hand-picked commit pairs produce a demo. Worse, a reader who suspects curation discounts
the entire number, and they cannot tell the difference from outside — which means the
sampling method has to be stated in the writeup, not just followed.

## Rejected
- **Phase 3 first, study later.** The original build order. Optimizes for a complete
  product over an early signal, and delays the only artifact that can be shown to someone
  outside.
- **Publishing the 13-row result as the study.** It is a unit test. Publishing it as
  evidence invites the "graded your own homework" reply and spends first-contact
  credibility on the weaker of the two claims.
- **Curating commit pairs that show dramatic staleness.** Produces a better-looking number
  that does not survive one question about methodology.

## Reverses if
The study comes back with a rate too low to be interesting — if real corpora turn out not
to invalidate their own test sets at a meaningful rate, the product thesis is weaker than
assumed and that is worth knowing before phase 3, not after. That is the same reason to
run it early.
