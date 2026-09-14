"""Detección de hardware y recomendación de configuración de minado."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def _sysctl(key: str) -> str | None:
    out = _run(["sysctl", "-n", key])
    return out or None


@dataclass
class Hardware:
    os: str
    arch: str
    cpu: str
    physical_cores: int
    logical_cores: int
    p_cores: int | None
    e_cores: int | None
    memory_gb: float
    recommended_threads: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def detect() -> Hardware:
    system = platform.system()
    arch = platform.machine()
    notes: list[str] = []

    physical = os.cpu_count() or 1
    logical = os.cpu_count() or 1
    p_cores: int | None = None
    e_cores: int | None = None
    cpu = platform.processor() or ""

    if system == "Darwin":
        cpu = _sysctl("machdep.cpu.brand_string") or _run(["sysctl", "-n", "hw.model"]) or "Apple Silicon"
        if p := _sysctl("hw.perflevel0.physicalcpu"):
            p_cores = int(p)
        if e := _sysctl("hw.perflevel1.physicalcpu"):
            e_cores = int(e)
        if _sysctl("hw.physicalcpu"):
            physical = int(_sysctl("hw.physicalcpu"))
        if _sysctl("hw.logicalcpu"):
            logical = int(_sysctl("hw.logicalcpu"))
        mem_bytes = int(_sysctl("hw.memsize") or 0)
    elif system == "Linux":
        cpu = ""
        cores_per_socket: set[str] = set()
        mem_bytes = 0
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    low = line.lower()
                    if low.startswith("model name") and not cpu:
                        cpu = line.split(":", 1)[1].strip()
                    elif line.startswith("core id"):
                        cores_per_socket.add(line.split(":", 1)[1].strip())
        except Exception:
            pass
        if cores_per_socket:
            physical = len(cores_per_socket)
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        mem_bytes = int(line.split()[1]) * 1024
                        break
        except Exception:
            pass
    else:  # Windows y otros
        mem_bytes = 0
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            mem_bytes = stat.ullTotalPhys
        except Exception:
            mem_bytes = 0

    memory_gb = round(mem_bytes / (1024**3), 1) if mem_bytes else 0.0

    # Recomendación: RandomX pide min(physical, memoria/2GiB) hilos; en laptops, dejar 1 core libre.
    usable = physical or (os.cpu_count() or 1)
    if memory_gb:
        usable = min(usable, max(1, int(memory_gb // 2)))
    recommended = max(1, usable)
    if system == "Darwin" and p_cores and e_cores:
        recommended = max(1, p_cores)  # MXMR usa P-cores por defecto en laptops
        notes.append(f"Apple Silicon: {p_cores} P-cores + {e_cores} E-cores; se recomiendan P-cores")
    if memory_gb and memory_gb < 4:
        notes.append("Menos de 4 GB de RAM: RandomX (XMR) puede ir muy lento o fallar")
    if system == "Darwin":
        notes.append("En laptops, XMRig con 'pause-on-battery' evita drenar la batería")
    if not shutil.which("xmrig"):
        notes.append("XMRig no está en PATH: MinerPro puede descargarlo y verificarlo por ti")

    return Hardware(
        os=system,
        arch=arch,
        cpu=cpu,
        physical_cores=physical,
        logical_cores=logical,
        p_cores=p_cores,
        e_cores=e_cores,
        memory_gb=memory_gb,
        recommended_threads=recommended,
        notes=notes,
    )


if __name__ == "__main__":
    print(json.dumps(detect().to_dict(), indent=2, ensure_ascii=False))
