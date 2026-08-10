from datetime import datetime, timedelta, timezone

from rugguard.store import LabelStore


def test_add_token_and_get_pending():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(
        pair="0xpair1",
        token="0xtoken1",
        block=100,
        initial_price=0.001,
        token0="0xalt",
        token1="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        detected_at=now,
    )
    pending = store.get_pending_tokens(min_age_hours=24, now=now + timedelta(hours=25))
    assert len(pending) == 1
    assert pending[0]["pair"] == "0xpair1"


def test_token_too_young_not_pending():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    pending = store.get_pending_tokens(min_age_hours=24, now=now + timedelta(hours=1))
    assert pending == []


def test_labeled_token_not_pending():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    store.update_label(pair="0xpair1", label="rug", label_price=0.00001)
    pending = store.get_pending_tokens(min_age_hours=24, now=now + timedelta(hours=25))
    assert pending == []


def test_update_label_records():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    store.update_label(pair="0xpair1", label="rug", label_price=0.00001)
    row = store.get_token("0xpair1")
    assert row["label"] == "rug"
    assert row["label_price"] == 0.00001


def test_get_training_rows():
    store = LabelStore(":memory:")
    now = datetime.now(timezone.utc)
    store.add_token(pair="0xpair1", token="0xtoken1", block=100, initial_price=0.001, detected_at=now)
    store.update_label(pair="0xpair1", label="rug", label_price=0.00001)
    store.add_token(pair="0xpair2", token="0xtoken2", block=200, initial_price=0.01, detected_at=now)
    rows = store.get_training_rows()
    assert len(rows) == 1
    assert rows[0]["label"] == "rug"
