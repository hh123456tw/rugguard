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
            **extract_features(json.loads(r["features"])),
        }
        for r in store_rows
        if r["features"]
    ]
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
