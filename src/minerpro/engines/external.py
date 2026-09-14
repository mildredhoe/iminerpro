"""Motor externo: ejecuta un minero que el usuario aporta (BTC/ASIC/GPU).

MinerPro no empaqueta mineros de SHA-256d. Para BTC en local, el usuario conecta
su propio minero (ASIC, bfgminer/cgminer, o cualquier programa Stratum) y MinerPro
genera el comando y las credenciales correctas, y muestra sus logs.

Plantilla de comando con marcadores:
  {url} {user} {pass} {threads} {extra}
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ..config import Profile, logs_dir
from .base import MinerStats


class ExternalEngine:
    name = "external"

    def __init__(self, profile: Profile):
        self.profile = profile
        self.proc: subprocess.Popen | None = None
        self._log_path = logs_dir() / f"external-{profile.name}.log"

    @property
    def template(self) -> str:
        return self.profile.extra.get("cmd", "")

    def command(self) -> list[str]:
        tmpl = self.template
        if not tmpl:
            raise RuntimeError(
                "no hay comando configurado; define profile.extra['cmd'] "
                "(ej: 'minerd -a sha256d -o {url} -u {user} -p {pass}')"
            )
        values = {
            "url": self.profile.pool_url,
            "user": self.profile.wallet,
            "pass": self.profile.extra.get("password", "x"),
            "threads": self.profile.threads or "auto",
            "extra": self.profile.extra.get("extra_args", ""),
        }
        filled = tmpl.format(**values)
        return shlex.split(filled)

    def preview(self) -> str:
        try:
            return " ".join(shlex.quote(a) for a in self.command())
        except RuntimeError as e:
            return f"(sin comando: {e})"

    def prepare(self, **_) -> None:  # compatibilidad con la interfaz
        self.command()  # valida que el comando existe

    def start(self) -> None:
        args = self.command()
        handle = open(self._log_path, "ab", buffering=0)
        self.proc = subprocess.Popen(
            args, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )

    def stop(self, timeout: float = 10.0) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    @property
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stats(self) -> MinerStats:
        return MinerStats(
            running=self.is_running,
            pool=self.profile.pool_url,
            cpu_brand=self.profile.extra.get("miner_name", "minero externo"),
        )

    def logs(self, lines: int = 40) -> list[str]:
        if not self._log_path.exists():
            return []
        with Path(self._log_path).open("r", errors="replace") as f:
            return f.readlines()[-lines:]
