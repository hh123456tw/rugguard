import os
import time

from dotenv import load_dotenv
from web3 import Web3

from rugguard.goplus_client import GoPlusClient
from rugguard.notifier import TelegramNotifier, format_alert_message
from rugguard.scanner import PancakePairScanner
from rugguard.scoring import compute_risk_score, risk_level

load_dotenv()

MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "30"))


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


BNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"


def run_once(seen: set[str]) -> None:
    w3 = Web3(Web3.HTTPProvider(os.getenv("BSC_RPC_URL")))
    scanner = PancakePairScanner(w3)
    goplus = GoPlusClient()
    notifier = TelegramNotifier(
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TELEGRAM_CHAT_ID"),
    )

    latest = w3.eth.block_number
    events = scanner.fetch_pairs(latest - 100, latest)
    new_events = [ev for ev in events if ev.pair not in seen]
    for ev in new_events:
        seen.add(ev.pair)
    print(f"found {len(events)} pairs, {len(new_events)} new")
    for ev in new_events:
        token = ev.token1 if ev.token0.lower() == BNB else ev.token0
        evaluate_token(goplus, notifier, token, ev.pair)


def main() -> None:
    seen: set[str] = set()
    while True:
        try:
            run_once(seen)
        except Exception as e:
            print(f"error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
