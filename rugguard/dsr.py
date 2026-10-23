"""Deflated Sharpe Ratio（Bailey & López de Prado, 2014）。

試了 N 組參數再挑最好的那一組，它的 Sharpe 會被高估。DSR 把「N 次嘗試裡碰巧最好」該有的水準
（SR0）扣掉，算出「真實 Sharpe 大於 0 的機率」。DSR 越接近 1 越可信；低於 0.95 就不能排除運氣。

用法：python -m rugguard.dsr
注意：Sharpe 一律用「每期、未年化」的值代入公式，顯示時才年化。
"""
import math
import statistics
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


def sharpe(x: list) -> float:
    """每期 Sharpe（平均 / 標準差）。全部相同（標準差 0）時回傳 0。"""
    sd = statistics.pstdev(x)
    return statistics.fmean(x) / sd if sd else 0.0


def moments(x: list) -> tuple[float, float]:
    """(偏態, 峰度)。峰度是一般定義（常態 = 3），不是超額峰度。"""
    m, sd = statistics.fmean(x), statistics.pstdev(x)
    if sd == 0:
        return 0.0, 3.0
    return (sum((v - m) ** 3 for v in x) / len(x) / sd ** 3,
            sum((v - m) ** 4 for v in x) / len(x) / sd ** 4)


def psr_from_moments(sr: float, n: int, skew: float, kurt: float, benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio：真實 Sharpe 大於 benchmark 的機率（考慮偏態與厚尾）。"""
    if n < 2:
        raise ValueError("樣本數太少")
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        raise ValueError("偏態與峰度極端，公式失效")
    return _NORMAL.cdf((sr - benchmark) * math.sqrt(n - 1) / math.sqrt(denom))


def psr(x: list, benchmark: float = 0.0) -> float:
    skew, kurt = moments(x)
    return psr_from_moments(sharpe(x), len(x), skew, kurt, benchmark)


def expected_max_sharpe(trial_variance: float, n_trials: int) -> float:
    """SR0：n_trials 次互相獨立、真實 Sharpe 都是 0 的嘗試中，最好那一個的預期 Sharpe。"""
    if n_trials < 2:
        return 0.0  # 只試一次沒有選擇偏誤
    return math.sqrt(trial_variance) * ((1 - EULER_GAMMA) * _NORMAL.inv_cdf(1 - 1 / n_trials)
                                        + EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e)))


def dsr(x: list, trial_sharpes: list, n_trials: int | None = None, benchmark: float = 0.0) -> float:
    """x：被挑中那組的報酬；trial_sharpes：所有嘗試的每期 Sharpe（算它們的變異數）；
    n_trials：嘗試次數，預設等於 len(trial_sharpes)。

    benchmark：虛無假設下所有嘗試的真實 Sharpe（預設 0；想問「有沒有贏買進持有」就填買進持有的每期 Sharpe）。
    這是把論文的 SR0 整個平移 benchmark（論文假設虛無假設的真實 Sharpe 為 0），不是論文原式。"""
    n = n_trials or len(trial_sharpes)
    return psr(x, benchmark + expected_max_sharpe(statistics.variance(trial_sharpes), n))


def break_even_trials(x: list, trial_sharpes: list, level: float = 0.95, limit: int = 10 ** 6,
                      benchmark: float = 0.0) -> int | None:
    """嘗試次數多到幾次，DSR 會掉到 level 以下。回傳那個最小的 N；到 limit 都還在 level 以上就回傳 None。"""
    if dsr(x, trial_sharpes, 2, benchmark) < level:
        return 2
    lo, hi = 2, 4
    while dsr(x, trial_sharpes, hi, benchmark) >= level:
        lo, hi = hi, hi * 2
        if hi > limit:
            return None
    while hi - lo > 1:  # DSR 隨 N 遞減，二分搜尋
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if dsr(x, trial_sharpes, mid, benchmark) >= level else (lo, mid)
    return hi


# ---------- 套用到本專案的回測 ----------

TRIAL_COUNTS = (None, 14, 50)  # None = 該組策略的實際數量；14、50 是把更多相關嘗試也算進去的敏感度
HEADER = (f"{'':>24} {'SR ann':>7} {'hurdle':>7} {'PSR':>6} {'DSR N=n':>8} {'DSR N=14':>9} {'DSR N=50':>9} "
          f"{'break-even N':>13}")


def _row(label: str, x: list, trial_series: list, periods_per_year: int, benchmark: float = 0.0) -> str:
    """hurdle = 要贏過的年化 Sharpe；PSR = 沒扣選擇偏誤的機率；DSR = 扣掉 N 次嘗試後的機率。"""
    trial_sr = [sharpe(t) for t in trial_series]
    cells = [dsr(x, trial_sr, n or len(trial_sr), benchmark) for n in TRIAL_COUNTS]
    be = break_even_trials(x, trial_sr, benchmark=benchmark)
    ann = math.sqrt(periods_per_year)
    return (f"{label:>24} {sharpe(x) * ann:>7.2f} {benchmark * ann:>7.2f} {psr(x, benchmark):>6.2f} {cells[0]:>8.2f} "
            f"{cells[1]:>9.2f} {cells[2]:>9.2f} {be if be is not None else '>1e6':>13}")


def report_trend(data_dir: str | None = None) -> None:
    from rugguard import trend

    split_ms = int(trend.SPLIT.timestamp() * 1000)
    rules = [(f"price>SMA{n}", trend.sma_rule(n)) for n in trend.SMA_DAYS] + [
        (f"momentum {n}d>0", trend.momentum_rule(n)) for n in trend.MOMENTUM_DAYS]
    for symbol in trend.SYMBOLS:
        rows = trend.load(symbol, data_dir or trend.DATA_DIR)
        times, closes = [r[0] for r in rows[1:]], [r[1] for r in rows]
        sims = {name: [r for r, _ in trend.simulate(closes, rule)] for name, rule in rules}
        bh = [r for r, _ in trend.simulate(closes, trend.buy_and_hold)]
        cut = next((i for i, t in enumerate(times) if t >= split_ms), len(times))
        print(f"\n===== {symbol}: {len(rules)} trend rules tried =====")
        for title, window, picked in (
                ("FULL SAMPLE, best rule by Sharpe", slice(None), lambda n: sharpe(sims[n])),
                ("TEST 2023+, rule picked on TRAIN only (but all test results were seen)", slice(cut, None),
                 lambda n: sharpe(sims[n][:cut]))):
            best = max(sims, key=picked)
            x, trials, bh_sr = sims[best][window], [s[window] for s in sims.values()], sharpe(bh[window])
            print(f"\n-- {title}: {best} --")
            print(HEADER)
            print(_row("Sharpe > 0", x, trials, 365))
            print(_row("Sharpe > buy&hold", x, trials, 365, bh_sr))


def report_funding(data_dir: str | None = None) -> None:
    from rugguard import funding

    data = {s: funding.load(s, data_dir or funding.DATA_DIR) for s in funding.SYMBOLS}
    split_ms = int(funding.SPLIT.timestamp() * 1000)
    cap, cash_step = 1 + 1 / funding.LEVERAGE, funding.CASH_RATE / funding.STEPS_PER_YEAR
    rules = [("always-on", funding.always_on)] + [
        (f"K={k} thr>{thr:.0%}", funding.threshold_rule(k, thr)) for k in funding.GRID_K for thr in funding.GRID_THRESHOLD]
    series = {}
    for name, rule in rules:
        # 持有時資本被套利佔用，賺 pnl；空手時資本拿現金收益，和基準相同，所以超額只有交易成本
        by_symbol = {s: [(t, p / cap - h * cash_step, h) for t, p, h in funding.simulate(rows, rule)]
                     for s, rows in data.items()}
        series[name] = [p for _, p, _ in funding.portfolio(by_symbol)]
    times = [t for t, _, _ in funding.portfolio({s: funding.simulate(rows, funding.always_on) for s, rows in data.items()})]
    cut = next((i for i, t in enumerate(times) if t >= split_ms), len(times))
    print(f"\n===== funding-rate strategies, excess return over {funding.CASH_RATE:.0%} cash ({len(rules)} rules tried) =====")
    for title, window, picked in (
            ("FULL SAMPLE, best rule by Sharpe", slice(None), lambda n: sharpe(series[n])),
            ("TEST 2023+, rule picked on TRAIN only (but all test results were seen)", slice(cut, None),
             lambda n: sharpe(series[n][:cut]))):
        best = max(series, key=picked)
        trials = [s[window] for s in series.values()]
        print(f"\n-- {title}: {best} --")
        print(HEADER)
        print(_row("excess > 0", series[best][window], trials, funding.STEPS_PER_YEAR))
        if window.start:
            x = series["always-on"][window]
            print(f"{'always-on (no pick)':>24} {sharpe(x) * math.sqrt(funding.STEPS_PER_YEAR):>7.2f} "
                  f"{0:>7.2f} {psr(x):>6.2f}   (one rule fixed in advance: DSR = PSR)")


if __name__ == "__main__":
    report_trend()
    report_funding()
