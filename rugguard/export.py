import csv
import io
import json

from rugguard.model import extract_features


def build_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_training_csv(store_rows: list, path: str) -> int:
    """寫出訓練集，回傳列數；沒有特徵的舊資料無法訓練，略過。"""
    rows = [
        {
            "pair": r["pair"],
            "token": r["token"],
            "block": r["block"],
            "detected_at": r["detected_at"],
            "initial_price": r["initial_price"],
            "label_price": r["label_price"],
            "label": r["label"],
            "ret": r["label_price"] / r["initial_price"] if r["initial_price"] > 0 else "",
            "version": json.loads(r["features"]).get("version", 1),
            **extract_features(json.loads(r["features"])),
        }
        for r in store_rows
        # invalid（交易對判斷錯誤）不匯出；它們不一定有 24h 價格
        if r["features"] and r["label"] != "invalid" and r["label_price"] is not None
    ]
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
