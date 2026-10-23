import pytest
from eth_abi import encode

from rugguard.bundler import MINT_TOPIC, SWAP_TOPIC
from rugguard.snipers import (TRANSFER_TOPIC, amm_sell_value, decode_trades, group_of,
                              insider_received, positions)
from rugguard.store import LabelStore

PAIR = "0x" + "11" * 20
SNIPER = "0x" + "aa" * 20
LATE = "0x" + "bb" * 20
ROUTER = "0x" + "cc" * 20


def topic(addr):
    return "0x" + "00" * 12 + addr[2:]


def swap(tx, block, idx, in0, in1, out0, out1, to=ROUTER):
    return {"topics": [SWAP_TOPIC, topic(ROUTER), topic(to)], "data": "0x" + encode(["uint256"] * 4, [in0, in1, out0, out1]).hex(),
            "transactionHash": tx, "blockNumber": block, "logIndex": idx}


def transfer(tx, frm, to, value=1):
    return {"topics": [TRANSFER_TOPIC, topic(frm), topic(to)], "data": "0x" + encode(["uint256"], [value]).hex(),
            "transactionHash": tx, "blockNumber": 0, "logIndex": 0}


def mint(block):
    return {"topics": [MINT_TOPIC, topic(ROUTER)], "data": "0x", "transactionHash": "0xm", "blockNumber": block, "logIndex": 0}


def test_decode_buy_and_sell_attributed_by_transfer_not_swap_to():
    # 新幣是 token0：買 = token0 流出；賣 = token0 流入，Swap 的 to 是路由合約
    pair_logs = [mint(100), swap("0x01", 100, 1, 0, 50, 1000, 0), swap("0x02", 105, 1, 1000, 0, 0, 80)]
    outs = [transfer("0x01", PAIR, SNIPER)]
    ins = [transfer("0x02", SNIPER, PAIR)]
    first_mint, trades = decode_trades(pair_logs, outs, ins, alt_is_token0=True)
    assert first_mint == 100
    assert trades == [("01", 1, 100, SNIPER, "buy", 1000, 50), ("02", 1, 105, SNIPER, "sell", 1000, 80)]


def test_decode_swap_without_matching_transfer_is_skipped():
    _, trades = decode_trades([swap("0x09", 100, 1, 0, 50, 1000, 0)], [], [], alt_is_token0=True)
    assert trades == []


def test_alt_token1_direction():
    pair_logs = [swap("0x01", 100, 1, 50, 0, 0, 1000)]  # 新幣是 token1：付 token0（報價幣）換 token1
    _, trades = decode_trades(pair_logs, [transfer("0x01", PAIR, SNIPER)], [], alt_is_token0=False)
    assert trades == [("01", 1, 100, SNIPER, "buy", 1000, 50)]


def test_positions_track_spent_received_held():
    trades = [("t1", 0, 100, SNIPER, "buy", 1000, 50), ("t2", 0, 130, SNIPER, "sell", 600, 90),
              ("t3", 0, 700, LATE, "buy", 10, 5)]
    pos = positions(trades, first_mint=100)
    assert pos[SNIPER] == {"first_buy": 0, "spent": 50, "received": 90, "held": 400}
    assert pos[LATE]["first_buy"] == 600


def test_seller_without_buy_in_window_is_not_a_position():
    pos = positions([("t1", 0, 100, LATE, "sell", 10, 5)], first_mint=100)
    assert pos == {}


def test_groups_boundaries():
    assert group_of(0) == "blocks 0-2 (sniper)"
    assert group_of(2) == "blocks 0-2 (sniper)"
    assert group_of(3) == "blocks 3-10"
    assert group_of(10) == "blocks 3-10"
    assert group_of(600) == "blocks 11-600"
    assert group_of(601) == "after 600 (our entry)"


def test_amm_sell_value():
    assert amm_sell_value(100, 100, 50) == pytest.approx(25)
    assert amm_sell_value(0, 100, 50) == 0
    assert amm_sell_value(10, 0, 50) == 0


def test_store_sniper_roundtrip():
    store = LabelStore(":memory:")
    store.add_sniper_trades("0xp", 100, [("t1", 0, 100, SNIPER, "buy", 1000, 50)])
    store.add_sniper_trades("0xq", None, [])
    assert store.get_sniper_done() == {"0xp": 100, "0xq": None}
    assert store.get_sniper_trades("0xp") == [("t1", 0, 100, SNIPER, "buy", 1000.0, 50.0)]


def test_insider_received_counts_only_sellers_who_never_bought():
    trades = [("t1", 0, 100, SNIPER, "buy", 1000, 50), ("t2", 0, 110, SNIPER, "sell", 1000, 70),
              ("t3", 0, 120, LATE, "sell", 5000, 300)]
    assert insider_received(trades) == 300
