"""streamlit run rugguard/dashboard.py"""
import json
import os

import pandas as pd

from rugguard.scoring import risk_level
from rugguard.store import LabelStore


def load_frame(db_path: str) -> pd.DataFrame:
    rows = LabelStore(db_path).get_all_tokens()
    df = pd.DataFrame([dict(r) for r in rows], columns=[
        "pair", "token", "detected_at", "score", "label", "initial_price", "label_price", "features"])
    df["level"] = df["score"].map(lambda s: risk_level(int(s)) if pd.notna(s) else "UNKNOWN")
    df["bundle_buyers"] = df["features"].map(
        lambda f: json.loads(f).get("max_same_block_buyers") if f else None)
    return df.drop(columns=["features"])


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="RugGuard", layout="wide")
    st.title("RugGuard 新代幣風險儀表板")
    df = load_frame(os.getenv("DB_PATH", "rugguard.db"))
    if df.empty:
        st.info("資料庫還沒有任何交易對，先執行 python -m rugguard.main")
        return

    labeled = df[df["label"].notna()]
    rug_rate = (labeled["label"] == "rug").mean() if len(labeled) else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("偵測交易對", len(df))
    c2.metric("已標籤", len(labeled))
    c3.metric("Rug 比例", f"{rug_rate:.0%}")

    st.subheader("風險等級分布")
    st.bar_chart(df["level"].value_counts())

    if len(labeled):
        st.subheader("各風險等級的實際 rug 比例")
        st.bar_chart(labeled.groupby("level")["label"].apply(lambda s: (s == "rug").mean()))

    st.subheader("最新交易對")
    st.dataframe(df.head(200), width="stretch")


if __name__ == "__main__":
    main()
