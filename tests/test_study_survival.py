"""Specification for the survival estimator, validated against planted curves.

The headline number of the study is produced here. If this is wrong, the study reports a
confident wrong half-life and nothing downstream can tell.
"""

from __future__ import annotations

from corpora.study.survival import (
    Observation,
    kaplan_meier,
    median_survival,
    survival_at,
)


def _obs(*pairs: tuple[float, bool]) -> list[Observation]:
    return [Observation(t, e) for t, e in pairs]


# --------------------------------------------------------------------------- #
# Hand-computable cases
# --------------------------------------------------------------------------- #


def test_no_observations_is_an_empty_curve() -> None:
    assert kaplan_meier([]) == []
    assert median_survival([]) is None


def test_a_textbook_curve_matches_hand_arithmetic() -> None:
    """Five anchors: two fail at 5, one censored at 10, one fails at 15, one censored at 20.

    t=5:  at risk 5, events 2 -> S = 1 - 2/5           = 0.6
    t=15: at risk 2, events 1 -> S = 0.6 * (1 - 1/2)   = 0.3
    """
    curve = kaplan_meier(
        _obs((5, True), (5, True), (10, False), (15, True), (20, False))
    )
    assert [(p.time, p.at_risk, p.events) for p in curve] == [(5, 5, 2), (15, 2, 1)]
    assert curve[0].survival == 0.6
    assert abs(curve[1].survival - 0.3) < 1e-12


def test_survival_is_one_before_the_first_event() -> None:
    curve = kaplan_meier(_obs((30, True), (30, True), (90, False), (90, False)))
    assert survival_at(curve, 0) == 1.0
    assert survival_at(curve, 29) == 1.0
    assert survival_at(curve, 30) == 0.5


# --------------------------------------------------------------------------- #
# Planted curves — the validation that matters
# --------------------------------------------------------------------------- #


def test_a_planted_curve_with_no_censoring_is_recovered_exactly() -> None:
    """100 anchors, half failing at 30 days and half at 100. Median must be 30."""
    planted = _obs(*([(30.0, True)] * 50 + [(100.0, True)] * 50))
    curve = kaplan_meier(planted)
    assert abs(survival_at(curve, 30) - 0.5) < 1e-12
    assert median_survival(curve) == 30.0


def test_censoring_does_not_bias_the_estimate() -> None:
    """The reason Kaplan-Meier is used at all.

    Same 100 anchors as above, but 40 of the late failures are censored at 60 days instead
    — they were still surviving when observation stopped. The estimate of S(30) must not
    move, because nothing about the first 30 days changed. A naive "fraction stale so far"
    would shift from 0.50 to 0.50/0.60 and report a worse half-life than the truth.
    """
    planted = _obs(*(
        [(30.0, True)] * 50 + [(60.0, False)] * 40 + [(100.0, True)] * 10
    ))
    curve = kaplan_meier(planted)
    assert abs(survival_at(curve, 30) - 0.5) < 1e-12
    assert median_survival(curve) == 30.0

    naive = 50 / (50 + 10)
    assert abs(naive - 0.5) > 0.3, "the naive estimator really is badly wrong here"


def test_a_median_that_is_never_reached_reports_none() -> None:
    """Not a missing value — a result. Most anchors outlived the observation window.

    Reporting the last observed survival instead would understate how long anchors last,
    which is the direction that flatters the product.
    """
    planted = _obs(*([(365.0, True)] * 10 + [(365.0, False)] * 90))
    curve = kaplan_meier(planted)
    assert survival_at(curve, 365) == 0.9
    assert median_survival(curve) is None


def test_a_step_curve_is_recovered_at_every_step() -> None:
    """Planted S(t): 0.8 at 7d, 0.6 at 30d, 0.4 at 90d, over 100 uncensored anchors."""
    planted = _obs(*(
        [(7.0, True)] * 20 + [(30.0, True)] * 20 + [(90.0, True)] * 20
        + [(365.0, False)] * 40
    ))
    curve = kaplan_meier(planted)
    for t, expected in ((7, 0.8), (30, 0.6), (90, 0.4)):
        assert abs(survival_at(curve, t) - expected) < 1e-12, f"S({t})"
    assert median_survival(curve) == 90.0


def test_everything_failing_at_once_gives_survival_zero() -> None:
    curve = kaplan_meier(_obs(*([(14.0, True)] * 25)))
    assert curve[-1].survival == 0.0
    assert median_survival(curve) == 14.0
