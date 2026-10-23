import math
import random

import pytest

from rugguard.dsr import (break_even_trials, dsr, expected_max_sharpe, moments, psr, psr_from_moments,
                          sharpe)


def noise(seed, n=500, mean=0.0, sd=0.01):
    rng = random.Random(seed)
    return [rng.gauss(mean, sd) for _ in range(n)]


def test_sharpe_and_zero_variance():
    assert sharpe([0.0, 0.0, 0.0]) == 0.0
    assert sharpe([1.0, 3.0]) == pytest.approx(2.0)  # 平均 2、母體標準差 1


def test_moments_normal_like_and_constant():
    skew, kurt = moments(noise(1, n=20000))
    assert abs(skew) < 0.1 and kurt == pytest.approx(3.0, abs=0.2)
    assert moments([5.0, 5.0]) == (0.0, 3.0)


def test_worked_example_matches_hand_calculation():
    # 年化 Sharpe 2.5、250 個交易日一年、T=1250、偏態 -3、峰度 10、100 次嘗試、
    # 嘗試間年化 Sharpe 變異數 0.5。用論文的公式手算約 0.90。
    sr, var = 2.5 / math.sqrt(250), 0.5 / 250
    result = psr_from_moments(sr, 1250, -3, 10, expected_max_sharpe(var, 100))
    assert result == pytest.approx(0.90, abs=0.005)


def test_psr_larger_benchmark_lowers_probability_and_zero_mean_is_not_certain():
    x = noise(2, mean=0.001)
    assert psr(x, 0.0) > psr(x, 0.05)
    assert 0.05 < psr(noise(3), 0.0) < 0.95  # 沒有任何優勢的雜訊，不該被判定顯著


def test_psr_long_strong_series_near_one():
    assert psr(noise(4, n=3000, mean=0.002)) > 0.999


def test_psr_raises_when_formula_breaks_and_when_too_few_samples():
    with pytest.raises(ValueError):
        psr_from_moments(10.0, 100, 10.0, 3.0)  # 分母 = 1 - 100 + 50 < 0
    with pytest.raises(ValueError):
        psr([0.1])


def test_one_trial_has_no_selection_bias_and_more_trials_raise_the_bar():
    assert expected_max_sharpe(0.01, 1) == 0.0
    assert expected_max_sharpe(0.01, 100) > expected_max_sharpe(0.01, 10) > 0


def test_dsr_decreases_with_trials_and_equals_psr_for_one_trial():
    x = noise(5, mean=0.001)
    trials = [sharpe(noise(s, mean=0.001)) for s in range(10, 20)]
    assert dsr(x, trials, 2) > dsr(x, trials, 10) > dsr(x, trials, 1000)
    assert dsr(x, trials, 1) == pytest.approx(psr(x, 0.0))


def test_best_of_many_pure_noise_looks_good_alone_but_not_after_deflation():
    # 50 組完全沒有優勢的策略，挑 Sharpe 最高的：單看它會顯著，扣掉選擇偏誤就不顯著
    trials = [noise(s, n=750) for s in range(100, 150)]
    sharpes = [sharpe(t) for t in trials]
    best = trials[sharpes.index(max(sharpes))]
    assert psr(best) > 0.95
    assert dsr(best, sharpes, 50) < 0.95


def test_break_even_trials():
    trials = [sharpe(noise(s, mean=0.0005)) for s in range(30, 40)]
    x = noise(6, n=2000, mean=0.001)
    n = break_even_trials(x, trials)
    assert n is not None and n >= 2
    assert dsr(x, trials, n) < 0.95 <= dsr(x, trials, n - 1) or n == 2
    assert break_even_trials(x, trials, level=0.0) is None  # DSR 永遠不會低於 0


def test_benchmark_raises_the_bar():
    x = noise(7, mean=0.001)
    trials = [sharpe(noise(s, mean=0.001)) for s in range(40, 50)]
    assert dsr(x, trials, 10, benchmark=0.05) < dsr(x, trials, 10, benchmark=0.0)
    assert break_even_trials(x, trials, benchmark=0.05) <= break_even_trials(x, trials)
