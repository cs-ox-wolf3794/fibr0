from fibr0 import compliance


def test_clean_text_passes():
    text = "Refining margins are likely to widen for Gulf Coast peers over the next five sessions."
    assert compliance.find_banned(text) == []
    assert compliance.is_publishable(text)


def test_banned_words_detected_case_insensitive():
    text = "Investors should BUY the dip and Hold through earnings."
    assert compliance.find_banned(text) == ["buy", "hold"]


def test_compound_words_are_still_caught():
    # CLAUDE.md is strict: the words themselves are banned, including inside long-term.
    assert compliance.find_banned("A long-term shortfall is likely.") == ["long"]


def test_target_price_phrase():
    assert compliance.find_banned("Analysts raised their price target to 120.") == ["price target"]


def test_substrings_inside_other_words_do_not_match():
    assert compliance.find_banned("Shareholders and stakeholders reacted to the buyback.") == []
