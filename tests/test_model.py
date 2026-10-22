import csv
import random

import pytest

from rugguard.model import FEATURES, MIN_V2_ROWS, RiskModel, extract_features, train


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
        w = csv.DictWriter(fh, fieldnames=["label", "ret", "version", *FEATURES])
        w.writeheader()
        w.writerows(rows)


RET = {"rug": 0.0, "normal": 1.0, "win": 3.0}


def synthetic_rows(n=300, version=1):
    rng = random.Random(0)
    rows = []
    for i in range(n):
        label = ["rug", "normal", "win"][i % 3]
        holders = rng.randint(500, 5000) if label == "win" else rng.randint(1, 400)
        raw = {"is_honeypot": "1" if label == "rug" else "0", "holder_count": str(holders)}
        rows.append({"label": label, "ret": RET[label], "version": version, **extract_features(raw)})
    return rows


def test_train_and_predict_risk_and_buy(tmp_path):
    csv_path, model_path = tmp_path / "t.csv", tmp_path / "m.txt"
    rows = synthetic_rows()
    rows.append({"label": "dead", "ret": "", "version": 1, **extract_features({})})  # dead 不參與訓練
    write_csv(csv_path, rows)

    train(str(csv_path), str(model_path))
    model = RiskModel(str(model_path))
    risk, buy = model.predict({"is_honeypot": "1", "holder_count": "10"})
    assert risk > 80 and buy < 20
    risk, buy = model.predict({"is_honeypot": "0", "holder_count": "3000"})
    assert risk < 20 and buy > 80


def test_train_prefers_v2_rows_when_enough(tmp_path, capsys):
    csv_path = tmp_path / "t.csv"
    write_csv(csv_path, synthetic_rows(60, version=1) + synthetic_rows(MIN_V2_ROWS, version=2))
    train(str(csv_path), str(tmp_path / "m.txt"))
    assert f"using {MIN_V2_ROWS} v2 rows only" in capsys.readouterr().out


def test_train_refuses_missing_class(tmp_path):
    csv_path = tmp_path / "t.csv"
    write_csv(csv_path, [r for r in synthetic_rows(30) if r["label"] != "win"])
    with pytest.raises(ValueError, match="win"):
        train(str(csv_path), str(tmp_path / "m.txt"))
