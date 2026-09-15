from __future__ import annotations

from app.services.text_match import fold_diacritics, normalize_key, similarity, strip_leading_article


def test_fold_diacritics_common_cases():
    assert fold_diacritics("Beyoncé") == "Beyonce"
    assert fold_diacritics("Mötley Crüe") == "Motley Crue"
    assert fold_diacritics("Sigur Rós") == "Sigur Ros"
    assert fold_diacritics("") == ""


def test_strip_leading_article():
    assert strip_leading_article("the beatles") == "beatles"
    assert strip_leading_article("a tribe called quest") == "tribe called quest"
    assert strip_leading_article("an example") == "example"
    assert strip_leading_article("theatre") == "theatre"  # not "the atre"


def test_normalize_key_folds_articles_and_diacritics():
    assert normalize_key("The Beatles") == normalize_key("Beatles")
    assert normalize_key("Beyoncé") == normalize_key("Beyonce")
    assert normalize_key("Mötley Crüe") == normalize_key("Motley Crue")
    assert normalize_key("AC/DC") == normalize_key("AC DC")


def test_similarity_is_diacritic_aware():
    assert similarity("Beyonce", "Beyoncé") == 1.0
    assert similarity("Sigur Ros", "Sigur Rós") == 1.0
    assert similarity("completely different", "not even close") < 0.5
