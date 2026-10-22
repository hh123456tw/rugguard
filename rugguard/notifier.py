import requests


def format_alert_message(
    token_address: str, pair: str, score: int, level: str, reasons: list[str]
) -> str:
    lines = [
        f"🚨 新代幣風險警示 [{level}]",
        f"風險分數: {score}/100",
        f"代幣: {token_address}",
        f"交易對: {pair}",
    ]
    if reasons:
        lines.append("原因: " + ", ".join(reasons))
    return "\n".join(lines)


def format_buy_message(token_address: str, pair: str, buy_score: int, risk_score: int) -> str:
    return "\n".join([
        "🟢 能買候選",
        f"能買分數: {buy_score}/100（模型估計 24h 漲 2 倍以上的機率）",
        f"風險分數: {risk_score}/100",
        f"代幣: {token_address}",
        f"交易對: {pair}",
        "僅為模型估計，不是投資建議；新代幣隨時可能歸零。",
    ])


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": self.chat_id, "text": message},
            timeout=15,
        )
        resp.raise_for_status()
