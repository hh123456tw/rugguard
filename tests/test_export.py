import csv
import json

from rugguard.export import build_csv, export_training_csv


def test_build_csv_contains_header_and_rows():
    rows = [
        {"pair": "0xpair1", "initial_price": 0.001, "label_price": 0.00005, "label": "rug"},
        {"pair": "0xpair2", "initial_price": 0.01, "label_price": 0.005, "label": "normal"},
    ]
    lines = build_csv(rows).strip().splitlines()
    assert "pair" in lines[0]
    assert "label" in lines[0]
    assert len(lines) == 3


def row(pair, features):
    return {"pair": pair, "token": "0xt", "block": 100, "detected_at": "t", "initial_price": 0.001,
            "label_price": 0.00005, "label": "rug", "features": features}


def test_export_writes_features(tmp_path):
    target = tmp_path / "train.csv"
    features = json.dumps({"is_honeypot": "1", "buy_tax": "0.2"})
    count = export_training_csv([row("0xpair1", features)], str(target))
    with open(target, newline="", encoding="utf-8") as f:
        data = list(csv.DictReader(f))
    assert count == 1
    assert data[0]["label"] == "rug"
    assert data[0]["is_honeypot"] == "1.0"
    assert data[0]["buy_tax"] == "0.2"
    assert float(data[0]["ret"]) == 0.05
    assert data[0]["version"] == "1"


def test_export_skips_rows_without_features(tmp_path):
    target = tmp_path / "train.csv"
    assert export_training_csv([row("0xold", None)], str(target)) == 0
    assert not target.exists()


def test_export_skips_invalid_rows_without_label_price(tmp_path):
    target = tmp_path / "train.csv"
    bad = {**row("0xbad", json.dumps({})), "label": "invalid", "label_price": None}
    assert export_training_csv([bad, row("0xok", json.dumps({}))], str(target)) == 1
