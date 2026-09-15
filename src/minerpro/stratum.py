# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Puente entre plataformas y el minero local: arma el destino Stratum.

Así se "empieza a minar" apuntando tu minero a la plataforma (nube/marketplace)
o a una pool, sin que MinerPro arranque nada por su cuenta.
"""

from __future__ import annotations

from dataclasses import dataclass

from .platforms.base import StratumEndpoint


@dataclass
class StratumTarget:
    host: str
    port: int
    url: str
    user: str
    password: str
    tls: bool
    algo: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "user": self.user,
            "password": self.password,
            "tls": self.tls,
            "algo": self.algo,
        }


def build_target(
    ep: StratumEndpoint,
    *,
    wallet: str = "",
    account: str = "",
    worker: str = "rig1",
    tls: bool = False,
) -> StratumTarget:
    values = {"wallet": wallet, "account": account, "worker": worker}
    missing = [k for k, v in values.items() if "{" + k + "}" in ep.username_template and not v]
    if missing:
        raise ValueError(f"faltan datos para el usuario: {', '.join(missing)}")
    user = ep.username_template.format(**values)
    port = ep.tls_port if (tls and ep.tls_port) else ep.port
    return StratumTarget(
        host=ep.host,
        port=port,
        url=f"{ep.host}:{port}",
        user=user,
        password=ep.password,
        tls=tls and ep.tls_port is not None,
        algo=ep.algo,
        notes=ep.notes,
    )


def xmrig_pool_entry(target: StratumTarget, coin: str = "monero") -> dict:
    """Convierte un destino Stratum en la entrada 'pools' de un config de XMRig."""
    return {
        "algo": None,
        "coin": coin,
        "url": target.url,
        "user": target.user,
        "pass": target.password,
        "keepalive": True,
        "enabled": True,
        "tls": target.tls,
    }
