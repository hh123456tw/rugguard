import os
from datetime import datetime

from rugguard.chains import split_pair

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
    """用已存的價格重算標籤（標籤規則改變時用），不需要查鏈。invalid 保持不動。"""
    rows = [r for r in store.get_training_rows() if r["label"] != "invalid"]
    for row in rows:
        store.set_label(row["pair"], decide_label(row["initial_price"], row["label_price"]))
    return len(rows)


def mark_invalid(store) -> int:
    """舊版只認 BNB：USDT/新幣 會把 USDT 當新幣，兩邊都不是報價幣的價格基準也不可靠。標成 invalid，不進訓練。"""
    count = 0
    for row in store.get_all_tokens():
        split = split_pair(row["token0"], row["token1"])
        if split is None or split[0].lower() != row["token"].lower():
            store.set_label(row["pair"], "invalid")
            count += 1
    return count
