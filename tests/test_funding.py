import csv
import random

import pytest

from rugguard.funding import (ONE_WAY_COST, STEP_MS, STEPS_PER_YEAR, always_on, load, max_rise, metrics,
                              portfolio, simulate, threshold_rule)


def rows(rates, perp=None, spot=None):
    perp = perp or [100.0] * len(rates)
    spot = spot or [100.0] * len(rates)
    return [(i * STEP_MS, r, perp[i], spot[i]) for i, r in enumerate(rates)]


def total(series):
    return sum(p for _, p, _ in series)


def test_always_on_collects_funding_minus_round_trip_cost():
    series = simulate(rows([0.0] + [0.0001] * 10), always_on)
    assert total(series) == pytest.approx(10 * 0.0001 - 2 * ONE_WAY_COST)


def test_basis_widening_loses_money_for_short_perp():
    # 永續漲、現貨不動：空單虧，現貨沒賺
    series = simulate(rows([0.0, 0.0], perp=[100, 110]), always_on)
    assert total(series) == pytest.approx(-0.10 - 2 * ONE_WAY_COST)


def test_spot_and_perp_moving_together_cancel():
    series = simulate(rows([0.0, 0.0], perp=[100, 150], spot=[100, 150]), always_on)
    assert total(series) == pytest.approx(-2 * ONE_WAY_COST)


def test_threshold_not_met_means_no_position_and_no_cost():
    series = simulate(rows([0.00001] * 20), threshold_rule(3, 0.10))
    assert total(series) == 0
    assert all(held == 0 for _, _, held in series)


def test_negative_funding_is_avoided_by_threshold_but_paid_by_always_on():
    r = rows([0.0] + [-0.001] * 10)
    assert total(simulate(r, always_on)) < -0.009
    assert total(simulate(r, threshold_rule(3, 0.0))) == 0


def test_rule_uses_only_past_rates_no_lookahead():
    # 第 5 步突然出現大額資金費率：第 5 步的決策只能看到第 4 步以前，所以賺不到
    rates = [0.0] * 5 + [0.01] + [0.0] * 4
    series = simulate(rows(rates), threshold_rule(1, 0.10))
    by_t = {t // STEP_MS: p for t, p, _ in series}
    assert by_t[5] == 0  # 沒持有，沒收到
    assert by_t[6] < 0  # 看到高費率後才進場，付進場成本（那一步費率已回到 0）


def test_open_position_pays_exit_cost_at_end():
    series = simulate(rows([0.0, 0.0001]), always_on)
    assert total(series) == pytest.approx(0.0001 - 2 * ONE_WAY_COST)


def test_metrics_annualized_on_capital():
    series = [(i, 0.0001, 1) for i in range(STEPS_PER_YEAR)]
    m = metrics(series, leverage=3)
    assert m["ann"] == pytest.approx(0.0001 * STEPS_PER_YEAR / (1 + 1 / 3))
    assert m["max_dd"] == 0


def test_metrics_drawdown_and_ci_bracket_mean():
    rng = random.Random(1)
    series = [(i, rng.gauss(0.0002, 0.001), 1) for i in range(900)]
    series[100] = (100, -0.05, 1)
    m = metrics(series, ci=True, boot=200)
    assert m["max_dd"] > 0
    assert m["ci_low"] < m["ann"] < m["ci_high"]


def test_metrics_empty_is_error():
    with pytest.raises(ValueError):
        metrics([])


def test_portfolio_averages_symbols_with_data_at_that_time():
    a = [(0, 0.01, 1), (1, 0.01, 1)]
    b = [(1, 0.03, 0)]
    assert portfolio({"a": a, "b": b}) == [(0, 0.01, 1), (1, 0.02, 0.5)]


def test_max_rise_window():
    assert max_rise([100, 90, 130, 100], steps=1) == pytest.approx(130 / 90 - 1)
    assert max_rise([100, 90, 130, 100], steps=3) == pytest.approx(130 / 90 - 1)
    assert max_rise([100, 100, 100], steps=2) == 0


def write(path, header, data):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)


def test_load_merges_4h_funding_and_keeps_last_contiguous_segment(tmp_path):
    h = 3600 * 1000
    # 前兩個 8h 桶是 4h 結算（各 2 筆），中間缺一桶，之後 8h 結算
    funding = [(4 * h + 6, "0.0001"), (8 * h + 3, "0.0002"), (12 * h, "0.0001"), (16 * h, "0.0002"),
               (40 * h + 5, "0.0003"), (48 * h, "0.0004")]
    base = str(tmp_path / "TESTUSDT")
    write(base + "_funding.csv", ["t", "r"], funding)
    times = [8 * h, 16 * h, 40 * h, 48 * h]
    write(base + "_perp.csv", ["t", "p"], [(t, 100) for t in times])
    write(base + "_spot.csv", ["t", "p"], [(t, 100) for t in times])
    got = load("TESTUSDT", str(tmp_path))
    assert [(r[0] // h, round(r[1], 6)) for r in got] == [(40, 0.0003), (48, 0.0004)]  # 缺口前的資料丟掉
    # 4h 合併：04:00 與 08:00 的費率相加成 08:00 那一桶
    write(base + "_funding.csv", ["t", "r"], funding[:4])
    got = load("TESTUSDT", str(tmp_path))
    assert [(r[0] // h, round(r[1], 6)) for r in got] == [(8, 0.0003), (16, 0.0003)]


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load("NOPEUSDT", str(tmp_path))
