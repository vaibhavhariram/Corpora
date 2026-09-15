"""The single normalizer.

Every byte of text that gets hashed, anchored, or shown to a generator passes through
`normalize()`. NORMALIZER_VERSION is stamped into every Snapshot.

Why this file is load-bearing
-----------------------------
On the system this design is derived from, query-side and index-side text went through
different normalization. The same token could be stored one way and looked up another.
Real production queries returned literally nothing because of it: technical identifiers
like `SLP_A_VAL=0`, `be=0`, and `F:PCH_SOC_SYNC`, plus Unicode dash variants, broke
tokenization before retrieval ever ran. The fix was described internally as "a vocabulary
migration that may require reindexing" — i.e. changing normalization invalidates
everything downstream.

Same is true here. Changing this file invalidates every anchor captured under the old
version. That is a breaking change: bump NORMALIZER_VERSION and write an ADR.

What it must NOT do
-------------------
- Must not lowercase. `SLP_A_VAL` and `slp_a_val` are different identifiers.
- Must not split, space, or re-case technical identifiers.
- Must not strip punctuation that carries meaning inside identifiers (`=`, `:`, `_`, `.`).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

NORMALIZER_VERSION = "1.0.0"

# Every dash-like codepoint that a document author might type, or that a word processor
# might autocorrect into their text, collapsed to ASCII hyphen-minus.
_DASHES = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2015": "-",  # horizontal bar
    "\u2212": "-",  # minus sign
    "\ufe58": "-",  # small em dash
    "\ufe63": "-",  # small hyphen-minus
    "\uff0d": "-",  # fullwidth hyphen-minus
}

# Whitespace variants collapsed to ASCII space. Non-breaking space in particular shows up
# constantly in documents exported from Word and breaks exact matching.
_SPACES = {
    "\u00a0": " ",  # no-break space
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u2007": " ",
    "\u2008": " ",
    "\u2009": " ",  # thin space
    "\u200a": " ",
    "\u202f": " ",  # narrow no-break space
    "\u205f": " ",
    "\u3000": " ",  # ideographic space
    "\t": " ",
}

# Quote variants. Smart quotes in a spec break exact-match lookup the same way dashes do.
_QUOTES = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
}

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_TRAILING_WS = re.compile(r"[ ]+$", flags=re.MULTILINE)
_MULTI_SPACE = re.compile(r"[ ]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

_TRANSLATION = str.maketrans({**_DASHES, **_SPACES, **_QUOTES})


def normalize(text: str) -> str:
    """Canonical text form. Deterministic, idempotent, case-preserving."""
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_TRANSLATION)
    text = _MULTI_SPACE.sub(" ", text)
    text = _TRAILING_WS.sub("", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    """SHA-256 of normalized text. The identity function for documents and spans.

    Callers should pass already-normalized text; normalizing again is harmless because
    `normalize` is idempotent, but double-normalizing hides bugs where raw text leaked in.
    """
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Technical identifiers
# --------------------------------------------------------------------------- #

# A token is "technical" if it looks like something a human would never retype by hand and
# a generator must therefore reproduce byte-for-byte. Deliberately broad: a false positive
# only costs us a stricter triage check, a false negative lets a broken test into the
# benchmark.
# ORDER MATTERS. Regex alternation is first-match-wins at each position, so the
# key=value form must precede the bare-identifier form. Otherwise `SLP_A_VAL=0` matches
# as `SLP_A_VAL` and the `=0` — the part that actually carries the assertion — is lost,
# which is precisely the mismatch this function exists to catch.
_TECHNICAL_TOKEN = re.compile(
    r"""
    (?:
        [A-Za-z_][A-Za-z0-9_]*[ ]*[=:][ ]*[^\s,;.?!]+   # be=0, SLP_A_VAL = 0, F:PCH_SOC_SYNC
      | 0x[0-9A-Fa-f]+                                  # hex literals
      | [0-9]+(?:\.[0-9]+){2,}                          # dotted versions / section numbers
      | [A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+              # SNAKE_CASE_IDENTIFIER
      | [A-Z]{2,}[0-9]+[A-Za-z0-9_]*                    # PCH2, SOC3B
      | [A-Z]{3,}                                       # bare acronyms: IBC, NFPA, RRF
    )
    """,
    re.VERBOSE,
)


def technical_tokens(text: str) -> list[str]:
    """Extract tokens that must survive generation verbatim.

    Used by triage: every technical token appearing in a generated question must appear
    byte-identical in the anchored span. If the generator wrote `SLP_A_VAL = 0` and the
    document says `SLP_A_VAL=0`, the test is probing the wrong string and is rejected as
    REJECT_TOKEN_MISMATCH.
    """
    return [m.group(0) for m in _TECHNICAL_TOKEN.finditer(normalize(text))]


def tokens_present_verbatim(question: str, span: str) -> tuple[bool, list[str]]:
    """Return (all_present, missing_tokens).

    Note the asymmetry: we check that the *question's* technical tokens appear in the span,
    not the reverse. A span may legitimately mention identifiers the question does not.
    """
    span_norm = normalize(span)
    missing = [t for t in technical_tokens(question) if t not in span_norm]
    return (not missing, missing)
