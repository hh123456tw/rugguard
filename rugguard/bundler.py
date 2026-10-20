from collections import defaultdict

from eth_abi import decode
from eth_utils import keccak, to_checksum_address
from web3 import Web3

SWAP_TOPIC = keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()


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


def fetch_early_buys(
    w3: Web3, pair: str, from_block: int, to_block: int, alt_is_token0: bool
) -> list[tuple[int, str]]:
    # shortcut: 買家取 Swap 的 `to`，多跳路由時會是下一個 pair；要精準需追 tx 的 from 與資金來源
    logs = w3.eth.get_logs(
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": w3.to_checksum_address(pair),
            "topics": [SWAP_TOPIC],
        }
    )
    return [b for log in logs if (b := decode_buy(log, alt_is_token0))]
