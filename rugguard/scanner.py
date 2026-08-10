from dataclasses import dataclass

from eth_abi import decode
from eth_utils import keccak, to_checksum_address
from web3 import Web3

PANCAAKESWAP_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
PAIR_CREATED_TOPIC = keccak(text="PairCreated(address,address,address,uint256)").hex()

PAIR_CREATED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "token0", "type": "address"},
        {"indexed": True, "name": "token1", "type": "address"},
        {"indexed": False, "name": "pair", "type": "address"},
        {"indexed": False, "name": "allPairsLength", "type": "uint256"},
    ],
    "name": "PairCreated",
    "type": "event",
}


@dataclass
class PairCreatedEvent:
    token0: str
    token1: str
    pair: str
    block_number: int


def _topic_suffix(topic) -> str:
    if isinstance(topic, str):
        return topic[-40:]
    return bytes(topic).hex()[-40:]


def decode_pair_created_log(log: dict) -> PairCreatedEvent:
    topics = log.get("topics", [])
    if len(topics) < 3:
        raise ValueError("log has fewer than 3 topics")

    token0 = to_checksum_address("0x" + _topic_suffix(topics[1]))
    token1 = to_checksum_address("0x" + _topic_suffix(topics[2]))

    data = log["data"]
    data_bytes = bytes(data) if isinstance(data, bytes) else bytes.fromhex(data[2:])
    pair, _all_pairs_length = decode(["address", "uint256"], data_bytes)
    pair = to_checksum_address(pair)

    return PairCreatedEvent(
        token0=token0,
        token1=token1,
        pair=pair,
        block_number=int(log.get("blockNumber", 0)),
    )


class PancakePairScanner:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.factory = w3.to_checksum_address(PANCAAKESWAP_FACTORY)

    def fetch_pairs(self, from_block: int, to_block: int) -> list[PairCreatedEvent]:
        logs = self.w3.eth.get_logs(
            {
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": self.factory,
                "topics": [PAIR_CREATED_TOPIC],
            }
        )
        return [decode_pair_created_log(log) for log in logs]
