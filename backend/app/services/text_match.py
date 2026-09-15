"""Shared name/title normalization and fuzzy-matching helpers.

Used by mb_local.py, musicbrainz.py, library.py and artists.py so every
matching path folds diacritics and articles the same way instead of each
file having its own slightly-different normalizer.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_LEADING_ARTICLE = re.compile(r"^(the|an|a)\s+", re.I)
_NON_WORD = re.compile(r"[^\w\s]", re.U)
_SPACE = re.compile(r"\s+")


def fold_diacritics(text: str) -> str:
    """Fold accented/combined characters to their base ASCII-ish form.

    "Beyoncé" -> "Beyonce", "Mötley Crüe" -> "Motley Crue", "Sigur Rós" -> "Sigur Ros".
    Characters with no decomposition (e.g. CJK) pass through unchanged.
    """
    if not text:
        return text
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def strip_leading_article(text: str) -> str:
    """Drop a leading "The"/"A"/"An" so "The Beatles" keys like "Beatles"."""
    return _LEADING_ARTICLE.sub("", text, count=1)


def normalize_key(text: str) -> str:
    """Identity-comparison key: fold diacritics, drop a leading article,
    lowercase, strip punctuation, collapse whitespace. No edition/paren
    stripping — safe for artist names and other identity comparisons where
    parenthetical content is either absent or itself meaningful.
    """
    t = fold_diacritics((text or "").strip()).lower()
    t = strip_leading_article(t)
    t = _NON_WORD.sub(" ", t)
    t = _SPACE.sub(" ", t).strip()
    return t


def similarity(a: str, b: str) -> float:
    """Diacritic-folded fuzzy ratio in [0, 1]. Inputs should already be
    normalized by the caller (normalize_key / normalize_title); folding here
    is just a safety net since it's idempotent and cheap.
    """
    fa = fold_diacritics((a or "").strip().lower())
    fb = fold_diacritics((b or "").strip().lower())
    return SequenceMatcher(None, fa, fb).ratio()
