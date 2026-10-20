from eth_abi import encode

from rugguard.bundler import SWAP_TOPIC, bundle_features, decode_buy

BUYER = "0x" + "ab" * 20


def swap_log(block, buyer, out0, out1):
    return {
        "blockNumber": block,
        "topics": [SWAP_TOPIC, "0x" + "00" * 32, "0x" + "00" * 12 + buyer[2:]],
        "data": "0x" + encode(["uint256"] * 4, [0, 1, out0, out1]).hex(),
    }


def test_decode_buy_alt_token0():
    block, buyer = decode_buy(swap_log(5, BUYER, 1000, 0), alt_is_token0=True)
    assert block == 5
    assert buyer.lower() == BUYER


def test_decode_sell_is_not_a_buy():
    # alt 是 token0，但流出的是 token1（BNB）= 賣出
    assert decode_buy(swap_log(5, BUYER, 0, 1000), alt_is_token0=True) is None


def test_bundle_features_counts_same_block_wallets():
    buys = [(1, "a"), (1, "b"), (1, "c"), (2, "a"), (3, "d")]
    assert bundle_features(buys) == {"early_buyers": 4, "max_same_block_buyers": 3}


def test_same_wallet_buying_twice_is_one_buyer():
    assert bundle_features([(1, "a"), (1, "a")]) == {"early_buyers": 1, "max_same_block_buyers": 1}


def test_bundle_features_no_buys():
    assert bundle_features([]) == {"early_buyers": 0, "max_same_block_buyers": 0}
