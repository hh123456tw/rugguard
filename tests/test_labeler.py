from datetime import datetime, timedelta, timezone

from rugguard.labeler import decide_label, label_pending_tokens, mark_invalid, relabel_all
from rugguard.store import LabelStore


def test_drop_over_90_percent_is_rug():
    assert decide_label(initial_price=0.001, current_price=0.00005) == "rug"


def test_drop_exactly_90_percent_is_rug():
    assert decide_label(initial_price=0.001, current_price=0.0001) == "rug"


def test_moderate_drop_is_normal():
    assert decide_label(initial_price=0.001, current_price=0.0005) == "normal"


def test_price_gain_is_normal():
    assert decide_label(initial_price=0.001, current_price=0.0015) == "normal"


def test_zero_current_price_is_rug():
    assert decide_label(initial_price=0.001, current_price=0) == "rug"


def test_zero_initial_price_is_dead():
    assert decide_label(initial_price=0, current_price=0.0005) == "dead"


def test_unchanged_price_is_dead():
    assert decide_label(initial_price=0.001, current_price=0.001) == "dead"


def test_tiny_change_is_not_dead():
    assert decide_label(initial_price=0.001, current_price=0.0010001) == "normal"


def test_double_is_win():
    assert decide_label(initial_price=0.001, current_price=0.002) == "win"


def test_just_below_double_is_normal():
    assert decide_label(initial_price=0.001, current_price=0.00199) == "normal"


class FakePriceFetcher:
    def __init__(self, prices: dict):
        self.prices = prices

    def __call__(self, pair: str) -> float:
        return self.prices[pair]


def test_label_pending_tokens_marks_rug():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    fetcher = FakePriceFetcher({"0xpair1": 0.00005})

    label_pending_tokens(store, fetcher, min_age_hours=24, now=now + timedelta(hours=25))

    row = store.get_token("0xpair1")
    assert row["label"] == "rug"


def test_label_pending_tokens_skips_young_tokens():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    fetcher = FakePriceFetcher({"0xpair1": 0.00005})

    label_pending_tokens(store, fetcher, min_age_hours=24, now=now + timedelta(hours=1))

    assert store.get_token("0xpair1")["label"] is None


def test_price_failure_skips_only_that_pair():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xbad", token="0xt1", block=100, initial_price=0.001, detected_at=now)
    store.add_token(pair="0xgood", token="0xt2", block=100, initial_price=0.001, detected_at=now)

    def fetcher(pair):
        if pair == "0xbad":
            raise RuntimeError("rpc error")
        return 0.0015

    assert label_pending_tokens(store, fetcher, min_age_hours=24, now=now + timedelta(hours=25)) == 1
    assert store.get_token("0xbad")["label"] is None
    assert store.get_token("0xgood")["label"] == "normal"


def test_relabel_all_uses_stored_prices():
    store = LabelStore(":memory:")
    store.add_token(pair="0xdead", token="0xt", block=1, initial_price=0.0)
    store.update_label(pair="0xdead", label="normal", label_price=0.5)
    store.add_token(pair="0xwin", token="0xt", block=1, initial_price=1.0)
    store.update_label(pair="0xwin", label="normal", label_price=3.0)
    assert relabel_all(store) == 2
    assert store.get_token("0xdead")["label"] == "dead"
    assert store.get_token("0xwin")["label"] == "win"


WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
USDT = "0x55d398326f99059ff775485246999027b3197955"


def test_mark_invalid_wrong_token_and_alt_alt_pairs():
    store = LabelStore(":memory:")
    store.add_token(pair="0xok", token="0xALT", token0="0xALT", token1=WBNB, block=1, initial_price=1.0)
    store.add_token(pair="0xusdt", token=USDT, token0=USDT, token1="0xALT", block=1, initial_price=1.0)
    store.add_token(pair="0xaltalt", token="0xA", token0="0xA", token1="0xB", block=1, initial_price=1.0)
    store.update_label(pair="0xusdt", label="win", label_price=5.0)
    assert mark_invalid(store) == 2
    assert store.get_token("0xok")["label"] is None
    assert store.get_token("0xusdt")["label"] == "invalid"
    assert store.get_token("0xaltalt")["label"] == "invalid"
    relabel_all(store)
    assert store.get_token("0xusdt")["label"] == "invalid"  # 重算標籤不會蓋掉 invalid
