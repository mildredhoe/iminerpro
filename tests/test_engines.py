# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Tests de motores, planificación y no-ejecución."""

from minerpro.config import Profile
from minerpro.engines.external import ExternalEngine
from minerpro.engines.xmrig import build_config
from minerpro.pools.registry import POOLS, by_name


def test_pool_registry_has_btc_and_xmr():
    coins = {p.coin for p in POOLS}
    assert "XMR" in coins and "BTC" in coins


def test_by_name_and_default():
    assert by_name("SupportXMR").coin == "XMR"
    assert by_name("CKPool Solo").coin == "BTC"


def test_xmrig_config_shape():
    cfg = build_config("WALLET", "pool.supportxmr.com:3333")
    assert cfg["http"]["port"] == 18080
    assert cfg["pools"][0]["user"] == "WALLET"
    assert cfg["pools"][0]["coin"] == "monero"


def test_external_engine_command_preview():
    prof = Profile(
        wallet="bc1qtest",
        pool_url="solo.ckpool.org:3333",
        coin="bitcoin",
        extra={"cmd": "cgminer -o {url} -u {user} -p {pass}"},
    )
    eng = ExternalEngine(prof)
    cmd = eng.command()
    assert cmd[0] == "cgminer"
    assert "solo.ckpool.org:3333" in cmd
    assert "bc1qtest" in cmd


def test_external_engine_no_command_is_safe():
    eng = ExternalEngine(Profile(pool_url="x:1", wallet="w"))
    # preview no debe romper aunque no haya comando definido
    assert "sin comando" in eng.preview()
