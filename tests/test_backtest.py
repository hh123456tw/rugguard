import pytest

from rugguard.backtest import rug_anatomy, simulate

ENTRY = 1.0


def path(*prices, start=101):
    return [(start + i, p) for i, p in enumerate(prices)]


def test_take_profit_hits_before_rug():
    assert simulate(path(1.2, 2.5, 0.01), ENTRY, final=0.0, tp=2, sl=None, cost=1.0) == 2


def test_take_profit_not_reached_holds_to_final():
    assert simulate(path(1.5, 0.5), ENTRY, final=0.3, tp=2, sl=None, cost=1.0) == pytest.approx(0.3)


def test_stop_loss_fills_at_observed_price_not_at_stop():
    # 一筆就從 0.9 掉到 0.02：停損 0.5 只能在 0.02 成交
    assert simulate(path(0.9, 0.02), ENTRY, final=0.0, tp=None, sl=0.5, cost=1.0) == pytest.approx(0.02)


def test_costs_applied():
    assert simulate(path(3.0), ENTRY, final=3.0, tp=2, sl=None, cost=0.9) == pytest.approx(1.8)


def test_hold_without_trades_uses_final():
    assert simulate([], ENTRY, final=1.1, tp=None, sl=None, cost=1.0) == pytest.approx(1.1)


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
        store.add_path_points([(pair, 100, 9.0, 1.0, 1.0), (pair, 150, 2.0, 1.0, 1.0)])
    trades = load_trades(store)
    assert len(trades) == 1
    t = trades[0]
    assert t["path"] == [(150, 2.0, 1.0)]  # 進場區塊本身不算
    assert t["final"] == 2.0  # 用路徑最後價格，不是 30 幾小時後才量的 label_price
    assert t["cost"] == pytest.approx(0.9975 ** 2 * 0.9)
    assert json.loads(store.get_token("0xdone")["features"])["path_complete"]
