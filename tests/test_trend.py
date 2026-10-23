import csv

import pytest

from rugguard.trend import (DAY_MS, ONE_WAY_COST, buy_and_hold, delayed, load, metrics, momentum_rule, sharpe_diff_ci,
                            simulate, sma_rule)


def total(series):
    return sum(r for r, _ in series)


def test_sma_rule_needs_close_strictly_above_average():
    rule = sma_rule(3)
    assert not rule([10, 10, 10, 11], 3)  # 前 3 天均線 10，收盤 10 不算站上
    assert rule([9, 10, 11, 12], 3)  # 前 3 天 [9,10,11] 均線 10，最後收盤 11 > 10
    assert not rule([12, 11, 10, 9], 3)  # 前 3 天收盤 10 < 均線 11
    assert not rule([1, 2, 3], 2)  # 第 2 天只有 2 天資料，不夠 3 天均線


def test_sma_rule_ignores_the_current_bar_no_lookahead():
    rule = sma_rule(3)
    assert rule([1, 2, 3, 1000], 3) == rule([1, 2, 3, 0.001], 3)


def test_momentum_rule_strictly_positive_and_no_lookahead():
    rule = momentum_rule(2)
    assert rule([10, 11, 12, 99], 3)  # closes[2]=12 > closes[0]=10
    assert not rule([10, 11, 10, 99], 3)  # 相等不算
    assert rule([10, 11, 12, 99], 3) == rule([10, 11, 12, -5], 3)
    assert not rule([10, 11], 2)  # 資料不夠


def test_buy_and_hold_pays_round_trip_cost_only():
    series = simulate([100.0] * 10, buy_and_hold)
    assert total(series) == pytest.approx(-2 * ONE_WAY_COST)


def test_hold_earns_next_bar_return_after_signal():
    # 第 2 天（索引 2）才持有，賺第 1→2 天的漲幅
    closes = [100, 100, 110, 110]
    series = simulate(closes, lambda c, i: i == 2, one_way=0.0)
    assert [round(r, 6) for r, _ in series] == [0.0, 0.1, 0.0]


def test_never_holding_costs_nothing():
    series = simulate([100, 90, 120, 80], lambda c, i: False)
    assert total(series) == 0
    assert all(h == 0 for _, h in series)


def test_switching_pays_cost_each_transition():
    series = simulate([100.0] * 6, lambda c, i: i in (2, 3), one_way=0.01)
    assert total(series) == pytest.approx(-0.02)  # 進一次、出一次


def test_metrics_cagr_drawdown_and_trades():
    series = [(0.10, 1), (-0.50, 1), (0.0, 0), (0.20, 1)]
    m = metrics(series)
    assert m["max_dd"] == pytest.approx(0.5)
    assert m["trades"] == 3  # 進、出、再進
    assert m["in_market"] == pytest.approx(0.75)
    equity = 1.1 * 0.5 * 1.2
    assert m["cagr"] == pytest.approx(equity ** (365 / 4) - 1)


def test_metrics_empty_is_error():
    with pytest.raises(ValueError):
        metrics([])


def test_sharpe_diff_ci_detects_clear_advantage_and_rejects_identical():
    import random

    rng = random.Random(3)
    base = [rng.gauss(0.0005, 0.02) for _ in range(600)]
    better = [x + 0.003 for x in base]  # 每天多賺 0.3%，同樣的波動
    diff, lo, hi = sharpe_diff_ci(better, base, boot=300)
    assert lo > 0 and diff > 0
    diff, lo, hi = sharpe_diff_ci(base, base, boot=300)
    assert diff == 0 and lo == 0 and hi == 0
    with pytest.raises(ValueError):
        sharpe_diff_ci([0.1], [0.1, 0.2])


def write_klines(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["openTime", "close"])
        w.writerows(rows)


def test_load_keeps_last_contiguous_segment(tmp_path):
    rows = [(0, 1), (DAY_MS, 2), (3 * DAY_MS, 4), (4 * DAY_MS, 5)]  # 缺第 2 天
    write_klines(tmp_path / "XUSDT_1d.csv", rows)
    assert load("XUSDT", str(tmp_path)) == [(3 * DAY_MS, 4.0), (4 * DAY_MS, 5.0)]


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load("NOPEUSDT", str(tmp_path))


def test_delayed_rule_uses_signal_one_day_late():
    rule = lambda closes, i: i == 3  # noqa: E731
    late = delayed(rule)
    assert [late([0] * 6, i) for i in range(6)] == [False, False, False, False, True, False]
