"""趨勢策略回測（BTC、ETH 現貨，只做多或空手）。

兩類規則：價格站上 N 日均線就持有；過去 N 日報酬為正就持有。否則持有現金。
用法：
  python -m rugguard.trend fetch    # 抓 Binance 現貨日 K 線到 data/trend/（不需要金鑰）
  python -m rugguard.trend report   # 回測並印出結果
"""
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

from rugguard.funding import _paged, _read, _save

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
DATA_DIR = os.getenv("TREND_DATA_DIR", "data/trend")
SPOT_KLINES = "https://api.binance.com/api/v3/klines"
DAY_MS = 86400 * 1000
DAYS_PER_YEAR = 365
# 現貨 taker 0.1% + 滑價 0.05%（BTC / ETH 很深，滑價小）；現金不計利息（保守）
ONE_WAY_COST = 0.001 + 0.0005
SPLIT = datetime(2023, 1, 1, tzinfo=timezone.utc)
SMA_DAYS = [20, 50, 100, 200]
MOMENTUM_DAYS = [30, 90, 180]


# ---------- 資料 ----------

def fetch(symbols=SYMBOLS, data_dir=DATA_DIR, start="2017-08-17") -> None:
    os.makedirs(data_dir, exist_ok=True)
    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    now_ms = int(time.time() * 1000)
    for sym in symbols:
        rows = _paged(SPOT_KLINES, {"symbol": sym, "interval": "1d"}, start_ms,
                      lambda r: (int(r[0]), r[4], int(r[6])), lambda r: int(r[0]))
        rows = [(t, close) for t, close, close_time in rows if close_time <= now_ms]  # 丟掉還沒收盤的那根
        _save(os.path.join(data_dir, f"{sym}_1d.csv"), ["openTime", "close"], rows)
        print(f"{sym}: {len(rows)} daily candles")


def load(symbol: str, data_dir: str = DATA_DIR) -> list[tuple[int, float]]:
    """回傳 [(日期 ms, 收盤價)]，只保留最後一段連續資料。檔案不存在就丟錯。"""
    rows = sorted((int(t), float(c)) for t, c in _read(os.path.join(data_dir, f"{symbol}_1d.csv")))
    start = 0
    for i in range(1, len(rows)):
        if rows[i][0] - rows[i - 1][0] != DAY_MS:
            start = i
    if start:
        print(f"note: {symbol} has a data gap; using only the last contiguous segment ({len(rows) - start} days)")
    return rows[start:]


# ---------- 規則與回測 ----------

def buy_and_hold(closes, i) -> bool:
    return True


def sma_rule(n: int):
    """第 i 天是否持有：只看第 i-1 天以前的收盤，收盤價嚴格高於最近 n 天均線才持有。"""
    return lambda closes, i: i >= n and closes[i - 1] > sum(closes[i - n:i]) / n


def momentum_rule(n: int):
    """第 i 天是否持有：只看第 i-1 天以前的收盤，過去 n 天報酬嚴格為正才持有。"""
    return lambda closes, i: i >= n + 1 and closes[i - 1] > closes[i - 1 - n]


def delayed(rule, days: int = 1):
    """晚 days 天才用訊號（訊號出現後隔天才成交），測試對成交時間是否敏感。"""
    return lambda closes, i: rule(closes, i - days)


def simulate(closes: list, hold_fn, one_way: float = ONE_WAY_COST) -> list[tuple[float, int]]:
    """回傳每天 [(報酬, 是否持有)]，從第 2 天起。進出場各付一次單邊成本，資料結束仍持有則補付出場成本。

    第 i 天的部位在第 i-1 天收盤時決定並成交，賺第 i-1 天收盤到第 i 天收盤的漲跌。
    """
    out, holding = [], False
    for i in range(1, len(closes)):
        want = bool(hold_fn(closes, i))
        ret = (closes[i] / closes[i - 1] - 1) if want else 0.0
        if want != holding:
            ret -= one_way
        holding = want
        out.append((ret, int(want)))
    if holding and out:
        out[-1] = (out[-1][0] - one_way, out[-1][1])
    return out


def metrics(series: list) -> dict:
    n = len(series)
    if n == 0:
        raise ValueError("沒有資料")
    rets = [r for r, _ in series]
    equity = peak = 1.0
    max_dd = 0.0
    for r in rets:
        equity *= 1 + r
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    sd = statistics.pstdev(rets)
    held = [h for _, h in series]
    return {
        "n": n,
        "cagr": equity ** (DAYS_PER_YEAR / n) - 1 if equity > 0 else -1.0,
        "max_dd": max_dd,
        "sharpe": statistics.fmean(rets) / sd * DAYS_PER_YEAR ** 0.5 if sd else 0.0,
        "in_market": statistics.fmean(held),
        "trades": sum(1 for a, b in zip([0] + held, held) if a != b),
    }


def sharpe_diff_ci(a: list, b: list, block: int = 30, boot: int = 1000) -> tuple[float, float, float]:
    """策略 a 與基準 b（同日期）夏普比率之差，區塊 bootstrap 95% 信賴區間：(差, 下界, 上界)。"""
    if len(a) != len(b) or not a:
        raise ValueError("兩組報酬長度要相同且不為空")

    def sharpe(x):
        sd = statistics.pstdev(x)
        return statistics.fmean(x) / sd * DAYS_PER_YEAR ** 0.5 if sd else 0.0

    n, rng, diffs = len(a), random.Random(0), []
    for _ in range(boot):
        idx = []
        while len(idx) < n:
            s = rng.randrange(0, max(1, n - block + 1))
            idx += range(s, min(s + block, n))
        idx = idx[:n]
        diffs.append(sharpe([a[i] for i in idx]) - sharpe([b[i] for i in idx]))
    diffs.sort()
    return sharpe(a) - sharpe(b), diffs[int(boot * 0.025)], diffs[int(boot * 0.975)]


def _split(series: list, times: list, ts_ms: int):
    cut = next((i for i, t in enumerate(times) if t >= ts_ms), len(times))
    return series[:cut], series[cut:]


def report(data_dir: str = DATA_DIR) -> None:
    split_ms = int(SPLIT.timestamp() * 1000)
    rules = [("buy & hold", buy_and_hold)] + [(f"price>SMA{n}", sma_rule(n)) for n in SMA_DAYS] + [
        (f"momentum {n}d>0", momentum_rule(n)) for n in MOMENTUM_DAYS]
    print(f"costs: one-way {ONE_WAY_COST:.2%}; cash earns 0%; long or flat only; train < {SPLIT.date()} <= test\n")
    for symbol in SYMBOLS:
        rows = load(symbol, data_dir)
        times, closes = [r[0] for r in rows[1:]], [r[1] for r in rows]
        d0 = datetime.fromtimestamp(rows[0][0] / 1000, timezone.utc).date()
        print(f"== {symbol}: {d0} -> {len(rows)} days ==")
        print(f"{'strategy':>16} | {'train CAGR':>10} {'Sharpe':>6} {'maxDD':>6} | {'test CAGR':>9} {'Sharpe':>6} "
              f"{'maxDD':>6} {'in mkt':>6} {'trades':>6}")
        sims, stats = {}, {}
        for name, rule in rules:
            sims[name] = simulate(closes, rule)
            train, test = _split(sims[name], times, split_ms)
            stats[name] = (metrics(train), metrics(test))
            tr, te = stats[name]
            print(f"{name:>16} | {tr['cagr']:>10.1%} {tr['sharpe']:>6.2f} {tr['max_dd']:>6.0%} | {te['cagr']:>9.1%} "
                  f"{te['sharpe']:>6.2f} {te['max_dd']:>6.0%} {te['in_market']:>6.0%} {te['trades']:>6}")
        base_sharpe = stats["buy & hold"][1]["sharpe"]
        others = [n for n, _ in rules if n != "buy & hold"]
        beat = sum(stats[n][1]["sharpe"] > base_sharpe for n in others)
        best = max(others, key=lambda n: stats[n][0]["sharpe"])
        test_a = [r for r, _ in _split(sims[best], times, split_ms)[1]]
        test_b = [r for r, _ in _split(sims["buy & hold"], times, split_ms)[1]]
        diff, lo, hi = sharpe_diff_ci(test_a, test_b)
        verdict = "better risk-adjusted" if lo > 0 else ("worse" if hi < 0 else "CI includes zero: no proof")
        te, bh = stats[best][1], stats["buy & hold"][1]
        print(f"\nbest on TRAIN (Sharpe): {best}")
        print(f"  out-of-sample: CAGR {te['cagr']:.1%} vs buy&hold {bh['cagr']:.1%}; maxDD {te['max_dd']:.0%} vs {bh['max_dd']:.0%}")
        print(f"  Sharpe difference vs buy&hold {diff:+.2f}, 95% CI [{lo:+.2f}, {hi:+.2f}] -> {verdict}")
        print(f"  rules with test Sharpe above buy&hold: {beat}/{len(others)}")
        rule = dict(rules)[best]
        for label, series in (("one day later", simulate(closes, delayed(rule))),
                              ("3x costs", simulate(closes, rule, one_way=3 * ONE_WAY_COST))):
            m = metrics(_split(series, times, split_ms)[1])
            print(f"  stress ({label}): test CAGR {m['cagr']:.1%}, Sharpe {m['sharpe']:.2f}, maxDD {m['max_dd']:.0%}")
        print()


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        report()
