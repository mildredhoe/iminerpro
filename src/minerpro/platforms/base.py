"""Plataformas externas (nube/pool) conectables por API.

Cada plataforma describe:
  · cómo obtener sus credenciales (paso a paso, con URLs oficiales),
  · qué permisos habilitar (y cuáles NO),
  · dónde se guardan las claves dentro de MinerPro,
  · cómo apuntar tu minero a su stratum para "empezar a minar".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CredentialField:
    """Un dato de autenticación y su variable de entorno equivalente."""

    key: str
    env: str
    label: str
    secret: bool = True
    help: str = ""


@dataclass(frozen=True)
class StratumEndpoint:
    """Endpoint Stratum para apuntar un minero (así se "empieza a minar")."""

    coin: str
    algo: str
    host: str
    port: int
    username_template: str  # plantillas: {wallet}, {account}, {worker}
    password: str = "x"
    tls_port: int | None = None
    notes: str = ""


@dataclass
class Platform:
    id: str
    name: str
    kind: str
    coins: list[str]
    url: str
    keys_url: str
    key_steps: list[str]
    api_permissions: list[str]
    warnings: list[str]
    fields: list[CredentialField]
    stratum: list[StratumEndpoint] = field(default_factory=list)
    notes: str = ""

    def stratum_for(self, symbol: str) -> StratumEndpoint | None:
        for ep in self.stratum:
            if ep.coin.upper() == symbol.upper():
                return ep
        return None

    def guide_lines(self) -> list[str]:
        out = [f"{self.name} ({self.kind}) · monedas: {', '.join(self.coins)}", ""]
        out.append("1) Obtén tus credenciales:")
        out.extend(f"   {i}. {s}" for i, s in enumerate(self.key_steps, 1))
        out.append("")
        out.append(f"   Página de claves: {self.keys_url}")
        out.append("")
        out.append("2) Permisos a habilitar:")
        out.extend(f"   · {p}" for p in self.api_permissions)
        out.append("")
        out.append("3) Dónde pegar las claves (dos formas):")
        out.append("   a) Interactivo (recomendado):  minerpro cloud connect " + self.id)
        out.append("   b) Archivo .env:  ~/.minerpro/.env   (o .env en el proyecto)")
        for f in self.fields:
            out.append(f"   {f.env}=...   # {f.label}")
        out.append("")
        out.append("4) Verifica la conexión (solo lectura):  minerpro cloud status " + self.id)
        if self.stratum:
            out.append("")
            out.append("5) Empezar a minar apuntando tu minero a su stratum:")
            for ep in self.stratum:
                out.append(f"   · {ep.coin}: {ep.host}:{ep.port}  ({ep.algo})")
        if self.warnings:
            out.append("")
            out.append("⚠ Avisos:")
            out.extend(f"   · {w}" for w in self.warnings)
        if self.notes:
            out.append("")
            out.append(f"Nota: {self.notes}")
        return out


_REGISTRY: dict[str, Platform] = {}


def register(platform: Platform) -> Platform:
    _REGISTRY[platform.id] = platform
    return platform


def get(platform_id: str) -> Platform:
    key = platform_id.lower()
    if key not in _REGISTRY:
        raise KeyError(f"plataforma desconocida: {platform_id}. Opciones: {', '.join(_REGISTRY)}")
    return _REGISTRY[key]


def all_platforms() -> list[Platform]:
    return list(_REGISTRY.values())
