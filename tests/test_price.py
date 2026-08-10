import pytest

from rugguard.price import compute_price_from_reserves


def test_price_token0_priced_in_token1():
    # token0 is the alt token, token1 is BNB (reference)
    # reserves: token0=1_000_000, token1=500 BNB
    # price per token = 500 / 1_000_000 = 0.0005 BNB
    price = compute_price_from_reserves(
        reserve0=1_000_000,
        reserve1=500,
        token0="0xalt",
        token1="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    )
    assert price == pytest.approx(0.0005)


def test_price_token1_priced_in_token0():
    # token1 is the alt token (flipped order), token0 is BNB
    # reserves: token0=500 BNB, token1=1_000_000
    price = compute_price_from_reserves(
        reserve0=500,
        reserve1=1_000_000,
        token0="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        token1="0xalt",
    )
    assert price == pytest.approx(0.0005)


def test_zero_reserve_returns_zero():
    price = compute_price_from_reserves(
        reserve0=0,
        reserve1=500,
        token0="0xalt",
        token1="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    )
    assert price == 0
