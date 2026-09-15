# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Motor XMRig: descarga verificada, configuración y control por API.

XMRig es software libre de xmrig.com. MinerPro descarga el binario oficial del
release de GitHub, verifica su SHA-256 contra el SHA256SUMS del mismo release y
lo ejecuta localmente. Nunca se descarga de terceros.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import tarfile
import zipfile
from pathlib import Path

import httpx

from ..config import Profile, bin_dir, cache_dir, logs_dir
from .base import MinerStats

GITHUB_RELEASE = "https://api.github.com/repos/xmrig/xmrig/releases/latest"
PINNED_VERSION = "6.26.0"  # fallback si la API de GitHub no responde o limita
DEFAULT_HTTP_PORT = 18080
XMRIG_USER_AGENT = "MinerPro/0.1 (+https://github.com/minerpro)"


# --------------------------------------------------------------------------- #
# Selección de asset según plataforma
# --------------------------------------------------------------------------- #
def asset_candidates() -> list[str]:
    system = platform.system()
    arch = platform.machine().lower()
    if system == "Darwin":
        return ["macos-arm64.tar.gz"] if arch in ("arm64", "aarch64") else ["macos-x64.tar.gz"]
    if system == "Linux":
        if arch in ("x86_64", "amd64"):
            return ["linux-static-x64.tar.gz"]
        return []  # XMRig no publica binario Linux arm64: hay que compilar
    if system == "Windows":
        return ["windows-arm64.zip"] if arch in ("arm64", "aarch64") else ["windows-x64.zip"]
    return []


def _pick_asset(assets: list[dict]) -> dict | None:
    for cand in asset_candidates():
        for a in assets:
            if a["name"].endswith(cand):
                return a
    return None


def latest_release(client: httpx.Client) -> dict:
    """Release de XMRig (usa la API de GitHub; degrada a versión fijada)."""
    try:
        r = client.get(GITHUB_RELEASE, headers={"User-Agent": XMRIG_USER_AGENT})
        r.raise_for_status()
        return r.json()
    except Exception:
        tag = f"v{PINNED_VERSION}"
        base = f"https://github.com/xmrig/xmrig/releases/download/{tag}"
        cands = asset_candidates()
        return {
            "tag_name": tag,
            "assets": [],
            "_fallback_base": base,
            "_fallback_candidates": cands,
        }


def _asset_url(release: dict, name: str) -> str:
    if release.get("_fallback_base"):
        return f"{release['_fallback_base']}/{name}"
    for a in release["assets"]:
        if a["name"] == name:
            return a["browser_download_url"]
    raise RuntimeError(f"asset no encontrado en el release: {name}")


def _download(client: httpx.Client, url: str, dest: Path, show=None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, headers={"User-Agent": XMRIG_USER_AGENT}, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        got = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
                got += len(chunk)
                if show and total:
                    show(got, total)
    return dest


def _verify_sha256(archive: Path, sums_text: str) -> str:
    want = None
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == archive.name:
            want = parts[0].strip().lower()
            break
    if want is None:
        raise RuntimeError(f"no hay SHA256 para {archive.name} en SHA256SUMS")
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got != want:
        raise RuntimeError(f"SHA256 no coincide para {archive.name}: {got} != {want}")
    return got


def _extract(archive: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(out_dir)
    else:
        with tarfile.open(archive, "r:gz") as t:
            # extracción segura
            for member in t.getmembers():
                target = (out_dir / member.name).resolve()
                if not str(target).startswith(str(out_dir.resolve())):
                    raise RuntimeError("archivo comprimido sospechoso (path traversal)")
            t.extractall(out_dir)
    for p in out_dir.rglob("xmrig*"):
        if p.is_file() and p.name.lower().startswith("xmrig") and not p.suffix:
            p.chmod(0o755)
            return p
    for p in out_dir.rglob("xmrig"):
        p.chmod(0o755)
        return p
    raise RuntimeError("no encontré el binario xmrig dentro del archivo")


def ensure_xmrig(show=None) -> tuple[Path, str]:
    """Devuelve (ruta_al_binario, versión). Descarga y verifica si hace falta."""
    env = os.environ.get("MINERPRO_XMRIG_PATH")
    if env and Path(env).exists():
        return Path(env), "custom"

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        release = latest_release(client)
        tag = release["tag_name"]
        ver = tag.lstrip("v")
        target_dir = bin_dir() / f"xmrig-{ver}"
        existing = target_dir / ("xmrig.exe" if platform.system() == "Windows" else "xmrig")
        if existing.exists():
            return existing, ver

        names = [a["name"] for a in release.get("assets", [])]
        asset = _pick_asset(release.get("assets", [])) if names else None
        if asset:
            name = asset["name"]
        elif release.get("_fallback_candidates"):
            name = f"xmrig-{ver}-{release['_fallback_candidates'][0]}"
        else:
            raise RuntimeError(
                "XMRig no publica binario oficial para esta plataforma; hay que compilar desde fuente"
            )

        archive = cache_dir() / name
        if not archive.exists():
            _download(client, _asset_url(release, name), archive, show=show)

        # verificación SHA-256
        sums_name = "SHA256SUMS"
        try:
            sums_url = _asset_url(release, sums_name)
        except RuntimeError:
            sums_url = f"https://github.com/xmrig/xmrig/releases/download/{tag}/{sums_name}"
        sums_text = client.get(sums_url, headers={"User-Agent": XMRIG_USER_AGENT}).text
        _verify_sha256(archive, sums_text)

        binary = _extract(archive, target_dir)
        return binary, ver


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
def build_config(
    wallet: str,
    pool_url: str,
    *,
    coin: str = "monero",
    http_port: int = DEFAULT_HTTP_PORT,
    tls: bool = False,
    pause_on_battery: bool = True,
    extra: dict | None = None,
) -> dict:
    cfg = {
        "api": {"id": None, "worker-id": None},
        "http": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": http_port,
            "access-token": None,
            "restricted": True,
        },
        "autosave": False,
        "background": False,
        "colors": False,
        "title": True,
        "randomx": {"init": -1, "mode": "auto", "1gb-pages": False, "rdms": False, "numa": True},
        "pools": [
            {
                "algo": None,
                "coin": coin,
                "url": pool_url,
                "user": wallet,
                "pass": "x",
                "rig-id": None,
                "nicehash": False,
                "keepalive": True,
                "enabled": True,
                "tls": tls,
                "tls-fingerprint": None,
                "daemon": False,
                "socks5": None,
                "self-select": None,
            }
        ],
        "print-time": 5,
        "verbose": 1,
        "watch": True,
        "pause-on-battery": pause_on_battery,
    }
    if extra:
        cfg.update(extra)
    return cfg


# --------------------------------------------------------------------------- #
# Motor
# --------------------------------------------------------------------------- #
class XmrigEngine:
    name = "xmrig"

    def __init__(self, profile: Profile, http_port: int = DEFAULT_HTTP_PORT):
        self.profile = profile
        self.http_port = http_port
        self.binary: Path | None = None
        self.version: str = ""
        self.proc: subprocess.Popen | None = None
        self._log_path = logs_dir() / f"xmrig-{profile.name}.log"
        self._cfg_path = profile.dir() / "config.json"

    # -- instalación/config -------------------------------------------------- #
    def prepare(self, show=None, *, tls: bool = False) -> Path:
        self.binary, self.version = ensure_xmrig(show=show)
        cfg = build_config(
            self.profile.wallet,
            self.profile.pool_url,
            coin=self.profile.coin,
            http_port=self.http_port,
            tls=tls,
        )
        self._cfg_path.write_text(json.dumps(cfg, indent=2))
        return self._cfg_path

    def install_only(self) -> tuple[Path, str]:
        self.binary, self.version = ensure_xmrig()
        return self.binary, self.version

    # -- ciclo de vida ------------------------------------------------------- #
    def start(self) -> None:
        if self.binary is None:
            self.prepare()
        assert self.binary is not None
        if not self._cfg_path.exists():
            cfg = build_config(self.profile.wallet, self.profile.pool_url, http_port=self.http_port)
            self._cfg_path.write_text(json.dumps(cfg, indent=2))

        args = [str(self.binary), "-c", str(self._cfg_path), "--no-color"]
        if self.profile.threads:
            args += ["-t", str(self.profile.threads)]

        handle = open(self._log_path, "ab", buffering=0)
        self.proc = subprocess.Popen(
            args,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(self.binary.parent),
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

    def returncode(self) -> int | None:
        return None if self.proc is None else self.proc.poll()

    # -- observabilidad ------------------------------------------------------ #
    def _api(self, path: str = "/1/summary") -> dict | None:
        try:
            r = httpx.get(f"http://127.0.0.1:{self.http_port}{path}", timeout=2.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            return None
        return None

    def stats(self) -> MinerStats:
        data = self._api()
        if not data:
            return MinerStats(running=self.is_running)
        hr = data.get("hashrate", {}) or {}
        total = hr.get("total") or [0, 0, 0]
        results = data.get("results", {}) or {}
        conn = data.get("connection", {}) or {}
        cpu = data.get("cpu", {}) or {}
        return MinerStats(
            running=not data.get("paused", False),
            algo=data.get("algo", ""),
            pool=conn.get("pool", "") or self.profile.pool_url,
            uptime_s=int(data.get("uptime", 0)),
            hashrate_10s=float(total[0] or 0),
            hashrate_max=float(hr.get("highest", 0) or 0),
            shares_good=int(results.get("shares_good", 0)),
            shares_total=int(results.get("shares_total", 0)),
            threads=int(cpu.get("threads", 0) or 0),
            cpu_brand=cpu.get("brand", "") or "",
            paused=bool(data.get("paused", False)),
            raw=data,
        )

    def logs(self, lines: int = 40) -> list[str]:
        if not self._log_path.exists():
            return []
        with open(self._log_path, "r", errors="replace") as f:
            return f.readlines()[-lines:]

    # -- utilidades ---------------------------------------------------------- #
    def benchmark(self, size: str = "1M") -> tuple[int, str]:
        """Benchmark real de hashing (sin pool). Devuelve (rc, salida)."""
        if self.binary is None:
            self.install_only()
        assert self.binary is not None
        proc = subprocess.run(
            [str(self.binary), f"--bench={size}", "--no-color"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
