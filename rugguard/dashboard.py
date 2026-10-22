"""streamlit run rugguard/dashboard.py"""
import json
import os

import pandas as pd

from rugguard.scoring import risk_level
from rugguard.store import LabelStore


def load_frame(db_path: str) -> pd.DataFrame:
    rows = LabelStore(db_path).get_all_tokens()
    df = pd.DataFrame([dict(r) for r in rows], columns=[
        "pair", "token", "detected_at", "score", "buy_score", "label", "initial_price", "label_price", "features"])
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
    traded = labeled[labeled["label"] != "dead"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("偵測交易對", len(df))
    c2.metric("已標籤（有交易）", f"{len(labeled)}（{len(traded)}）")
    c3.metric("有交易中 rug 比例", f"{(traded['label'] == 'rug').mean():.0%}" if len(traded) else "-")
    c4.metric("有交易中 win 比例", f"{(traded['label'] == 'win').mean():.0%}" if len(traded) else "-")

    st.subheader("能買候選（尚未滿 24h，依能買分數排序）")
    st.caption("能買分數 = 模型估計 24h 漲 2 倍以上的機率；僅供研究，不是投資建議。")
    cand = df[df["buy_score"].notna() & df["label"].isna()].sort_values("buy_score", ascending=False)
    st.dataframe(cand.head(30), width="stretch")

    if len(labeled):
        st.subheader("標籤分布")
        st.bar_chart(labeled["label"].value_counts())

    st.subheader("風險等級分布")
    st.bar_chart(df["level"].value_counts())

    if len(labeled):
        st.subheader("各風險等級的實際 rug 比例")
        st.bar_chart(labeled.groupby("level")["label"].apply(lambda s: (s == "rug").mean()))

    st.subheader("最新交易對")
    st.dataframe(df.head(200), width="stretch")


if __name__ == "__main__":
    main()
