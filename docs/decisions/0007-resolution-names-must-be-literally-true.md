# ADR-0007: Every resolution name must be literally true of every case that reaches it

**Status:** accepted
**Amends:** ADR-0005 (which introduced the widened bucket under its old name)

## Decision
Rename the valid outcomes:

| was               | now                | fires when                                             |
|-------------------|--------------------|--------------------------------------------------------|
| `VALID`           | `VALID`            | span hits, same place, context intact — nothing changed |
| `VALID_MOVED`     | `VALID_REPAIRED`   | span hits, position **or** context changed; anchor updated |
| `VALID_RELOCATED` | `VALID_RELOCATED`  | span hits under a different heading or document        |

The naming constraint, which applies to any future member: **each name must be literally
true of every case that reaches it.** Not "usually true", not "true of the motivating
example".

## Why
ADR-0005 was right that `VALID` should require a `context_hash` match — "nothing changed
near this anchor" is different information from "we found it", and the distinction is worth
reporting. The logic stands.

But widening the bucket made its name false. `VALID_MOVED` now fires for
`reword_neighbor`, where the span sits at byte offset 271 before the edit and byte offset
271 after it. Nothing moved. The name asserts a movement that did not happen.

This matters more here than in a normal codebase because `Resolution` is customer-facing:
it is rendered in the diff report and will propagate into every downstream doc. The pitch
is "we catch the small lie your green dashboard is telling you." A product making that
claim cannot ship a small lie in its own output. The cost of being caught in one is not
proportional to the size of the inaccuracy — it is the whole premise.

`VALID_REPAIRED` is true in every case that reaches it: the anchor's recorded position or
context no longer matched the corpus, and we updated it. `VALID_RELOCATED` is true in every
case that reaches it: the span's address — its document, its heading path, or both —
changed.

The rename also states the customer-relevant distinction more directly. What a customer
needs from this enum is *did this need repair, and did anyone have to look at it* — not a
taxonomy of edit shapes.

## Cost paid
`tests/test_anchors.py` asserted `Resolution.VALID_MOVED` in `test_position_is_never_identity`
and had to be touched, against the standing rule not to modify it. The change is one
identifier and no semantics: the test asserts the same outcome for the same mutation. The
rule exists to stop an implementation being fitted to a weakened spec; a directed rename is
neither.

The alternative — keeping `VALID_MOVED` as a Python enum alias so the old name resolves to
the new member — was rejected. It keeps the suite green without touching it, and leaves the
false name in the codebase and in anything that reads the enum by name, which is the entire
problem.

## Rejected
- **Leaving the name and narrowing the logic back.** Would restore the ADR-0005 defect:
  reporting "nothing changed" about a document that changed under the anchor.
- **`VALID_MOVED_OR_CONTEXT_CHANGED`.** Literally true and unusable.
- **An enum alias for the old name.** See above.

## Reverses if
Nothing. The specific names may change again; the constraint that produced them does not.
Any new member is checked against it before it ships, while the cost of a rename is still
one commit rather than a customer-visible break.
