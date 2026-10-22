"""紙上交易：照策略開虛擬倉位、即時判斷出場、記錄扣成本後損益。不動用任何真錢。"""
import os

from rugguard.chains import CHAIN

TAKE_PROFIT = float(os.getenv("PAPER_TP", "2.0"))
STOP_LOSS = float(os.getenv("PAPER_SL", "0.5"))
MAX_HOLD_BLOCKS = int(float(os.getenv("PAPER_MAX_HOURS", "24")) * 3600 / CHAIN["block_seconds"])


def exit_decision(entry: float, price: float | None, block: int, expires_block: int,
                  tp: float = TAKE_PROFIT, sl: float = STOP_LOSS) -> tuple[str, float] | None:
    """回傳 (出場原因, 毛報酬倍數)，還不出場回傳 None。和回測同樣的假設：停利剛好在 tp 成交，停損在看到的價格成交。"""
    if price is not None:
        r = price / entry
        if r >= tp:
            return "take_profit", tp
        if r <= sl:
            return "stop_loss", r
    if block >= expires_block:
        return "time", (price / entry) if price is not None else 0.0
    return None


def open_position(store, notifier, pair: str, token: str, block: int, price: float, cost: float, buy_score: int) -> None:
    store.open_position(pair, token, block, price, cost, block + MAX_HOLD_BLOCKS)
    _send(notifier, f"📝 紙上買入 {token}\n交易對: {pair}\n能買分數: {buy_score}\n"
                    f"策略: 停利 {TAKE_PROFIT}x / 停損 {STOP_LOSS}x / 最長 {MAX_HOLD_BLOCKS} 塊")


def update_positions(store, notifier, points: list[tuple], block: int) -> int:
    """points: 本輪價格取樣 (pair, block, price, ...)。回傳本輪平倉數。"""
    prices = {p[0]: p[2] for p in points}
    closed = 0
    for pos in store.get_open_positions():
        price = prices.get(pos["pair"].lower())
        if price is None and block >= pos["expires_block"]:
            path = store.get_path(pos["pair"])
            price = path[-1]["price"] if path else None
        decision = exit_decision(pos["entry_price"], price, block, pos["expires_block"])
        if decision is None:
            continue
        reason, gross = decision
        net = gross * pos["cost"]
        store.close_position(pos["pair"], block, reason, net)
        closed += 1
        _send(notifier, f"📝 紙上賣出 {pos['token']}（{reason}）\n報酬（扣成本）: {net:.2f}x")
    return closed


def _send(notifier, msg: str) -> None:
    try:
        notifier.send(msg)
    except Exception as e:
        print(f"telegram send failed: {e}")
