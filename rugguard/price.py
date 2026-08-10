from web3 import Web3

BNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"

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
    token0 = token0.lower()
    token1 = token1.lower()
    if token0 == BNB:
        # price per alt token = reserve_BNB / reserve_alt
        if reserve1 == 0:
            return 0.0
        return reserve0 / reserve1
    else:
        # token0 is the alt token
        if reserve0 == 0:
            return 0.0
        return reserve1 / reserve0


def get_pair_price(w3: Web3, pair: str, token0: str, token1: str) -> float:
    contract = w3.eth.contract(
        address=w3.to_checksum_address(pair), abi=PAIR_ABI
    )
    reserve0, reserve1, _ = contract.functions.getReserves().call()
    return compute_price_from_reserves(reserve0, reserve1, token0, token1)
