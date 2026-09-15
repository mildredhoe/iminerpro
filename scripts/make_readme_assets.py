#!/usr/bin/env python3
"""Genera los SVG del README a partir de la salida REAL de los comandos.

Uso:
    python scripts/make_readme_assets.py

Escribe assets/terminal-*.svg. Nada se inventa:
  · `minerpro demo mine|doctor` → interfaz con datos de EJEMPLO (marcados como DEMO).
  · `minerpro cloud market`     → mercado EN VIVO de NiceHash (si hay red).

Los comandos se ejecutan con NO_COLOR=1 para que el SVG controle los colores.
"""

from __future__ import annotations

import html
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

CHAR_W = 8.4
LINE_H = 20
PAD_X = 22
PAD_TOP = 58
PAD_BOTTOM = 22
TITLE_H = 40
COLUMNS = 100

CARDS = [
    ("terminal-mine.svg", "minerpro mine · dashboard en vivo", ["minerpro", "demo", "mine", "--width", str(COLUMNS), "--no-notice"]),
    ("terminal-market.svg", "minerpro cloud market · NiceHash en vivo", ["minerpro", "cloud", "market", "--algo", "SHA256", "--top", "6"]),
    ("terminal-doctor.svg", "minerpro doctor", ["minerpro", "demo", "doctor", "--width", str(COLUMNS), "--no-notice"]),
]


def run(cmd: list[str]) -> str | None:
    env = dict(os.environ)
    env.update({"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": str(COLUMNS)})
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ! no pude ejecutar {' '.join(cmd)}: {exc}")
        return None
    if proc.returncode != 0:
        print(f"  ! {' '.join(cmd)} falló (rc={proc.returncode}); se omite")
        return None
    return (proc.stdout or proc.stderr).rstrip("\n")


def color_for(line: str) -> str:
    if "✓" in line:
        return "#50fa7b"
    if "✗" in line:
        return "#ff5555"
    if line.strip().startswith(("⚠", "!", "·")):
        return "#8be9fd"
    if "│" in line or line.startswith(("┌", "└", "├", "┏", "┗", "┡", "┃")):
        return "#c8c8c8"
    return "#e6e6e6"


def build_svg(title: str, body: str) -> str:
    lines = body.splitlines() or [""]
    width_chars = max(len(line) for line in lines)
    width = int(PAD_X * 2 + width_chars * CHAR_W) + 4
    height = PAD_TOP + len(lines) * LINE_H + PAD_BOTTOM

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, '
        f'Menlo, Consolas, monospace">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0%" stop-color="#111214"/><stop offset="100%" stop-color="#0b0c0d"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" '
        'fill="url(#bg)" stroke="#26282c"/>',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{TITLE_H}" rx="12" fill="#16181b"/>',
        f'<rect x="0.5" y="{TITLE_H - 12}" width="{width - 1}" height="12" fill="#16181b"/>',
        f'<line x1="0" y1="{TITLE_H}" x2="{width}" y2="{TITLE_H}" stroke="#26282c"/>',
        '<circle cx="24" cy="20" r="6" fill="#ff5f57"/>',
        '<circle cx="46" cy="20" r="6" fill="#febc2e"/>',
        '<circle cx="68" cy="20" r="6" fill="#28c840"/>',
        f'<text x="{width / 2}" y="25" fill="#9aa0a6" font-size="13" text-anchor="middle">'
        f"{html.escape(title)}</text>",
    ]
    for i, line in enumerate(lines):
        y = PAD_TOP + i * LINE_H
        parts.append(
            f'<text x="{PAD_X}" y="{y}" fill="{color_for(line)}" font-size="13" '
            f'xml:space="preserve">{html.escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    for filename, title, cmd in CARDS:
        body = run(cmd)
        if body is None:
            continue
        out = ASSETS / filename
        out.write_text(build_svg(title, body))
        print(f"escrito {out.relative_to(ROOT)}  ({len(body.splitlines())} líneas)")


if __name__ == "__main__":
    main()
