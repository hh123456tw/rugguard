from collections import defaultdict

from eth_abi import decode
from eth_utils import keccak, to_checksum_address
from web3 import Web3

SWAP_TOPIC = "0x" + keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex().removeprefix("0x")
MINT_TOPIC = "0x" + keccak(text="Mint(address,uint256,uint256)").hex().removeprefix("0x")
BURN_TOPIC = "0x" + keccak(text="Burn(address,uint256,uint256,address)").hex().removeprefix("0x")


def _hex(value) -> str:
    return value if isinstance(value, str) else bytes(value).hex()


def decode_buy(log: dict, alt_is_token0: bool) -> tuple[int, str] | None:
    """回傳 (block, 買家)；不是買入 alt 代幣的 swap 回傳 None。"""
    data = log["data"]
    data_bytes = bytes(data) if isinstance(data, bytes) else bytes.fromhex(data[2:])
    _in0, _in1, out0, out1 = decode(["uint256"] * 4, data_bytes)
    if (out0 if alt_is_token0 else out1) == 0:
        return None
    buyer = to_checksum_address("0x" + _hex(log["topics"][2])[-40:])
    return int(log.get("blockNumber", 0)), buyer


def bundle_features(buys: list[tuple[int, str]]) -> dict:
    by_block = defaultdict(set)
    for block, buyer in buys:
        by_block[block].add(buyer)
    return {
        "early_buyers": len({buyer for _, buyer in buys}),
        "max_same_block_buyers": max((len(s) for s in by_block.values()), default=0),
    }


def activity_features(logs: list, alt_is_token0: bool) -> dict:
    """觀察窗內的買家（bundler）與流動性加入 / 撤出次數。"""
    buys, adds, removes = [], 0, 0
    for log in logs:
        topic = "0x" + _hex(log["topics"][0]).lower().removeprefix("0x")
        if topic == SWAP_TOPIC:
            if b := decode_buy(log, alt_is_token0):
                buys.append(b)
        elif topic == MINT_TOPIC:
            adds += 1
        elif topic == BURN_TOPIC:
            removes += 1
    return {**bundle_features(buys), "lp_adds": adds, "lp_removes": removes}


def fetch_pair_activity(w3: Web3, pair: str, from_block: int, to_block: int, alt_is_token0: bool) -> dict:
    # shortcut: 買家取 Swap 的 `to`，多跳路由時會是下一個 pair；要精準需追 tx 的 from 與資金來源
    logs = w3.eth.get_logs(
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": w3.to_checksum_address(pair),
            "topics": [[SWAP_TOPIC, MINT_TOPIC, BURN_TOPIC]],
        }
    )
    return activity_features(logs, alt_is_token0)
