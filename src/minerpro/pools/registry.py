# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Pools de minería reales y sus APIs de estadísticas."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Pool:
    name: str
    coin: str
    algo: str
    url: str
    fee: str
    website: str
    # Plantilla de la API pública de stats por wallet ({wallet} se reemplaza)
    stats_api: str | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


POOLS: list[Pool] = [
    Pool(
        name="SupportXMR",
        coin="XMR",
        algo="rx/0 (RandomX)",
        url="pool.supportxmr.com:3333",
        fee="0.6% (PPLNS)",
        website="https://supportxmr.com",
        stats_api="https://supportxmr.com/api/miner/{wallet}/stats",
        notes="Pago automático, muy usada y con API pública",
    ),
    Pool(
        name="MoneroOcean",
        coin="XMR",
        algo="rx/0 + cambio automático de algoritmo",
        url="gulf.moneroocean.stream:10128",
        fee="0% (PPLNS)",
        website="https://moneroocean.stream",
        stats_api="https://api.moneroocean.stream/miner/{wallet}/stats",
        notes="Elige el algoritmo más rentable por ti",
    ),
    Pool(
        name="HashVault",
        coin="XMR",
        algo="rx/0 (RandomX)",
        url="pool.hashvault.pro:3333",
        fee="0.9% (PPLNS)",
        website="https://pool.hashvault.pro",
        stats_api="https://pool.hashvault.pro/api/miner/{wallet}/stats",
        notes="Infraestructura grande, TLS disponible en :443",
    ),
    Pool(
        name="Monero P2Pool",
        coin="XMR",
        algo="rx/0 (RandomX) descentralizado",
        url="127.0.0.1:3333",
        fee="0% (sin pool central)",
        website="https://p2pool.io",
        stats_api=None,
        notes="Requiere ejecutar p2pool + monerod localmente",
    ),
    # --- Bitcoin / SHA-256d ---
    Pool(
        name="CKPool Solo",
        coin="BTC",
        algo="sha256d (solo/lotería)",
        url="solo.ckpool.org:3333",
        fee="2% del bloque",
        website="https://solo.ckpool.org",
        stats_api="https://solo.ckpool.org/users/{wallet}",
        notes="Lotería: si encuentras el bloque, cobras completo. Pensado para ASIC.",
    ),
    Pool(
        name="Public Pool",
        coin="BTC",
        algo="sha256d (solo)",
        url="public-pool.io:21496",
        fee="0%",
        website="https://public-pool.io",
        stats_api="https://public-pool.io:40557/api/client/{wallet}",
        notes="Solo mining para Bitaxe/NerdMiner y mineros Stratum pequeños",
    ),
    Pool(
        name="Braiins Pool",
        coin="BTC",
        algo="sha256d",
        url="stratum.braiins.com:3333",
        fee="~1.5% (FPPS)",
        website="https://pool.braiins.com",
        stats_api=None,
        notes="Pool clásica de BTC (ex Slush Pool)",
    ),
]


def by_name(name: str) -> Pool:
    for p in POOLS:
        if p.name.lower() == name.lower():
            return p
    known = ", ".join(p.name for p in POOLS)
    raise KeyError(f"pool desconocida: {name!r}. Opciones: {known}")


def default_pool() -> Pool:
    return POOLS[0]
