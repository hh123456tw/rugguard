"""狙擊者研究：開盤當下買進的錢包到底有沒有賺錢。

用法：
  python -m rugguard.snipers fetch    # 抓建池後 2 小時的 Swap / Mint / Transfer（可中斷續跑）
  python -m rugguard.snipers report   # 算各組錢包的損益

需要支援歷史 eth_getLogs 的 RPC（BACKFILL_RPC_URL，預設 bloXroute 公開節點）。
"""
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from eth_abi import decode
from eth_utils import keccak
from web3 import Web3

from rugguard.backtest import BLOCK_SECONDS, quote_usd
from rugguard.backfill import CHUNK_BLOCKS
from rugguard.bundler import MINT_TOPIC, SWAP_TOPIC
from rugguard.chains import split_pair

TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex().removeprefix("0x")
WINDOW_BLOCKS = int(2 * 3600 / BLOCK_SECONDS)  # 建池後 2 小時
WORKERS = int(os.getenv("BACKFILL_WORKERS", "8"))
MIN_POSITION_USD = 1.0  # 低於 1 美元多半是檢查 honeypot 的測試買單，不算真的部位
RETRIES = 4
# 依「開盤（第一次加流動性）後第幾個區塊買進」分組；600 塊是本系統的進場時間點
# 實測 BSC 狙擊單集中在加流動性後的下一個區塊（加流動性的交易先進 mempool / builder），所以 0-2 塊都算狙擊
GROUPS = [("blocks 0-2 (sniper)", 0, 2), ("blocks 3-10", 3, 10), ("blocks 11-600", 11, 600),
          ("after 600 (our entry)", 601, 10 ** 9)]


def _hex(value) -> str:
    return (value if isinstance(value, str) else bytes(value).hex()).lower().removeprefix("0x")


def _addr(topic) -> str:
    return "0x" + _hex(topic)[-40:]


def _data(log) -> bytes:
    d = log["data"]
    return bytes(d) if isinstance(d, bytes) else bytes.fromhex(_hex(d))


def decode_trades(pair_logs: list, transfers_out: list, transfers_in: list, alt_is_token0: bool) -> tuple[int | None, list]:
    """把同一筆交易的 Swap 和新幣 Transfer 配對。

    回傳 (第一次加流動性的區塊, [(tx, log_index, block, wallet, side, 新幣數量, 報價幣數量)])。
    買家 = 從池子收到新幣的地址；賣家 = 把新幣轉進池子的地址（Swap 的 to 常是路由合約，不能用）。
    """
    first_mint = min((int(l["blockNumber"]) for l in pair_logs if "0x" + _hex(l["topics"][0]) == MINT_TOPIC),
                     default=None)
    receivers = defaultdict(list)  # tx -> 從池子收到新幣的地址
    senders = defaultdict(list)  # tx -> 把新幣轉進池子的地址
    for log in transfers_out:
        receivers[_hex(log["transactionHash"])].append(_addr(log["topics"][2]))
    for log in transfers_in:
        senders[_hex(log["transactionHash"])].append(_addr(log["topics"][1]))

    trades = []
    for log in pair_logs:
        if "0x" + _hex(log["topics"][0]) != SWAP_TOPIC:
            continue
        in0, in1, out0, out1 = decode(["uint256"] * 4, _data(log))
        alt_in, alt_out = (in0, out0) if alt_is_token0 else (in1, out1)
        quote_in, quote_out = (in1, out1) if alt_is_token0 else (in0, out0)
        tx, block, index = _hex(log["transactionHash"]), int(log["blockNumber"]), int(log["logIndex"])
        if alt_out > 0 and receivers[tx]:
            trades.append((tx, index, block, receivers[tx][0], "buy", alt_out, quote_in))
        elif alt_in > 0 and senders[tx]:
            trades.append((tx, index, block, senders[tx][0], "sell", alt_in, quote_out))
    return first_mint, trades


def amm_sell_value(amount_alt: float, reserve_alt: float, reserve_quote: float) -> float:
    """把 amount_alt 顆新幣賣進池子能拿回多少報價幣（不含手續費）。"""
    if amount_alt <= 0 or reserve_alt <= 0:
        return 0.0
    return reserve_quote * amount_alt / (reserve_alt + amount_alt)


def positions(trades: list, first_mint: int) -> dict:
    """每個錢包在這個幣的部位：(第一次買進距開盤幾塊, 花費, 賣回, 剩餘新幣)。"""
    pos = {}
    for _, _, block, wallet, side, alt, quote in sorted(trades, key=lambda t: (t[2], t[1])):
        p = pos.setdefault(wallet, {"first_buy": None, "spent": 0.0, "received": 0.0, "held": 0.0})
        if side == "buy":
            if p["first_buy"] is None:
                p["first_buy"] = block - first_mint
            p["spent"] += quote
            p["held"] += alt
        else:
            p["received"] += quote
            p["held"] = max(0.0, p["held"] - alt)
    return {w: p for w, p in pos.items() if p["first_buy"] is not None}


def insider_received(trades: list) -> float:
    """窗口內沒買過卻在賣的錢包（開發者 / 內部人，籌碼是建池時拿到的）一共拿走多少報價幣。"""
    buyers = {t[3] for t in trades if t[4] == "buy"}
    return sum(t[6] for t in trades if t[4] == "sell" and t[3] not in buyers)


def group_of(first_buy: int) -> str | None:
    return next((name for name, lo, hi in GROUPS if lo <= first_buy <= hi), None)


# ---------- 抓資料 ----------

def _pad(address: str) -> str:
    return "0x" + "00" * 12 + address.lower().removeprefix("0x")


def get_logs_retry(w3: Web3, params: dict) -> list:
    # 公開節點常逾時：等一下再試，全部失敗才讓這個交易對留到下次
    for attempt in range(RETRIES):
        try:
            return w3.eth.get_logs(params)
        except Exception:
            if attempt == RETRIES - 1:
                raise
            time.sleep(15 * (attempt + 1))
    return []


def fetch_pair(w3: Web3, row) -> tuple[int | None, list]:
    split = split_pair(row["token0"], row["token1"])
    token, alt_is_token0 = split
    pair = w3.to_checksum_address(row["pair"])
    token = w3.to_checksum_address(token)
    pair_logs, outs, ins = [], [], []
    start, end = row["block"], row["block"] + WINDOW_BLOCKS
    for s in range(start, end + 1, CHUNK_BLOCKS):
        e = min(s + CHUNK_BLOCKS - 1, end)
        pair_logs += get_logs_retry(w3, {"fromBlock": s, "toBlock": e, "address": pair,
                                         "topics": [[SWAP_TOPIC, MINT_TOPIC]]})
        outs += get_logs_retry(w3, {"fromBlock": s, "toBlock": e, "address": token,
                                    "topics": [TRANSFER_TOPIC, _pad(row["pair"])]})
        ins += get_logs_retry(w3, {"fromBlock": s, "toBlock": e, "address": token,
                                   "topics": [TRANSFER_TOPIC, None, _pad(row["pair"])]})
    return decode_trades(pair_logs, outs, ins, alt_is_token0)


def target_rows(store) -> list:
    rows = []
    for r in store.get_training_rows():
        if r["label"] not in ("rug", "normal", "win") or not r["features"] or r["initial_price"] <= 0:
            continue
        if json.loads(r["features"]).get("path_complete") and split_pair(r["token0"], r["token1"]):
            rows.append(r)
    return rows


def fetch(store, w3: Web3) -> None:
    done = store.get_sniper_done()
    todo = [r for r in target_rows(store) if r["pair"] not in done]
    print(f"{len(todo)} pairs to fetch with {WORKERS} workers")
    with ThreadPoolExecutor(WORKERS) as ex:
        futures = [(r, ex.submit(fetch_pair, w3, r)) for r in todo]
        for n, (row, fut) in enumerate(futures, 1):
            try:
                first_mint, trades = fut.result()
            except Exception as e:
                print(f"failed {row['pair']}: {e}")
                continue
            store.add_sniper_trades(row["pair"], first_mint, trades)
            print(f"{n}/{len(todo)} {row['pair']} mint={first_mint} trades={len(trades)}")


# ---------- 分析 ----------

def report(store) -> None:
    rows = {r["pair"]: r for r in target_rows(store)}
    results = defaultdict(list)  # 組別 -> [(報酬倍數, 損益美元, 花費美元)]
    wallets = defaultdict(lambda: [0.0, 0.0, 0])  # 狙擊錢包 -> [總花費美元, 總拿回美元, 幣數]
    creator_snipes, tokens, insiders, dust = 0, 0, 0.0, defaultdict(int)
    for pair, first_mint in store.get_sniper_done().items():
        row = rows.get(pair)
        if row is None or first_mint is None:
            continue
        tokens += 1
        usd = quote_usd(row["token0"], row["token1"]) / 10 ** 18
        end_block = row["block"] + WINDOW_BLOCKS
        path = [p for p in store.get_path(pair) if p["block"] <= end_block]
        reserve_alt, reserve_quote = (path[-1]["reserve_alt"], path[-1]["reserve_bnb"]) if path else (0.0, 0.0)
        creator = json.loads(row["features"]).get("creator_address", "").lower()
        trades = store.get_sniper_trades(pair)
        insiders += insider_received(trades) * usd
        for wallet, p in positions(trades, first_mint).items():
            group = group_of(p["first_buy"])
            if group is None or p["spent"] <= 0:
                continue
            if p["spent"] * usd < MIN_POSITION_USD:
                dust[group] += 1
                continue
            final = p["received"] + amm_sell_value(p["held"], reserve_alt, reserve_quote)
            results[group].append((final / p["spent"], (final - p["spent"]) * usd, p["spent"] * usd))
            if group == GROUPS[0][0]:
                w = wallets[wallet]
                w[0], w[1], w[2] = w[0] + p["spent"] * usd, w[1] + final * usd, w[2] + 1
                creator_snipes += wallet == creator

    print(f"tokens analysed: {tokens}; window: first {WINDOW_BLOCKS} blocks (~2h) after first liquidity add")
    print(f"positions under ${MIN_POSITION_USD:.0f} (test buys) excluded: {dict(dust)}")
    print(f"{'group':>24} {'positions':>9} {'median $':>8} {'profitable':>10} {'median x':>8} "
          f"{'total PnL $':>12} {'PnL/spent':>9}")
    for name, _, _ in GROUPS:
        res = results[name]
        if not res:
            continue
        spent = sum(s for _, _, s in res)
        total = sum(pnl for _, pnl, _ in res)
        print(f"{name:>24} {len(res):>9} {statistics.median(s for _, _, s in res):>8.0f} "
              f"{sum(r > 1 for r, _, _ in res) / len(res):>10.0%} "
              f"{statistics.median(r for r, _, _ in res):>8.2f} {total:>12.0f} {total / spent if spent else 0:>9.0%}")

    print(f"\nsellers who never bought in the window (dev / insiders) received: ${insiders:.0f}")
    repeat = {w: v for w, v in wallets.items() if v[2] >= 3}
    print(f"sniper wallets that were the token creator: {creator_snipes}")
    print(f"wallets sniping >= 3 tokens: {len(repeat)}")
    if repeat:
        ranked = sorted(repeat.items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True)
        win = sum(1 for _, v in ranked if v[1] > v[0])
        total = sum(v[1] - v[0] for _, v in ranked)
        print(f"  profitable overall: {win}/{len(ranked)}; combined PnL ${total:.0f}")
        for w, (spent, got, n) in ranked[:5] + ranked[-3:]:
            print(f"  {w} tokens={n} spent=${spent:.0f} got=${got:.0f} pnl=${got - spent:.0f}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    from rugguard.store import LabelStore

    load_dotenv()
    store = LabelStore(os.getenv("DB_PATH", "rugguard.db"))
    if sys.argv[1:] == ["fetch"]:
        fetch(store, Web3(Web3.HTTPProvider(os.getenv("BACKFILL_RPC_URL", "https://bsc.rpc.blxrbdn.com"),
                                            request_kwargs={"timeout": 120})))
    else:
        report(store)
