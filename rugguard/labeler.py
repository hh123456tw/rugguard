from datetime import datetime

RUG_THRESHOLD = 0.1  # 價格跌到初始 10% 以下


def decide_label(initial_price: float, current_price: float) -> str:
    if initial_price <= 0:
        return "normal"
    if current_price <= 0:
        return "rug"
    ratio = current_price / initial_price
    return "rug" if ratio <= RUG_THRESHOLD else "normal"


def label_pending_tokens(
    store,
    price_fetcher,
    min_age_hours: int = 24,
    now: datetime | None = None,
) -> int:
    pending = store.get_pending_tokens(min_age_hours=min_age_hours, now=now)
    labeled = 0
    for row in pending:
        current = price_fetcher(row["pair"])
        label = decide_label(row["initial_price"], current)
        store.update_label(pair=row["pair"], label=label, label_price=current)
        labeled += 1
    return labeled
