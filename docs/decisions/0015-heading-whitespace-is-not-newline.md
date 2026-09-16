# ADR-0015: The heading regex matches spaces and tabs, not `\s`

**Status:** accepted
**Bumps:** `MARKDOWN_LOADER_VERSION` → `builtin-markdown-1.1.0`

## Decision
`_HEADING` becomes `^(#{1,6})(?:[ \t]+(.+))?$`. Two changes: the whitespace class is
`[ \t]` rather than `\s`, and the title group is optional so an empty heading stays a
heading with an empty title.

## The defect
`\s` matches newlines. `.` does not. So on a hashes-only line, `\s+` consumed the newline
and the blank line after it, and `(.+)$` captured the **next** non-blank line as the
heading's title.

An empty ATX heading is valid CommonMark, and `normalize()` strips trailing whitespace, so
a line written `"# "` arrives at the parser as `"#"` and triggers it.

When the swallowed line was itself a heading, the damage compounded:

```
# Pods            ->  (1, ["Pods"])
#                 ->  (1, ["## Lifecycle"])   <- phantom; the hashes are inside the TITLE
## Lifecycle      ->  gone entirely
### Termination   ->  (3, ["## Lifecycle", "Termination"])
## Networking     ->  (2, ["## Lifecycle", "Networking"])
```

The phantom is level 1, so it becomes root ancestor of **every heading below it in the
file** — one stray line corrupts `heading_path` for every anchor in the rest of the
document.

## Why it mattered
Verified end to end, not argued. With the stray `#` present in both snapshots and the
answer reworded:

| | classification | `needs_review` |
|---|---|---|
| before the fix | `DESTROYED` | 0 |
| after the fix | `STALE` | 1 |

`STALE` is the money case. It was being routed to `Action.WATCH`, invisible to the
reviewer, and `STALE` vs `DESTROYED` is exactly what the study reads its headline off.

Same damage class ADR-0013 was written to close for fenced code blocks, arriving by a
different door — and invisible for the same reason: the fixture corpus contains no empty
headings, so all 92 tests passed either way. The fence exclusion does not help, because a
stray `#` is prose, not code.

## Found by an adversarial review, and one claim was wrong
Five independent review lenses over `diff/build.py` produced 13 candidate findings; each
was then handed to a refute-by-default verifier. Twelve were refuted. This was the one that
survived, and it was not in `build.py` at all — it was in the loader written one commit
earlier.

The verifier also corrected part of the original claim. The reviewer asserted that removing
a stray `#` from an otherwise untouched document would report `VALID_RELOCATED` instead of
`VALID`; the correct answer there is `VALID_REPAIRED`, because deleting the line shifts the
span's offset. That half is a bucket swap inside the valid family and moves no headline. The
`STALE` → `DESTROYED` half is the defect and stands alone. Recording this because "the
review found something" and "the review was right about everything it found" are different
claims, and only the first one is true.

## What this does NOT fix
The first attempt at a regression test conflated two defects and kept failing after the fix
was correct. Isolating them showed a **separate, pre-existing limitation**: renaming an
ancestor heading *and* rewording the answer in the same commit still yields `DESTROYED`,
with no empty heading anywhere. `_heading_span` requires exact full-ancestry equality, so a
renamed grandparent makes every descendant a miss.

That is spec-conformant — rule 5 requires the heading path to resolve, and it genuinely does
not — so changing it means changing the cascade's semantics, which is a CLAUDE.md-level
decision and not a patch. Filed as issue #7 with three options sketched. Its bias is
downward on the measured staleness rate, which understates our own headline; worth noting
that this is the one direction of error that wanting an impressive number would never catch.

## Why the version bump
`heading_path` and heading offsets change for any document containing an empty heading, so
anchors captured under `1.0.0` are not comparable. `assert_comparable` compares loader
versions by exact equality, so the specific number carries no semantics — `1.1.0` versus
`2.0.0` behaves identically. The number is documentation; the inequality is the mechanism.
No benchmark exists yet, so the practical cost of the bump is zero, which is precisely why
it should be spent now rather than after one does.

## Remaining known gaps in this parser
Recorded so they are accepted rather than forgotten:

- Setext (underlined) headings are not recognised (ADR-0013)
- Trailing closing sequences — `## Title ##` — are not stripped, so the title retains them
- HTML blocks are not excluded the way fenced code blocks are

None appear in Kubernetes documentation in a form that matters, and each would be a further
version bump.

## Reverses if
Nothing. `\s` in a line-anchored multiline pattern is a defect, not a trade-off.
