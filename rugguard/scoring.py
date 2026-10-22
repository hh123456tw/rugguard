HIGH_TAX = 0.1  # GoPlus 稅率是 0-1 刻度，0.1 = 10%
MIN_LOCKED_LP = 0.5  # 鎖倉（含黑洞地址）LP 低於 50% 視為未鎖
BUNDLE_BUYERS = 5  # 同一區塊內 >= 5 個不同錢包買入視為 bundler


def lp_locked_ratio(token: dict) -> float | None:
    holders = token.get("lp_holders")
    if not holders:
        return None  # GoPlus 還沒有 LP 資料，未知
    return sum(_to_float(h.get("percent")) for h in holders if str(h.get("is_locked")) == "1")


BURN_ADDRESSES = {"0x000000000000000000000000000000000000dead", "0x0000000000000000000000000000000000000000"}


def top10_holder_percent(holders: list | None, pair: str) -> float | None:
    """前 10 大持有人占比，排除交易對本身與銷毀地址（那些不是真的持有人）。"""
    if not holders:
        return None
    skip = BURN_ADDRESSES | {pair.lower()}
    real = [h for h in holders if str(h.get("address", "")).lower() not in skip]
    return sum(_to_float(h.get("percent")) for h in real[:10])


def compute_risk_score(token: dict) -> int:
    score = 0

    if token.get("is_honeypot") == "1":
        score += 30

    locked = lp_locked_ratio(token)
    if locked is not None and locked < MIN_LOCKED_LP:
        score += 20

    if _to_float(token.get("buy_tax")) > HIGH_TAX:
        score += 10
    if _to_float(token.get("sell_tax")) > HIGH_TAX:
        score += 10

    if token.get("can_take_back_ownership") == "1":
        score += 10
    if token.get("owner_change_balance") == "1":
        score += 10

    if _to_int(token.get("holder_count")) < 100:
        score += 5

    if _to_int(token.get("max_same_block_buyers")) >= BUNDLE_BUYERS:
        score += 10

    return min(score, 100)


def risk_level(score: int) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "WARN"
    return "SAFE"


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
