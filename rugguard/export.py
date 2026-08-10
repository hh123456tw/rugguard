import csv
import io


def build_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_training_csv(store_rows: list, path: str) -> None:
    rows = [
        {
            "pair": r["pair"],
            "token": r["token"],
            "block": r["block"],
            "detected_at": r["detected_at"],
            "initial_price": r["initial_price"],
            "label_price": r["label_price"],
            "label": r["label"],
        }
        for r in store_rows
    ]
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
