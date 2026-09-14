"""Tests de validación de wallets y direcciones."""

from minerpro import btc, coins, wallet

XMR_MAINNET = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"


def test_keccak_known_vector():
    assert wallet.keccak_256(b"").hex() == (
        "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    )


def test_monero_valid():
    r = wallet.validate_monero_address(XMR_MAINNET)
    assert r.ok and r.network == "mainnet"


def test_monero_bad_checksum():
    bad = XMR_MAINNET[:-1] + ("X" if XMR_MAINNET[-1] != "X" else "Y")
    assert not wallet.validate_monero_address(bad).ok


def test_monero_short():
    assert not wallet.validate_monero_address("4abc").ok


def test_btc_p2pkh_genesis():
    r = btc.validate_btc_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert r.ok and r.kind == "P2PKH"


def test_btc_bech32_bip173():
    assert btc.validate_btc_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4").ok


def test_btc_bech32_bad_checksum():
    assert not btc.validate_btc_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5").ok


def test_coins_dispatch():
    ok, _, kind = coins.validate_address("XMR", XMR_MAINNET)
    assert ok and kind == "mainnet"
    ok, _, kind = coins.validate_address("BTC", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert ok and kind == "P2PKH"
