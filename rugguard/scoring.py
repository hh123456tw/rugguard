def compute_risk_score(token: dict) -> int:
    score = 0

    if token.get("is_honeypot") == "1":
        score += 30

    if token.get("liquidity") == "0":
        score += 20

    buy_tax = _to_float(token.get("buy_tax"))
    sell_tax = _to_float(token.get("sell_tax"))
    if buy_tax > 10:
        score += 10
    if sell_tax > 10:
        score += 10

    if token.get("can_take_back_ownership") == "1":
        score += 10
    if token.get("owner_change_balance") == "1":
        score += 10

    holder_count = _to_int(token.get("holder_count"))
    if holder_count < 100:
        score += 5

    return score


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
