"""Policy: what to DO about a resolution.

`resolve.py` observes. This module decides. They are separate files because the actions
are not equally reversible:

- a repair is silent, automatic, and undoable
- a review costs a human ten minutes
- a retirement removes a test from a customer's coverage permanently, and tells nobody

Only the first two can be inferred from a single observation. Retirement is the one
place where being wrong costs the customer something they cannot get back, so it needs
history plus a human, and it is the one action `resolve()` must never be able to cause.

See ADR-0008.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import NEEDS_REVIEW, Action, Resolution

# --------------------------------------------------------------------------- #
# Per-resolution action
# --------------------------------------------------------------------------- #

_ACTIONS: dict[Resolution, Action] = {
    Resolution.VALID: Action.NONE,
    Resolution.VALID_REPAIRED: Action.REPAIR,
    Resolution.VALID_RELOCATED: Action.REPAIR_AND_NOTE,
    Resolution.STALE: Action.REVIEW,
    Resolution.AMBIGUOUS: Action.REVIEW,
    Resolution.DESTROYED: Action.WATCH,
}


def action_for(resolution: Resolution) -> Action:
    """The action one resolution warrants on its own, with no history.

    Never returns RETIRE. A single DESTROYED means "not visible in this snapshot", which
    warrants recording the observation and carrying the test forward unchanged — see
    `should_propose_retirement` for the only path to retirement.
    """
    return _ACTIONS[resolution]


def needs_human(resolution: Resolution) -> bool:
    """Whether this resolution consumes review time. Review is the scarce resource."""
    return resolution in NEEDS_REVIEW


# --------------------------------------------------------------------------- #
# Retirement
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetirementPolicy:
    """When repeated DESTROYED observations justify *proposing* retirement.

    PROVISIONAL NUMBERS. These are placeholders, not measurements. The real distribution
    — how long a section typically stays missing before it comes back — comes out of the
    Kubernetes churn study. Do not quote these to a customer as tuned.
    """

    consecutive_destroyed: int = 3
    """How many consecutive DESTROYED observations before retirement is even proposed."""

    min_elapsed: timedelta = timedelta(days=14)
    """How long that run must span. Three observations ten minutes apart is one event
    observed three times, not a sustained absence."""


DEFAULT_RETIREMENT_POLICY = RetirementPolicy()


def should_propose_retirement(
    observations: Sequence[tuple[datetime, Resolution]],
    policy: RetirementPolicy = DEFAULT_RETIREMENT_POLICY,
) -> bool:
    """Whether a test is a *candidate* for retirement. Retires nothing by itself.

    `observations` is one anchor's history, oldest first. Only the trailing run of
    DESTROYED counts: a single successful resolution anywhere in between means the
    evidence came back, which resets the clock. That is the emptied-then-refilled case,
    and it is why retirement cannot be a property of one diff.
    """
    run: list[datetime] = []
    for when, resolution in reversed(observations):
        if resolution is not Resolution.DESTROYED:
            break
        run.append(when)

    if len(run) < policy.consecutive_destroyed:
        return False

    # run is newest-first; the span is from its oldest member to its newest.
    return (run[0] - run[-1]) >= policy.min_elapsed


def may_retire(
    observations: Sequence[tuple[datetime, Resolution]],
    *,
    confirmed_by: str | None,
    policy: RetirementPolicy = DEFAULT_RETIREMENT_POLICY,
) -> bool:
    """Whether a test may actually be retired.

    Requires both halves: the policy proposes, a named human confirms. Neither alone is
    sufficient, and there is deliberately no way to express "retire automatically".
    """
    if not confirmed_by:
        return False
    return should_propose_retirement(observations, policy)
