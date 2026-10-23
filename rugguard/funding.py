"""資金費率套利回測：現貨做多 + 永續合約做空（delta neutral），收取資金費率。

用法：
  python -m rugguard.funding fetch    # 抓 Binance 公開資料到 data/funding/（不需要金鑰）
  python -m rugguard.funding report   # 回測並印出結果
"""
import csv
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

import requests

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
DATA_DIR = os.getenv("FUNDING_DATA_DIR", "data/funding")
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
PERP_KLINES = "https://fapi.binance.com/fapi/v1/klines"
SPOT_KLINES = "https://api.binance.com/api/v3/klines"

STEP_MS = 8 * 3600 * 1000
STEPS_PER_YEAR = 3 * 365
# 成本（佔名目金額比例）：Binance 一般帳戶 taker 費率；滑價每個腿 2 bp
SPOT_FEE, PERP_FEE, SLIPPAGE = 0.001, 0.0005, 0.0002
ONE_WAY_COST = SPOT_FEE + PERP_FEE + 2 * SLIPPAGE
LEVERAGE = 3  # 永續空單槓桿；資本 = 現貨 1 + 保證金 1/槓桿
CASH_RATE = float(os.getenv("CASH_RATE", "0.04"))  # 拿來比較的無風險收益（穩定幣放貸）
SPLIT = datetime(2023, 1, 1, tzinfo=timezone.utc)
GRID_K = [1, 3, 9]  # 用過去幾次資金費率的平均決定要不要持有
GRID_THRESHOLD = [0.0, 0.05, 0.10, 0.20]  # 年化門檻


# ---------- 抓資料 ----------

def _get(url: str, params: dict):
    for attempt in range(4):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (418, 429):
            time.sleep(30 * (attempt + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"{url} 重試後仍失敗")


def _paged(url: str, params: dict, start_ms: int, to_row, time_of) -> list:
    out = []
    while True:
        rows = _get(url, {**params, "startTime": start_ms, "limit": 1000})
        if not rows:
            break
        out += [to_row(r) for r in rows]
        if len(rows) < 1000:
            break
        start_ms = time_of(rows[-1]) + 1
    return sorted(set(out))


def _save(path: str, header: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def fetch(symbols=SYMBOLS, data_dir=DATA_DIR, start="2019-09-01") -> None:
    os.makedirs(data_dir, exist_ok=True)
    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    for sym in symbols:
        base = os.path.join(data_dir, sym)
        funding = _paged(FUNDING_URL, {"symbol": sym}, start_ms,
                         lambda r: (int(r["fundingTime"]), r["fundingRate"]), lambda r: int(r["fundingTime"]))
        _save(base + "_funding.csv", ["fundingTime", "fundingRate"], funding)
        for name, url in (("perp", PERP_KLINES), ("spot", SPOT_KLINES)):
            klines = _paged(url, {"symbol": sym, "interval": "8h"}, start_ms,
                            lambda r: (int(r[0]), r[1]), lambda r: int(r[0]))
            _save(f"{base}_{name}.csv", ["openTime", "open"], klines)
        print(f"{sym}: {len(funding)} funding records")


def _read(path: str) -> list:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))[1:]


def load(symbol: str, data_dir: str = DATA_DIR) -> list[tuple[int, float, float, float]]:
    """回傳 [(時間 ms, 該 8 小時的資金費率合計, 永續價, 現貨價)]，只保留最後一段連續資料。

    有些幣的資金費率每 4 小時結算一次，這裡合併成每 8 小時一筆（費率相加）。
    價格用結算時間點那根 8 小時 K 線的開盤價。
    """
    base = os.path.join(data_dir, symbol)  # 檔案不存在就直接丟錯，不給假資料
    funding: dict[int, float] = {}
    for ft, rate in _read(base + "_funding.csv"):
        minute = round(int(ft) / 60000) * 60000
        bucket = -(-minute // STEP_MS) * STEP_MS  # 往上取整到 8 小時邊界
        funding[bucket] = funding.get(bucket, 0.0) + float(rate)
    perp = {int(t): float(p) for t, p in _read(base + "_perp.csv")}
    spot = {int(t): float(p) for t, p in _read(base + "_spot.csv")}
    ts = sorted(t for t in funding if t in perp and t in spot)
    start = 0
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] != STEP_MS:
            start = i
    if start:
        print(f"note: {symbol} has a data gap; using only the last contiguous segment ({len(ts) - start} steps)")
    return [(t, funding[t], perp[t], spot[t]) for t in ts[start:]]


# ---------- 回測 ----------

def always_on(rates, i) -> bool:
    return True


def threshold_rule(k: int, annual: float):
    """用「過去 k 次」的平均資金費率（年化）決定是否持有；只看第 i 步之前已知的資料。"""
    return lambda rates, i: i >= k and sum(rates[i - k:i]) / k * STEPS_PER_YEAR > annual


def simulate(rows, hold_fn, one_way: float = ONE_WAY_COST) -> list[tuple[int, float, int]]:
    """回傳 [(時間, 每單位名目的損益, 是否持有)]。

    第 i 步涵蓋 [t(i-1), t(i)]：持有就收到 t(i) 結算的資金費率，加上基差損益
    （現貨報酬 - 永續報酬，假設每步把名目金額調回 1）。進出場各付一次單邊成本，
    資料結束時仍持有則補付出場成本。shortcut: 不模擬保證金追加與爆倉，見 report 的價格上漲幅度。
    """
    rates = [r[1] for r in rows]
    out, holding = [], False
    for i in range(1, len(rows)):
        t, rate, perp, spot = rows[i]
        want = bool(hold_fn(rates, i))
        pnl = -one_way if want != holding else 0.0
        if want:
            p0, s0 = rows[i - 1][2], rows[i - 1][3]
            pnl += rate + (spot / s0 - 1) - (perp / p0 - 1)
        holding = want
        out.append((t, pnl, int(want)))
    if holding and out:
        t, pnl, held = out[-1]
        out[-1] = (t, pnl - one_way, held)
    return out


def portfolio(series_by_symbol: dict) -> list[tuple[int, float, float]]:
    """等權組合：每個時間點取有資料的幣的平均。"""
    by_t: dict[int, list] = {}
    for series in series_by_symbol.values():
        for t, pnl, held in series:
            by_t.setdefault(t, []).append((pnl, held))
    return [(t, statistics.fmean(p for p, _ in v), statistics.fmean(h for _, h in v)) for t, v in sorted(by_t.items())]


def metrics(series, leverage: int = LEVERAGE, ci: bool = False, block: int = 90, boot: int = 1000) -> dict:
    cap = 1 + 1 / leverage
    pnl = [p / cap for _, p, _ in series]
    n = len(pnl)
    if n == 0:
        raise ValueError("沒有資料")
    cum = peak = dd = 0.0
    for p in pnl:
        cum += p
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    sd = statistics.pstdev(pnl)
    result = {
        "n": n,
        "ann": sum(pnl) / n * STEPS_PER_YEAR,
        "max_dd": dd,
        "sharpe": statistics.fmean(pnl) / sd * STEPS_PER_YEAR ** 0.5 if sd else 0.0,
        "in_market": statistics.fmean(h for _, _, h in series),
    }
    if ci:
        rng, means = random.Random(0), []
        for _ in range(boot):  # 區塊 bootstrap：資金費率前後相關，不能逐筆重抽
            total = count = 0
            while count < n:
                s = rng.randrange(0, max(1, n - block + 1))
                chunk = pnl[s:s + block]
                total, count = total + sum(chunk), count + len(chunk)
            means.append(total / count * STEPS_PER_YEAR)
        means.sort()
        result["ci_low"], result["ci_high"] = means[int(boot * 0.025)], means[int(boot * 0.975)]
    return result


def max_rise(prices: list, steps: int) -> float:
    """任一時間點起算 steps 步內，價格最大漲幅（空單最大帳面虧損 ≈ 需要的保證金緩衝）。"""
    return max((prices[j] / prices[i] - 1 for i in range(len(prices)) for j in range(i + 1, min(i + steps + 1, len(prices)))),
               default=0.0)


def _split(series, ts_ms: int):
    return [s for s in series if s[0] < ts_ms], [s for s in series if s[0] >= ts_ms]


def _pct(x: float) -> str:
    return f"{x:6.1%}"


def report(data_dir: str = DATA_DIR) -> None:
    data = {s: load(s, data_dir) for s in SYMBOLS}
    split_ms = int(SPLIT.timestamp() * 1000)

    print(f"costs: one-way {ONE_WAY_COST:.2%} of notional (spot {SPOT_FEE:.2%} + perp {PERP_FEE:.2%} + slippage), "
          f"leverage {LEVERAGE}x -> capital {1 + 1 / LEVERAGE:.2f} per 1 notional; cash benchmark {CASH_RATE:.0%}/yr")
    print("\n== funding income only (annualized on notional, before costs) ==")
    for s, rows in data.items():
        rates = [r[1] for r in rows]
        d0 = datetime.fromtimestamp(rows[0][0] / 1000, timezone.utc).date()
        print(f"{s:>8} {d0} -> {len(rows):>5} steps  mean {statistics.fmean(rates) * STEPS_PER_YEAR:6.1%}  "
              f"positive {sum(r > 0 for r in rates) / len(rates):4.0%}")
    years = sorted({datetime.fromtimestamp(r[0] / 1000, timezone.utc).year for rows in data.values() for r in rows})
    print("by year (mean across symbols): " + "  ".join(
        f"{y}: {statistics.fmean(r[1] for rows in data.values() for r in rows if datetime.fromtimestamp(r[0] / 1000, timezone.utc).year == y) * STEPS_PER_YEAR:5.1%}"
        for y in years))

    candidates = [("always-on", always_on)] + [
        (f"K={k} thr>{thr:.0%}", threshold_rule(k, thr)) for k in GRID_K for thr in GRID_THRESHOLD]
    results = {}
    for name, rule in candidates:
        by_symbol = {s: simulate(rows, rule) for s, rows in data.items()}
        pf = portfolio(by_symbol)
        train, test = _split(pf, split_ms)
        results[name] = (by_symbol, metrics(train), metrics(test))

    print(f"\n== strategies, equal-weight portfolio of {len(SYMBOLS)} symbols; train < {SPLIT.date()} <= test ==")
    print(f"{'strategy':>16} {'train ann':>9} {'test ann':>9} {'+idle cash':>10} {'test maxDD':>10} "
          f"{'test Sharpe':>11} {'in market':>9}")
    for name, (_, tr, te) in results.items():
        # 空手的時候資本拿現金收益，所以總報酬 = 策略報酬 + 空手比例 × 現金收益
        print(f"{name:>16} {_pct(tr['ann']):>9} {_pct(te['ann']):>9} "
              f"{_pct(te['ann'] + (1 - te['in_market']) * CASH_RATE):>10} {_pct(te['max_dd']):>10} "
              f"{te['sharpe']:>11.1f} {te['in_market']:>9.0%}")

    best = max((n for n in results if n != "always-on"), key=lambda n: results[n][1]["ann"])
    print(f"\nbest threshold rule on TRAIN only: {best}")
    for name in ("always-on", best):
        by_symbol, _, _ = results[name]
        _, test = _split(portfolio(by_symbol), split_ms)
        m = metrics(test, ci=True)
        idle = (1 - m["in_market"]) * CASH_RATE  # 空手期間的現金收益
        lo, hi = m["ci_low"] + idle, m["ci_high"] + idle
        verdict = "beats cash" if lo > CASH_RATE else ("CI includes cash" if hi > CASH_RATE else "below cash")
        print(f"{name:>16} out-of-sample incl. idle cash: ann {_pct(m['ann'] + idle)}  95% CI [{lo:.1%}, {hi:.1%}]  -> {verdict}")
        per_symbol = {s: metrics(_split(series, split_ms)[1])["ann"] for s, series in by_symbol.items()}
        print("                 per symbol (test): " + "  ".join(f"{s[:-4]} {v:5.1%}" for s, v in per_symbol.items()))

    print("\n== always-on: leverage (capital efficiency) and the most recent 12 months ==")
    pf = portfolio(results["always-on"][0])
    recent_ms = pf[-1][0] - 365 * 24 * 3600 * 1000
    for lev in (1, 2, 3):
        print(f"leverage {lev}x (capital {1 + 1 / lev:.2f}): since {SPLIT.year} {_pct(metrics(_split(pf, split_ms)[1], lev)['ann'])}"
              f"   last 12 months {_pct(metrics(_split(pf, recent_ms)[1], lev)['ann'])}")
    majors = portfolio({s: results["always-on"][0][s] for s in ("BTCUSDT", "ETHUSDT")})
    print(f"BTC+ETH only, 3x, last 12 months: {_pct(metrics(_split(majors, recent_ms)[1])['ann'])}")

    print("\n== margin risk of the short leg (largest perp price rise from any start) ==")
    for s, rows in data.items():
        perp = [r[2] for r in rows]
        print(f"{s:>8} within 3 days {max_rise(perp, 9):6.1%}   within 7 days {max_rise(perp, 21):6.1%}   "
              f"(a {LEVERAGE}x short is liquidated near +{1 / LEVERAGE - 0.005:.0%} without adding margin)")


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        report()
