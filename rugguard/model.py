import sys

from rugguard.scoring import _to_float, lp_locked_ratio

FLAGS = [
    "is_honeypot",
    "can_take_back_ownership",
    "owner_change_balance",
    "hidden_owner",
    "is_mintable",
    "is_open_source",
    "is_proxy",
    "transfer_pausable",
    "slippage_modifiable",
    "is_blacklisted",
    "external_call",
]
NUMERIC = ["buy_tax", "sell_tax", "holder_count", "creator_percent", "owner_percent",
           "early_buyers", "max_same_block_buyers"]
FEATURES = FLAGS + NUMERIC + ["lp_locked_ratio"]


def extract_features(raw: dict) -> dict[str, float]:
    feats = {f: float(raw.get(f) == "1") for f in FLAGS}
    feats.update({f: _to_float(raw.get(f)) for f in NUMERIC})
    locked = lp_locked_ratio(raw)
    feats["lp_locked_ratio"] = -1.0 if locked is None else locked  # -1 = 未知
    return feats


def train(csv_path: str, model_path: str) -> None:
    import lightgbm as lgb
    import pandas as pd
    from sklearn.model_selection import cross_val_score

    df = pd.read_csv(csv_path)
    X = df[FEATURES]
    y = (df["label"] == "rug").astype(int)
    minority = int(min(y.sum(), len(y) - y.sum()))
    if minority < 2:
        raise ValueError(f"need >= 2 rug and >= 2 normal rows, got {int(y.sum())} rug / {len(y) - int(y.sum())} normal")

    clf = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15,
                             min_child_samples=min(20, minority), verbose=-1)
    auc = cross_val_score(clf, X, y, cv=min(5, minority), scoring="roc_auc")
    print(f"cross-val AUC: {auc.mean():.3f} (+/- {auc.std():.3f}), n={len(y)}, rug={int(y.sum())}")
    clf.fit(X, y)
    clf.booster_.save_model(model_path)
    print(f"saved model to {model_path}")


class RiskModel:
    def __init__(self, model_path: str):
        import lightgbm as lgb

        self.booster = lgb.Booster(model_file=model_path)

    def score(self, raw: dict) -> int:
        feats = extract_features(raw)
        prob = self.booster.predict([[feats[f] for f in FEATURES]])[0]
        return round(float(prob) * 100)


if __name__ == "__main__":
    # python -m rugguard.model training_data.csv rugguard_model.txt
    train(sys.argv[1] if len(sys.argv) > 1 else "training_data.csv",
          sys.argv[2] if len(sys.argv) > 2 else "rugguard_model.txt")
