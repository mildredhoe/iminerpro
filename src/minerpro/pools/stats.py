# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Estadísticas reales de pool por wallet (APIs públicas)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .registry import Pool

PICONERO = 1e12
SATOSHI = 1e8


@dataclass
class PoolStats:
    ok: bool
    pool: str = ""
    coin: str = "XMR"
    hashrate: float = 0.0
    accepted: int = 0
    rejected: int = 0
    pending_xmr: float = 0.0
    paid_xmr: float = 0.0
    raw: dict | None = None
    error: str = ""


def _f(d: dict, *keys, default=0.0) -> float:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


def _i(d: dict, *keys, default=0) -> int:
    return int(_f(d, *keys, default=default))


def fetch(pool: Pool, wallet: str, timeout: float = 10.0) -> PoolStats:
    if not pool.stats_api:
        return PoolStats(ok=False, pool=pool.name, error="esta pool no expone API de stats")
    url = pool.stats_api.format(wallet=wallet)
    divisor = PICONERO if pool.coin.upper() == "XMR" else SATOSHI
    try:
        r = httpx.get(url, timeout=timeout, headers={"User-Agent": "MinerPro/0.1"})
        if r.status_code != 200:
            return PoolStats(ok=False, pool=pool.name, coin=pool.coin, error=f"HTTP {r.status_code}")
        d = r.json()
    except ValueError:
        return PoolStats(
            ok=False,
            pool=pool.name,
            coin=pool.coin,
            error="esta pool no entrega JSON en su API de stats",
        )
    except Exception as e:
        return PoolStats(ok=False, pool=pool.name, coin=pool.coin, error=f"{type(e).__name__}: {e}")

    return PoolStats(
        ok=True,
        pool=pool.name,
        coin=pool.coin,
        hashrate=_f(d, "hash", "hashrate", "hashRate"),
        accepted=_i(d, "validShares", "valid_shares", "accepted"),
        rejected=_i(d, "invalidShares", "invalid_shares", "rejected"),
        pending_xmr=_f(d, "amtDue", "pending", "balance") / divisor,
        paid_xmr=_f(d, "amtPaid", "paid", "totalPaid") / divisor,
        raw=d,
    )
