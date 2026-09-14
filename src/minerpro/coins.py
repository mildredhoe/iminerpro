"""Modelo de monedas soportadas: XMR (RandomX) y BTC (SHA-256d)."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import btc, wallet


@dataclass(frozen=True)
class Coin:
    symbol: str
    name: str
    algo: str
    local_engines: list[str]
    cloud_engines: list[str]
    pools: list[str]
    miner_binaries: list[str]
    reality: str
    notes: list[str] = field(default_factory=list)

    @property
    def address_kind(self) -> str:
        return "Monero (XMR)" if self.symbol == "XMR" else "Bitcoin (BTC)"


def validate_address(symbol: str, address: str) -> tuple[bool, str, str]:
    """Valida una dirección para la moneda dada. Devuelve (ok, detalle, red/tipo)."""
    if symbol.upper() == "XMR":
        r = wallet.validate_monero_address(address)
        return r.ok, r.reason, (r.network or "")
    if symbol.upper() == "BTC":
        r = btc.validate_btc_address(address)
        return r.ok, r.reason, (r.kind or "")
    return False, f"moneda no soportada: {symbol}", ""


COINS: dict[str, Coin] = {
    "XMR": Coin(
        symbol="XMR",
        name="Monero",
        algo="RandomX (rx/0)",
        local_engines=["xmrig", "mxmr", "p2pool"],
        cloud_engines=["pool-stats", "nicehash"],
        pools=["SupportXMR", "MoneroOcean", "HashVault", "Monero P2Pool"],
        miner_binaries=["xmrig", "mxmr"],
        reality="Minar XMR con CPU en un PC normal es rentable en términos relativos: es la mejor opción local.",
        notes=[
            "RandomX está diseñado para CPU; una GPU no ayuda con XMR.",
            "Cada hilo necesita ~2 GB de RAM para el dataset.",
        ],
    ),
    "BTC": Coin(
        symbol="BTC",
        name="Bitcoin",
        algo="SHA-256d",
        local_engines=["external", "stratum-solo"],
        cloud_engines=["nicehash", "cloud-contract", "pool-stats"],
        pools=["solo.ckpool.org", "public-pool.io", "NiceHash (hashrate arrendado)"],
        miner_binaries=["bitaxe/nerdminer (ASIC)", "cgminer/bfgminer (ASIC)", "cualquier minero Stratum"],
        reality=(
            "Minar BTC en un PC es inviable para ganar dinero: la red usa ASIC. "
            "Tiene sentido como lotería (solo) o arrendando hashrate (nube)."
        ),
        notes=[
            "Local real: conectar tu ASIC/rig por Stratum (MinerPro genera el comando y las credenciales).",
            "Lotería: solo.ckpool.org paga el bloque completo a tu wallet (~1 en millones).",
            "Nube: NiceHash arrienda hashrate real; los 'contratos' de otras plataformas son alto riesgo.",
        ],
    ),
}


def get(symbol: str) -> Coin:
    key = symbol.upper()
    if key not in COINS:
        raise KeyError(f"moneda no soportada: {symbol}. Opciones: {', '.join(COINS)}")
    return COINS[key]
