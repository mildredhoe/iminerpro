"""Rutas, perfiles y configuración persistente de MinerPro."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "minerpro"


def app_dir() -> Path:
    override = os.environ.get("MINERPRO_HOME")
    base = Path(override) if override else Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def bin_dir() -> Path:
    p = app_dir() / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = app_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profiles_dir() -> Path:
    p = app_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = app_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Profile:
    """Un perfil de minado: wallet + pool + ajustes de motor."""

    name: str = "default"
    wallet: str = ""
    pool_name: str = "SupportXMR"
    pool_url: str = "pool.supportxmr.com:3333"
    coin: str = "monero"
    engine: str = "xmrig"
    threads: int | None = None
    extra: dict = field(default_factory=dict)

    def dir(self) -> Path:
        p = profiles_dir() / self.name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save(self) -> Path:
        path = self.dir() / "profile.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, name: str = "default") -> "Profile":
        path = profiles_dir() / name / "profile.json"
        if not path.exists():
            return cls(name=name)
        data = json.loads(path.read_text())
        data.pop("name", None)
        return cls(name=name, **data)

    @classmethod
    def list_names(cls) -> list[str]:
        if not profiles_dir().exists():
            return []
        return sorted(p.name for p in profiles_dir().iterdir() if (p / "profile.json").exists())
