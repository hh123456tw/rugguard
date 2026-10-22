import pytest
from eth_abi import encode

from rugguard.bundler import BURN_TOPIC, MINT_TOPIC, SWAP_TOPIC, activity_features
from rugguard.price import quote_reserve_usd
from rugguard.scoring import top10_holder_percent
from rugguard.store import LabelStore

WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
USDT = "0x55d398326f99059ff775485246999027b3197955"
BUYER = "0x" + "ab" * 20
PAIR = "0x" + "cd" * 20


def log(topic, data=b"", block=1):
    return {"blockNumber": block, "topics": [topic, "0x" + "00" * 32, "0x" + "00" * 12 + BUYER[2:]],
            "data": "0x" + data.hex()}


def test_activity_counts_lp_events_and_buys():
    logs = [
        log(MINT_TOPIC, encode(["uint256"] * 2, [1, 1])),
        log(SWAP_TOPIC, encode(["uint256"] * 4, [0, 1, 500, 0])),  # 買入（新幣是 token0）
        log(BURN_TOPIC, encode(["uint256"] * 2, [1, 1])),
        log("0x" + "ee" * 32),  # 不認識的事件不計
    ]
    f = activity_features(logs, alt_is_token0=True)
    assert (f["lp_adds"], f["lp_removes"], f["early_buyers"]) == (1, 1, 1)


def test_top10_excludes_pair_and_burn_addresses():
    holders = [
        {"address": PAIR.upper().replace("0X", "0x"), "percent": "0.5"},
        {"address": "0x000000000000000000000000000000000000dEaD", "percent": "0.3"},
        {"address": BUYER, "percent": "0.15"},
        {"address": "0x" + "01" * 20, "percent": "0.05"},
    ]
    assert top10_holder_percent(holders, PAIR) == pytest.approx(0.2)


def test_top10_only_counts_ten():
    holders = [{"address": f"0x{i:040x}", "percent": "0.05"} for i in range(1, 16)]
    assert top10_holder_percent(holders, PAIR) == pytest.approx(0.5)


def test_top10_unknown_without_holders():
    assert top10_holder_percent(None, PAIR) is None


def test_liquidity_usd_stable_and_native():
    one = 10 ** 18
    assert quote_reserve_usd(500 * one, 7, USDT, "0xalt", native_usd=None) == pytest.approx(500)
    assert quote_reserve_usd(7, 2 * one, "0xalt", WBNB, native_usd=600) == pytest.approx(1200)
    assert quote_reserve_usd(7, 2 * one, "0xalt", WBNB, native_usd=None) is None


def test_creator_history_counts_only_same_creator():
    store = LabelStore(":memory:")
    creator = "0x" + "ab" * 20
    store.add_token(pair="0x1", token="t", block=1, initial_price=1.0, features={"creator_address": creator})
    store.update_label(pair="0x1", label="rug", label_price=0.0)
    store.add_token(pair="0x2", token="t", block=1, initial_price=1.0, features={"creator_address": creator})
    # 前綴相同但不同的地址不能算進來
    store.add_token(pair="0x3", token="t", block=1, initial_price=1.0,
                    features={"creator_address": creator + "ff"})
    assert store.creator_history(creator.upper().replace("0X", "0x")) == (2, 1)
    assert store.creator_history("") == (0, 0)
