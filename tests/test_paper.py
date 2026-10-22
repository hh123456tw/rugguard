import pytest

from rugguard import paper
from rugguard.store import LabelStore


class Notifier:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


def test_exit_take_profit():
    assert paper.exit_decision(1.0, 2.5, block=10, expires_block=100, tp=2, sl=0.5) == ("take_profit", 2)


def test_exit_stop_loss_at_observed_price():
    assert paper.exit_decision(1.0, 0.01, block=10, expires_block=100, tp=2, sl=0.5) == ("stop_loss", 0.01)


def test_no_exit_inside_band():
    assert paper.exit_decision(1.0, 1.4, block=10, expires_block=100, tp=2, sl=0.5) is None


def test_exit_on_time_without_price_is_total_loss():
    # 到期還拿不到價格（池子被清空等），保守當作歸零
    assert paper.exit_decision(1.0, None, block=100, expires_block=100) == ("time", 0.0)


def test_positions_open_update_close():
    store, n = LabelStore(":memory:"), Notifier()
    paper.open_position(store, n, "0xPair", "0xtok", block=100, price=1.0, cost=0.9, buy_score=70)
    assert len(store.get_open_positions()) == 1

    assert paper.update_positions(store, n, [("0xpair", 110, 1.5, 1, 1)], block=110) == 0
    assert paper.update_positions(store, n, [("0xpair", 120, 3.0, 1, 1)], block=120) == 1
    pos = store.get_positions()[0]
    assert pos["reason"] == "take_profit"
    assert pos["net_return"] == pytest.approx(paper.TAKE_PROFIT * 0.9)
    assert store.get_open_positions() == []
    assert len(n.sent) == 2


def test_expired_position_uses_last_path_price():
    store, n = LabelStore(":memory:"), Notifier()
    paper.open_position(store, n, "0xp", "0xt", block=100, price=1.0, cost=1.0, buy_score=70)
    store.add_path_points([("0xp", 150, 1.3, 1, 1)])
    expires = store.get_open_positions()[0]["expires_block"]
    assert paper.update_positions(store, n, [], block=expires) == 1
    assert store.get_positions()[0]["net_return"] == pytest.approx(1.3)
