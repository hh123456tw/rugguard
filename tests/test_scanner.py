import pytest

from rugguard.scanner import decode_pair_created_log, PairCreatedEvent


def test_decode_pair_created_log():
    pair_addr = "0x1234567890abcdef1234567890abcdef12345678"
    log = {
        "address": "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",
        "topics": [
            "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9",
            "0x000000000000000000000000bb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
            "0x000000000000000000000000e9e7cea3dedca5984780bafc599bd69add087d56",
        ],
        "data": (
            "0x" + "00" * 12 + pair_addr[2:]
            + "00" * 31 + "01"
        ),
        "blockNumber": 100,
        "transactionHash": "0xabc",
        "logIndex": 0,
    }
    from eth_utils import to_checksum_address

    event = decode_pair_created_log(log)
    assert isinstance(event, PairCreatedEvent)
    assert event.token0 == to_checksum_address("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c")
    assert event.token1 == to_checksum_address("0xe9e7cea3dedca5984780bafc599bd69add087d56")
    assert event.pair == to_checksum_address(pair_addr)
    assert event.block_number == 100


def test_decode_missing_topics_raises():
    with pytest.raises(ValueError):
        decode_pair_created_log({"topics": [], "data": "0x"})
