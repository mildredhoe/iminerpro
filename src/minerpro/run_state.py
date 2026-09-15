"""Estado de la ejecución actual: qué minero está corriendo y desde cuándo.

Permite que `status`, `logs` y `stop` funcionen en otra terminal, y que `mine`
sepa si ya hay algo minando. Todo vive en ~/.minerpro/run/.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import app_dir


def run_dir() -> Path:
    p = app_dir() / "run"
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_path() -> Path:
    return run_dir() / "state.json"


@dataclass
class RunState:
    pid: int
    profile: str
    coin: str
    pool: str
    wallet: str
    engine: str
    port: int
    started_at: float
    log_path: str
    binary: str = ""
    restarts: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> int:
        return max(0, int(time.time() - self.started_at))

    def to_dict(self) -> dict:
        return asdict(self)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def save(state: RunState) -> Path:
    path = state_path()
    path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    return path


def load() -> RunState | None:
    path = state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        clear()
        return None
    known = {f for f in RunState.__dataclass_fields__}
    payload = {k: v for k, v in data.items() if k in known}
    try:
        return RunState(**payload)
    except TypeError:
        clear()
        return None


def clear() -> None:
    path = state_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def current() -> RunState | None:
    """Estado actual, o None si no hay minero vivo (limpia el archivo si quedó huérfano)."""
    state = load()
    if state is None:
        return None
    if not _pid_alive(state.pid):
        clear()
        return None
    return state
