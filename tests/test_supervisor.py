from rugguard.supervisor import BACKFILL_RERUN_SECONDS, BACKFILL_RETRY_SECONDS, next_backfill_delay


def test_backfill_failure_retries_soon():
    assert next_backfill_delay(1) == BACKFILL_RETRY_SECONDS


def test_backfill_success_reruns_later():
    assert next_backfill_delay(0) == BACKFILL_RERUN_SECONDS > BACKFILL_RETRY_SECONDS
