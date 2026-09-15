"""Datos de mercado y estimación de rentabilidad, con las mismas cuentas que la app.

Fuentes en vivo (con respaldo):
  - Red de Monero: moneroblocks -> blockchair -> xmrchain
  - Precios: CoinGecko
  - Mercado de hashrate: NiceHash (algoritmos y órdenes activas)

Ninguna cifra se inventa: si no hay dato, la función falla con un mensaje claro.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

NICEHASH = "https://api2.nicehash.com"
PICONERO = 1e12

Json = dict
Get = Callable[[str], Json]


def default_get(url: str) -> Json:
    r = httpx.get(url, timeout=20, headers={"User-Agent": "MinerPro/0.1"})
    r.raise_for_status()
    return r.json()


@dataclass
class NetworkStats:
    difficulty: float
    hashrate_hps: float
    block_reward: float | None
    height: int
    source: str

    @property
    def blocks_per_day(self) -> float:
        return 720.0  # Monero: un bloque cada 2 minutos


@dataclass
class Prices:
    coin_usd: float
    btc_usd: float
    source: str


@dataclass
class Estimate:
    speed_hps: float
    network_share: float
    coins_mined: float
    cost_btc: float
    cost_usd: float
    revenue_usd: float
    net_usd: float
    break_even_btc_per_unit_day: float
    network_source: str
    price_source: str

    @property
    def profitable(self) -> bool:
        return self.net_usd > 0


def fetch_network(get: Get = default_get) -> NetworkStats:
    errors: list[str] = []
    try:
        o = get("https://moneroblocks.info/api/get_stats")
        return NetworkStats(
            difficulty=float(o["difficulty"]),
            hashrate_hps=float(o["hashrate"]),
            block_reward=float(o["last_reward"]) / PICONERO,
            height=int(o["height"]),
            source="moneroblocks.info",
        )
    except Exception as e:
        errors.append(f"moneroblocks: {e}")
    try:
        d = get("https://api.blockchair.com/monero/stats")["data"]
        difficulty = float(d["difficulty"])
        hashrate = float(d.get("hashrate_24h") or difficulty / 120.0)
        return NetworkStats(difficulty, hashrate, None, int(d["best_block_height"]), "blockchair.com")
    except Exception as e:
        errors.append(f"blockchair: {e}")
    try:
        d = get("https://xmrchain.net/api/networkinfo")["data"]
        difficulty = float(d["difficulty"])
        return NetworkStats(difficulty, difficulty / 120.0, None, int(d["height"]), "xmrchain.net")
    except Exception as e:
        errors.append(f"xmrchain: {e}")
    raise RuntimeError("sin datos de red de Monero (" + "; ".join(errors) + ")")


def fetch_prices(get: Get = default_get) -> Prices:
    o = get("https://api.coingecko.com/api/v3/simple/price?ids=monero,bitcoin&vs_currencies=usd")
    return Prices(float(o["monero"]["usd"]), float(o["bitcoin"]["usd"]), "coingecko")


def nicehash_algorithm(algo: str, get: Get = default_get) -> dict:
    data = get(f"{NICEHASH}/main/api/v2/mining/algorithms/")
    for item in data.get("miningAlgorithms", []):
        if item.get("algorithm", "").upper() == algo.upper():
            return item
    raise RuntimeError(f"NiceHash no informa el algoritmo {algo}")


def nicehash_best_price(algo: str, get: Get = default_get) -> tuple[float, int]:
    """Mejor precio (BTC por unidad de mercado y día) y cuántas órdenes tienen actividad."""
    data = get(f"{NICEHASH}/main/api/v2/public/orders/active2/?algorithm={algo.upper()}")
    orders = [
        o for o in data.get("list", [])
        if int(o.get("rigsCount") or 0) > 0 or float(o.get("acceptedCurrentSpeed") or 0) > 0
    ]
    if not orders:
        raise RuntimeError(f"sin órdenes activas para {algo} en NiceHash")
    best = min(float(o["price"]) for o in orders)
    return best, len(orders)


def format_hashrate(hps: float) -> str:
    for limit, unit in (
        (1e15, "PH/s"), (1e12, "TH/s"), (1e9, "GH/s"), (1e6, "MH/s"), (1e3, "kH/s"),
    ):
        if hps >= limit:
            return f"{hps / limit:.3f} {unit}"
    return f"{hps:.0f} H/s"


def estimate(
    speed_units: float,
    price_btc_per_unit_day: float,
    days: float,
    pool_fee_percent: float,
    market_factor_hps: float,
    network: NetworkStats,
    prices: Prices,
    block_reward: float,
) -> Estimate:
    """Mismas cuentas que la app: costo BTC, monedas esperadas, ingreso y neto en USD."""
    if market_factor_hps <= 0:
        raise ValueError("el factor de mercado debe ser mayor que cero")
    if network.hashrate_hps <= 0:
        raise ValueError("el hashrate de red debe ser mayor que cero")
    if prices.btc_usd <= 0:
        raise ValueError("el precio de BTC debe ser mayor que cero")

    speed_hps = speed_units * market_factor_hps
    share = speed_hps / network.hashrate_hps
    coins = share * block_reward * network.blocks_per_day * days * (1.0 - pool_fee_percent / 100.0)

    cost_btc = price_btc_per_unit_day * speed_units * days
    cost_usd = cost_btc * prices.btc_usd
    revenue_usd = coins * prices.coin_usd
    net_usd = revenue_usd - cost_usd

    unit_days = speed_units * days
    break_even = (revenue_usd / prices.btc_usd / unit_days) if unit_days > 0 else 0.0

    return Estimate(
        speed_hps=speed_hps,
        network_share=share,
        coins_mined=coins,
        cost_btc=cost_btc,
        cost_usd=cost_usd,
        revenue_usd=revenue_usd,
        net_usd=net_usd,
        break_even_btc_per_unit_day=break_even,
        network_source=network.source,
        price_source=prices.source,
    )
