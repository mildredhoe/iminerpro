"""CLI de MinerPro (Typer).

MinerPro deja todo **listo** para minar: valida wallets, elige pool/moneda, genera
configuraciones y muestra el comando exacto. El minado lo arranca el usuario con
`minerpro mine` (o `--dry-run` para solo ver el plan, sin ejecutar nada).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, coins, hardware, market, preflight, run_state, secrets, stratum, tui
from . import demo as demo_mod
from .config import Profile, load_env, logs_dir
from .engines.external import ExternalEngine
from .engines.xmrig import DEFAULT_HTTP_PORT, XmrigEngine
from .platforms import all_platforms
from .platforms import catalog as provider_catalog
from .platforms import get as get_platform
from .platforms.binance import BinanceClient
from .platforms.nicehash import NiceHashClient, NiceHashWriteDisabled, PublicNiceHash
from .pools import stats as pool_stats
from .pools.registry import POOLS, by_name, default_pool

app = typer.Typer(
    add_completion=False,
    help="MinerPro — deja todo listo para minar BTC o XMR, en local o en la nube.",
    no_args_is_help=True,
)
cloud_app = typer.Typer(
    help="Plataformas de nube/pool: mercado, cuenta y acciones (con --confirm).",
    no_args_is_help=True,
)
app.add_typer(cloud_app, name="cloud")
_columns = os.environ.get("COLUMNS", "")
console = Console(width=int(_columns)) if _columns.isdigit() else Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"MinerPro {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    """MinerPro: prepara todo para minar de verdad (BTC o XMR, local o nube)."""
    load_env()


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


@app.command("coins")
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


@app.command()
def demo(
    panel: str = typer.Argument("mine", help="mine (dashboard) o doctor (hardware)"),
    width: int = typer.Option(100, "--width", help="Ancho de la salida"),
    notice: bool = typer.Option(True, "--notice/--no-notice", help="Mostrar el aviso de datos de ejemplo"),
) -> None:
    """Muestra la interfaz con datos de EJEMPLO, sin minar ni tocar tu equipo."""
    if panel not in ("mine", "doctor"):
        console.print("[red]panel inválido: usa 'mine' o 'doctor'[/red]")
        raise typer.Exit(2)
    text = demo_mod.to_stdout(panel, width, notice)
    console.print(text, markup=False, highlight=False, soft_wrap=True)


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
    t.add_row("Pendiente", f"{s.pending_xmr:.8f} {s.coin}")
    t.add_row("Pagado", f"{s.paid_xmr:.8f} {s.coin}")
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
# Nube: plataformas conectables (NiceHash, Binance, ...)
# --------------------------------------------------------------------------- #
@cloud_app.command("platforms")
def cloud_platforms() -> None:
    """Plataformas que se pueden conectar por API."""
    t = Table(title="Plataformas conectables")
    t.add_column("ID", style="bold cyan")
    t.add_column("Nombre")
    t.add_column("Tipo")
    t.add_column("Monedas")
    t.add_column("Claves")
    for p in all_platforms():
        t.add_row(p.id, p.name, p.kind, ", ".join(p.coins), p.keys_url)
    console.print(t)
    console.print("[grey50]Ver el paso a paso: minerpro cloud guide <id>[/grey50]")


@cloud_app.command("guide")
def cloud_guide(
    platform: str = typer.Argument(..., help="ID de la plataforma (nicehash, binance)"),
) -> None:
    """Cómo obtener las API keys y dónde pegarlas en MinerPro."""
    try:
        p = get_platform(platform)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    from rich.text import Text

    body = "\n".join(p.guide_lines())
    console.print(Panel(Text(body), title=f"Guía: {p.name}", border_style="cyan"))
    console.print(f"[grey50]Almacén de claves actual: {secrets.storage_backend()}[/grey50]")


@cloud_app.command("connect")
def cloud_connect(
    platform: str = typer.Argument(..., help="ID de la plataforma (nicehash, binance)"),
) -> None:
    """Pide las credenciales y las guarda de forma segura (llavero del sistema)."""
    try:
        p = get_platform(platform)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)

    console.print(f"[bold]{p.name}[/bold] · obtén tus claves en {p.keys_url}")
    console.print("[grey50]Permisos necesarios:[/grey50]")
    for perm in p.api_permissions:
        console.print(f"  · {perm}")

    for f in p.fields:
        while True:
            value = typer.prompt(f"  {f.label}", hide_input=f.secret, default="")
            if value:
                break
            console.print("  [yellow]requerido[/yellow]")
        secrets.store(f.key, value)

    console.print(f"[green]✓[/green] Credenciales de {p.name} guardadas en {secrets.storage_backend()}")
    console.print(f"  Verifica con: minerpro cloud status {p.id}")


@cloud_app.command("status")
def cloud_status(
    platform: str = typer.Argument("nicehash", help="ID de la plataforma"),
) -> None:
    """Consulta (solo lectura) tu cuenta en la plataforma."""
    try:
        p = get_platform(platform)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)

    if p.id == "nicehash":
        client = NiceHashClient.from_store()
        if client is None:
            console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
            console.print("[grey50]O define MINERPRO_NICEHASH_KEY / _SECRET / _ORG en .env[/grey50]")
            raise typer.Exit(1)
        try:
            acc = client.accounts()
        except Exception as e:
            console.print(f"[red]Error consultando NiceHash:[/red] {e}")
            raise typer.Exit(1)
        t = Table(title="NiceHash · balance (solo lectura)")
        t.add_column("Moneda", style="bold cyan")
        t.add_column("Disponible")
        t.add_column("Pendiente")
        for item in acc.get("total", {}).get("accounts", []) or acc.get("accounts", []) or []:
            t.add_row(
                str(item.get("currency", "?")),
                str(item.get("available", "0")),
                str(item.get("pending", "0")),
            )
        console.print(t)
        return

    if p.id == "binance":
        client = BinanceClient.from_store()
        if client is None:
            console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect binance")
            console.print("[grey50]O define MINERPRO_BINANCE_KEY / _SECRET en .env[/grey50]")
            raise typer.Exit(1)
        try:
            st = client.status()
            accts = client.accounts()
        except Exception as e:
            console.print(f"[red]Error consultando Binance:[/red] {e}")
            raise typer.Exit(1)
        t = Table(title="Binance Pool · cuentas de minería (solo lectura)")
        t.add_column("Moneda", style="bold cyan")
        t.add_column("Hashrate")
        t.add_column("Algo")
        for item in accts.get("data", []) or []:
            t.add_row(
                str(item.get("type", "?")).upper(),
                str(item.get("hashRate", "0")),
                ", ".join(item.get("algoName", "").split(",")) if item.get("algoName") else "",
            )
        console.print(t)
        console.print(f"[grey50]Estado de la cuenta: {st.get('data', st)}[/grey50]")
        return

    console.print(f"[yellow]{p.name} no tiene conector de lectura todavía.[/yellow]")


@cloud_app.command("stratum")
def cloud_stratum(
    platform: str = typer.Argument(..., help="ID de la plataforma"),
    coin: str = typer.Option("XMR", "--coin", "-c", help="BTC o XMR"),
    wallet: str = typer.Option("", "--wallet", "-w", help="Tu dirección/cuenta"),
    account: str = typer.Option("", "--account", help="Cuenta de minería (Binance)"),
    worker: str = typer.Option("rig1", "--worker", help="Nombre del worker"),
    tls: bool = typer.Option(False, "--tls", help="Usar el puerto TLS"),
    write_xmrig: bool = typer.Option(
        False, "--write-xmrig", help="Escribir un config.json de XMRig con este destino"
    ),
) -> None:
    """Arma el destino Stratum para empezar a minar (no lanza el minero)."""
    try:
        p = get_platform(platform)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    ep = p.stratum_for(coin)
    if ep is None:
        console.print(f"[red]{p.name} no ofrece stratum para {coin}.[/red]")
        raise typer.Exit(2)
    try:
        target = stratum.build_target(ep, wallet=wallet, account=account, worker=worker, tls=tls)
    except ValueError as e:
        console.print(f"[red]Falta un dato:[/red] {e}")
        raise typer.Exit(2)

    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Plataforma", p.name)
    t.add_row("Moneda", coin.upper())
    t.add_row("Algoritmo", target.algo)
    t.add_row("Stratum", f"{target.url}" + (" (TLS)" if target.tls else ""))
    t.add_row("Usuario", target.user)
    t.add_row("Password", target.password)
    console.print(Panel(t, title="Destino para tu minero", border_style="green"))
    if target.notes:
        console.print(f"[grey50]{target.notes}[/grey50]")

    if write_xmrig:
        from .engines.xmrig import build_config

        prof = Profile(name=f"{p.id}-{coin.lower()}", wallet=target.user, pool_url=target.url)
        cfg = build_config(
            target.user,
            target.url,
            coin="monero" if coin.upper() == "XMR" else "bitcoin",
            tls=target.tls,
        )
        cfg["pools"] = [stratum.xmrig_pool_entry(target, "monero" if coin.upper() == "XMR" else "bitcoin")]
        path = prof.dir() / "config.json"
        path.write_text(json.dumps(cfg, indent=2))
        console.print(f"[green]✓[/green] Config de XMRig escrito en {path} (no se ejecutó nada)")

    console.print(
        "[grey50]Para empezar a minar: usa estos datos en tu minero, o "
        f"`minerpro mine -c {coin.upper()} -w <tu_wallet>` si el usuario es tu wallet.[/grey50]"
    )


@cloud_app.command("providers")
def cloud_providers_cmd() -> None:
    """Catálogo de plataformas (incluye contratos de cloud mining con su riesgo)."""
    t = Table(title="Catálogo (ninguna es recomendación de inversión)", show_lines=True)
    t.add_column("Plataforma", style="bold cyan")
    t.add_column("Tipo")
    t.add_column("Monedas")
    t.add_column("Fee")
    t.add_column("Riesgo")
    t.add_column("URL")
    for p in provider_catalog.PROVIDERS:
        risk_style = {"bajo": "green", "medio": "yellow", "alto": "red", "ALTO": "bold red"}.get(p.risk, "white")
        t.add_row(p.name, p.kind, p.coins, p.fee, f"[{risk_style}]{p.risk}[/{risk_style}]", p.url)
    console.print(t)
    console.print("[grey50]MinerPro no compra contratos ni mueve fondos por su cuenta: tú confirmas cada acción.[/grey50]")


def _as_list(data, *keys) -> list:
    """Normaliza respuestas que a veces vienen como lista y a veces envueltas."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


@cloud_app.command("market")
def cloud_market(
    algo: str = typer.Option("SHA256", "--algo", "-a", help="Algoritmo (SHA256, RANDOMXMONERO...)"),
    top: int = typer.Option(8, "--top", help="Cuántas órdenes mostrar"),
) -> None:
    """Mercado de hashrate EN VIVO de NiceHash. No necesita claves."""
    nh = PublicNiceHash()
    try:
        info = nh.algorithm(algo)
        paying = nh.paying_by_algo().get(algo.upper(), {})
        orders = nh.active_orders(algo)
    except Exception as e:
        console.print(f"[red]No pude leer el mercado:[/red] {e}")
        raise typer.Exit(1)

    if info:
        t = Table.grid(padding=(0, 2))
        t.add_column(style="grey50", justify="right")
        t.add_column(style="bold")
        t.add_row("Algoritmo", f"{info.get('algorithm')} ({info.get('title', '')})")
        t.add_row("Habilitado", "sí" if info.get("enabled") else "no")
        t.add_row("Factor de mercado", f"{info.get('displayMarketFactor')} ({info.get('marketFactor')})")
        console.print(Panel(t, title=f"NiceHash · {algo.upper()} · datos en vivo", border_style="cyan"))

    if paying:
        console.print(f"[grey50]Pago actual (unidades de NiceHash): {paying.get('paying')}[/grey50]")
        console.print(
            f"[grey50]Velocidad total del algoritmo: {float(paying.get('speed', 0)):,.2f}[/grey50]"
        )

    live = [
        o
        for o in orders
        if int(o.get("rigsCount", 0) or 0) > 0 or float(o.get("acceptedCurrentSpeed", 0) or 0) > 0
    ]
    live = sorted(live or orders, key=lambda o: float(o.get("price", 0) or 0))[:top]
    t = Table(title="Órdenes activas con rigs (precio más bajo primero)")
    t.add_column("Precio", style="bold green", justify="right")
    t.add_column("Mercado")
    t.add_column("Velocidad límite", justify="right")
    t.add_column("Velocidad real", justify="right")
    t.add_column("Rigs", justify="right")
    for o in live:
        t.add_row(
            f"{float(o.get('price', 0)):.8f}",
            str(o.get("market", "")),
            f"{float(o.get('speedLimit', 0) or 0):.6f}",
            f"{float(o.get('acceptedCurrentSpeed', 0) or 0):.6f}",
            str(o.get("rigsCount", "")),
        )
    console.print(t)
    console.print(
        "[grey50]Precio y velocidad van en la unidad de mercado del algoritmo "
        "(ver 'Factor de mercado' arriba).[/grey50]"
    )


@cloud_app.command("rigs")
def cloud_rigs(platform: str = typer.Argument("nicehash", help="Plataforma")) -> None:
    """Tus rigs reportando a NiceHash (solo lectura)."""
    if platform != "nicehash":
        console.print("[red]Solo disponible para nicehash.[/red]")
        raise typer.Exit(2)
    client = NiceHashClient.from_store()
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
        raise typer.Exit(1)
    try:
        data = client.rigs()
    except Exception as e:
        console.print(f"[red]Error consultando rigs:[/red] {e}")
        raise typer.Exit(1)
    rigs = _as_list(data, "miningRigs", "rigs")
    t = Table(title="Rigs en NiceHash")
    t.add_column("Rig", style="bold cyan")
    t.add_column("Estado")
    t.add_column("Dispositivos", justify="right")
    t.add_column("Rentabilidad BTC/día", justify="right")
    for r in rigs:
        prof = r.get("profitability", {}) or {}
        t.add_row(
            str(r.get("name", "?")),
            str(r.get("minerStatus", r.get("status", "?"))),
            str(len(r.get("devices", []) or [])),
            f"{float(prof.get('btcPerDay', 0) or r.get('profitabilityBtc', 0) or 0):.8f}",
        )
    console.print(t if rigs else "[grey50]No hay rigs reportando.[/grey50]")


@cloud_app.command("orders")
def cloud_orders(
    algo: str = typer.Option("SHA256", "--algo", "-a"),
    platform: str = typer.Option("nicehash", "--platform"),
) -> None:
    """Tus órdenes de hashrate (solo lectura)."""
    if platform != "nicehash":
        console.print("[red]Solo disponible para nicehash.[/red]")
        raise typer.Exit(2)
    client = NiceHashClient.from_store()
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
        raise typer.Exit(1)
    try:
        data = client.my_orders(algo)
    except Exception as e:
        console.print(f"[red]Error consultando órdenes:[/red] {e}")
        raise typer.Exit(1)
    orders = _as_list(data, "orders", "list")
    t = Table(title=f"Mis órdenes · {algo.upper()}")
    t.add_column("ID", style="bold cyan")
    t.add_column("Precio", justify="right")
    t.add_column("Límite", justify="right")
    t.add_column("Disponible", justify="right")
    t.add_column("Estado")
    for o in orders:
        t.add_row(
            str(o.get("id", ""))[:8],
            f"{float(o.get('price', 0) or 0):.8f}",
            f"{float(o.get('limit', o.get('speedLimit', 0)) or 0):.6f}",
            f"{float(o.get('availableAmount', 0) or 0):.8f}",
            str(o.get("status", {}).get("code", o.get("status", ""))),
        )
    console.print(t if orders else "[grey50]Sin órdenes activas.[/grey50]")


@cloud_app.command("pool-add")
def cloud_pool_add(
    name: str = typer.Option(..., "--name", help="Nombre de la pool en NiceHash"),
    algo: str = typer.Option("SHA256", "--algo", "-a"),
    host: str = typer.Option(..., "--host", help="Host Stratum de tu pool"),
    port: int = typer.Option(..., "--port", help="Puerto Stratum"),
    username: str = typer.Option(..., "--username", help="Tu wallet/worker en esa pool"),
    password: str = typer.Option("x", "--password"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirma la escritura en tu cuenta"),
) -> None:
    """Registra una pool en NiceHash para apuntar hashrate comprado (requiere --confirm)."""
    if not confirm:
        console.print("[yellow]Falta --confirm.[/yellow] Esta acción escribe en tu cuenta de NiceHash.")
        raise typer.Exit(1)
    client = NiceHashClient.from_store(allow_write=True)
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
        raise typer.Exit(1)
    try:
        res = client.create_pool(name, algo.upper(), host, port, username, password)
    except NiceHashWriteDisabled as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creando la pool:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Pool creada: [bold]{res.get('id', res)}[/bold]")


@cloud_app.command("buy")
def cloud_buy(
    algo: str = typer.Option("SHA256", "--algo", "-a"),
    market: str = typer.Option("EU", "--market", help="EU, USA, EU_N, ASIA..."),
    price: float = typer.Option(..., "--price", help="Precio en BTC por unidad de velocidad"),
    amount: float = typer.Option(..., "--amount", help="BTC a gastar en la orden"),
    limit: float = typer.Option(..., "--limit", help="Velocidad máxima a pagar (límite)"),
    pool_id: str = typer.Option(..., "--pool-id", help="ID de pool en NiceHash (ver cloud pool-add)"),
    order_type: int = typer.Option(0, "--type", help="0 = estándar, 1 = fija"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirma el gasto de BTC"),
) -> None:
    """Compra hashrate en NiceHash (cloud mining real). Gasta BTC de tu cuenta."""
    if not confirm:
        console.print(
            Panel(
                f"Esto crea una orden de compra de hashrate:\n"
                f"  algoritmo {algo.upper()} · mercado {market}\n"
                f"  precio {price} BTC · gasto {amount} BTC · límite {limit}\n\n"
                "[yellow]Gasta BTC real de tu cuenta de NiceHash.[/yellow]\n"
                "Si estás seguro, repite con [bold]--confirm[/bold].",
                title="Compra de hashrate (no ejecutada)",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)
    client = NiceHashClient.from_store(allow_write=True)
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect nicehash")
        raise typer.Exit(1)
    try:
        order = client.create_order(
            market=market,
            algorithm=algo,
            price=price,
            limit=limit,
            amount=amount,
            pool_id=pool_id,
            order_type=order_type,
        )
    except NiceHashWriteDisabled as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creando la orden:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Orden creada: [bold]{order.get('id', order)}[/bold]")


@cloud_app.command("cancel")
def cloud_cancel(
    order_id: str = typer.Option(..., "--order-id"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Cancela una orden de hashrate en NiceHash."""
    if not confirm:
        console.print("[yellow]Falta --confirm.[/yellow] Repite con --confirm para cancelar la orden.")
        raise typer.Exit(1)
    client = NiceHashClient.from_store(allow_write=True)
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow]")
        raise typer.Exit(1)
    try:
        client.cancel_order(order_id)
    except NiceHashWriteDisabled as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error cancelando:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Orden {order_id[:8]} cancelada")


@cloud_app.command("refill")
def cloud_refill(
    order_id: str = typer.Option(..., "--order-id"),
    amount: float = typer.Option(..., "--amount", help="BTC a agregar"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Agrega BTC a una orden de hashrate existente."""
    if not confirm:
        console.print("[yellow]Falta --confirm.[/yellow] Esta acción gasta BTC de tu cuenta.")
        raise typer.Exit(1)
    client = NiceHashClient.from_store(allow_write=True)
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow]")
        raise typer.Exit(1)
    try:
        client.refill_order(order_id, amount)
    except NiceHashWriteDisabled as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error recargando:[/red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Orden {order_id[:8]} recargada con {amount} BTC")


@cloud_app.command("workers")
def cloud_workers(
    algo: str = typer.Option("sha256d", "--algo", "-a", help="Algoritmo del pool (sha256d, etc.)"),
    account: str = typer.Option(..., "--account", help="Tu cuenta de minería en Binance Pool"),
    page: int = typer.Option(1, "--page"),
) -> None:
    """Workers de tu cuenta de Binance Pool (solo lectura)."""
    client = BinanceClient.from_store()
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect binance")
        raise typer.Exit(1)
    try:
        data = client.workers(algo, account, page)
    except Exception as e:
        console.print(f"[red]Error consultando workers:[/red] {e}")
        raise typer.Exit(1)
    workers = _as_list(data, "workerDatas", "data")
    t = Table(title=f"Binance Pool · workers de {account}")
    t.add_column("Worker", style="bold cyan")
    t.add_column("Hashrate", justify="right")
    t.add_column("Último share", justify="right")
    t.add_column("Estado")
    for w in workers:
        t.add_row(
            str(w.get("workerName", "?")),
            str(w.get("hashRate", "0")),
            str(w.get("lastShareTime", "")),
            "activo" if w.get("status", 1) in (1, "1") else "inactivo",
        )
    console.print(t if workers else "[grey50]Sin workers para esa cuenta/algoritmo.[/grey50]")


@cloud_app.command("earnings")
def cloud_earnings(
    algo: str = typer.Option("sha256d", "--algo", "-a"),
    account: str = typer.Option(..., "--account"),
    coin: str = typer.Option("BTC", "--coin"),
) -> None:
    """Ganancias de tu cuenta de Binance Pool (solo lectura)."""
    client = BinanceClient.from_store()
    if client is None:
        console.print("[yellow]Sin credenciales.[/yellow] Usa: minerpro cloud connect binance")
        raise typer.Exit(1)
    try:
        data = client.earnings(algo, account, coin)
    except Exception as e:
        console.print(f"[red]Error consultando ganancias:[/red] {e}")
        raise typer.Exit(1)
    rows = _as_list(data, "accountProfits", "data")
    t = Table(title=f"Binance Pool · ganancias ({coin})")
    t.add_column("Inicio", style="bold")
    t.add_column("Tipo")
    t.add_column("Ganancia", justify="right")
    t.add_column("Hashrate", justify="right")
    for r in rows:
        t.add_row(
            str(r.get("time", "")),
            str(r.get("type", "")),
            str(r.get("profitAmount", r.get("amount", "0"))),
            str(r.get("hashRate", "0")),
        )
    console.print(t if rows else "[grey50]Sin registros de ganancias.[/grey50]")


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
    restart: bool = typer.Option(False, "--restart", help="Reiniciar el minero si se cae solo"),
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

    # Chequeos previos: mejor fallar aquí que descubrirlo mirando el log.
    binary = getattr(engine, "binary", None)
    checks = [
        preflight.check_binary(binary),
        preflight.check_port_free(port),
        preflight.check_pool(pool.url),
    ]
    for ch in checks:
        style = "green" if ch.ok else ("red" if ch.fatal else "yellow")
        console.print(f"  [{style}]{ch.mark}[/{style}] {ch.name}: {ch.detail}")
    can_continue, _ = preflight.run_all(checks)
    if not can_continue:
        console.print("[red]Hay un problema que impide minar.[/red]")
        raise typer.Exit(3)

    if run_state.current() is not None:
        console.print("[yellow]Ya hay un minero corriendo.[/yellow] Usa minerpro status o minerpro stop.")
        raise typer.Exit(4)

    engine.start()
    state = run_state.RunState(
        pid=os.getpid(),
        profile=prof.name,
        coin=c.symbol,
        pool=pool.url,
        wallet=wallet_addr,
        engine=engine.name,
        port=port,
        started_at=time.time(),
        log_path=str(getattr(engine, "_log_path", "")),
        binary=str(binary or ""),
    )
    run_state.save(state)

    stop_requested = {"value": False, "signal": False}
    previous_handler = signal.getsignal(signal.SIGINT)

    def on_interrupt(signum, frame):
        stop_requested["value"] = True
        stop_requested["signal"] = True
        engine.stop()

    signal.signal(signal.SIGINT, on_interrupt)

    def session() -> None:
        """Una corrida: espera la API y muestra el dashboard o los logs."""
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
                    stop_requested["value"] = True
                    break
                time.sleep(5)
        else:
            if seconds:
                import threading

                threading.Timer(seconds, on_interrupt, args=(0, None)).start()
            tui.run(engine, prof.name, pool, wallet_addr, console=console)

    try:
        while True:
            session()
            if stop_requested["value"] or not restart:
                break
            state.restarts += 1
            run_state.save(state)
            wait = min(30, 3 * state.restarts)
            console.print(f"[yellow]El minero se detuvo. Reinicio {state.restarts} en {wait}s.[/yellow]")
            time.sleep(wait)
            engine.start()
    except KeyboardInterrupt:
        stop_requested["value"] = True
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        engine.stop()
        run_state.clear()
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



# --------------------------------------------------------------------------- #
# Control del minero en curso (funciona desde otra terminal)
# --------------------------------------------------------------------------- #
def _read_local_api(port: int, timeout: float = 2.0) -> dict | None:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/1/summary", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


@app.command()
def status() -> None:
    """Qué está minando ahora mismo, con datos de la API local del minero."""
    st = run_state.current()
    if st is None:
        console.print("[yellow]No hay ningún minero corriendo.[/yellow]")
        console.print("[grey50]Arrancá uno con: minerpro mine -c XMR -w <tu_wallet>[/grey50]")
        raise typer.Exit(1)

    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Perfil", st.profile)
    t.add_row("Moneda", st.coin)
    t.add_row("Pool", st.pool)
    t.add_row("Motor", st.engine)
    t.add_row("PID", str(st.pid), )
    t.add_row("Uptime", tui.fmt_duration(st.uptime_seconds))
    if st.restarts:
        t.add_row("Reinicios", str(st.restarts))
    t.add_row("Log", st.log_path or "—")

    data = _read_local_api(st.port)
    if data:
        hr = (data.get("hashrate") or {}).get("total") or [0, 0, 0]
        res = data.get("results") or {}
        conn = data.get("connection") or {}
        t.add_row("Hashrate", tui.fmt_hashrate(float(hr[0] or 0)))
        t.add_row("Shares", f"{res.get('shares_good', 0)} ok / {res.get('shares_total', 0) - res.get('shares_good', 0)} rechazados")
        t.add_row("Conexión", str(conn.get("pool", "")) or "—")
    console.print(Panel(t, title="Minero en curso", border_style="green"))
    if not data:
        console.print(
            "[grey50]No pude leer la API local. Si es un minero externo (ASIC), es normal: "
            "revisá el log con minerpro logs -f[/grey50]"
        )


@app.command()
def logs(
    lines: int = typer.Option(40, "--lines", "-n", help="Cuántas líneas mostrar"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Seguir el log en vivo"),
) -> None:
    """Muestra el log del minero (el de la corrida actual o el último que hubo)."""
    st = run_state.load()
    path: Path | None = Path(st.log_path) if st and st.log_path else None
    if path is None or not path.exists():
        candidates = sorted(logs_dir().glob("*.log"), key=lambda q: q.stat().st_mtime, reverse=True)
        path = candidates[0] if candidates else None
    if path is None or not path.exists():
        console.print("[yellow]Todavía no hay logs.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[grey50]{path}[/grey50]")
    if not follow:
        with path.open("r", errors="replace") as f:
            for line in f.readlines()[-lines:]:
                _print_log_line(line.rstrip("\n"))
        return
    console.print("[grey50]Ctrl+C para salir[/grey50]")
    try:
        with path.open("r", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    _print_log_line(line.rstrip("\n"))
                else:
                    time.sleep(0.4)
    except KeyboardInterrupt:
        return


def _print_log_line(line: str) -> None:
    style = "grey62"
    low = line.lower()
    if "accepted" in low:
        style = "green"
    elif "rejected" in low or "error" in low:
        style = "red"
    elif "new job" in low or "use " in low:
        style = "cyan"
    console.print(line, style=style, highlight=False)


@app.command()
def stop() -> None:
    """Detiene el minero que está corriendo (parada limpia)."""
    st = run_state.current()
    if st is None:
        console.print("[yellow]No hay ningún minero corriendo.[/yellow]")
        raise typer.Exit(1)
    try:
        os.kill(st.pid, signal.SIGINT)
    except OSError as e:
        console.print(f"[red]No pude avisarle al proceso:[/red] {e}")
    for _ in range(40):
        if run_state.current() is None:
            console.print("[green]✓[/green] Minero detenido.")
            return
        time.sleep(0.25)
    console.print("[yellow]No se detuvo a tiempo; revisá el proceso.[/yellow]")
    raise typer.Exit(1)


# --------------------------------------------------------------------------- #
# Rentabilidad
# --------------------------------------------------------------------------- #
@app.command()
def estimate(
    coin: str = typer.Option("XMR", "--coin", "-c", help="Moneda a minar"),
    algo: str = typer.Option("RANDOMXMONERO", "--algo", "-a", help="Algoritmo en NiceHash"),
    speed: Optional[float] = typer.Option(None, "--speed", "-s", help="Velocidad a arrendar (unidades de mercado)"),
    days: float = typer.Option(1.0, "--days", "-d", help="Días de arriendo"),
    price: Optional[float] = typer.Option(None, "--price", help="Precio en BTC por unidad y día (por defecto, el mejor del mercado)"),
    fee: float = typer.Option(0.6, "--fee", help="Fee de la pool en porcentaje"),
    hashrate: Optional[float] = typer.Option(None, "--hashrate", help="H/s de tu propio equipo (modo local)"),
    watts: Optional[float] = typer.Option(None, "--watts", help="Consumo del equipo en watts (modo local)"),
    kwh: float = typer.Option(0.15, "--kwh", help="Precio del kWh en USD (modo local)"),
) -> None:
    """Cuánto costaría y cuánto se esperaría ganar, con datos en vivo."""
    price_data = market.fetch_prices()
    net = market.fetch_network()
    reward = net.block_reward

    if hashrate is not None:
        # Modo local: no se arrienda nada, se paga electricidad.
        if reward is None:
            console.print(f"[red]La fuente {net.source} no informa la recompensa de bloque.[/red]")
            raise typer.Exit(1)
        share = hashrate / net.hashrate_hps
        coins = share * reward * net.blocks_per_day * days * (1 - fee / 100.0)
        revenue = coins * price_data.coin_usd
        cost = 0.0
        if watts:
            cost = (watts / 1000.0) * 24.0 * days * kwh
        t = Table.grid(padding=(0, 2))
        t.add_column(style="grey50", justify="right")
        t.add_column(style="bold")
        t.add_row("Modo", "local (tu equipo)")
        t.add_row("Hashrate", market.format_hashrate(hashrate))
        t.add_row("Cuota de red", f"{share * 100:.5f}%")
        t.add_row(f"{coin} esperados", f"{coins:.6f}")
        t.add_row("Ingreso", f"${revenue:,.2f} USD")
        if watts:
            t.add_row("Electricidad", f"${cost:,.2f} USD ({watts:.0f} W a ${kwh:.3f}/kWh)")
            t.add_row("Neto", f"${revenue - cost:,.2f} USD")
        t.add_row("Datos", f"red: {net.source} · precio: {price_data.source}")
        console.print(Panel(t, title="Estimación de minado local", border_style="cyan"))
        console.print("[grey50]Es una estimación con datos reales, no una promesa.[/grey50]")
        return

    # Modo nube: se arrienda hashrate.
    if speed is None:
        console.print("[red]Falta --speed[/red] (unidades de mercado, por ejemplo GH/s) o usá --hashrate para modo local.")
        raise typer.Exit(2)
    units = market.nicehash_algorithm(algo)
    factor = float(units["marketFactor"])
    orders = 0
    chosen = price
    if chosen is None:
        chosen, orders = market.nicehash_best_price(algo)
    if reward is None:
        console.print(f"[red]La fuente {net.source} no informa la recompensa de bloque.[/red]")
        raise typer.Exit(1)

    est = market.estimate(speed, chosen, days, fee, factor, net, price_data, reward)
    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey50", justify="right")
    t.add_column(style="bold")
    t.add_row("Modo", "nube (hashrate arrendado)")
    t.add_row("Algoritmo", f"{algo.upper()} · unidad de mercado: {units.get('displayMarketFactor')}")
    t.add_row("Velocidad", f"{speed:g} unidades ({market.format_hashrate(est.speed_hps)})")
    t.add_row("Precio usado", f"{chosen:.8f} BTC por unidad y día" + (f" (mejor de {orders} órdenes)" if orders else ""))
    t.add_row("Días", f"{days:g}")
    t.add_row("Cuota de red", f"{est.network_share * 100:.5f}%")
    t.add_row(f"{coin} esperados", f"{est.coins_mined:.6f}")
    t.add_row("Costo", f"${est.cost_usd:,.2f} USD ({est.cost_btc:.8f} BTC)")
    t.add_row("Ingreso", f"${est.revenue_usd:,.2f} USD")
    console.print(Panel(t, title="Estimación de arriendo", border_style="cyan"))
    verdict = "rentable" if est.profitable else "a pérdida"
    style = "green" if est.profitable else "red"
    console.print(
        f"[bold]Neto:[/bold] [{style}]${est.net_usd:,.2f} USD ({verdict})[/{style}] · "
        f"precio de equilibrio {est.break_even_btc_per_unit_day:.8f} BTC"
    )
    console.print(
        f"[grey50]Datos: red {est.network_source} · precios {est.price_source} · "
        "la dificultad y el precio cambian, y la suerte del pool también.[/grey50]"
    )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
