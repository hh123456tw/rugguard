from rugguard.scoring import compute_risk_score, risk_level


def test_honeypot_token_gets_high_risk_score():
    token = {
        "is_honeypot": "1",
        "buy_tax": "0",
        "sell_tax": "0",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "liquidity": "1",
        "holder_count": "5000",
    }
    assert compute_risk_score(token) >= 30


def test_unlocked_liquidity_adds_risk():
    token = {
        "is_honeypot": "0",
        "buy_tax": "0",
        "sell_tax": "0",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "liquidity": "0",
        "holder_count": "5000",
    }
    assert compute_risk_score(token) >= 20


def test_high_taxes_add_risk():
    token = {
        "is_honeypot": "0",
        "buy_tax": "15",
        "sell_tax": "12",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "liquidity": "1",
        "holder_count": "5000",
    }
    assert compute_risk_score(token) >= 20


def test_owner_can_steal_adds_risk():
    token = {
        "is_honeypot": "0",
        "buy_tax": "0",
        "sell_tax": "0",
        "can_take_back_ownership": "1",
        "owner_change_balance": "1",
        "liquidity": "1",
        "holder_count": "5000",
    }
    assert compute_risk_score(token) >= 10


def test_clean_token_gets_low_score():
    token = {
        "is_honeypot": "0",
        "buy_tax": "0",
        "sell_tax": "0",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "liquidity": "1",
        "holder_count": "5000",
    }
    assert compute_risk_score(token) < 10


def test_very_few_holders_adds_risk():
    token = {
        "is_honeypot": "0",
        "buy_tax": "0",
        "sell_tax": "0",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "liquidity": "1",
        "holder_count": "50",
    }
    assert compute_risk_score(token) >= 5


def test_risk_level_thresholds():
    assert risk_level(5) == "SAFE"
    assert risk_level(40) == "WARN"
    assert risk_level(70) == "HIGH"
    assert risk_level(90) == "CRITICAL"
