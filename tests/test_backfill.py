from rugguard.backfill import CHUNK_BLOCKS, HORIZON_BLOCKS, last_per_block, plan_chunks


def test_plan_chunks_covers_horizon_without_gaps():
    chunks = plan_chunks(1000, done=set())
    assert chunks[0] == (1001, 1000 + CHUNK_BLOCKS)
    assert chunks[-1][1] == 1000 + HORIZON_BLOCKS
    assert all(b[0] == a[1] + 1 for a, b in zip(chunks, chunks[1:]))


def test_plan_chunks_skips_done():
    all_chunks = plan_chunks(1000, done=set())
    rest = plan_chunks(1000, done={all_chunks[0][0]})
    assert rest == all_chunks[1:]


def test_last_per_block_keeps_end_of_block_price():
    pts = [("p", 5, 1.0, 1, 1), ("p", 5, 0.01, 1, 1), ("p", 6, 0.5, 1, 1)]
    assert last_per_block(pts) == [("p", 5, 0.01, 1, 1), ("p", 6, 0.5, 1, 1)]
