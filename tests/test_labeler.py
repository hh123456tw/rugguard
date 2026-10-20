from datetime import datetime, timedelta, timezone

from rugguard.labeler import decide_label, label_pending_tokens
from rugguard.store import LabelStore


def test_drop_over_90_percent_is_rug():
    assert decide_label(initial_price=0.001, current_price=0.00005) == "rug"


def test_drop_exactly_90_percent_is_rug():
    assert decide_label(initial_price=0.001, current_price=0.0001) == "rug"


def test_moderate_drop_is_normal():
    assert decide_label(initial_price=0.001, current_price=0.0005) == "normal"


def test_price_gain_is_normal():
    assert decide_label(initial_price=0.001, current_price=0.002) == "normal"


def test_zero_current_price_is_rug():
    assert decide_label(initial_price=0.001, current_price=0) == "rug"


def test_zero_initial_price_not_rug():
    assert decide_label(initial_price=0, current_price=0.0005) == "normal"


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
        return 0.002

    assert label_pending_tokens(store, fetcher, min_age_hours=24, now=now + timedelta(hours=25)) == 1
    assert store.get_token("0xbad")["label"] is None
    assert store.get_token("0xgood")["label"] == "normal"
