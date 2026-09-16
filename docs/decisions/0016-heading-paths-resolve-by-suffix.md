# ADR-0016: A heading path resolves by suffix, not by full-ancestry equality

**Status:** accepted
**Amends:** ADR-0001 (heading semantics), the resolution cascade in CLAUDE.md
**Closes:** issue #7

## Decision
`heading_paths_resolve(anchor_path, candidate_path)` is true when the two paths share a
non-empty suffix. `["Handbook", "Termination"]` resolves an anchor captured at
`["Guide", "Termination"]`; `["Guide", "Shutdown"]` does not.

Applied in both places the cascade asks "does this heading still address the same thing":

- `_heading_span`, choosing which heading to read candidate spans from (exact match wins
  outright; otherwise longest shared suffix, ties broken on document order)
- the span-found-once branch, deciding `VALID_RELOCATED` versus `VALID_REPAIRED`

**The leaf is the address. Ancestors are context.**

## Why this is a bug and not a preference

**The cascade already made this call once.** Rule 3 exists because a renamed heading is not
a reason to lose an anchor — `VALID_RELOCATED` means "span found, heading changed or
missing." Exact full-ancestry matching honoured that at the leaf and contradicted it at the
parent. Rename the heading: handled. Rename its parent: not handled. Same event, two
answers, and only the arbitrary one was implemented.

**The bias direction decides it.** An ancestor rename plus a rewording reported `DESTROYED`:
no review, `Action.WATCH`, test carried forward with an expected answer that is now wrong.
That is a false negative on the money case. It also biases the study's staleness rate
**downward** — the one direction of error that wanting an impressive number would never
surface, and therefore the one most likely to survive unexamined.

**The failure was unbounded.** A phantom or renamed root corrupts every descendant in the
file. One commit renaming `# Guide` turns every anchor below it into a potential false
`DESTROYED`. Verified: a renamed root with a three-deep descendant now resolves `STALE`
where it previously resolved `DESTROYED`.

**Real corpora re-parent constantly.** Kubernetes documentation restructures sections
routinely, and the study runs on exactly that churn.

Spec-conformance was not a defence. CLAUDE.md rule 5 says the heading must resolve; what
*resolving* means was never decided. This decides it rather than overrides it.

## Why a repeated leaf name is not a new risk
`_heading_span` is reached only from `_resolve_missing_span` — that is, only after the span
was found nowhere in the snapshot. The span-hash count has already spoken by then, and
`AMBIGUOUS` is defined on it. Suffix matching widens which heading we read replacement text
from; it does not weaken how the evidence itself is disambiguated. Ties break on document
order so the result stays deterministic.

## What changed in the classifications
Two mutation rows added; the table is now 15.

| row | before | after |
|---|---|---|
| `rename_ancestor_heading` (span intact) | `VALID_RELOCATED` | `VALID_REPAIRED` |
| `rename_ancestor_and_reword_answer` | **`DESTROYED`** | **`STALE`** |

The first is a mislabel correction and moves no headline — under suffix semantics the
address still resolves, so nothing relocated. The second is the defect.

All thirteen pre-existing rows classify exactly as before. The review set
(`NEEDS_REVIEW`) gained `rename_ancestor_and_reword_answer` and lost nothing — verified by
computing the set difference in both directions before editing the test.

## The verifier edit this authorises
`tests/fixtures/mutations.py` gains two rows; `tests/test_anchors.py`'s
`test_only_stale_and_ancestor_need_review` assertion gains one name. This is an
**extension**, not a weakening: no existing row changed its expected classification, and no
name left the review set. That distinction is the whole reason `verifier_protected` demands
an ADR rather than just a label.

## Rejected
- **Leave it, document the bias in the study's methodology.** The safe default, and wrong.
  It ships a known false-negative on the product's central case in order to avoid changing
  eight lines, and asks the reader to discount the headline by an unquantified amount.
- **Match on the leaf only, ignoring depth.** Equivalent for every case seen so far, but
  discards information for free. Longest-suffix keeps a deeper agreement as a better match.
- **A seventh cascade outcome for "heading moved and span changed".** More faithful, and one
  more path through the cascade plus a customer-facing enum member for a distinction a
  reviewer does not act on differently. `STALE` with a note already says it.

## Reverses if
A corpus turns up where leaf heading names repeat so heavily that suffix matching routinely
reads candidate spans from the wrong section. The symptom would be `STALE` results whose
`candidate_spans` are unrelated to the anchor. Watch for it in the study; the fix would be
to require a minimum suffix length rather than to restore exact ancestry.
