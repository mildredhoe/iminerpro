"""CLI de MinerPro (Typer).

MinerPro deja todo **listo** para minar: valida wallets, elige pool/moneda, genera
configuraciones y muestra el comando exacto. El minado lo arranca el usuario con
`minerpro mine` (o `--dry-run` para solo ver el plan, sin ejecutar nada).
"""

from __future__ import annotations

import sys
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, coins, hardware, secrets, tui
from .cloud import providers as cloud_providers
from .cloud.nicehash import KEY_ID, KEY_ORG, KEY_SECRET, NiceHashClient
from .config import Profile
from .engines.external import ExternalEngine
from .engines.xmrig import DEFAULT_HTTP_PORT, XmrigEngine
from .pools import stats as pool_stats
from .pools.registry import POOLS, by_name, default_pool

app = typer.Typer(
    add_completion=False,
    help="MinerPro — deja todo listo para minar BTC o XMR, en local o en la nube.",
    no_args_is_help=True,
)
cloud_app = typer.Typer(help="Plataformas de nube/pool (solo lectura y conexión).", no_args_is_help=True)
app.add_typer(cloud_app, name="cloud")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"MinerPro {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    """MinerPro: prepara todo para minar de verdad (BTC o XMR, local o nube)."""


# --------------------------------------------------------------------------- #
# Información
# --------------------------------------------------------------------------- #
@app.command()
def doctor() -> None:
    """Detecta tu hardware y qué mineros tienes disponibles (no mina nada)."""
    hw = hardware.detect()
    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Sistema", f"{hw.os} {hw.arch}")
    t.add_row("CPU", hw.cpu)
    t.add_row("Núcleos", f"{hw.physical_cores} físicos / {hw.logical_cores} lógicos")
    if hw.p_cores:
        t.add_row("P/E cores", f"{hw.p_cores} P + {hw.e_cores} E")
    t.add_row("RAM", f"{hw.memory_gb} GB")
    t.add_row("Hilos recomendados (XMR)", str(hw.recommended_threads))
    console.print(Panel(t, title="Hardware detectado", border_style="cyan"))

    cmds = Table.grid(padding=(0, 2))
    cmds.add_column(style="bold")
    cmds.add_column(style="grey50")
    import shutil

    for b in ("xmrig", "mxmr", "cgminer", "bfgminer", "minerd"):
        found = shutil.which(b)
        cmds.add_row(f"{b}:", "en PATH" if found else "no instalado")
    console.print(Panel(cmds, title="Mineros detectados", border_style="grey50"))

    console.print(f"[grey50]Secrets guardados en: {secrets.storage_backend()}[/grey50]")
    for note in hw.notes:
        console.print(f"[grey50]· {note}[/grey50]")


@app.command()
def coins_cmd() -> None:  # nombre de función distinto para no chocar con el módulo
    """Muestra BTC y XMR: cómo se mina local y en nube con cada una."""
    t = Table(title="Monedas soportadas", show_lines=True)
    t.add_column("Moneda", style="bold cyan")
    t.add_column("Algoritmo")
    t.add_column("Local")
    t.add_column("Nube")
    t.add_column("Realidad")
    for c in coins.COINS.values():
        t.add_row(
            f"{c.name} ({c.symbol})",
            c.algo,
            ", ".join(c.local_engines),
            ", ".join(c.cloud_engines),
            c.reality,
        )
    console.print(t)


app.command("coins")(coins_cmd)


@app.command("pools")
def pools_cmd(
    coin: Optional[str] = typer.Option(None, "--coin", "-c", help="Filtrar por moneda (BTC/XMR)"),
) -> None:
    """Lista pools reales (BTC y XMR) con fee y API de stats."""
    t = Table(title="Pools disponibles")
    t.add_column("Pool", style="bold cyan")
    t.add_column("Moneda")
    t.add_column("Fee")
    t.add_column("URL")
    t.add_column("Stats API")
    for p in POOLS:
        if coin and p.coin.lower() != coin.lower():
            continue
        t.add_row(p.name, p.coin, p.fee, p.url, "sí" if p.stats_api else "no")
    console.print(t)


@app.command()
def wallet(
    address: str = typer.Argument(..., help="Dirección (XMR o BTC); se autodetecta"),
) -> None:
    """Valida una dirección Monero o Bitcoin (checksum real)."""
    symbol = "XMR" if address.startswith("4") or address.startswith("8") else "BTC"
    ok, detail, kind = coins.validate_address(symbol, address)
    if ok:
        console.print(f"[green]✓[/green] {symbol} válida · {kind}")
    else:
        console.print(f"[red]✗[/red] {symbol}: {detail}")
        raise typer.Exit(2)


@app.command()
def install() -> None:
    """Descarga y verifica XMRig (SHA-256 del release oficial) para XMR."""

    def progress(got: int, total: int) -> None:
        console.print(f"\r  descargando… {100 * got / total:5.1f}%", end="")

    try:
        path, ver = XmrigEngine(Profile()).install_only()
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"\n[green]✓[/green] XMRig {ver} verificado y listo en {path}")


@app.command()
def poolstats(
    wallet_addr: str = typer.Option(..., "--wallet", help="Tu dirección"),
    pool_name: str = typer.Option(default_pool().name, "--pool", help="Nombre de la pool"),
) -> None:
    """Muestra el balance real que la pool reporta para tu wallet."""
    p = by_name(pool_name)
    s = pool_stats.fetch(p, wallet_addr)
    if not s.ok:
        console.print(f"[red]No pude leer stats:[/red] {s.error}")
        raise typer.Exit(1)
    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Pool", s.pool)
    t.add_row("Hashrate reportado", tui.fmt_hashrate(s.hashrate))
    t.add_row("Shares", f"{s.accepted} ok / {s.rejected} rechazados")
    t.add_row("Pendiente", f"{s.pending_xmr:.8f} XMR")
    t.add_row("Pagado", f"{s.paid_xmr:.8f} XMR")
    console.print(Panel(t, title="Stats reales de la pool", border_style="yellow"))


# --------------------------------------------------------------------------- #
# Planificación (no ejecuta nada)
# --------------------------------------------------------------------------- #
@app.command()
def plan(
    coin: str = typer.Option("XMR", "--coin", "-c", help="BTC o XMR"),
    wallet_addr: str = typer.Option("", "--wallet", "-w", help="Tu dirección"),
    pool_name: str = typer.Option("", "--pool", "-p", help="Nombre de la pool"),
    mode: str = typer.Option("local", "--mode", help="local | cloud"),
    miner_cmd: str = typer.Option("", "--miner-cmd", help="Comando de minero externo (BTC)"),
) -> None:
    """Explica EXACTAMENTE qué haría MinerPro. No arranca ningún minero."""
    c = coins.get(coin)
    if mode == "cloud":
        console.print(Panel(
            f"[bold]{c.name}[/bold] en nube: se conecta (solo lectura) a las plataformas\n"
            + "\n".join(f"· {e}" for e in c.cloud_engines)
            + "\n\nNo compra contratos ni mueve fondos. Ver: [bold]minerpro cloud providers[/bold]",
            title="Plan (nube)", border_style="cyan",
        ))
        return

    default_pool_name = "SupportXMR" if c.symbol == "XMR" else "CKPool Solo"
    p = by_name(pool_name or default_pool_name)
    ok, detail, kind = (False, "no entregada", "") if not wallet_addr else coins.validate_address(c.symbol, wallet_addr)
    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Moneda", f"{c.name} ({c.symbol}) · {c.algo}")
    t.add_row("Wallet", f"{wallet_addr or '—'}" + (f" ({kind})" if ok else f" [red]({detail})[/red]"))
    t.add_row("Pool", f"{p.name} · {p.url} · fee {p.fee}")
    if c.symbol == "XMR":
        t.add_row("Motor local", "XMRig (descarga oficial + SHA-256), CPU/GPU")
        t.add_row("Comando", f"minerpro mine -c XMR -w {wallet_addr or '<XMR>'} -p {p.name}")
    else:
        t.add_row("Motor local", "Minero externo Stratum (tu ASIC/rig)")
        t.add_row(
            "Comando minero",
            miner_cmd or "[yellow]define --miner-cmd[/yellow] "
            "(ej: 'cgminer -o {url} -u {user} -p {pass}')",
        )
        t.add_row("Comando", f"minerpro mine -c BTC -w {wallet_addr or '<BTC>'} -p {p.name}")
    console.print(Panel(t, title=f"Plan local ({c.symbol})", border_style="green"))
    console.print("[grey50]Nada se ejecutó. Usa `minerpro mine ...` cuando quieras minar de verdad.[/grey50]")


# --------------------------------------------------------------------------- #
# Nube
# --------------------------------------------------------------------------- #
@cloud_app.command("providers")
def cloud_providers_cmd() -> None:
    """Catálogo de plataformas de nube/pool con su riesgo."""
    t = Table(title="Plataformas (ninguna es recomendación de inversión)", show_lines=True)
    t.add_column("Plataforma", style="bold cyan")
    t.add_column("Tipo")
    t.add_column("Monedas")
    t.add_column("Fee")
    t.add_column("Riesgo")
    t.add_column("URL")
    for p in cloud_providers.PROVIDERS:
        risk_style = {"bajo": "green", "medio": "yellow", "alto": "red", "ALTO": "bold red"}.get(p.risk, "white")
        t.add_row(p.name, p.kind, p.coins, p.fee, f"[{risk_style}]{p.risk}[/{risk_style}]", p.url)
    console.print(t)
    console.print("[grey50]MinerPro no compra contratos ni mueve fondos: solo conecta y muestra datos.[/grey50]")


@cloud_app.command("connect")
def cloud_connect(
    provider: str = typer.Argument("nicehash", help="Proveedor (por ahora: nicehash)"),
    api_key: str = typer.Option(..., "--api-key", prompt=True),
    api_secret: str = typer.Option(..., "--api-secret", prompt=True, hide_input=True),
    org_id: str = typer.Option("", "--org-id"),
) -> None:
    """Guarda credenciales de API en el llavero (nunca en texto plano si hay keyring)."""
    if provider.lower() != "nicehash":
        console.print("[red]Proveedor no soportado todavía.[/red]")
        raise typer.Exit(2)
    secrets.store(KEY_ID, api_key)
    secrets.store(KEY_SECRET, api_secret)
    if org_id:
        secrets.store(KEY_ORG, org_id)
    console.print(f"[green]✓[/green] Credenciales guardadas en {secrets.storage_backend()}")


@cloud_app.command("status")
def cloud_status(
    provider: str = typer.Argument("nicehash", help="Proveedor"),
) -> None:
    """Consulta (solo lectura) tu cuenta en la plataforma."""
    if provider.lower() != "nicehash":
        console.print("[red]Proveedor no soportado todavía.[/red]")
        raise typer.Exit(2)
    client = NiceHashClient.from_store()
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
        raise typer.Exit(1)
    try:
        acc = client.accounts()
    except Exception as e:
        console.print(f"[red]Error consultando NiceHash:[/red] {e}")
        raise typer.Exit(1)
    t = Table(title="NiceHash (solo lectura)")
    t.add_column("Moneda", style="bold cyan")
    t.add_column("Disponible")
    t.add_column("Pendiente")
    for item in acc.get("total", {}).get("accounts", []) or acc.get("accounts", []):
        t.add_row(
            str(item.get("currency", "?")),
            str(item.get("available", "0")),
            str(item.get("pending", "0")),
        )
    console.print(t)


# --------------------------------------------------------------------------- #
# Minar (arranca el minero de verdad)
# --------------------------------------------------------------------------- #
def _build_engine(coin_symbol: str, prof: Profile, port: int, miner_cmd: str):
    if coin_symbol == "XMR":
        return XmrigEngine(prof, http_port=port)
    prof.extra["cmd"] = miner_cmd or prof.extra.get("cmd", "")
    return ExternalEngine(prof)


@app.command()
def mine(
    wallet_addr: str = typer.Option(..., "--wallet", "-w", help="Tu dirección (XMR o BTC)"),
    coin: str = typer.Option("XMR", "--coin", "-c", help="BTC o XMR"),
    pool_name: str = typer.Option("", "--pool", "-p", help="Nombre de la pool"),
    profile_name: str = typer.Option("default", "--profile", help="Nombre del perfil"),
    threads: Optional[int] = typer.Option(None, "--threads", "-t", help="Hilos de CPU (XMR)"),
    port: int = typer.Option(DEFAULT_HTTP_PORT, "--port", help="Puerto local de la API de XMRig"),
    tls: bool = typer.Option(False, "--tls", help="Usar TLS hacia la pool"),
    miner_cmd: str = typer.Option("", "--miner-cmd", help="Comando del minero externo (BTC)"),
    seconds: Optional[int] = typer.Option(None, "--seconds", help="Detener tras N segundos"),
    plain: bool = typer.Option(False, "--plain", help="Sin TUI: solo logs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Solo muestra el plan, no ejecuta nada"),
) -> None:
    """Minar de verdad contra una pool (BTC o XMR). Usa --dry-run para no ejecutar."""
    c = coins.get(coin)
    ok, detail, kind = coins.validate_address(c.symbol, wallet_addr)
    if not ok:
        console.print(f"[red]Wallet inválida:[/red] {detail}")
        raise typer.Exit(2)

    default_pool_name = "SupportXMR" if c.symbol == "XMR" else "CKPool Solo"
    pool = by_name(pool_name or default_pool_name)
    prof = Profile(
        name=profile_name,
        wallet=wallet_addr,
        pool_name=pool.name,
        pool_url=pool.url,
        coin="monero" if c.symbol == "XMR" else "bitcoin",
        engine="xmrig" if c.symbol == "XMR" else "external",
        threads=threads,
        extra={"cmd": miner_cmd} if miner_cmd else {},
    )
    engine = _build_engine(c.symbol, prof, port, miner_cmd)

    if dry_run:
        console.print(Panel(
            f"Moneda: [bold]{c.name}[/bold]\nPool: [bold]{pool.name}[/bold] ({pool.url})\n"
            f"Wallet: {kind}\nMotor: {engine.name}\n"
            + (f"Comando: {engine.preview()}" if hasattr(engine, "preview") else "Comando: XMRig (se descarga/verifica)"),
            title="Dry-run: nada se ejecuta", border_style="yellow",
        ))
        return

    # Recién aquí se toca el disco/red para instalar y arrancar el minero.
    prof.save()
    if c.symbol == "XMR":
        def progress(got: int, total: int) -> None:
            console.print(f"\r  descargando XMRig… {100 * got / total:5.1f}%", end="")

        engine.prepare(show=progress)
        console.print(f"\n[green]✓[/green] XMRig {engine.version} · minando a [bold]{pool.name}[/bold]")
    else:
        engine.prepare()
        console.print(f"[green]✓[/green] Minero externo: {engine.preview()}")

    engine.start()
    try:
        for _ in range(20):
            if engine.stats().raw:
                break
            time.sleep(0.5)

        if plain:
            deadline = time.time() + seconds if seconds else None
            while engine.is_running:
                s = engine.stats()
                console.print(
                    f"[green]{tui.fmt_hashrate(s.hashrate_10s):>12}[/green]  "
                    f"aceptados {s.shares_good}  rechazados {s.shares_bad}  "
                    f"uptime {tui.fmt_duration(s.uptime_s)}"
                )
                if deadline and time.time() > deadline:
                    break
                time.sleep(5)
        else:
            if seconds:
                import threading

                threading.Timer(seconds, engine.stop).start()
            tui.run(engine, prof.name, pool, wallet_addr, console=console)
    finally:
        engine.stop()
        s = engine.stats()
        console.print(
            f"[bold]Resumen:[/bold] {tui.fmt_hashrate(s.hashrate_max)} pico · "
            f"{s.shares_good} shares aceptados · uptime {tui.fmt_duration(s.uptime_s)}"
        )
        if pool.stats_api:
            ps = pool_stats.fetch(pool, wallet_addr)
            if ps.ok:
                console.print(
                    f"[grey50]Pool: {ps.accepted} aceptados · pendiente "
                    f"{ps.pending_xmr:.8f}[/grey50]"
                )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
