from rugguard.notifier import format_alert_message, format_buy_message


def test_format_alert_message_contains_key_info():
    msg = format_alert_message(
        token_address="0xabc",
        pair="0xpair",
        score=85,
        level="CRITICAL",
        reasons=["honeypot", "tax"],
    )
    assert "0xabc" in msg
    assert "85" in msg
    assert "CRITICAL" in msg
    assert "honeypot" in msg


def test_format_buy_message_has_scores_and_disclaimer():
    msg = format_buy_message("0xabc", "0xpair", buy_score=72, risk_score=15)
    assert "72/100" in msg and "15/100" in msg and "0xabc" in msg
    assert "不是投資建議" in msg
