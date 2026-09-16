# ADR-0014: `tests/` is linted in CI, and the verifier files with it

**Status:** accepted

## Decision
`pr.yml` runs `ruff check src scripts tests`. Clearing the pre-existing findings required
editing two verifier files, so this ADR is also the record that authorises that edit under
`verifier_protected`.

## Why
Writing the `diff/snapshots.py` tests, ruff caught this:

```python
def test_comparable_snapshots_pass_the_guard() -> None:
    assert_comparable(_snap(V1, "v1"), _snap(V1, "v2")) is None   # no `assert`
```

A test that verified nothing and passed green. Ruff sees it (`B015`); CI did not, because
the lint step covered `src` and `scripts` only.

That is a **false-green verifier, in the directory that holds the verifier** — the precise
failure this product exists to catch in other people's systems, sitting inside our own test
suite, invisible to the gate that is supposed to protect it.

The gap is specific and worth naming. `verifier_protected` stops the mutation table being
**modified** without a deliberate act. Nothing stopped it being **degraded**. A row that
silently stops asserting is exactly as damaging as a row deleted, and only one of those was
caught. Linting `tests/` does not close that gap completely — no linter understands whether
an assertion is *meaningful* — but it closes the mechanical half, which is the half that
just bit us.

This is the third self-directed defect this project's discipline has found, and all three
are the same shape: **a check that failed to fail.** The line-based normalizer check that
went quiet on uncommitted work. The negative test that passed when it should have failed.
Now a test that asserted nothing. A check nobody has deliberately broken is not a verified
check — a sentence that has now earned its place in the study writeup.

## The verifier edit this authorises
Two findings, both in files under `verifier_protected`:

- `tests/fixtures/mutations.py` — `Callable` imported from `typing` rather than
  `collections.abc` (`UP035`)
- `tests/test_anchors.py` — import block ordering (`I001`)

**Both are import-only.** No assertion, expected classification, anchored span, or mutation
body changed. Verified two ways: a textual diff restricted to non-import lines came back
empty, and a fingerprint over all 13 rows — name, expected `Resolution`, anchored span, and
the exact corpus each `apply()` produces — was computed to confirm the table's semantics
are untouched. 92 tests green before and after.

This is the process working rather than overhead. The label and this ADR are what make a
verifier edit a deliberate act, and the cost of that ceremony for a formatting fix is about
four minutes.

## Rejected
- **Leaving `tests/` unlinted.** Keeps three cosmetic findings out of sight at the price of
  letting the next assertion-free test through silently.
- **Linting `tests/` but excluding the verifier files.** Exempts exactly the two files where
  a degraded assertion does the most damage.
- **A custom "every test contains an assert" check in `check_invariants.py`.** Ruff's `B015`
  and friends already cover the mechanical cases, and a bespoke AST rule would be one more
  piece of machinery needing its own negative tests.

## Reverses if
Ruff's default rule set starts producing noise in `tests/` that has nothing to do with
correctness. The response then is to narrow the rule selection, not to stop linting.
