import csv
import random

import pytest

from rugguard.model import FEATURES, RiskModel, extract_features, train


def test_extract_features_parses_goplus_fields():
    f = extract_features({"is_honeypot": "1", "buy_tax": "0.2", "holder_count": "50",
                          "lp_holders": [{"percent": "0.3", "is_locked": 1}]})
    assert set(f) == set(FEATURES)
    assert f["is_honeypot"] == 1.0
    assert f["buy_tax"] == 0.2
    assert f["lp_locked_ratio"] == 0.3
    assert f["is_mintable"] == 0.0


def test_extract_features_unknown_lp_is_minus_one():
    assert extract_features({})["lp_locked_ratio"] == -1.0


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["label", *FEATURES])
        w.writeheader()
        w.writerows(rows)


def test_train_and_predict_separates_rugs(tmp_path):
    rng = random.Random(0)
    rows = []
    for i in range(200):
        rug = i % 2 == 0
        holders = rng.randint(1, 50) if rug else rng.randint(500, 5000)
        raw = {"is_honeypot": "1" if rug else "0", "holder_count": str(holders)}
        rows.append({"label": "rug" if rug else "normal", **extract_features(raw)})
    csv_path, model_path = tmp_path / "t.csv", tmp_path / "m.txt"
    write_csv(csv_path, rows)

    train(str(csv_path), str(model_path))
    model = RiskModel(str(model_path))
    assert model.score({"is_honeypot": "1", "holder_count": "10"}) > 80
    assert model.score({"is_honeypot": "0", "holder_count": "3000"}) < 20


def test_train_refuses_single_class(tmp_path):
    csv_path = tmp_path / "t.csv"
    write_csv(csv_path, [{"label": "normal", **extract_features({})} for _ in range(10)])
    with pytest.raises(ValueError, match="rug"):
        train(str(csv_path), str(tmp_path / "m.txt"))
