import pytest

from rugguard.goplus_client import GoPlusClient


def test_parse_response_extracts_token_security():
    raw = {
        "code": 1,
        "message": "OK",
        "result": {
            "0xabc": {
                "is_honeypot": "1",
                "buy_tax": "5",
                "sell_tax": "5",
                "liquidity": "1",
                "holder_count": "1000",
            }
        },
    }
    result = GoPlusClient.parse_response(raw, "0xabc")
    assert result["is_honeypot"] == "1"
    assert result["holder_count"] == "1000"


def test_parse_response_raises_on_api_error():
    raw = {"code": 1001, "message": "not support", "result": {}}
    with pytest.raises(ValueError, match="not support"):
        GoPlusClient.parse_response(raw, "0xabc")


def test_parse_response_raises_when_token_missing():
    raw = {"code": 1, "message": "OK", "result": {"0xother": {}}}
    with pytest.raises(ValueError, match="0xabc"):
        GoPlusClient.parse_response(raw, "0xabc")
