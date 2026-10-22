"""停利/停損回測與 rug 型態分析。用法：python -m rugguard.backtest"""
import json
import os
import statistics

from rugguard.scoring import _to_float

SWAP_FEE = 0.0025  # PancakeSwap v2 每次交易手續費
TAKE_PROFITS = [None, 1.2, 1.5, 2, 3, 5, 10]
STOP_LOSSES = [None, 0.7, 0.5]
BLOCK_SECONDS = 0.45


def simulate(path: list[tuple[int, float]], entry: float, final: float,
             tp: float | None, sl: float | None, cost: float) -> float:
    """path: 進場後依序的 (block, price)。回傳扣成本後的報酬倍數（1 = 打平）。

    停利假設剛好在 tp 成交；停損在觸發後看到的那個價格成交（rug 時通常已接近 0）。
    """
    for _, price in path:
        r = price / entry
        if tp and r >= tp:
            return tp * cost
        if sl and r <= sl:
            return r * cost
    return final / entry * cost


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


def summarize(returns: list[float]) -> dict:
    return {
        "n": len(returns),
        "mean": statistics.fmean(returns),
        "median": statistics.median(returns),
        "profitable": sum(r > 1 for r in returns) / len(returns),
    }


def load_trades(store) -> list[dict]:
    trades = []
    for row in store.get_training_rows():
        if row["label"] == "dead" or not row["features"] or row["initial_price"] <= 0:
            continue
        feats = json.loads(row["features"])
        if feats.get("version", 1) < 2:
            continue  # 舊資料沒有進場區塊與價格路徑
        path = store.get_path(row["pair"])
        if not path:
            continue
        entry_block = row["block"] + int(feats["entry_delay_blocks"])
        trades.append({
            "entry": row["initial_price"],
            "entry_block": entry_block,
            "final": row["label_price"],
            "label": row["label"],
            "buy_score": row["buy_score"],
            "cost": (1 - SWAP_FEE) ** 2 * (1 - _to_float(feats.get("buy_tax"))) * (1 - _to_float(feats.get("sell_tax"))),
            "path": [(p["block"], p["price"], p["reserve_alt"]) for p in path if p["block"] > entry_block],
        })
    return trades


def report(trades: list[dict]) -> None:
    if not trades:
        print("no v2 trades with price paths yet; let the collector run > 24h")
        return
    groups = {"all traded": trades}
    scored = sorted((t for t in trades if t["buy_score"] is not None), key=lambda t: -t["buy_score"])
    if len(scored) >= 10:
        groups["top 10% buy score"] = scored[: len(scored) // 10]

    for name, group in groups.items():
        print(f"\n== {name} (n={len(group)}) ==")
        print(f"{'take profit':>11} {'stop loss':>9} {'mean':>7} {'median':>7} {'profitable':>10}")
        for tp in TAKE_PROFITS:
            for sl in STOP_LOSSES:
                rets = [simulate([(b, p) for b, p, _ in t["path"]], t["entry"], t["final"],
                                 tp, sl, t["cost"]) for t in group]
                s = summarize(rets)
                print(f"{tp or 'hold 24h':>11} {sl or '-':>9} {s['mean']:7.2f} {s['median']:7.2f} {s['profitable']:10.0%}")

    rugs = [a for t in trades if t["label"] == "rug"
            if (a := rug_anatomy(t["path"], t["entry"], t["entry_block"]))]
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
