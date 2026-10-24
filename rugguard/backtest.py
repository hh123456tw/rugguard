"""停利/停損回測與 rug 型態分析。用法：python -m rugguard.backtest"""
import json
import os
import random
import statistics

from rugguard.chains import CHAIN
from rugguard.scoring import _to_float

SWAP_FEE = 0.0025  # PancakeSwap v2 每次交易手續費
TAKE_PROFITS = [None, 1.2, 1.5, 2, 3, 5, 10]
STOP_LOSSES = [None, 0.7, 0.5]
BLOCK_SECONDS = CHAIN["block_seconds"]
HORIZON_BLOCKS = int(24 * 3600 / BLOCK_SECONDS)
# 觸發後要等幾個塊才成交：快速機器人約 3 塊；本系統每分鐘輪詢約 60 秒
LATENCIES = {"bot ~1.4s": 3, "1-min poll": int(60 / BLOCK_SECONDS)}
POSITION_USD = float(os.getenv("POSITION_USD", "20"))  # 每筆部位大小
MAX_FIRST_JUMP = 50
MIN_ENTRY_USD = float(os.getenv("MIN_ENTRY_USD", "1000"))  # 進場流動性太小的池子買不進去，不回測
NATIVE_USD_APPROX = 700  # shortcut: 舊資料沒存當時 BNB 價，用固定值換算流動性；要精準需存每筆進場時的 BNB 價


def trade_cost(feats: dict) -> float:
    """一買一賣的保留比例：兩次手續費 + 買稅 + 賣稅。"""
    return (1 - SWAP_FEE) ** 2 * (1 - _to_float(feats.get("buy_tax"))) * (1 - _to_float(feats.get("sell_tax")))


def simulate(path: list[tuple[int, float, float, float]], entry: float, tp: float | None, sl: float | None,
             cost: float, latency: int = 0, position: float = 1.0) -> float:
    """path: 進場後依序的 (block, price, 新幣儲備, 報價幣儲備)，儲備為鏈上原始單位。
    position: 投入的報價幣（原始單位）。回傳扣成本後的報酬倍數（1 = 打平）。

    用 AMM 公式算實際能賣回多少：所得 = 報價幣儲備 × 持有顆數 / (新幣儲備 + 持有顆數)。
    所以賣出最多只能拿走池子裡的報價幣；被抽乾或被燒幣的池子，價格再高也賣不到錢。
    買入用第一個價格點的報價幣儲備估算自己推高價格的損失。
    觸發停利 / 停損後，用 latency 個塊之後的狀態以市價賣出。24h 都沒交易代表價格沒變。
    """
    if not path:
        return cost
    first_quote = path[0][3]
    held = position / entry * first_quote / (first_quote + position) if first_quote > 0 else 0.0

    # 新幣儲備大減、報價幣卻沒增加：AMM 交易做不到，是合約直接改餘額（honeypot / 操縱），之後一律視為賣不掉
    manipulated_from = next((i for i in range(1, len(path))
                             if path[i][2] < path[i - 1][2] * 0.5 and path[i][3] <= path[i - 1][3] * 1.01), None)
    # shortcut: 進場與第一個價格點之間沒有儲備可比，第一筆就漲 50 倍以上視為操縱；要精準需記錄進場當下的儲備
    if path[0][1] / entry > MAX_FIRST_JUMP:
        manipulated_from = 0

    def value(i: int) -> float:
        if manipulated_from is not None and i >= manipulated_from:
            return 0.0
        _, _, reserve_alt, reserve_quote = path[i]
        return reserve_quote * held / (reserve_alt + held) / position if held else 0.0

    def fill(i: int) -> float:
        target, j = path[i][0] + latency, i
        while j + 1 < len(path) and path[j + 1][0] <= target:
            j += 1
        return value(j)

    for i in range(len(path)):
        r = value(i)
        if (tp and r >= tp) or (sl and r <= sl):
            return fill(i) * cost
    return value(len(path) - 1) * cost


def rug_anatomy(path: list[tuple[int, float, float]], entry: float, entry_block: int) -> dict | None:
    """path: (block, price, alt 儲備)。回傳第一次跌到 10% 以下時的情況。"""
    prev_price, prev_alt, peak = entry, None, entry
    for block, price, reserve_alt in path:
        if price <= entry * 0.1:
            return {
                "minutes_to_crash": (block - entry_block) * BLOCK_SECONDS / 60,
                # 上一次取樣還 >= 50%，這次已 <= 10%：輪詢間隔內就崩完，來不及逃
                "one_step": prev_price >= entry * 0.5,
                # 撤池會把兩邊儲備一起抽走；倒貨則是 alt 儲備變多
                "liquidity_pulled": prev_alt is not None and reserve_alt < prev_alt,
                "peak_before": peak / entry,
            }
        prev_price, prev_alt, peak = price, reserve_alt, max(peak, price)
    return None


def summarize(returns: list[float], resamples: int = 1000) -> dict:
    # bootstrap 95% 信賴區間：下界 > 1 才算「扣費後期望值為正」站得住
    rng = random.Random(0)
    means = sorted(statistics.fmean(rng.choices(returns, k=len(returns))) for _ in range(resamples))
    return {
        "n": len(returns),
        "mean": statistics.fmean(returns),
        "median": statistics.median(returns),
        "profitable": sum(r > 1 for r in returns) / len(returns),
        "ci_low": means[int(resamples * 0.025)],
        "ci_high": means[int(resamples * 0.975)],
    }


def entry_liquidity_usd(feats: dict, path: list, token0: str, token1: str) -> float | None:
    if feats.get("liquidity_usd") is not None:
        return feats["liquidity_usd"]
    if not path:
        return None
    # 舊資料：用進場後第一個價格點的報價幣儲備近似
    return path[0]["reserve_bnb"] / 10 ** 18 * quote_usd(token0, token1)


def quote_usd(token0: str, token1: str) -> float:
    quote = token0 if token0.lower() in CHAIN["quotes"] else token1
    return 1.0 if quote.lower() in CHAIN["stables"] else NATIVE_USD_APPROX


def load_trades(store) -> list[dict]:
    trades = []
    for row in store.get_training_rows():
        if row["label"] not in ("rug", "normal", "win") or not row["features"] or row["initial_price"] <= 0:
            continue
        feats = json.loads(row["features"])
        # 舊資料要回補完整路徑才能回測；v2 由蒐集程式即時取樣
        if feats.get("version", 1) < 2 and not feats.get("path_complete"):
            continue
        entry_block = feats.get("entry_block") or row["block"] + int(feats["entry_delay_blocks"])
        path = [p for p in store.get_path(row["pair"]) if entry_block < p["block"] <= entry_block + HORIZON_BLOCKS]
        trades.append({
            "entry": row["initial_price"],
            "entry_block": entry_block,
            "entry_usd": entry_liquidity_usd(feats, path, row["token0"], row["token1"]),
            "label": row["label"],
            "buy_score": row["buy_score"],
            "cost": trade_cost(feats),
            "path": [(p["block"], p["price"], p["reserve_alt"], p["reserve_bnb"]) for p in path],
            "position": POSITION_USD / quote_usd(row["token0"], row["token1"]) * 10 ** 18,
        })
    return trades


def eligible(trades: list[dict]) -> list[dict]:
    """進場流動性夠大（買得進去）的交易；未知也排除。"""
    return [t for t in trades if t["entry_usd"] is not None and t["entry_usd"] >= MIN_ENTRY_USD]


def top_decile(trades: list[dict]) -> list[dict]:
    """有能買分數的交易中，分數最高的 10%（少於 10 筆時回傳空）。分數相同時保持原本順序。"""
    scored = sorted((t for t in trades if t["buy_score"] is not None), key=lambda t: -t["buy_score"])
    return scored[: len(scored) // 10] if len(scored) >= 10 else []


def report(trades: list[dict]) -> None:
    if not trades:
        print("no v2 trades with price paths yet; let the collector run > 24h")
        return
    kept = eligible(trades)
    print(f"excluded {len(trades) - len(kept)} trades with entry liquidity < ${MIN_ENTRY_USD:.0f} or unknown; "
          f"{len(kept)} left")
    trades = kept
    if not trades:
        return
    groups = {"all traded": trades}
    top = top_decile(trades)
    if top:
        groups["top 10% buy score"] = top

    for (name, group), (lat_name, latency) in [(g, lat) for g in groups.items() for lat in LATENCIES.items()]:
        print(f"\n== {name} (n={len(group)}), ${POSITION_USD:.0f}/trade, fill latency {lat_name} ({latency} blocks) ==")
        print(f"{'take profit':>11} {'stop loss':>9} {'mean':>7} {'95% CI':>15} {'median':>7} {'profitable':>10}")
        for tp in TAKE_PROFITS:
            for sl in STOP_LOSSES:
                rets = [simulate(t["path"], t["entry"], tp, sl, t["cost"], latency, t["position"]) for t in group]
                s = summarize(rets)
                ci = f"[{s['ci_low']:.2f}, {s['ci_high']:.2f}]"
                flag = "  <- EV>1" if s["ci_low"] > 1 else ""
                print(f"{tp or 'hold 24h':>11} {sl or '-':>9} {s['mean']:7.2f} {ci:>15} {s['median']:7.2f} "
                      f"{s['profitable']:10.0%}{flag}")

    rugs = [a for t in trades if t["label"] == "rug"
            if (a := rug_anatomy([(b, p, alt) for b, p, alt, _ in t["path"]], t["entry"], t["entry_block"]))]
    if rugs:
        print(f"\n== rug anatomy (n={len(rugs)}) ==")
        print(f"one-step crash (no time to exit): {sum(a['one_step'] for a in rugs) / len(rugs):.0%}")
        print(f"liquidity pulled (vs dumped):     {sum(a['liquidity_pulled'] for a in rugs) / len(rugs):.0%}")
        print(f"median minutes entry -> crash:    {statistics.median(a['minutes_to_crash'] for a in rugs):.1f}")
        for k in (1.2, 1.5, 2, 3):
            print(f"reached {k}x before crashing:       {sum(a['peak_before'] >= k for a in rugs) / len(rugs):.0%}")


if __name__ == "__main__":
    from rugguard.store import LabelStore

    report(load_trades(LabelStore(os.getenv("DB_PATH", "rugguard.db"))))
