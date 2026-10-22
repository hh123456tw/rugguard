"""鏈的設定。擴展到其他 Uniswap v2 系的 EVM 鏈時，只要加一筆設定並設 CHAIN 環境變數。"""
import os

CHAINS = {
    "bsc": {
        "goplus_chain_id": "56",
        "factory": "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",  # PancakeSwap v2
        "block_seconds": 0.45,
        # 報價幣：交易對必須剛好一邊是這些，另一邊才是要評估的新幣
        "quotes": {
            "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
            "0x55d398326f99059ff775485246999027b3197955",  # USDT
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
        },
        "stables": {
            "0x55d398326f99059ff775485246999027b3197955",
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
        },
        # USDT/WBNB 池：token0 = USDT，所以原生幣不是 token0
        "native_usd_pair": ("0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE", False),
    },
}

CHAIN = CHAINS[os.getenv("CHAIN", "bsc")]


def split_pair(token0: str, token1: str) -> tuple[str, bool] | None:
    """回傳 (新幣地址, 新幣是否為 token0)；兩邊都是或都不是報價幣時回傳 None（不評估）。"""
    q0, q1 = token0.lower() in CHAIN["quotes"], token1.lower() in CHAIN["quotes"]
    if q0 == q1:
        return None
    return (token1, False) if q0 else (token0, True)
