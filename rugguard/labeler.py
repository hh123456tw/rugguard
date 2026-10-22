import os
from datetime import datetime

RUG_THRESHOLD = 0.1  # 價格跌到買入價 10% 以下
WIN_RETURN = float(os.getenv("WIN_RETURN", "2.0"))  # 24h 後 >= 2 倍 = 能買
TRADED_LABELS = ("rug", "normal", "win")  # dead 不進訓練


def decide_label(initial_price: float, current_price: float) -> str:
    if initial_price <= 0:
        return "dead"  # 評估當下沒有流動性，沒有可買的價格
    if current_price == initial_price:
        return "dead"  # 儲備完全沒變 = 沒人交易
    ratio = current_price / initial_price
    if ratio <= RUG_THRESHOLD:
        return "rug"
    if ratio >= WIN_RETURN:
        return "win"
    return "normal"


def label_pending_tokens(
    store,
    price_fetcher,
    min_age_hours: int = 24,
    now: datetime | None = None,
) -> int:
    pending = store.get_pending_tokens(min_age_hours=min_age_hours, now=now)
    labeled = 0
    for row in pending:
        try:
            current = price_fetcher(row["pair"])
        except Exception as e:
            # 單一交易對失敗不影響其他，下一輪再試
            print(f"label price failed for {row['pair']}: {e}")
            continue
        label = decide_label(row["initial_price"], current)
        store.update_label(pair=row["pair"], label=label, label_price=current)
        labeled += 1
    return labeled


def relabel_all(store) -> int:
    """用已存的價格重算標籤（標籤規則改變時用），不需要查鏈。"""
    rows = store.get_training_rows()
    for row in rows:
        store.set_label(row["pair"], decide_label(row["initial_price"], row["label_price"]))
    return len(rows)
