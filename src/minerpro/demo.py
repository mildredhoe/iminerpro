"""Datos de ejemplo para mostrar la interfaz sin minar ni usar tu equipo.

Todo lo que sale de aquí está **marcado como DEMO**: son cifras realistas de un
equipo típico (Ryzen 9 5950X minando RandomX) para documentación y material de
presentación. Nunca se presentan como si fueran tuyas ni se usan en el flujo real.
"""

from __future__ import annotations

import io

from rich.console import Console

from .engines.base import MinerStats
from .pools.registry import by_name
from .pools.stats import PoolStats
from .tui import render_frame

DEMO_NOTICE = "DEMO · datos de ejemplo (no es tu equipo ni tu wallet)"

DEMO_HARDWARE = {
    "os": "Linux x86_64",
    "cpu": "AMD Ryzen 9 5950X 16-Core Processor",
    "physical_cores": 16,
    "logical_cores": 32,
    "memory_gb": 32.0,
    "recommended_threads": 16,
    "gpu": "NVIDIA GeForce RTX 3070 (no usada con RandomX)",
    "notes": [
        "RandomX rinde mejor usando los núcleos físicos completos",
        "En laptops, XMRig con 'pause-on-battery' evita drenar la batería",
        "MinerPro puede descargar y verificar XMRig por ti",
    ],
}

DEMO_MINERS = [
    ("xmrig", "6.26.0 · verificado (SHA-256)"),
    ("mxmr", "no instalado"),
    ("cgminer", "no instalado"),
    ("bfgminer", "no instalado"),
]

DEMO_STATS = MinerStats(
    running=True,
    algo="rx/0",
    pool="pool.supportxmr.com:3333",
    uptime_s=4 * 3600 + 12 * 60 + 8,
    hashrate_10s=13842.0,
    hashrate_max=14096.0,
    shares_good=128,
    shares_total=129,
    threads=16,
    cpu_brand="AMD Ryzen 9 5950X",
)

DEMO_POOL = PoolStats(
    ok=True,
    pool="SupportXMR",
    hashrate=13910.0,
    accepted=271,
    rejected=1,
    pending_xmr=0.00341214,
    paid_xmr=0.04510892,
)

DEMO_LOGS = [
    "[2026-09-14 21:04:11]  use pool pool.supportxmr.com:3333 0.6%",
    "[2026-09-14 21:04:11]  new job from pool.supportxmr.com:3333 diff 120K algo rx/0 height=3217501",
    "[2026-09-14 21:05:02]  accepted (412/0) diff 120K (46 ms)",
    "[2026-09-14 21:06:37]  accepted (413/0) diff 120K (52 ms)",
    "[2026-09-14 21:08:19]  speed 10s/60s/15m 13842 13776 13701 H/s max 14096 H/s",
    "[2026-09-14 21:09:55]  accepted (414/0) diff 120K (48 ms)",
]


def _demo_console(width: int) -> Console:
    """Consola que solo captura: nunca escribe al stdout real."""
    return Console(
        record=True,
        width=width,
        force_terminal=False,
        no_color=True,
        file=io.StringIO(),
    )


def _render(renderable, width: int = 100) -> str:
    console = _demo_console(width)
    console.print(renderable)
    return console.export_text().rstrip("\n")


def dashboard_text(width: int = 100) -> str:
    """Cuadro del dashboard con datos de ejemplo (misma TUI que el modo real)."""
    pool = by_name("SupportXMR")
    history = [12500 + 340 * i + (120 if i % 3 else -90) for i in range(40)]
    history += [13800, 13842]
    frame = render_frame("demo-ryzen", pool, DEMO_STATS, DEMO_POOL, DEMO_LOGS, [float(h) for h in history])
    return _render(frame, width=width)


def hardware_text(width: int = 100) -> str:
    """Bloque tipo `doctor` con hardware de ejemplo."""
    from rich.panel import Panel
    from rich.table import Table

    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Sistema", DEMO_HARDWARE["os"])
    t.add_row("CPU", DEMO_HARDWARE["cpu"])
    t.add_row(
        "Núcleos",
        f"{DEMO_HARDWARE['physical_cores']} físicos / {DEMO_HARDWARE['logical_cores']} lógicos",
    )
    t.add_row("RAM", f"{DEMO_HARDWARE['memory_gb']} GB")
    t.add_row("GPU", DEMO_HARDWARE["gpu"])
    t.add_row("Hilos recomendados (XMR)", str(DEMO_HARDWARE["recommended_threads"]))
    panel = Panel(t, title="Hardware detectado", border_style="cyan")

    m = Table.grid(padding=(0, 2))
    m.add_column(style="bold")
    m.add_column(style="grey50")
    for name, state in DEMO_MINERS:
        m.add_row(f"{name}:", state)
    miners = Panel(m, title="Mineros detectados", border_style="grey50")

    console = _demo_console(width)
    console.print(panel)
    console.print(miners)
    console.print("[grey50]Secrets guardados en: keyring (Keychain / DPAPI / Secret Service)[/grey50]")
    for note in DEMO_HARDWARE["notes"]:
        console.print(f"[grey50]· {note}[/grey50]")
    return console.export_text().rstrip("\n")


def to_stdout(panel: str = "mine", width: int = 100, notice: bool = True) -> str:
    """Texto completo para la terminal o el README."""
    body = hardware_text(width) if panel == "doctor" else dashboard_text(width)
    if not notice:
        return body
    return f"⚠ {DEMO_NOTICE}\n\n" + body


def _main() -> None:  # pragma: no cover - utilidad manual
    import sys

    panel = sys.argv[1] if len(sys.argv) > 1 else "mine"
    out = io.StringIO()
    out.write(to_stdout(panel))
    print(out.getvalue())


if __name__ == "__main__":  # pragma: no cover
    _main()
