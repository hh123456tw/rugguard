import pytest

from rugguard.chains import split_pair
from rugguard.price import compute_price_from_reserves

WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
USDT = "0x55d398326f99059ff775485246999027b3197955"
ALT = "0x" + "aa" * 20
ALT2 = "0x" + "bb" * 20


def test_usdt_token0_new_coin_is_token1():
    # 之前的錯誤：只認 BNB，USDT/新幣 會把 USDT 當成新幣
    assert split_pair(USDT, ALT) == (ALT, False)


def test_new_coin_token0_with_wbnb():
    assert split_pair(ALT, WBNB) == (ALT, True)


def test_checksum_case_still_matches():
    assert split_pair(USDT.upper().replace("0X", "0x"), ALT) == (ALT, False)


def test_two_quotes_not_evaluated():
    assert split_pair(WBNB, USDT) is None


def test_two_alts_not_evaluated():
    assert split_pair(ALT, ALT2) is None


def test_near_miss_address_is_not_a_quote():
    near = USDT[:-1] + ("6" if USDT[-1] != "6" else "7")
    assert split_pair(near, ALT) is None


def test_price_with_usdt_token0():
    # 1000 USDT 對 1,000,000 新幣 → 每顆 0.001 USDT
    assert compute_price_from_reserves(1000, 1_000_000, USDT, ALT) == pytest.approx(0.001)
