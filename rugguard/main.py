import os
import time

from dotenv import load_dotenv
from web3 import Web3

from rugguard.export import export_training_csv
from rugguard.goplus_client import GoPlusClient
from rugguard.labeler import label_pending_tokens
from rugguard.notifier import TelegramNotifier, format_alert_message
from rugguard.price import get_pair_price
from rugguard.scanner import PancakePairScanner
from rugguard.scoring import compute_risk_score, risk_level
from rugguard.store import LabelStore

load_dotenv()

MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "30"))
LABEL_MIN_AGE_HOURS = int(os.getenv("LABEL_MIN_AGE_HOURS", "24"))
LABEL_FREQUENCY = int(os.getenv("LABEL_FREQUENCY", "6"))  # 每幾小時回填一次標籤
BNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"


def alert_reasons(token: dict) -> list[str]:
    reasons = []
    if token.get("is_honeypot") == "1":
        reasons.append("honeypot")
    if token.get("liquidity") == "0":
        reasons.append("liquidity unlocked")
    if token.get("can_take_back_ownership") == "1":
        reasons.append("owner can steal")
    if token.get("owner_change_balance") == "1":
        reasons.append("owner can change balance")
    try:
        if float(token.get("buy_tax", 0)) > 10:
            reasons.append(f"high buy tax {token['buy_tax']}%")
        if float(token.get("sell_tax", 0)) > 10:
            reasons.append(f"high sell tax {token['sell_tax']}%")
    except (TypeError, ValueError):
        pass
    return reasons


def evaluate_token(goplus: GoPlusClient, notifier: TelegramNotifier, token: str, pair: str) -> None:
    security = goplus.fetch_token_security(token)
    score = compute_risk_score(security)
    level = risk_level(score)
    if score >= MIN_ALERT_SCORE:
        notifier.send(
            format_alert_message(
                token_address=token,
                pair=pair,
                score=score,
                level=level,
                reasons=alert_reasons(security),
            )
        )


def record_new_pair(w3: Web3, store: LabelStore, ev) -> None:
    token = ev.token1 if ev.token0.lower() == BNB else ev.token0
    try:
        price = get_pair_price(w3, ev.pair, ev.token0, ev.token1)
    except Exception as e:
        print(f"price snapshot failed for {ev.pair}: {e}")
        return
    store.add_token(
        pair=ev.pair,
        token=token,
        block=ev.block_number,
        initial_price=price,
        token0=ev.token0,
        token1=ev.token1,
    )


def run_once(seen: set[str]) -> None:
    w3 = Web3(Web3.HTTPProvider(os.getenv("BSC_RPC_URL")))
    scanner = PancakePairScanner(w3)
    goplus = GoPlusClient()
    notifier = TelegramNotifier(
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TELEGRAM_CHAT_ID"),
    )
    store = LabelStore(os.getenv("DB_PATH", "rugguard.db"))

    latest = w3.eth.block_number
    events = scanner.fetch_pairs(latest - 100, latest)
    new_events = [ev for ev in events if ev.pair not in seen]
    for ev in new_events:
        seen.add(ev.pair)
    print(f"found {len(events)} pairs, {len(new_events)} new")
    for ev in new_events:
        token = ev.token1 if ev.token0.lower() == BNB else ev.token0
        evaluate_token(goplus, notifier, token, ev.pair)
        record_new_pair(w3, store, ev)


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
    export_training_csv(store.get_training_rows(), "training_data.csv")
    print("exported to training_data.csv")


def main() -> None:
    if os.getenv("RUGGUARD_EXPORT") == "1":
        export_labels()
        return
    seen: set[str] = set()
    last_label = time.time()
    while True:
        try:
            run_once(seen)
            if time.time() - last_label >= LABEL_FREQUENCY * 3600:
                run_labeling()
                last_label = time.time()
        except Exception as e:
            print(f"error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
