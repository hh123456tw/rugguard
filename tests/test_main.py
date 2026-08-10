from rugguard.main import alert_reasons


def test_alert_reasons_detects_honeypot():
    token = {"is_honeypot": "1", "liquidity": "1", "buy_tax": "0", "sell_tax": "0"}
    assert "honeypot" in alert_reasons(token)


def test_alert_reasons_detects_high_tax():
    token = {"is_honeypot": "0", "liquidity": "1", "buy_tax": "25", "sell_tax": "0"}
    assert "high buy tax 25%" in alert_reasons(token)


def test_alert_reasons_clean_token_no_reasons():
    token = {"is_honeypot": "0", "liquidity": "1", "buy_tax": "0", "sell_tax": "0"}
    assert alert_reasons(token) == []
