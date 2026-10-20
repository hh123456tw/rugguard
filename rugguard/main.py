import os
import time

from dotenv import load_dotenv
from web3 import Web3

from rugguard.bundler import bundle_features, fetch_early_buys
from rugguard.export import export_training_csv
from rugguard.goplus_client import GoPlusClient
from rugguard.labeler import label_pending_tokens
from rugguard.model import RiskModel
from rugguard.notifier import TelegramNotifier, format_alert_message
from rugguard.price import get_pair_price
from rugguard.scanner import PancakePairScanner
from rugguard.scoring import (
    BUNDLE_BUYERS,
    HIGH_TAX,
    MIN_LOCKED_LP,
    _to_float,
    _to_int,
    compute_risk_score,
    lp_locked_ratio,
    risk_level,
)
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


def load_model() -> RiskModel | None:
    path = os.getenv("MODEL_PATH", "rugguard_model.txt")
    return RiskModel(path) if os.path.exists(path) else None


def process_pair(w3, goplus, notifier, store, model, ev, latest: int) -> None:
    alt_is_token0 = ev.token0.lower() != BNB
    token = ev.token0 if alt_is_token0 else ev.token1
    security = goplus.fetch_token_security(token)
    buys = fetch_early_buys(w3, ev.pair, ev.block_number, latest, alt_is_token0)
    features = {**security, **bundle_features(buys)}
    score = model.score(features) if model else compute_risk_score(features)
    price = get_pair_price(w3, ev.pair, ev.token0, ev.token1)
    store.add_token(
        pair=ev.pair,
        token=token,
        block=ev.block_number,
        initial_price=price,
        token0=ev.token0,
        token1=ev.token1,
        features=features,
        score=score,
    )
    if score >= MIN_ALERT_SCORE:
        try:
            notifier.send(
                format_alert_message(
                    token_address=token,
                    pair=ev.pair,
                    score=score,
                    level=risk_level(score),
                    reasons=alert_reasons(features),
                )
            )
        except Exception as e:
            print(f"telegram send failed for {ev.pair}: {e}")


def run_once(seen: set[str], model: RiskModel | None = None) -> None:
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
    print(f"found {len(events)} pairs, {len(new_events)} new")
    for ev in new_events:
        try:
            process_pair(w3, goplus, notifier, store, model, ev, latest)
        except Exception as e:
            # 新代幣常常 GoPlus 還查不到；不加進 seen，下一輪（仍在 100 區塊內）會重試
            print(f"skip {ev.pair} this round: {e}")
            continue
        seen.add(ev.pair)


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
    seen: set[str] = set()
    model = load_model()
    print("scoring with LightGBM model" if model else "scoring with rules")
    last_label = time.time()
    while True:
        try:
            run_once(seen, model)
            if time.time() - last_label >= LABEL_FREQUENCY * 3600:
                run_labeling()
                last_label = time.time()
        except Exception as e:
            print(f"error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
