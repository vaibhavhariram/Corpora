# ADR-0006: Three mutation rows corrected to match their stated intent

**Status:** accepted

## Context
`tests/fixtures/mutations.py` is the spec, and three of its thirteen rows could not pass as
written. Two were *provably* unsatisfiable: they handed `resolve()` a signal vector
identical to another row that expects a different answer. No implementation can separate
them, so this was not a question of getting the cascade right.

Measured against the fixture corpus, where `pos`/`heading`/`context` are the three signals
available at resolution time:

| row                 | pos | heading | context | expected      |
|---------------------|-----|---------|---------|---------------|
| `unicode_dash_swap` | T   | T       | **F**   | `VALID`       |
| `reword_neighbor`   | T   | T       | **F**   | `VALID_MOVED` |
| `no_change`         | T   | T       | T       | `VALID`       |
| `merge_documents`   | T   | T       | T       | `VALID_MOVED` |

The third row, `delete_section`, never executed at all: its precondition string did not
occur in `SPEC_A`, so `_edit()` raised `AssertionError` before any anchor was resolved. The
`DESTROYED` arm of the cascade had no coverage.

## Decision
Repair the three fixtures. Every `expected` classification is unchanged — the corpus and
the edits change so that each row performs the mutation its own description claims.

**1. `unicode_dash_swap` — the corpus had no dash to swap.**
`SPEC_A` contained `sideband`, with no hyphen anywhere in the document. The mutation
replaced it with `side–band`, *inserting* a dash rather than swapping one. The normalizer
maps en dash to ASCII hyphen; it cannot map an inserted dash to nothing. So the row
contradicted both its own description ("ASCII hyphen replaced with an en dash") and the
architecture table ("normalizer absorbs"), and the text genuinely differed after
normalization.

Fix: `SPEC_A` now reads `side-band`, and the mutation swaps that ASCII hyphen for an en
dash. Normalized v1 and v2 are now byte-identical, which is what "the normalizer absorbs
it" means, and the row now exercises the normalizer through the anchor path as intended.

**2. `merge_documents` — the merge landed below the anchor.**
`apply` produced `spec_a + spec_b`, placing the appended content *after* the anchored span.
The span stayed at offset 271 in both revisions, with its heading and its 400-character
context window untouched — locally indistinguishable from `no_change`.

Fix: merge as `spec_b + spec_a`. The span moves 271 → 443, which is what makes a merge a
`VALID_MOVED` rather than a no-op. Direction of concatenation is an authoring choice; which
side of the anchor the new content lands on is the entire content of the test.

**3. `delete_section` — precondition string did not match the corpus.**
The `old` string joined two sentences with `\n` where `SPEC_A` has a space.

Fix: correct the whitespace. The mutation removes the section body and leaves the
`## 2.1 S3 Entry` heading standing with nothing under it; that resolves to `DESTROYED` by
ADR-0005.

## Rejected
- **Bending the cascade to fit the rows.** Impossible for rows 1 and 2, and the attempt
  would have meant inventing a signal `resolve()` does not receive.
- **Changing the `expected` values instead.** `docs/architecture.md` states all three
  outcomes independently of the fixture code. The expectations were right; the edits that
  were supposed to produce them were wrong.
- **Deleting the heading too in `delete_section`.** Would also yield `DESTROYED`, but via a
  weaker path — it would stop exercising the "heading survives, body does not" branch,
  which is the one that has to distinguish `DESTROYED` from `STALE`.

## Consequence for the public study
These rows were silently not measuring what the table claims. Precision and recall on
staleness detection are still 13/13 against the corrected table, but any number quoted from
a run before this commit covered 12 rows, one of which was mislabeled. Nothing has been
published yet, so there is nothing to retract.

## Reverses if
The corrections are re-litigated with a different fixture corpus. The constraint they answer
does not go away: no two rows may present identical `pos`/`heading`/`context` signals and
expect different classifications. That is a property any future mutation table must hold.
