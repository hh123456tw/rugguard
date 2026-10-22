"""回補舊代幣進場後 24h 的逐筆價格路徑（Sync 事件），供回測使用。

用法：python -m rugguard.backfill
需要支援歷史 eth_getLogs 的 RPC（BACKFILL_RPC_URL，預設 bloXroute 公開節點：每次最多 5000 塊、約 15 秒）。
可中斷，重跑會從沒完成的區段接著做。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from eth_utils import keccak
from web3 import Web3

from rugguard.backtest import BLOCK_SECONDS, HORIZON_BLOCKS
from rugguard.labeler import TRADED_LABELS
from rugguard.paths import to_point

SYNC_TOPIC = "0x" + keccak(text="Sync(uint112,uint112)").hex().removeprefix("0x")
CHUNK_BLOCKS = 5000
WORKERS = int(os.getenv("BACKFILL_WORKERS", "8"))


def plan_chunks(entry_block: int, done: set[int]) -> list[tuple[int, int]]:
    """進場後 HORIZON_BLOCKS 內、尚未完成的 (起, 迄) 區段。"""
    end = entry_block + HORIZON_BLOCKS
    return [(s, min(s + CHUNK_BLOCKS - 1, end))
            for s in range(entry_block + 1, end + 1, CHUNK_BLOCKS) if s not in done]


def last_per_block(points: list[tuple]) -> list[tuple]:
    # 同一區塊多筆交易只留最後一筆（區塊結束時的價格）
    by_block = {}
    for p in points:
        by_block[p[1]] = p
    return list(by_block.values())


def block_timestamp(w3: Web3, number: int) -> int:
    # BSC 區塊 extraData 太長，web3 解析 get_block 會報錯，直接讀原始欄位
    return int(w3.provider.make_request("eth_getBlockByNumber", [hex(number), False])["result"]["timestamp"], 16)


def estimate_block(w3: Web3, ts: float, near: int) -> int:
    block = near
    for _ in range(4):
        block += round((ts - block_timestamp(w3, block)) / BLOCK_SECONDS)
    return block


def fetch_chunk(w3: Web3, row, start: int, end: int) -> list[tuple]:
    logs = w3.eth.get_logs({"fromBlock": start, "toBlock": end,
                            "address": w3.to_checksum_address(row["pair"]), "topics": [SYNC_TOPIC]})
    points = []
    for log in logs:
        data = log["data"]
        raw = bytes(data) if isinstance(data, bytes) else bytes.fromhex(data[2:])
        points.append(to_point(row["pair"], int(log["blockNumber"]), row["token0"], row["token1"], raw))
    return last_per_block(points)


def entry_block_for(w3: Web3, row, feats: dict) -> int:
    if "entry_block" in feats:
        return feats["entry_block"]
    if "entry_delay_blocks" in feats:
        return row["block"] + int(feats["entry_delay_blocks"])
    # 舊資料：進場 = 偵測當下，用偵測時間反推區塊
    ts = datetime.fromisoformat(row["detected_at"]).timestamp()
    return estimate_block(w3, ts, row["block"])


def run(store, w3_hist: Web3, w3_blocks: Web3) -> None:
    rows = [r for r in store.get_training_rows()
            if r["label"] in TRADED_LABELS and r["features"] and r["initial_price"] > 0]
    todo = []
    for row in rows:
        feats = json.loads(row["features"])
        if feats.get("path_complete"):
            continue
        if "entry_block" not in feats:
            feats["entry_block"] = entry_block_for(w3_blocks, row, feats)
            store.update_features(row["pair"], feats)
        chunks = plan_chunks(feats["entry_block"], store.get_done_chunks(row["pair"]))
        todo.append((row, feats, chunks))
    total = sum(len(c) for _, _, c in todo)
    print(f"{len(todo)} tokens, {total} chunks to fetch with {WORKERS} workers")

    done_count = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for row, feats, chunks in todo:
            futures = [(s, ex.submit(fetch_chunk, w3_hist, row, s, e)) for s, e in chunks]
            ok = True
            for start, fut in futures:
                try:
                    store.add_path_points(fut.result())
                    store.mark_chunk_done(row["pair"], start)
                    done_count += 1
                except Exception as e:
                    ok = False
                    print(f"chunk failed {row['pair']} @{start}: {e}")
            if ok:
                feats["path_complete"] = True
                store.update_features(row["pair"], feats)
            print(f"{done_count}/{total} chunks, {row['pair']} {'complete' if ok else 'partial'}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    from rugguard.store import LabelStore

    load_dotenv()
    run(
        LabelStore(os.getenv("DB_PATH", "rugguard.db")),
        Web3(Web3.HTTPProvider(os.getenv("BACKFILL_RPC_URL", "https://bsc.rpc.blxrbdn.com"),
                               request_kwargs={"timeout": 120})),
        Web3(Web3.HTTPProvider(os.getenv("BSC_RPC_URL"))),
    )
