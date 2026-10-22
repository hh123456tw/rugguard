from web3 import Web3

from rugguard.chains import CHAIN

PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"},
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]


def compute_price_from_reserves(
    reserve0: int, reserve1: int, token0: str, token1: str
) -> float:
    # 價格 = 每顆新幣值多少報價幣（WBNB / USDT ...）
    if token0.lower() in CHAIN["quotes"]:
        return reserve0 / reserve1 if reserve1 else 0.0
    return reserve1 / reserve0 if reserve0 else 0.0


def get_pair_reserves(w3: Web3, pair: str) -> tuple[int, int]:
    contract = w3.eth.contract(address=w3.to_checksum_address(pair), abi=PAIR_ABI)
    reserve0, reserve1, _ = contract.functions.getReserves().call()
    return reserve0, reserve1


def get_pair_price(w3: Web3, pair: str, token0: str, token1: str) -> float:
    return compute_price_from_reserves(*get_pair_reserves(w3, pair), token0, token1)


def quote_reserve_usd(reserve0: int, reserve1: int, token0: str, token1: str, native_usd: float | None) -> float | None:
    """池子裡報價幣那一邊值多少美元（流動性深度）。原生幣價格未知時回傳 None。"""
    quote, reserve = (token0, reserve0) if token0.lower() in CHAIN["quotes"] else (token1, reserve1)
    amount = reserve / 10 ** 18  # BSC 上的 WBNB / USDT / BUSD / USDC 都是 18 位小數
    if quote.lower() in CHAIN["stables"]:
        return amount
    return amount * native_usd if native_usd else None


def get_native_usd(w3: Web3) -> float:
    pair, native_is_token0 = CHAIN["native_usd_pair"]
    r0, r1 = get_pair_reserves(w3, pair)
    return r1 / r0 if native_is_token0 else r0 / r1
