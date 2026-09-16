"""Specification for how a heading path resolves after the document is restructured.

Suffix matching, not full-ancestry equality. See ADR-0016. These are the unit-level
properties; the end-to-end consequences are two rows in the mutation table.
"""

from __future__ import annotations

from corpora.anchors.resolve import heading_paths_resolve


def test_identical_paths_resolve() -> None:
    assert heading_paths_resolve(["Guide", "Termination"], ["Guide", "Termination"])


def test_a_renamed_ancestor_still_resolves() -> None:
    """The whole point. `# Guide` -> `# Handbook` does not move `## Termination`."""
    assert heading_paths_resolve(["Guide", "Termination"], ["Handbook", "Termination"])


def test_a_renamed_leaf_does_not_resolve() -> None:
    """The leaf IS the address. Renaming it is a relocation, which rule 3 already covers."""
    assert not heading_paths_resolve(["Guide", "Termination"], ["Guide", "Shutdown"])


def test_a_re_parented_section_resolves() -> None:
    """Promoted to top level, or pushed deeper — the tail is what identifies it."""
    assert heading_paths_resolve(["Guide", "Ops", "Termination"], ["Termination"])
    assert heading_paths_resolve(["Termination"], ["A", "B", "Termination"])


def test_an_unrelated_path_does_not_resolve() -> None:
    assert not heading_paths_resolve(["Guide", "Termination"], ["Other", "Networking"])


def test_a_span_under_no_heading_resolves_only_to_no_heading() -> None:
    """Document preamble, before any heading."""
    assert heading_paths_resolve([], [])
    assert not heading_paths_resolve([], ["Anything"])
    assert not heading_paths_resolve(["Anything"], [])


def test_matching_is_on_the_tail_not_the_head() -> None:
    """A shared ancestor with a different leaf is not a match — that would resolve every
    sibling section to every other one."""
    assert not heading_paths_resolve(["Guide", "A"], ["Guide", "B"])


def test_resolution_is_symmetric() -> None:
    a, b = ["Guide", "Ops", "Termination"], ["Handbook", "Termination"]
    assert heading_paths_resolve(a, b) == heading_paths_resolve(b, a)
