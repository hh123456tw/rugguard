import pytest

from rugguard.backtest import rug_anatomy, simulate

ENTRY = 1.0


BIG = 1e12  # 池子遠大於部位：買賣不太推動價格


def path(*prices, start=101):
    # 照 AMM 恆定乘積（新幣 × 報價幣 = BIG²）做出指定價格：價格漲時報價幣跟著變多
    return [(start + i, p, BIG / p ** 0.5, BIG * p ** 0.5) for i, p in enumerate(prices)]


def sim(p, **kw):
    return simulate(p, ENTRY, kw.pop("tp", None), kw.pop("sl", None), kw.pop("cost", 1.0), **kw)


def test_take_profit_fills_at_next_state_after_latency():
    # 2.5 觸發停利，但成交時（延遲 1 塊）已跌到 0.01
    assert sim(path(1.2, 2.5, 0.01), tp=2, latency=1) == pytest.approx(0.01, rel=1e-3)


def test_take_profit_without_latency_sells_at_trigger_state():
    assert sim(path(1.2, 2.5, 0.01), tp=2) == pytest.approx(2.5, rel=1e-3)


def test_take_profit_not_reached_holds_to_last_price():
    assert sim(path(1.5, 0.5), tp=2) == pytest.approx(0.5, rel=1e-3)


def test_stop_loss_fills_at_observed_price_not_at_stop():
    # 一筆就從 0.9 掉到 0.02：停損 0.5 只能在 0.02 成交
    assert sim(path(0.9, 0.02), sl=0.5) == pytest.approx(0.02, rel=1e-3)


def test_costs_applied():
    assert sim(path(3.0), tp=2, cost=0.9) == pytest.approx(2.7, rel=1e-3)


def test_no_trades_in_24h_is_flat():
    assert simulate([], ENTRY, None, None, 0.99) == pytest.approx(0.99)


def test_drained_pool_dust_price_is_worthless():
    # 報價幣從 1e12 被抽到 1：殘渣讓價格看起來 1000 倍，但只賣得到幾乎 0
    p = [(101, 1.1, BIG / 1.1, BIG), (102, 1000.0, 1 / 1000.0, 1.0)]
    assert simulate(p, ENTRY, 2, None, 1.0, 0, 1e6) < 0.01


def test_burned_alt_reserve_capped_by_quote_in_pool():
    # 合約把池裡新幣燒到剩 1：價格 1e12 倍，但最多只能拿走池裡全部報價幣
    position = 1e10
    p = [(101, 1.0, BIG, BIG), (102, 1e12, 1.0, BIG)]
    r = simulate(p, ENTRY, 2, None, 1.0, 0, position)
    assert r <= BIG / position + 1e-9


def test_large_position_pays_price_impact_small_does_not():
    # 歷史池子不含自己的買單，大部位的買、賣衝擊各算一次（偏保守）；小部位幾乎沒影響
    p = [(101, 1.0, BIG, BIG)]
    assert simulate(p, ENTRY, None, None, 1.0, 0, BIG) < 0.6
    assert simulate(p, ENTRY, None, None, 1.0, 0, BIG / 1e6) == pytest.approx(1.0, rel=1e-4)


def test_rug_anatomy_one_step_liquidity_pull():
    p = [(110, 1.8, 1000.0), (120, 0.0001, 1.0)]  # alt 儲備也被抽走 = 撤池
    a = rug_anatomy(p, ENTRY, entry_block=100)
    assert a["one_step"] and a["liquidity_pulled"]
    assert a["peak_before"] == pytest.approx(1.8)
    assert a["minutes_to_crash"] == pytest.approx(20 * 0.45 / 60)


def test_rug_anatomy_gradual_dump_is_escapable():
    # alt 儲備一路變多 = 有人倒貨，價格分段下跌
    a = rug_anatomy([(101, 0.6, 1000.0), (102, 0.3, 2000.0), (103, 0.05, 9000.0)], ENTRY, entry_block=100)
    assert not a["one_step"] and not a["liquidity_pulled"]


def test_rug_anatomy_no_crash_returns_none():
    assert rug_anatomy([(101, 0.5, 1000.0)], ENTRY, entry_block=100) is None


def test_load_trades_v1_needs_complete_backfill_and_uses_last_path_price():
    import json

    from rugguard.backtest import load_trades
    from rugguard.store import LabelStore

    store = LabelStore(":memory:")
    for pair, complete in (("0xdone", True), ("0xpartial", False)):
        feats = {"entry_block": 100, "buy_tax": "0.1"}
        if complete:
            feats["path_complete"] = True
        store.add_token(pair=pair, token="t", block=90, initial_price=1.0, features=feats)
        store.update_label(pair=pair, label="rug", label_price=0.0)
        store.add_path_points([(pair, 100, 9.0, 1.0, 1.0), (pair, 150, 2.0, 1.0, 3.0 * 10 ** 18)])
    trades = load_trades(store)
    assert len(trades) == 1
    t = trades[0]
    assert t["path"] == [(150, 2.0, 1.0, 3.0 * 10 ** 18)]  # 進場區塊本身不算
    assert t["entry_usd"] == pytest.approx(3.0 * 700)  # 報價幣不是穩定幣：3 BNB × 近似價 700
    assert t["position"] == pytest.approx(20 / 700 * 10 ** 18)
    assert t["cost"] == pytest.approx(0.9975 ** 2 * 0.9)
    assert json.loads(store.get_token("0xdone")["features"])["path_complete"]


def test_summarize_ci_brackets_mean():
    from rugguard.backtest import summarize

    s = summarize([0.0] * 80 + [3.0] * 20)
    assert s["ci_low"] < s["mean"] < s["ci_high"]
    assert s["mean"] == pytest.approx(0.6)
    assert s["ci_high"] < 1  # 這種分布扣費前就不賺錢


def test_summarize_constant_returns_tight_ci():
    from rugguard.backtest import summarize

    s = summarize([1.2] * 50)
    assert s["ci_low"] == pytest.approx(1.2) and s["ci_high"] == pytest.approx(1.2)


def test_alt_reserve_drop_without_quote_inflow_is_manipulation():
    # 新幣儲備 1e12 -> 1e3、報價幣不變：合約改餘額，價格暴衝也賣不掉
    p = [(101, 1.0, BIG, BIG), (102, 1e9, 1e3, BIG), (103, 1e9, 1e3, BIG)]
    assert sim(p, tp=2) == 0.0


def test_real_buy_pressure_is_not_manipulation():
    # 有人買入：新幣儲備減半、報價幣變兩倍 → 正常的 4 倍
    p = [(101, 1.0, BIG, BIG), (102, 4.0, BIG / 2, BIG * 2)]
    assert sim(p, tp=2) == pytest.approx(4.0, rel=1e-3)


def test_first_point_huge_jump_from_entry_is_manipulation():
    p = [(101, 1e9, BIG, BIG)]
    assert sim(p, tp=2) == 0.0
