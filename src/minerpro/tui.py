"""TUI de MinerPro (Rich): dashboard de minado con datos reales."""

from __future__ import annotations

import time
from collections import deque

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .engines.base import MinerEngine, MinerStats
from .pools import stats as pool_stats
from .pools.registry import Pool
from .pools.stats import PoolStats

GREEN = "bright_green"
CYAN = "cyan"
YELLOW = "yellow"
RED = "red"
DIM = "grey50"

LOGO = r"""
  __  __ ___ _   _ _____ ____    ____  ____   ___
 |  \/  |_ _| \ | | ____|  _ \  |  _ \|  _ \ / _ \
 | |\/| || ||  \| |  _| | |_) | | |_) | |_) | | | |
 | |  | || || |\  | |___|  _ <  |  __/|  _ <| |_| |
 |_|  |_|___|_| \_|_____|_| \_\ |_|   |_| \_\\___/
"""


def fmt_hashrate(hs: float) -> str:
    if hs >= 1e6:
        return f"{hs / 1e6:.2f} MH/s"
    if hs >= 1e3:
        return f"{hs / 1e3:.2f} kH/s"
    return f"{hs:.0f} H/s"


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def sparkline(values: list[float], width: int = 60) -> Text:
    """Mini gráfico ASCII de la serie de hashrate."""
    blocks = "▁▂▃▄▅▆▇█"
    vals = list(values)[-width:]
    if not vals:
        vals = [0.0]
    hi = max(vals) or 1.0
    lo = min(vals)
    span = (hi - lo) or 1.0
    text = Text(style=GREEN)
    for v in vals:
        idx = int((v - lo) / span * (len(blocks) - 1))
        text.append(blocks[idx])
    return text


def _header(profile_name: str, pool: Pool, stats: MinerStats) -> Panel:
    left = Text(LOGO, style=CYAN)
    info = Table.grid(padding=(0, 2))
    info.add_column(style=DIM, justify="right")
    info.add_column(style="bold")
    info.add_row("perfil", profile_name)
    info.add_row("pool", f"{pool.name}  [grey50]{stats.pool or pool.url}[/grey50]")
    info.add_row("algoritmo", stats.algo or pool.algo)
    info.add_row("CPU", stats.cpu_brand or "—")
    info.add_row("uptime", fmt_duration(stats.uptime_s))
    return Panel(
        Group(Align.center(left), info),
        title="[b]MINER PRO[/b] · minado real",
        border_style=CYAN,
    )


def _hashrate_panel(stats: MinerStats, history: deque) -> Panel:
    body = Table.grid()
    body.add_column(justify="center")
    body.add_row(Text(fmt_hashrate(stats.hashrate_10s), style=f"bold {GREEN}", justify="center"))
    body.add_row(Text(f"10s en vivo · pico {fmt_hashrate(stats.hashrate_max)}", style=DIM, justify="center"))
    body.add_row(sparkline(list(history)))
    return Panel(body, title="Hashrate", border_style=GREEN)


def _shares_panel(stats: MinerStats, pool: PoolStats | None) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style=DIM, justify="right")
    t.add_column(style="bold", justify="right")
    t.add_column(style=CYAN, justify="right")

    def row(label, session, poolv):
        t.add_row(label, str(session), poolv)

    t.add_row("", Text("sesión", style=DIM), Text("pool", style=DIM))
    row("aceptados", stats.shares_good, str(pool.accepted) if pool and pool.ok else "—")
    row("rechazados", stats.shares_bad, str(pool.rejected) if pool and pool.ok else "—")
    ratio = f"{stats.accept_ratio * 100:.1f}%" if stats.shares_total else "—"
    row("aceptación", ratio, "—")
    pending = f"{pool.pending_xmr:.6f} XMR" if pool and pool.ok else "—"
    paid = f"{pool.paid_xmr:.6f} XMR" if pool and pool.ok else "—"
    row("pendiente", "", pending)
    row("pagado", "", paid)
    row("hilos", stats.threads or "auto", "")
    return Panel(t, title="Shares y balance", border_style=YELLOW)


def _logs_panel(lines: list[str]) -> Panel:
    text = Text()
    for ln in lines:
        ln = ln.rstrip("\n")
        style = DIM
        if "accepted" in ln:
            style = GREEN
        elif "rejected" in ln or "error" in ln.lower():
            style = RED
        elif "new job" in ln or "use " in ln:
            style = CYAN
        text.append(ln[:160] + "\n", style=style)
    if not lines:
        text.append("esperando salida del minero…", style=DIM)
    return Panel(text, title="Log de XMRig (real)", border_style=DIM)


def render_frame(
    profile_name: str,
    pool: Pool,
    stats: MinerStats,
    pool_state: "PoolStats | None",
    logs: list[str],
    history: list[float],
) -> Group:
    """Un cuadro completo del dashboard, reutilizable por la TUI y por `demo`."""
    return Group(
        _header(profile_name, pool, stats),
        _hashrate_panel(stats, history),
        _shares_panel(stats, pool_state),
        _logs_panel(logs),
    )


def run(
    engine: MinerEngine,
    profile_name: str,
    pool: Pool,
    wallet: str,
    *,
    refresh: float = 1.0,
    console: Console | None = None,
    should_stop=None,
) -> None:
    """Dashboard en vivo. Sale con Ctrl+C deteniendo el minero."""
    console = console or Console()
    history: deque[float] = deque(maxlen=90)
    pool_state: PoolStats | None = None
    last_pool_fetch = 0.0

    def render(stats: MinerStats) -> Group:
        return render_frame(profile_name, pool, stats, pool_state, engine.logs(14), list(history))

    try:
        with Live(render(MinerStats()), console=console, refresh_per_second=4, screen=False) as live:
            while True:
                stats = engine.stats()
                history.append(stats.hashrate_10s)
                now = time.time()
                if now - last_pool_fetch > 30 and pool.stats_api:
                    pool_state = pool_stats.fetch(pool, wallet)
                    last_pool_fetch = now
                live.update(render(stats))
                if should_stop is not None and should_stop():
                    console.print("[yellow]Parada pedida.[/yellow]")
                    break
                if not engine.is_running:
                    console.print("[yellow]El minero terminó.[/yellow]")
                    break
                time.sleep(refresh)
    except KeyboardInterrupt:
        console.print("[yellow]Detenido por el usuario.[/yellow]")
