from rugguard.scoring import compute_risk_score, lp_locked_ratio, risk_level

CLEAN = {
    "is_honeypot": "0",
    "buy_tax": "0",
    "sell_tax": "0",
    "can_take_back_ownership": "0",
    "owner_change_balance": "0",
    "lp_holders": [{"percent": "0.95", "is_locked": 1}, {"percent": "0.05", "is_locked": 0}],
    "holder_count": "5000",
}


def token(**overrides):
    return {**CLEAN, **overrides}


def test_honeypot_token_gets_high_risk_score():
    assert compute_risk_score(token(is_honeypot="1")) >= 30


def test_unlocked_liquidity_adds_risk():
    t = token(lp_holders=[{"percent": "0.9", "is_locked": "0"}, {"percent": "0.1", "is_locked": "1"}])
    assert compute_risk_score(t) == 20


def test_unknown_lp_holders_adds_no_liquidity_risk():
    t = token()
    del t["lp_holders"]
    assert lp_locked_ratio(t) is None
    assert compute_risk_score(t) == 0


def test_lp_locked_ratio_sums_locked_holders():
    assert lp_locked_ratio(CLEAN) == 0.95


def test_high_taxes_add_risk():
    # GoPlus 稅率是 0-1 刻度
    assert compute_risk_score(token(buy_tax="0.15", sell_tax="0.12")) == 20


def test_tax_at_exactly_ten_percent_is_not_high():
    assert compute_risk_score(token(buy_tax="0.1", sell_tax="0.1")) == 0


def test_unknown_tax_is_not_high():
    assert compute_risk_score(token(buy_tax="", sell_tax=None)) == 0


def test_owner_can_steal_adds_risk():
    assert compute_risk_score(token(can_take_back_ownership="1", owner_change_balance="1")) == 20


def test_clean_token_gets_low_score():
    assert compute_risk_score(CLEAN) < 10


def test_very_few_holders_adds_risk():
    assert compute_risk_score(token(holder_count="50")) == 5


def test_bundled_buys_add_risk():
    assert compute_risk_score(token(max_same_block_buyers=5)) == 10
    assert compute_risk_score(token(max_same_block_buyers=4)) == 0


def test_score_capped_at_100():
    t = token(
        is_honeypot="1", buy_tax="0.5", sell_tax="0.5", can_take_back_ownership="1",
        owner_change_balance="1", holder_count="1", max_same_block_buyers=9,
        lp_holders=[{"percent": "1", "is_locked": "0"}],
    )
    assert compute_risk_score(t) == 100


def test_risk_level_thresholds():
    assert risk_level(5) == "SAFE"
    assert risk_level(40) == "WARN"
    assert risk_level(70) == "HIGH"
    assert risk_level(90) == "CRITICAL"
