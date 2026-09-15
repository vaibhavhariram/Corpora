"""Normalizer tests. These should pass on a fresh clone — normalize.py is implemented.

If any of these break, every anchor in every customer benchmark silently changes meaning.
Treat a failure here as a breaking change, not a bug fix.
"""

from corpora.corpus.normalize import (
    normalize,
    technical_tokens,
    tokens_present_verbatim,
)


def test_idempotent() -> None:
    s = "Section  3.1 \u2013 the F:LINK_SYNC handshake\r\n\r\n\r\ntimes out."
    assert normalize(normalize(s)) == normalize(s)


def test_dash_variants_collapse() -> None:
    assert normalize("a\u2013b") == normalize("a\u2014b") == normalize("a-b")


def test_nbsp_collapses() -> None:
    assert normalize("12\u00a0milliseconds") == "12 milliseconds"


def test_case_is_preserved() -> None:
    """PWR_SEQ_VAL and pwr_seq_val are different identifiers."""
    assert normalize("PWR_SEQ_VAL") == "PWR_SEQ_VAL"
    assert normalize("PWR_SEQ_VAL") != normalize("pwr_seq_val")


def test_technical_identifiers_survive_intact() -> None:
    for token in ["PWR_SEQ_VAL=0", "be=0", "F:LINK_SYNC", "0xFF", "3.1.2", "NFPA"]:
        assert token in normalize(f"value is {token} per spec")


def test_technical_token_extraction() -> None:
    toks = technical_tokens("Does PWR_SEQ_VAL=0 hold while F:LINK_SYNC is set on DEV_A?")
    assert "PWR_SEQ_VAL=0" in toks
    assert "F:LINK_SYNC" in toks
    assert "DEV_A" in toks


def test_spacing_inside_identifier_is_caught() -> None:
    """The generator writing `PWR_SEQ_VAL = 0` when the doc says `PWR_SEQ_VAL=0` produces a
    test that probes the wrong string. Triage must reject it."""
    ok, missing = tokens_present_verbatim(
        "Is PWR_SEQ_VAL = 0 asserted?", "The controller asserts PWR_SEQ_VAL=0 before entry."
    )
    assert not ok and missing
