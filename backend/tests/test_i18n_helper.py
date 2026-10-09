from questtour.services.i18n import pick_text


def test_pick_text_falls_back_to_base():
    assert pick_text("base", None, "de") == "base"
    assert pick_text("base", {"sr": "Srpski"}, "de") == "base"


def test_pick_text_returns_translation():
    assert pick_text("base", {"de": "Basis"}, "de") == "Basis"


def test_pick_text_returns_bulgarian_translation():
    assert pick_text("base", {"bg": "База"}, "bg") == "База"


def test_pick_text_falls_back_for_blank_translation():
    assert pick_text("base", {"de": ""}, "de") == "base"
    assert pick_text("base", {"de": "   "}, "de") == "base"
