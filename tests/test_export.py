import csv
import io

from rugguard.export import build_csv, export_training_csv


def test_build_csv_contains_header_and_rows():
    rows = [
        {"pair": "0xpair1", "initial_price": 0.001, "label_price": 0.00005, "label": "rug"},
        {"pair": "0xpair2", "initial_price": 0.01, "label_price": 0.005, "label": "normal"},
    ]
    csv_text = build_csv(rows)
    lines = csv_text.strip().splitlines()
    assert "pair" in lines[0]
    assert "label" in lines[0]
    assert len(lines) == 3


def test_export_writes_file(tmp_path):
    store_rows = [
        {"pair": "0xpair1", "token": "0xtoken1", "block": 100, "detected_at": "t", "initial_price": 0.001, "label_price": 0.00005, "label": "rug"}
    ]
    target = tmp_path / "train.csv"
    export_training_csv(store_rows, str(target))
    with open(target, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = list(reader)
    assert len(data) == 1
    assert data[0]["label"] == "rug"
