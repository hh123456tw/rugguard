from datetime import datetime, timedelta, timezone

from eth_abi import encode

from rugguard.paths import to_point
from rugguard.store import LabelStore

BNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
PAIR = "0x" + "11" * 20


def test_to_point_alt_token0():
    raw = encode(["uint112", "uint112", "uint32"], [1000, 5, 0])
    assert to_point(PAIR.upper().replace("0X", "0x"), 7, "0xAlt", BNB, raw) == (PAIR, 7, 0.005, 1000.0, 5.0)


def test_to_point_alt_token1():
    raw = encode(["uint112", "uint112", "uint32"], [5, 1000, 0])
    assert to_point(PAIR, 7, BNB, "0xAlt", raw) == (PAIR, 7, 0.005, 1000.0, 5.0)


def test_store_path_roundtrip_and_dedupe():
    store = LabelStore(":memory:")
    pts = [(PAIR, 5, 0.5, 10.0, 1.0), (PAIR, 4, 0.4, 10.0, 1.0)]
    store.add_path_points(pts)
    store.add_path_points(pts)  # 同一區塊重複取樣不重複存
    assert [(r["block"], r["price"]) for r in store.get_path(PAIR)] == [(4, 0.4), (5, 0.5)]


def test_tracking_pairs_only_priced_and_recent():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xa", token="t", block=1, initial_price=1.0, detected_at=now)
    store.add_token(pair="0xb", token="t", block=1, initial_price=0.0, detected_at=now)
    store.add_token(pair="0xc", token="t", block=1, initial_price=1.0, detected_at=now - timedelta(hours=25))
    assert [r["pair"] for r in store.get_tracking_pairs(now=now)] == ["0xa"]
