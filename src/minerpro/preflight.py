"""Chequeos previos: que la pool responda, que el puerto esté libre, que el minero corra.

La idea es fallar temprano y con un mensaje útil, en vez de arrancar el minero y
descubrir el problema viendo el log.
"""

from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fatal: bool = False

    @property
    def mark(self) -> str:
        return "✓" if self.ok else ("✗" if self.fatal else "!")


def check_pool(url: str, timeout: float = 5.0) -> Check:
    host, _, port = url.partition(":")
    if not host or not port.isdigit():
        return Check("pool alcanzable", False, f"url inválida: {url}", fatal=True)
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return Check("pool alcanzable", True, f"{url} responde")
    except socket.gaierror:
        return Check(
            "pool alcanzable",
            False,
            f"no puedo resolver {host}: revisá tu conexión a internet o el DNS",
        )
    except OSError as e:
        return Check("pool alcanzable", False, f"no pude conectar a {url}: {e.strerror or e}")


def check_port_free(port: int) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return Check(
                "puerto de la API libre",
                False,
                f"el puerto {port} está ocupado: puede haber otro minero corriendo",
            )
    return Check("puerto de la API libre", True, f"puerto {port} disponible")


def check_binary(path: Path | None, timeout: float = 10.0) -> Check:
    if path is None:
        return Check("minero ejecutable", True, "se usa un minero externo")
    if not path.exists():
        return Check("minero ejecutable", False, f"no existe {path}", fatal=True)
    try:
        out = subprocess.run(
            [str(path), "--version"], capture_output=True, text=True, timeout=timeout
        )
        line = (out.stdout or out.stderr).strip().splitlines()
        version = line[0] if line else "sin salida"
        return Check("minero ejecutable", out.returncode == 0, version)
    except (OSError, subprocess.SubprocessError) as e:
        return Check("minero ejecutable", False, f"no pude ejecutarlo: {e}", fatal=True)


def run_all(checks: list[Check]) -> tuple[bool, list[Check]]:
    """Devuelve (puede_continuar, checks). Solo los fatales bloquean."""
    return all(c.ok or not c.fatal for c in checks), checks
