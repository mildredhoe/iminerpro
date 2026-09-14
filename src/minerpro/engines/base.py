"""Interfaz común de motores de minado."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class MinerStats:
    """Estado real reportado por el motor de minado."""

    running: bool = False
    algo: str = ""
    pool: str = ""
    uptime_s: int = 0
    hashrate_10s: float = 0.0
    hashrate_max: float = 0.0
    shares_good: int = 0
    shares_total: int = 0
    threads: int = 0
    cpu_brand: str = ""
    paused: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def shares_bad(self) -> int:
        return max(0, self.shares_total - self.shares_good)

    @property
    def accept_ratio(self) -> float:
        return (self.shares_good / self.shares_total) if self.shares_total else 0.0


@runtime_checkable
class MinerEngine(Protocol):
    """Cualquier backend de minado (XMRig, mxmr nativo, ...)."""

    name: str

    def prepare(self, wallet: str, pool_url: str, *, threads: int | None = None) -> None:
        """Descarga/instala y escribe la configuración. Idempotente."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def stats(self) -> MinerStats: ...

    def logs(self, lines: int = 40) -> list[str]: ...

    @property
    def is_running(self) -> bool: ...
