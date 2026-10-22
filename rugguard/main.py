import os
import time

from dotenv import load_dotenv
from web3 import Web3

from rugguard.chains import split_pair
from rugguard.bundler import fetch_pair_activity
from rugguard.export import export_training_csv
from rugguard.goplus_client import GoPlusClient
from rugguard.labeler import label_pending_tokens
from rugguard.model import RiskModel, train
from rugguard import paper
from rugguard.backtest import trade_cost
from rugguard.paths import record_paths
from rugguard.notifier import TelegramNotifier, format_alert_message, format_buy_message
from rugguard.price import compute_price_from_reserves, get_native_usd, get_pair_price, get_pair_reserves, quote_reserve_usd
from rugguard.scanner import PancakePairScanner
from rugguard.scoring import (
    BUNDLE_BUYERS,
    HIGH_TAX,
    MIN_LOCKED_LP,
    _to_float,
    _to_int,
    compute_risk_score,
    top10_holder_percent,
    lp_locked_ratio,
    risk_level,
)
from rugguard.store import LabelStore

load_dotenv()

MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "30"))
LABEL_MIN_AGE_HOURS = int(os.getenv("LABEL_MIN_AGE_HOURS", "24"))
LABEL_FREQUENCY = int(os.getenv("LABEL_FREQUENCY", "6"))  # 每幾小時回填一次標籤
MIN_BUY_SCORE = int(os.getenv("MIN_BUY_SCORE", "50"))
# BSC 約 0.45 秒一塊：600 塊 ≈ 4.5 分鐘後才評估，4000 塊 ≈ 30 分鐘沒流動性就放棄（其他鏈依出塊時間調整）
ENTRY_DELAY_BLOCKS = int(os.getenv("ENTRY_DELAY_BLOCKS", "600"))
MAX_WAIT_BLOCKS = int(os.getenv("MAX_WAIT_BLOCKS", "4000"))
MAX_SCAN_RANGE = 2000


def alert_reasons(token: dict) -> list[str]:
    reasons = []
    if token.get("is_honeypot") == "1":
        reasons.append("honeypot")
    locked = lp_locked_ratio(token)
    if locked is not None and locked < MIN_LOCKED_LP:
        reasons.append(f"liquidity unlocked ({locked:.0%} locked)")
    if token.get("can_take_back_ownership") == "1":
        reasons.append("owner can steal")
    if token.get("owner_change_balance") == "1":
        reasons.append("owner can change balance")
    buy_tax = _to_float(token.get("buy_tax"))
    sell_tax = _to_float(token.get("sell_tax"))
    if buy_tax > HIGH_TAX:
        reasons.append(f"high buy tax {buy_tax:.0%}")
    if sell_tax > HIGH_TAX:
        reasons.append(f"high sell tax {sell_tax:.0%}")
    buyers = _to_int(token.get("max_same_block_buyers"))
    if buyers >= BUNDLE_BUYERS:
        reasons.append(f"bundled buys ({buyers} wallets in one block)")
    return reasons


MODEL_PATH = os.getenv("MODEL_PATH", "rugguard_model.txt")
RETRAIN_DAYS = float(os.getenv("RETRAIN_DAYS", "7"))


def load_model() -> RiskModel | None:
    return RiskModel(MODEL_PATH) if os.path.exists(MODEL_PATH) else None


def retrain(model: RiskModel | None) -> RiskModel | None:
    """匯出最新標籤並重訓；新模型時間外 win AUC 明顯較差就保留舊的。"""
    export_labels()
    try:
        metrics = train("training_data.csv", MODEL_PATH, only_if_better=True)
    except ValueError as e:
        print(f"retrain skipped: {e}")
        return model
    return load_model() if metrics["saved"] else model


def evaluate_pair(w3, goplus, notifier, store, model, ev, latest: int, native_usd: float | None = None) -> bool:
    """回傳 True = 已評估存檔或放棄，False = 還要再等。"""
    split = split_pair(ev.token0, ev.token1)
    if split is None:
        return True  # 兩邊都是（或都不是）報價幣：不是新幣上線，不評估
    if latest < ev.block_number + ENTRY_DELAY_BLOCKS:
        return False
    token, alt_is_token0 = split
    reserves = get_pair_reserves(w3, ev.pair)
    price = compute_price_from_reserves(*reserves, ev.token0, ev.token1)
    if price <= 0:
        # 還沒加流動性就沒有可買的價格，繼續等
        if latest >= ev.block_number + MAX_WAIT_BLOCKS:
            print(f"give up {ev.pair}: no liquidity after {MAX_WAIT_BLOCKS} blocks")
            return True
        return False
    security = goplus.fetch_token_security(token)
    # 特徵只看買入決策前固定 ENTRY_DELAY_BLOCKS 個區塊，避免偵測時間不同造成偏差
    activity = fetch_pair_activity(w3, ev.pair, latest - ENTRY_DELAY_BLOCKS, latest, alt_is_token0)
    prior_tokens, prior_rugs = store.creator_history(security.get("creator_address", ""))
    features = {
        **security,
        **activity,
        "entry_delay_blocks": latest - ev.block_number,
        "liquidity_usd": quote_reserve_usd(*reserves, ev.token0, ev.token1, native_usd),
        "top10_holder_percent": top10_holder_percent(security.get("holders"), ev.pair),
        "creator_prior_tokens": prior_tokens,
        "creator_prior_rugs": prior_rugs,
        "version": 2,
    }
    if model:
        score, buy_score = model.predict(features)
    else:
        score, buy_score = compute_risk_score(features), None
    store.add_token(
        pair=ev.pair,
        token=token,
        block=ev.block_number,
        initial_price=price,
        token0=ev.token0,
        token1=ev.token1,
        features=features,
        score=score,
        buy_score=buy_score,
    )
    messages = []
    if score >= MIN_ALERT_SCORE:
        messages.append(format_alert_message(
            token_address=token, pair=ev.pair, score=score,
            level=risk_level(score), reasons=alert_reasons(features),
        ))
    if buy_score is not None and buy_score >= MIN_BUY_SCORE:
        messages.append(format_buy_message(token, ev.pair, buy_score, score))
        paper.open_position(store, notifier, ev.pair, token, latest, price, trade_cost(features), buy_score)
    for msg in messages:
        try:
            notifier.send(msg)
        except Exception as e:
            print(f"telegram send failed for {ev.pair}: {e}")
    return True


def run_once(state: dict, model: RiskModel | None = None) -> None:
    w3 = Web3(Web3.HTTPProvider(os.getenv("BSC_RPC_URL")))
    scanner = PancakePairScanner(w3)
    goplus = GoPlusClient()
    notifier = TelegramNotifier(
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TELEGRAM_CHAT_ID"),
    )
    store = LabelStore(os.getenv("DB_PATH", "rugguard.db"))
    pending = state.setdefault("pending", {})

    latest = w3.eth.block_number
    try:
        native_usd = get_native_usd(w3)
    except Exception as e:
        native_usd = None
        print(f"native price failed: {e}")
    # shortcut: 停機或啟動時只補最近 MAX_SCAN_RANGE 塊；要補更久需分段查 get_logs
    start = max(state.get("last_block", latest - MAX_SCAN_RANGE) + 1, latest - MAX_SCAN_RANGE)
    events = scanner.fetch_pairs(start, latest)
    state["last_block"] = latest
    new = [ev for ev in events if ev.pair not in pending and store.get_token(ev.pair) is None]
    for ev in new:
        pending[ev.pair] = ev
    print(f"blocks {start}-{latest}: {len(events)} pairs, {len(new)} new, {len(pending)} pending")

    for pair, ev in list(pending.items()):
        try:
            done = evaluate_pair(w3, goplus, notifier, store, model, ev, latest, native_usd)
        except Exception as e:
            # 新代幣常常 GoPlus 還查不到，等下一輪；等太久就放棄
            done = latest >= ev.block_number + MAX_WAIT_BLOCKS
            print(f"{'give up' if done else 'retry later'} {pair}: {e}")
        if done:
            del pending[pair]

    try:
        points = record_paths(w3, store, latest)
        print(f"recorded {len(points)} price points")
        closed = paper.update_positions(store, notifier, points, latest)
        if closed:
            print(f"paper: closed {closed} positions")
    except Exception as e:
        print(f"price path recording failed: {e}")


def run_labeling() -> None:
    w3 = Web3(Web3.HTTPProvider(os.getenv("BSC_RPC_URL")))
    store = LabelStore(os.getenv("DB_PATH", "rugguard.db"))

    def fetch_price(pair: str) -> float:
        row = store.get_token(pair)
        return get_pair_price(w3, pair, row["token0"], row["token1"])

    labeled = label_pending_tokens(store, fetch_price, min_age_hours=LABEL_MIN_AGE_HOURS)
    if labeled:
        print(f"labeled {labeled} tokens")


def export_labels() -> None:
    store = LabelStore(os.getenv("DB_PATH", "rugguard.db"))
    count = export_training_csv(store.get_training_rows(), "training_data.csv")
    if count:
        print(f"exported {count} rows to training_data.csv")
    else:
        print("no labeled rows with features yet, nothing exported")


def main() -> None:
    if os.getenv("RUGGUARD_EXPORT") == "1":
        export_labels()
        return
    state: dict = {}
    model = load_model()
    print("scoring with LightGBM model" if model else "scoring with rules")
    last_label = 0.0  # 啟動時先回填一次標籤，不用等 6 小時
    last_train = time.time()
    while True:
        try:
            run_once(state, model)
            if time.time() - last_label >= LABEL_FREQUENCY * 3600:
                run_labeling()
                last_label = time.time()
            if time.time() - last_train >= RETRAIN_DAYS * 86400:
                model = retrain(model)
                last_train = time.time()
        except Exception as e:
            print(f"error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
