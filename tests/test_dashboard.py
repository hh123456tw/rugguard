from rugguard.dashboard import load_frame
from rugguard.store import LabelStore


def test_load_frame_adds_level_and_bundle(tmp_path):
    db = str(tmp_path / "d.db")
    store = LabelStore(db)
    store.add_token(pair="0xa", token="0xt", block=1, initial_price=1.0,
                    features={"max_same_block_buyers": 6}, score=85)
    store.add_token(pair="0xb", token="0xt", block=2, initial_price=1.0)
    df = load_frame(db).set_index("pair")
    assert df.loc["0xa", "level"] == "CRITICAL"
    assert df.loc["0xa", "bundle_buyers"] == 6
    assert df.loc["0xb", "level"] == "UNKNOWN"


def test_load_frame_empty_db(tmp_path):
    assert load_frame(str(tmp_path / "e.db")).empty


def test_paper_frame_lists_positions(tmp_path):
    from rugguard.dashboard import paper_frame

    db = str(tmp_path / "p.db")
    store = LabelStore(db)
    store.open_position("0xa", "0xt", 1, 1.0, 1.0, 100)
    store.open_position("0xb", "0xt", 1, 1.0, 1.0, 100)
    store.close_position("0xb", 50, "take_profit", 1.8)
    df = paper_frame(db).set_index("pair")
    assert df["net_return"].isna().sum() == 1
    assert df.loc["0xb", "net_return"] == 1.8


def test_paper_frame_empty(tmp_path):
    from rugguard.dashboard import paper_frame

    assert paper_frame(str(tmp_path / "e.db")).empty
