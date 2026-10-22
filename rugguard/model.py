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
           "early_buyers", "max_same_block_buyers", "entry_delay_blocks",
           "lp_adds", "lp_removes", "liquidity_usd", "top10_holder_percent",
           "creator_prior_tokens", "creator_prior_rugs"]
FEATURES = FLAGS + NUMERIC + ["lp_locked_ratio"]
CLASSES = ["rug", "normal", "win"]  # dead（沒交易）不訓練
MIN_V2_ROWS = 200  # 新流程（延遲評估）資料夠多後只用新資料，避免和舊的偵測當下特徵混用


OPTIONAL = ("liquidity_usd", "top10_holder_percent")  # 查不到時用 -1，和真的 0 分開


def extract_features(raw: dict) -> dict[str, float]:
    feats = {f: float(raw.get(f) == "1") for f in FLAGS}
    feats.update({f: _to_float(raw.get(f)) for f in NUMERIC})
    for f in OPTIONAL:
        if raw.get(f) is None:
            feats[f] = -1.0
    locked = lp_locked_ratio(raw)
    feats["lp_locked_ratio"] = -1.0 if locked is None else locked  # -1 = 未知
    return feats


def _classifier(min_count: int):
    import lightgbm as lgb

    return lgb.LGBMClassifier(objective="multiclass", n_estimators=200, learning_rate=0.05, num_leaves=15,
                              min_child_samples=max(2, min(20, min_count)), verbose=-1)


def walk_forward(df, n_splits: int = 5):
    """依時間先後：用前面的資料訓練、預測後面的一段，逐段往前滾。回傳 (有預測的列, 機率)。"""
    import numpy as np
    from sklearn.model_selection import TimeSeriesSplit

    df = df.sort_values("detected_at") if "detected_at" in df else df
    X, y = df[FEATURES], df["label"].map(CLASSES.index)
    probs = np.full((len(df), len(CLASSES)), np.nan)
    for train_idx, test_idx in TimeSeriesSplit(n_splits=n_splits).split(X):
        counts = y.iloc[train_idx].value_counts()
        if len(counts) < len(CLASSES):
            continue  # 這段訓練資料缺某一類，跳過
        clf = _classifier(int(counts.min())).fit(X.iloc[train_idx], y.iloc[train_idx])
        probs[test_idx] = clf.predict_proba(X.iloc[test_idx])
    mask = ~np.isnan(probs[:, 0])
    return df[mask], probs[mask]


def evaluate(df, probs) -> dict:
    import pandas as pd
    from sklearn.metrics import roc_auc_score

    y = df["label"].map(CLASSES.index).to_numpy()

    def auc(cls):
        truth = y == cls
        return float(roc_auc_score(truth, probs[:, cls])) if 0 < truth.sum() < len(truth) else float("nan")

    top = probs[:, 2] >= pd.Series(probs[:, 2]).quantile(0.9)
    metrics = {
        "n_eval": int(len(y)),
        "rug_auc": auc(0),
        "win_auc": auc(2),
        "top10_win_rate": float((y[top] == 2).mean()),
        "top10_rug_rate": float((y[top] == 0).mean()),
        "base_win_rate": float((y == 2).mean()),
        "base_rug_rate": float((y == 0).mean()),
    }
    if "ret" in df:
        metrics["top10_median_ret"] = float(pd.Series(df["ret"].to_numpy()[top]).median())
    return metrics


def train(csv_path: str, model_path: str, only_if_better: bool = False) -> dict:
    """訓練並存檔，回傳時間外驗證指標。only_if_better=True 時，win AUC 比現有模型差 0.02 以上就不覆蓋。"""
    import json
    import os

    import pandas as pd

    df = pd.read_csv(csv_path)
    df = df[df["label"].isin(CLASSES)]
    version = df["version"] if "version" in df else pd.Series(1, index=df.index)
    if (version >= 2).sum() >= MIN_V2_ROWS:
        df = df[version >= 2]
        print(f"using {len(df)} v2 rows only")
    else:
        print(f"warning: only {(version >= 2).sum()} v2 rows, training on all {len(df)} traded rows")

    y = df["label"].map(CLASSES.index)
    counts = y.value_counts()
    if len(counts) < len(CLASSES) or counts.min() < 2:
        raise ValueError(f"need >= 2 rows of each of rug/normal/win, got {df['label'].value_counts().to_dict()}")

    eval_df, probs = walk_forward(df)
    metrics = {"n": int(len(df)), **{c: int((y == i).sum()) for i, c in enumerate(CLASSES)}, **evaluate(eval_df, probs)}
    print("walk-forward (train on past, test on future): " + json.dumps(metrics, ensure_ascii=False))

    meta_path = model_path + ".json"
    if only_if_better and os.path.exists(meta_path):
        old = json.load(open(meta_path, encoding="utf-8"))
        if metrics["win_auc"] < old.get("win_auc", 0) - 0.02:
            print(f"not saved: win AUC {metrics['win_auc']:.3f} worse than current {old['win_auc']:.3f}")
            return {**metrics, "saved": False}

    clf = _classifier(int(counts.min())).fit(df[FEATURES], y)
    clf.booster_.save_model(model_path)
    json.dump(metrics, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"saved model to {model_path}")
    return {**metrics, "saved": True}


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
