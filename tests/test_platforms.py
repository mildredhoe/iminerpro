"""Tests de plataformas (firma NiceHash/Binance) y Stratum."""

import hashlib
import hmac

import pytest

from minerpro import stratum
from minerpro.config import load_env
from minerpro.platforms import get as get_platform
from minerpro.platforms.binance import sign_query
from minerpro.platforms.nicehash import sign_message, signature


def test_nicehash_message_layout_matches_reference():
    """El layout debe ser: key \\0 time \\0 nonce \\0 \\0 org \\0 \\0 METHOD \\0 path \\0 query."""
    msg = sign_message("KEY", "123", "NONCE", "ORG", "GET", "/main/api/v2/x", "a=1", "")
    expected = b"KEY\x00123\x00NONCE\x00\x00ORG\x00\x00GET\x00/main/api/v2/x\x00a=1"
    assert msg == expected


def test_nicehash_message_with_body_appends_body():
    msg = sign_message("K", "1", "N", "O", "POST", "/p", "", '{"a":1}')
    assert msg.endswith(b"\x00{\"a\":1}")


def test_nicehash_signature_is_hmac_sha256_hex():
    msg = sign_message("KEY", "123", "NONCE", "ORG", "GET", "/path", "", "")
    got = signature("SECRET", msg)
    assert got == hmac.new(b"SECRET", msg, hashlib.sha256).hexdigest()
    assert len(got) == 64


def test_binance_signature_known_vector():
    """Vector verificado con `openssl dgst -sha256 -hmac`."""
    query = (
        "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1"
        "&recvWindow=5000&timestamp=1499827319559"
    )
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7HchQV"
    signed = sign_query(
        {
            "symbol": "LTCBTC",
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": 1,
            "price": 0.1,
            "recvWindow": 5000,
            "timestamp": 1499827319559,
        },
        secret,
    )
    assert signed == (
        query + "&signature=406396f82a5a5ad01cf4fd0ddfbe85a969c9d12b7bcfe507f8e5e134e7cf0464"
    )


def test_platforms_registered():
    assert get_platform("nicehash").id == "nicehash"
    assert get_platform("binance").id == "binance"
    assert get_platform("NiceHash").name == "NiceHash"


def test_platform_guides_have_steps_and_env():
    for pid in ("nicehash", "binance"):
        p = get_platform(pid)
        assert p.key_steps and p.api_permissions and p.fields
        assert all(f.env.startswith("MINERPRO_") for f in p.fields)
        assert any("NO habilitar" in w or "Nunca" in w for w in p.warnings)


def test_nicehash_stratum_for_xmr_uses_wallet():
    ep = get_platform("nicehash").stratum_for("XMR")
    assert ep is not None
    target = stratum.build_target(ep, wallet="BTCADDR", tls=True)
    assert target.user == "BTCADDR"
    assert target.tls and target.port == 443


def test_binance_stratum_uses_account_and_worker():
    ep = get_platform("binance").stratum_for("BTC")
    target = stratum.build_target(ep, account="MiningBTC", worker="rig7")
    assert target.user == "MiningBTC.rig7"
    assert target.host == "sha256.poolbinance.com"


def test_stratum_missing_field_raises():
    ep = get_platform("binance").stratum_for("BTC")
    with pytest.raises(ValueError):
        stratum.build_target(ep, account="", worker="rig1")


def test_xmrig_pool_entry_shape():
    target = stratum.build_target(get_platform("nicehash").stratum_for("XMR"), wallet="W")
    entry = stratum.xmrig_pool_entry(target)
    assert entry["url"] == target.url and entry["user"] == "W" and entry["coin"] == "monero"


def test_load_env_reads_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comentario\nMINERPRO_TEST_VAR="hola"\nOTRA=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINERPRO_TEST_VAR", raising=False)
    loaded = load_env()
    assert env in loaded
    import os

    assert os.environ["MINERPRO_TEST_VAR"] == "hola"


# --------------------------------------------------------------------------- #
# Escritura desactivada por defecto (nada mueve fondos sin permiso explícito)
# --------------------------------------------------------------------------- #
def test_nicehash_writes_blocked_by_default():
    from minerpro.platforms.nicehash import NiceHashClient, NiceHashWriteDisabled

    client = NiceHashClient("key", "secret", "org")  # allow_write=False
    for call in (
        lambda: client.create_pool("p", "SHA256", "host", 3333, "user"),
        lambda: client.cancel_order("id"),
        lambda: client.refill_order("id", 0.001),
        lambda: client.create_order(
            market="EU", algorithm="SHA256", price=1.0, limit=1.0, amount=0.001, pool_id="p"
        ),
        lambda: client.set_price_and_limit("id", price=1.0, limit=1.0, algorithm="SHA256"),
    ):
        with pytest.raises(NiceHashWriteDisabled):
            call()


def test_binance_writes_blocked_by_default():
    from minerpro.platforms.binance import BinanceClient

    client = BinanceClient("key", "secret")  # allow_write=False
    with pytest.raises(PermissionError):
        client.resale_create(
            user_name="acc",
            algo="sha256d",
            to_pool_user="otro",
            hash_rate=1.0,
            start_ms=0,
            end_ms=1,
        )
    with pytest.raises(PermissionError):
        client.resale_cancel("config", "acc")


# --------------------------------------------------------------------------- #
# Mercado público (sin claves)
# --------------------------------------------------------------------------- #
def test_public_nicehash_parses_market(monkeypatch):
    from minerpro.platforms import nicehash

    def fake_get(path, params=None, timeout=20.0):
        if "simplemultialgo" in path:
            return {
                "miningAlgorithms": [
                    {"algorithm": "SHA256", "title": "SHA256", "paying": 7.1e-11, "speed": 1280.0},
                    {"algorithm": "RANDOMXMONERO", "title": "RandomXmonero", "paying": 0.03, "speed": 100000.0},
                ]
            }
        if path.endswith("/algorithms/"):
            return {"miningAlgorithms": [{"algorithm": "SHA256", "displayMarketFactor": "EH"}]}
        if "orders/active2" in path:
            return {"list": [{"price": "0.71", "rigsCount": 51}, {"price": "0.70", "rigsCount": 0}]}
        return {}

    monkeypatch.setattr(nicehash, "public_get", fake_get)
    nh = nicehash.PublicNiceHash()
    paying = nh.paying_by_algo()
    assert paying["SHA256"]["paying"] == pytest.approx(7.1e-11)
    assert nh.algorithm("sha256")["displayMarketFactor"] == "EH"
    assert nh.best_price("SHA256") == pytest.approx(0.70)


def test_demo_output_is_labelled_and_does_not_print(capsys):
    from minerpro import demo

    text = demo.to_stdout("mine", width=100)
    assert "DEMO" in text.splitlines()[0]
    assert "13.84 kH/s" in text
    captured = capsys.readouterr()
    assert captured.out == ""  # el modo demo no imprime en stdout por su cuenta
