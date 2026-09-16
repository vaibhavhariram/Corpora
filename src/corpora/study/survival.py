"""Kaplan-Meier survival estimation for the staleness study.

Right-censored time-to-event data needs a survival estimator. The naive alternative — "what
percentage went stale within 90 days" — silently drops every anchor not yet observed that
long, which on this design is 14.3% of the sample at the 365-day horizon.

No model, no randomness, no clock. The headline number is produced by arithmetic that can be
checked by hand, for the same reason grading is deterministic (ADR-0004).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    """One anchor's outcome: when it was last seen, and whether the event occurred.

    `time` is the horizon in days at which the event was first observed, or — when `event`
    is False — the last horizon at which the anchor was observed still surviving.
    """

    time: float
    event: bool


@dataclass(frozen=True)
class SurvivalPoint:
    time: float
    at_risk: int
    events: int
    survival: float


def kaplan_meier(observations: Sequence[Observation]) -> list[SurvivalPoint]:
    """Survival curve, one point per distinct event time.

    S(t) = product over event times t_i <= t of (1 - d_i / n_i), where d_i is the number of
    events at t_i and n_i the number still at risk immediately before it. Censored
    observations leave the risk set without counting as events, which is the whole point.
    """
    if not observations:
        return []

    event_times = sorted({o.time for o in observations if o.event})
    curve: list[SurvivalPoint] = []
    survival = 1.0

    for t in event_times:
        at_risk = sum(1 for o in observations if o.time >= t)
        events = sum(1 for o in observations if o.event and o.time == t)
        if at_risk == 0:
            continue
        survival *= 1.0 - events / at_risk
        curve.append(SurvivalPoint(t, at_risk, events, survival))

    return curve


def median_survival(curve: Sequence[SurvivalPoint]) -> float | None:
    """First time at which survival drops to or below 0.5.

    None when the curve never reaches 0.5 — the median is *not reached*, which is a real
    and reportable result rather than a missing value. Reporting the last observed survival
    instead would understate how long anchors last.
    """
    for point in curve:
        if point.survival <= 0.5:
            return point.time
    return None


def survival_at(curve: Sequence[SurvivalPoint], time: float) -> float:
    """Estimated surviving fraction at `time`. 1.0 before the first event."""
    survival = 1.0
    for point in curve:
        if point.time > time:
            break
        survival = point.survival
    return survival
