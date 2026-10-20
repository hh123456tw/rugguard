from types import SimpleNamespace

import pytest

import rugguard.main as main
from rugguard.main import alert_reasons, process_pair
from rugguard.store import LabelStore

BNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"


def test_alert_reasons_detects_honeypot():
    assert "honeypot" in alert_reasons({"is_honeypot": "1"})


def test_alert_reasons_detects_high_tax():
    assert "high buy tax 25%" in alert_reasons({"buy_tax": "0.25", "sell_tax": "0"})


def test_alert_reasons_bad_buy_tax_still_checks_sell_tax():
    assert alert_reasons({"buy_tax": "n/a", "sell_tax": "0.3"}) == ["high sell tax 30%"]


def test_alert_reasons_clean_token_no_reasons():
    assert alert_reasons({"is_honeypot": "0", "buy_tax": "0", "sell_tax": "0"}) == []


class FakeGoPlus:
    def __init__(self, result):
        self.result = result

    def fetch_token_security(self, token):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, msg):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append(msg)


EV = SimpleNamespace(token0="0xALT", token1=BNB, pair="0xpair", block_number=100)


@pytest.fixture(autouse=True)
def no_chain(monkeypatch):
    monkeypatch.setattr(main, "fetch_early_buys", lambda *a: [(100, "0xa"), (100, "0xb")])
    monkeypatch.setattr(main, "get_pair_price", lambda *a: 0.002)


def test_process_pair_stores_features_and_alerts():
    store, notifier = LabelStore(":memory:"), FakeNotifier()
    process_pair(None, FakeGoPlus({"is_honeypot": "1", "holder_count": "5"}), notifier, store, None, EV, 110)
    row = store.get_token("0xpair")
    assert row["token"] == "0xALT"
    assert row["score"] == 35
    assert '"max_same_block_buyers": 2' in row["features"]
    assert len(notifier.sent) == 1


def test_process_pair_goplus_failure_raises_and_stores_nothing():
    store = LabelStore(":memory:")
    with pytest.raises(ValueError):
        process_pair(None, FakeGoPlus(ValueError("not found")), FakeNotifier(), store, None, EV, 110)
    assert store.get_token("0xpair") is None


def test_process_pair_telegram_failure_still_stores():
    store = LabelStore(":memory:")
    process_pair(None, FakeGoPlus({"is_honeypot": "1"}), FakeNotifier(fail=True), store, None, EV, 110)
    assert store.get_token("0xpair") is not None


def test_process_pair_uses_model_when_present():
    store = LabelStore(":memory:")
    model = SimpleNamespace(score=lambda feats: 77)
    process_pair(None, FakeGoPlus({}), FakeNotifier(), store, model, EV, 110)
    assert store.get_token("0xpair")["score"] == 77
