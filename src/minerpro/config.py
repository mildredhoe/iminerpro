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


def load_env() -> list[Path]:
    """Carga variables desde `.env` del proyecto y de ~/.minerpro/.env.

    No sobreescribe variables ya definidas en el entorno del proceso. Devuelve los
    archivos que existían. Formato simple: KEY=VALUE, # comentarios.
    """
    loaded: list[Path] = []
    candidates = [Path.cwd() / ".env", app_dir() / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        loaded.append(path)
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    return loaded


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
