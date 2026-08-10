from rugguard.notifier import format_alert_message


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
