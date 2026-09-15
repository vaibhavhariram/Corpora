"""Synthetic corpus + mutation harness.

This file is three things at once:

  1. the test suite for anchor resolution
  2. the validation strategy that works with zero customers
  3. the experiment behind the public study

Because we author both the corpus and the edits, ground truth is free. Every mutation has
exactly one correct classification. That yields precision and recall on staleness detection
itself, with no domain expert and no customer.

The fixture corpus deliberately imitates a real technical spec: numbered headings, technical
identifiers with `=` and `:`, an acronym that collides, a table, and a cross-reference.
Those are the shapes that broke retrieval on the system this design comes from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from corpora.models import Resolution

# --------------------------------------------------------------------------- #
# Fixture corpus
# --------------------------------------------------------------------------- #

SPEC_A = """\
# 1 Overview

This document defines the power sequencing behavior of the controller.

## 1.1 Scope

Applies to products PCH2 and PCH3. Legacy product PCH1 is out of scope.

# 2 Sleep States

## 2.1 S3 Entry

The controller asserts SLP_A_VAL=0 before transitioning to S3. The assertion window
is 12 milliseconds. Firmware must not issue sideband traffic during this window.

## 2.2 S3 Exit

On exit the controller deasserts SLP_A_VAL=1 and waits 40 milliseconds before
resuming telemetry. See section 3.1 for the reset interaction.

# 3 Reset

## 3.1 Warm Reset

A warm reset preserves the F:PCH_SOC_SYNC state. The handshake timeout is 250
milliseconds.

## 3.2 Cold Reset

A cold reset clears all state including F:PCH_SOC_SYNC.
"""

SPEC_B = """\
# 1 Telemetry

## 1.1 Sampling

Telemetry is sampled at 100 Hz on PCH2 and 200 Hz on PCH3.

## 1.2 Reporting

Reports are emitted every 500 milliseconds when be=1 is set.
"""

CORPUS_V1: dict[str, str] = {
    "spec-a.md": SPEC_A,
    "spec-b.md": SPEC_B,
}

# The spans tests anchor to. Each is unique in V1 unless a mutation makes it otherwise.
SPAN_S3_ENTRY = "The assertion window\nis 12 milliseconds."
SPAN_WARM_RESET = "The handshake timeout is 250\nmilliseconds."
SPAN_SCOPE = "Applies to products PCH2 and PCH3."


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mutation:
    name: str
    description: str
    apply: Callable[[dict[str, str]], dict[str, str]]
    anchored_span: str
    expected: Resolution
    note: str = ""


def _edit(corpus: dict[str, str], path: str, old: str, new: str) -> dict[str, str]:
    out = dict(corpus)
    assert old in out[path], f"mutation precondition failed: {old!r} not in {path}"
    out[path] = out[path].replace(old, new, 1)
    return out


MUTATIONS: list[Mutation] = [
    # ---- should resolve clean ------------------------------------------------
    Mutation(
        name="no_change",
        description="corpus is byte-identical",
        apply=lambda c: dict(c),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID,
    ),
    Mutation(
        name="whitespace_only",
        description="double spaces and trailing whitespace introduced near the anchor",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "before transitioning to S3.",
            "before  transitioning to S3.   ",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID,
        note="the normalizer must absorb this; if this test fails, normalize.py is wrong",
    ),
    Mutation(
        name="unicode_dash_swap",
        description="ASCII hyphen replaced with an en dash",
        apply=lambda c: _edit(c, "spec-a.md", "sideband", "side\u2013band"),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID,
        note="the exact class of change that broke real production queries",
    ),
    # ---- should repair silently ---------------------------------------------
    Mutation(
        name="insert_paragraph_above",
        description="a new paragraph is inserted above the anchored span",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "## 2.1 S3 Entry\n",
            "## 2.0 Preconditions\n\nAll rails must be stable.\n\n## 2.1 S3 Entry\n",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID_MOVED,
        note="THE canonical failure of positional chunk IDs; must not be STALE",
    ),
    Mutation(
        name="reword_neighbor",
        description="a neighboring sentence is reworded, the anchored span is untouched",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "Firmware must not issue sideband traffic during this window.",
            "Sideband traffic is prohibited for the duration of the window.",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID_MOVED,
        note="context changed, span did not; still valid",
    ),
    Mutation(
        name="rename_heading",
        description="the enclosing heading is renamed",
        apply=lambda c: _edit(c, "spec-a.md", "## 2.1 S3 Entry", "## 2.1 Entry into S3"),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID_RELOCATED,
    ),
    Mutation(
        name="move_section_to_other_file",
        description="the whole 3.1 section moves from spec-a into spec-b",
        apply=lambda c: {
            "spec-a.md": c["spec-a.md"].replace(
                "## 3.1 Warm Reset\n\nA warm reset preserves the F:PCH_SOC_SYNC state. "
                "The handshake timeout is 250\nmilliseconds.\n\n",
                "",
            ),
            "spec-b.md": c["spec-b.md"]
            + "\n## 1.3 Warm Reset\n\nA warm reset preserves the F:PCH_SOC_SYNC state. "
            "The handshake timeout is 250\nmilliseconds.\n",
        },
        anchored_span=SPAN_WARM_RESET,
        expected=Resolution.VALID_RELOCATED,
        note="must search other documents before concluding DESTROYED",
    ),
    Mutation(
        name="split_document",
        description="spec-a is split into two files at the section-3 boundary",
        apply=lambda c: {
            "spec-a.md": c["spec-a.md"].split("# 3 Reset")[0],
            "spec-a-reset.md": "# 3 Reset" + c["spec-a.md"].split("# 3 Reset")[1],
            "spec-b.md": c["spec-b.md"],
        },
        anchored_span=SPAN_WARM_RESET,
        expected=Resolution.VALID_RELOCATED,
    ),
    Mutation(
        name="merge_documents",
        description="spec-b is appended into spec-a and removed",
        apply=lambda c: {"spec-a.md": c["spec-a.md"] + "\n" + c["spec-b.md"]},
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.VALID_MOVED,
    ),
    # ---- MUST be flagged ----------------------------------------------------
    Mutation(
        name="reword_answer_sentence",
        description="the anchored sentence itself is reworded",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "The assertion window\nis 12 milliseconds.",
            "The controller holds the assertion for a fixed interval.",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.STALE,
        note="the test still runs and its expected answer is now wrong",
    ),
    Mutation(
        name="change_number_in_answer",
        description="a single value inside the anchored span changes",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "is 12 milliseconds.",
            "is 18 milliseconds.",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.STALE,
        note="nastiest case in the whole product: smallest possible edit, test now asserts "
        "a false fact, everything still looks green",
    ),
    Mutation(
        name="duplicate_section",
        description="the anchored section is copied into a second location",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "# 3 Reset",
            "## 2.3 S3 Entry (duplicate)\n\nThe controller asserts SLP_A_VAL=0 before "
            "transitioning to S3. The assertion window\nis 12 milliseconds.\n\n# 3 Reset",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.AMBIGUOUS,
    ),
    # ---- should retire ------------------------------------------------------
    Mutation(
        name="delete_section",
        description="the anchored section is removed entirely",
        apply=lambda c: _edit(
            c,
            "spec-a.md",
            "The controller asserts SLP_A_VAL=0 before transitioning to S3. "
            "The assertion window\nis 12 milliseconds.\n"
            "Firmware must not issue sideband traffic during this window.\n",
            "",
        ),
        anchored_span=SPAN_S3_ENTRY,
        expected=Resolution.DESTROYED,
    ),
]

MUTATIONS_BY_NAME = {m.name: m for m in MUTATIONS}
