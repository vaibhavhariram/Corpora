# ADR-0005: `VALID` requires a context match; an emptied heading is `DESTROYED`

**Status:** accepted

## Decision
Two tie-breaks in the resolution cascade, neither of which was pinned down by
`docs/architecture.md`:

1. **Rule 1 (`VALID`) requires `context_hash` to match as well as the position.** A span
   found at its recorded offset inside edited surroundings is `VALID_MOVED`, not `VALID`.
2. **A heading that survives with an empty body resolves to `DESTROYED`, not `STALE`.**
   `STALE` additionally requires at least one non-empty candidate span beneath the heading.

## Why

**On (1).** The architecture table says "span hash hits, same location → `VALID`", which
left "same location" undefined. Offset equality alone is not evidence that the location is
the same — it is evidence that the byte count above the span did not change, which is a
coincidence, not a verification. Two mutation rows depend on the distinction:
`reword_neighbor` leaves the span at the identical offset while rewriting the sentence next
to it, and must still be reported as a repair rather than as "nothing happened."

The cost of being wrong here is asymmetric and cheap in one direction. `VALID` and
`VALID_MOVED` are both auto-repairable and neither consumes review time (CLAUDE.md:
"Review is the scarce resource"), so widening `VALID_MOVED` costs nothing. Reporting
`VALID` for a document that changed under the anchor costs the diff its credibility.

This also gives `context_hash` a defined job in the valid path. Previously it was described
only as a repair aid in the stale path.

**On (2).** `STALE` means "the text still looks runnable but its expected answer is now
wrong — a human must judge the new text." If the section was emptied, there is no new text
to judge. `tests/test_anchors.py::test_stale_reports_what_the_text_says_now` encodes this
directly: a `STALE` result must populate `candidate_spans`. A `STALE` with nothing in it
spends a reviewer's attention to tell them the evidence is gone, which is what `DESTROYED`
already says, in the bucket that retires the test.

## Rejected
- **`VALID` on offset equality alone.** Makes `reword_neighbor` and `no_change`
  indistinguishable, and reports "unchanged" about a changed document.
- **Comparing the document's `content_hash` against the previous snapshot.** Would separate
  the cases, but `resolve()` receives only the new snapshot and an `Anchor`, and `Anchor`
  records no document hash. Adding one would make every anchor in a document invalid
  whenever any byte of that document moved — reintroducing exactly the whole-document
  coupling that content-addressed anchors exist to avoid.
- **`STALE` whenever the heading resolves, empty or not.** Sends empty sections to the
  review queue, which is the resource the cascade is designed to conserve.

## Reverses if
Real corpora show sections that are legitimately emptied in one commit and refilled in the
next. Then an emptied heading is a transient state rather than a retirement, and it should
become `STALE` with an explicit "section emptied" note. Nothing observed so far suggests
this; revisit against real Git churn in the Kubernetes study.
