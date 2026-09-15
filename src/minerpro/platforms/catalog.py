# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Catálogo de plataformas de nube/pool. Solo lectura + enlaces, sin pagos automáticos."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str
    coins: str
    model: str
    fee: str
    risk: str
    url: str
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# risk: bajo / medio / alto. Ningún proveedor aquí es una recomendación de inversión.
PROVIDERS: list[Provider] = [
    Provider(
        name="NiceHash",
        kind="marketplace de hashrate",
        coins="BTC y otros",
        model="Compras hashrate por horas; el mercado fija el precio",
        fee="comisión por orden + fee de minado",
        risk="medio",
        url="https://www.nicehash.com",
        notes="El modelo cloud más transparente; requiere entender el mercado.",
    ),
    Provider(
        name="Braiins Pool",
        kind="pool BTC",
        coins="BTC",
        model="Pool PPLNS/FPPS para tu propio hardware o hashrate",
        fee="~1.5% FPPS",
        risk="bajo",
        url="https://pool.braiins.com",
        notes="Pool histórica de Bitcoin (ex Slush Pool).",
    ),
    Provider(
        name="ViaBTC / F2Pool / Antpool",
        kind="pools BTC",
        coins="BTC",
        model="Pools grandes de Bitcoin para ASIC",
        fee="variable (1-4%)",
        risk="medio",
        url="https://www.viabtc.com/pool",
        notes="Mucha concentración de hashrate; revisa políticas de pago.",
    ),
    Provider(
        name="solo.ckpool.org",
        kind="pool solo (lotería)",
        coins="BTC",
        model="Si encuentras un bloque, cobras el bloque completo (menos 2%)",
        fee="2%",
        risk="alto (probabilidad ínfima)",
        url="https://solo.ckpool.org",
        notes="Lottery mining honesto; pensado para ASIC, no para CPU.",
    ),
    Provider(
        name="public-pool.io",
        kind="pool solo",
        coins="BTC",
        model="Solo mining con ASIC (Bitaxe, NerdMiner y similares)",
        fee="0-2%",
        risk="alto (probabilidad ínfima)",
        url="https://public-pool.io",
        notes="Compatible con mineros Stratum pequeños.",
    ),
    Provider(
        name="Contratos de cloud mining (genérico)",
        kind="contratos",
        coins="BTC y otros",
        model="Pagas un contrato y una empresa mina por ti",
        fee="cuota diaria de mantenimiento + comisión",
        risk="ALTO",
        url="https://theminermag.com",
        notes=(
            "Aquí vive la mayoría de las estafas tipo Ponzi. MinerPro NO automatiza "
            "compras de contratos. Verifica la empresa y lee la letra chica."
        ),
    ),
]


def by_name(name: str) -> Provider:
    for p in PROVIDERS:
        if p.name.lower() == name.lower():
            return p
    raise KeyError(f"proveedor desconocido: {name}")
