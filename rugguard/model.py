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
           "early_buyers", "max_same_block_buyers", "entry_delay_blocks"]
FEATURES = FLAGS + NUMERIC + ["lp_locked_ratio"]
CLASSES = ["rug", "normal", "win"]  # dead（沒交易）不訓練
MIN_V2_ROWS = 200  # 新流程（延遲評估）資料夠多後只用新資料，避免和舊的偵測當下特徵混用


def extract_features(raw: dict) -> dict[str, float]:
    feats = {f: float(raw.get(f) == "1") for f in FLAGS}
    feats.update({f: _to_float(raw.get(f)) for f in NUMERIC})
    locked = lp_locked_ratio(raw)
    feats["lp_locked_ratio"] = -1.0 if locked is None else locked  # -1 = 未知
    return feats


def train(csv_path: str, model_path: str) -> None:
    import lightgbm as lgb
    import pandas as pd
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    df = pd.read_csv(csv_path)
    df = df[df["label"].isin(CLASSES)]
    version = df["version"] if "version" in df else pd.Series(1, index=df.index)
    if (version >= 2).sum() >= MIN_V2_ROWS:
        df = df[version >= 2]
        print(f"using {len(df)} v2 rows only")
    else:
        print(f"warning: only {(version >= 2).sum()} v2 rows, training on all {len(df)} traded rows")

    X = df[FEATURES]
    y = df["label"].map(CLASSES.index)
    counts = y.value_counts()
    if len(counts) < len(CLASSES) or counts.min() < 2:
        raise ValueError(f"need >= 2 rows of each of rug/normal/win, got {df['label'].value_counts().to_dict()}")

    clf = lgb.LGBMClassifier(objective="multiclass", n_estimators=200, learning_rate=0.05, num_leaves=15,
                             min_child_samples=min(20, int(counts.min())), verbose=-1)
    # 不打亂：折大致依時間切，比隨機切更接近實戰
    cv = StratifiedKFold(n_splits=min(5, int(counts.min())))
    probs = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")
    print(f"n={len(y)} " + " ".join(f"{c}={int((y == i).sum())}" for i, c in enumerate(CLASSES)))
    print(f"rug AUC: {roc_auc_score(y == 0, probs[:, 0]):.3f}  win AUC: {roc_auc_score(y == 2, probs[:, 2]):.3f}")

    top = probs[:, 2] >= pd.Series(probs[:, 2]).quantile(0.9)
    base = (y == 2).mean()
    print(f"top 10% by buy score: win rate {(y[top] == 2).mean():.0%} (base {base:.0%}), "
          f"rug rate {(y[top] == 0).mean():.0%} (base {(y == 0).mean():.0%})")
    if "ret" in df:
        print(f"top 10% median 24h return: {df['ret'][top].median():.2f}x (all traded: {df['ret'].median():.2f}x)")

    clf.fit(X, y)
    clf.booster_.save_model(model_path)
    print(f"saved model to {model_path}")


class RiskModel:
    def __init__(self, model_path: str):
        import lightgbm as lgb

        self.booster = lgb.Booster(model_file=model_path)

    def predict(self, raw: dict) -> tuple[int, int]:
        """回傳 (風險分數 = P(rug)×100, 能買分數 = P(win)×100)。"""
        feats = extract_features(raw)
        probs = self.booster.predict([[feats[f] for f in FEATURES]])[0]
        return round(float(probs[0]) * 100), round(float(probs[2]) * 100)


if __name__ == "__main__":
    # python -m rugguard.model training_data.csv rugguard_model.txt
    train(sys.argv[1] if len(sys.argv) > 1 else "training_data.csv",
          sys.argv[2] if len(sys.argv) > 2 else "rugguard_model.txt")
