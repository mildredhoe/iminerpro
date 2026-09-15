# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Guardado seguro de credenciales (API keys).

Usa el llavero del sistema si `keyring` está disponible (Keychain en macOS,
DPAPI en Windows, Secret Service en Linux). Si no, cae a un archivo con permisos
0600 y avisa. Nunca escribe secretos en logs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import app_dir

SERVICE = "minerpro"


def _keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:
        return None


def _fallback_path() -> Path:
    return app_dir() / "secrets.json"


def _load_fallback() -> dict:
    p = _fallback_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_fallback(data: dict) -> None:
    p = _fallback_path()
    p.write_text(json.dumps(data))
    os.chmod(p, 0o600)


def store(name: str, value: str) -> str:
    kr = _keyring()
    if kr is not None:
        kr.set_password(SERVICE, name, value)
        return "keyring"
    data = _load_fallback()
    data[name] = value
    _save_fallback(data)
    return "file"


def load(name: str) -> str | None:
    kr = _keyring()
    if kr is not None:
        return kr.get_password(SERVICE, name)
    return _load_fallback().get(name)


def delete(name: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
        return
    data = _load_fallback()
    data.pop(name, None)
    _save_fallback(data)


def storage_backend() -> str:
    return "keyring" if _keyring() is not None else "file (0600)"


def resolve(name: str, *env_names: str) -> str | None:
    """Busca un secreto en variables de entorno y luego en el almacén seguro."""
    for env in env_names:
        value = os.environ.get(env)
        if value:
            return value.strip()
    return load(name)
