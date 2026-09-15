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
    s = "Section  3.1 \u2013 the F:PCH_SOC_SYNC handshake\r\n\r\n\r\ntimes out."
    assert normalize(normalize(s)) == normalize(s)


def test_dash_variants_collapse() -> None:
    assert normalize("a\u2013b") == normalize("a\u2014b") == normalize("a-b")


def test_nbsp_collapses() -> None:
    assert normalize("12\u00a0milliseconds") == "12 milliseconds"


def test_case_is_preserved() -> None:
    """SLP_A_VAL and slp_a_val are different identifiers."""
    assert normalize("SLP_A_VAL") == "SLP_A_VAL"
    assert normalize("SLP_A_VAL") != normalize("slp_a_val")


def test_technical_identifiers_survive_intact() -> None:
    for token in ["SLP_A_VAL=0", "be=0", "F:PCH_SOC_SYNC", "0xFF", "3.1.2", "NFPA"]:
        assert token in normalize(f"value is {token} per spec")


def test_technical_token_extraction() -> None:
    toks = technical_tokens("Does SLP_A_VAL=0 hold while F:PCH_SOC_SYNC is set on PCH2?")
    assert "SLP_A_VAL=0" in toks
    assert "F:PCH_SOC_SYNC" in toks
    assert "PCH2" in toks


def test_spacing_inside_identifier_is_caught() -> None:
    """The generator writing `SLP_A_VAL = 0` when the doc says `SLP_A_VAL=0` produces a
    test that probes the wrong string. Triage must reject it."""
    ok, missing = tokens_present_verbatim(
        "Is SLP_A_VAL = 0 asserted?", "The controller asserts SLP_A_VAL=0 before entry."
    )
    assert not ok and missing
