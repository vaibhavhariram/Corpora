"""Specification for the observation/action split.

`resolve()` observes; `policy` decides. The property these tests exist to protect is
that no single observation can retire a test — retirement is destructive, permanent,
and invisible to the customer once done.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from corpora.anchors.policy import (
    DEFAULT_RETIREMENT_POLICY,
    RetirementPolicy,
    action_for,
    may_retire,
    needs_human,
    should_propose_retirement,
)
from corpora.models import NEEDS_REVIEW, Action, Resolution

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _history(
    *offsets_and_resolutions: tuple[int, Resolution],
) -> list[tuple[datetime, Resolution]]:
    """Build one anchor's observation history from (day offset, resolution) pairs."""
    return [(T0 + timedelta(days=d), r) for d, r in offsets_and_resolutions]


# --------------------------------------------------------------------------- #
# Per-resolution action
# --------------------------------------------------------------------------- #


def test_every_resolution_has_an_action() -> None:
    for resolution in Resolution:
        assert isinstance(action_for(resolution), Action)


def test_no_single_resolution_can_retire() -> None:
    """The whole point of the split. RETIRE is unreachable from one observation."""
    for resolution in Resolution:
        assert action_for(resolution) is not Action.RETIRE


def test_destroyed_watches_rather_than_retires() -> None:
    assert action_for(Resolution.DESTROYED) is Action.WATCH
    assert not needs_human(Resolution.DESTROYED)


def test_only_stale_and_ambiguous_cost_review_time() -> None:
    costly = {r for r in Resolution if needs_human(r)}
    assert costly == set(NEEDS_REVIEW) == {Resolution.STALE, Resolution.AMBIGUOUS}


def test_repairs_are_silent() -> None:
    assert action_for(Resolution.VALID) is Action.NONE
    assert action_for(Resolution.VALID_REPAIRED) is Action.REPAIR
    assert action_for(Resolution.VALID_RELOCATED) is Action.REPAIR_AND_NOTE


# --------------------------------------------------------------------------- #
# Retirement
# --------------------------------------------------------------------------- #


def test_one_destroyed_never_proposes_retirement() -> None:
    assert not should_propose_retirement(_history((0, Resolution.DESTROYED)))


def test_no_history_never_proposes_retirement() -> None:
    assert not should_propose_retirement([])


def test_sustained_absence_proposes_retirement() -> None:
    assert should_propose_retirement(
        _history(
            (0, Resolution.DESTROYED),
            (20, Resolution.DESTROYED),
            (40, Resolution.DESTROYED),
        )
    )


def test_a_burst_of_observations_is_not_a_sustained_absence() -> None:
    """Three checks in one afternoon is one event seen three times."""
    assert not should_propose_retirement(
        _history(
            (0, Resolution.DESTROYED),
            (0, Resolution.DESTROYED),
            (1, Resolution.DESTROYED),
        )
    )


def test_refill_resets_the_clock() -> None:
    """The emptied-in-one-commit-refilled-in-the-next case.

    This is the failure the split exists to prevent: a transient absence must not cost
    the customer a test.
    """
    assert not should_propose_retirement(
        _history(
            (0, Resolution.DESTROYED),
            (20, Resolution.DESTROYED),
            (30, Resolution.VALID),
            (60, Resolution.DESTROYED),
        )
    )


def test_retirement_needs_a_named_human() -> None:
    sustained = _history(
        (0, Resolution.DESTROYED),
        (20, Resolution.DESTROYED),
        (40, Resolution.DESTROYED),
    )
    assert should_propose_retirement(sustained)
    assert not may_retire(sustained, confirmed_by=None)
    assert not may_retire(sustained, confirmed_by="")
    assert may_retire(sustained, confirmed_by="a.reviewer")


def test_confirmation_alone_is_not_enough() -> None:
    """A human cannot retire a test the policy has not proposed."""
    assert not may_retire(
        _history((0, Resolution.DESTROYED)), confirmed_by="a.reviewer"
    )


def test_policy_is_configurable_and_defaults_are_conservative() -> None:
    assert DEFAULT_RETIREMENT_POLICY.consecutive_destroyed >= 2
    assert DEFAULT_RETIREMENT_POLICY.min_elapsed >= timedelta(days=1)

    impatient = RetirementPolicy(consecutive_destroyed=2, min_elapsed=timedelta(0))
    two = _history((0, Resolution.DESTROYED), (1, Resolution.DESTROYED))
    assert should_propose_retirement(two, impatient)
    assert not should_propose_retirement(two)
