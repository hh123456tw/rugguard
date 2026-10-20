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
