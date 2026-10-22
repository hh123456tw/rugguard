from eth_abi import decode
from web3 import Web3

from rugguard.chains import CHAIN
from rugguard.price import compute_price_from_reserves

# 公開 RPC 不接受多地址 get_logs，改用 Multicall3 一次讀多個交易對的 getReserves
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
GET_RESERVES = bytes.fromhex("0902f1ac")
CHUNK = 200
MULTICALL_ABI = [{
    "name": "aggregate3",
    "type": "function",
    "stateMutability": "payable",
    "inputs": [{"name": "calls", "type": "tuple[]", "components": [
        {"name": "target", "type": "address"},
        {"name": "allowFailure", "type": "bool"},
        {"name": "callData", "type": "bytes"},
    ]}],
    "outputs": [{"name": "returnData", "type": "tuple[]", "components": [
        {"name": "success", "type": "bool"},
        {"name": "returnData", "type": "bytes"},
    ]}],
}]


def to_point(pair: str, block: int, token0: str, token1: str, raw: bytes) -> tuple:
    """回傳 (pair, block, price, 新幣儲備, 報價幣儲備)。"""
    # getReserves 回傳 3 個欄位、Sync 事件 2 個；前兩個都是 reserve0, reserve1
    r0, r1 = decode(["uint112", "uint112"], raw[:64])
    alt_is_token0 = token0.lower() not in CHAIN["quotes"]
    price = compute_price_from_reserves(r0, r1, token0, token1)
    return (pair.lower(), block, price, float(r0 if alt_is_token0 else r1), float(r1 if alt_is_token0 else r0))


def record_paths(w3: Web3, store, block: int) -> list[tuple]:
    # shortcut: 每輪取樣一次（約 1-2 分鐘），看不到同一分鐘內的每筆交易；要逐筆需付費 RPC 的 get_logs
    rows = store.get_tracking_pairs()
    multicall = w3.eth.contract(address=MULTICALL3, abi=MULTICALL_ABI)
    points = []
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        calls = [(w3.to_checksum_address(r["pair"]), True, GET_RESERVES) for r in chunk]
        results = multicall.functions.aggregate3(calls).call(block_identifier=block)
        for r, (ok, raw) in zip(chunk, results):
            if ok and len(raw) == 96:
                points.append(to_point(r["pair"], block, r["token0"], r["token1"], raw))
    store.add_path_points(points)
    return points
