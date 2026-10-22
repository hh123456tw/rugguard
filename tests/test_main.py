import json
from types import SimpleNamespace

import pytest

import rugguard.main as main
from rugguard.main import alert_reasons
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
READY = 100 + main.ENTRY_DELAY_BLOCKS


@pytest.fixture
def chain(monkeypatch):
    calls = {}

    def buys(w3, pair, start, end, alt_is_token0):
        calls["window"] = (start, end)
        return [(start, "0xa"), (start, "0xb")]

    monkeypatch.setattr(main, "fetch_early_buys", buys)
    monkeypatch.setattr(main, "get_pair_price", lambda *a: calls.get("price", 0.002))
    return calls


def run(store, goplus=None, notifier=None, model=None, latest=READY):
    return main.evaluate_pair(None, goplus or FakeGoPlus({}), notifier or FakeNotifier(), store, model, EV, latest)


def test_waits_until_entry_delay(chain):
    store = LabelStore(":memory:")
    assert run(store, latest=READY - 1) is False
    assert store.get_token("0xpair") is None


def test_waits_while_no_liquidity_then_gives_up(chain):
    store = LabelStore(":memory:")
    chain["price"] = 0.0
    assert run(store) is False
    assert run(store, latest=100 + main.MAX_WAIT_BLOCKS) is True
    assert store.get_token("0xpair") is None


def test_evaluate_stores_features_with_fixed_window(chain):
    store, notifier = LabelStore(":memory:"), FakeNotifier()
    latest = READY + 50
    assert run(store, FakeGoPlus({"is_honeypot": "1", "holder_count": "5"}), notifier, latest=latest)
    row = store.get_token("0xpair")
    assert row["token"] == "0xALT"
    assert row["score"] == 35
    assert row["initial_price"] == 0.002
    assert chain["window"] == (latest - main.ENTRY_DELAY_BLOCKS, latest)
    feats = json.loads(row["features"])
    assert feats["max_same_block_buyers"] == 2
    assert feats["entry_delay_blocks"] == latest - 100
    assert feats["version"] == 2
    assert len(notifier.sent) == 1


def test_goplus_failure_raises_and_stores_nothing(chain):
    store = LabelStore(":memory:")
    with pytest.raises(ValueError):
        run(store, FakeGoPlus(ValueError("not found")))
    assert store.get_token("0xpair") is None


def test_telegram_failure_still_stores(chain):
    store = LabelStore(":memory:")
    run(store, FakeGoPlus({"is_honeypot": "1"}), FakeNotifier(fail=True))
    assert store.get_token("0xpair") is not None


def test_model_scores_and_buy_alert(chain):
    store, notifier = LabelStore(":memory:"), FakeNotifier()
    run(store, notifier=notifier, model=SimpleNamespace(predict=lambda f: (10, 80)))
    row = store.get_token("0xpair")
    assert (row["score"], row["buy_score"]) == (10, 80)
    assert len(notifier.sent) == 1
    assert "能買候選" in notifier.sent[0]


def test_low_buy_score_no_alert(chain):
    notifier = FakeNotifier()
    run(LabelStore(":memory:"), notifier=notifier, model=SimpleNamespace(predict=lambda f: (10, 49)))
    assert notifier.sent == []
