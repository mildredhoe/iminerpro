# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Validación de direcciones Bitcoin (base58check y bech32/bech32m)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_INDEX = {c: i for i, c in enumerate(_BECH32_CHARSET)}

_BECH32_CONST = 1
_BECH32M_CONST = 0x2BC830A3


def _b58check_decode(s: str) -> bytes:
    num = 0
    for ch in s:
        digit = _B58_INDEX.get(ch)
        if digit is None:
            raise ValueError(f"carácter base58 inválido: {ch!r}")
        num = num * 58 + digit
    size = (len(s) * 733) // 1000 + 1
    raw = num.to_bytes(size, "big")
    # quitar ceros de relleno a la izquierda que aporta el cálculo por entero
    while len(raw) > 25 and raw[0] == 0:
        raw = raw[1:]
    return raw


def _sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def validate_base58_btc(address: str) -> tuple[bool, str]:
    if len(address) < 26 or len(address) > 35:
        return False, f"largo inválido ({len(address)})"
    try:
        raw = _b58check_decode(address)
    except ValueError as e:
        return False, str(e)
    if len(raw) != 25:
        return False, f"bytes inválidos ({len(raw)}, se esperan 25)"
    payload, checksum = raw[:21], raw[21:]
    if _sha256d(payload)[:4] != checksum:
        return False, "checksum inválido"
    version = payload[0]
    kind = {0x00: "P2PKH", 0x05: "P2SH"}.get(version)
    if kind is None:
        return False, f"versión desconocida ({version})"
    return True, kind


def _bech32_polymod(values: list[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= generator[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def validate_bech32_btc(address: str) -> tuple[bool, str]:
    if not (address.startswith("bc1") or address.startswith("BC1")):
        return False, "no empieza con bc1"
    if address.lower() != address and address.upper() != address:
        return False, "mezcla mayúsculas y minúsculas"
    addr = address.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        return False, "estructura bech32 inválida"
    hrp, data_part = addr[:pos], addr[pos + 1 :]
    if hrp != "bc":
        return False, f"red no bitcoin ({hrp})"
    try:
        data = [_BECH32_INDEX[c] for c in data_part]
    except KeyError as e:
        return False, f"carácter bech32 inválido: {e}"
    if _bech32_polymod(_bech32_hrp_expand(hrp) + data) == _BECH32_CONST:
        spec = "bech32"
    elif _bech32_polymod(_bech32_hrp_expand(hrp) + data) == _BECH32M_CONST:
        spec = "bech32m"
    else:
        return False, "checksum bech32 inválido"
    witver = data[0]
    if witver == 0 and spec != "bech32":
        return False, "witness v0 debe usar bech32"
    if witver != 0 and spec != "bech32m":
        return False, "witness v1+ debe usar bech32m"
    program = data[1:-6]
    if not (2 <= len(program) <= 40):
        return False, "longitud de programa inválida"
    if witver == 0 and len(program) not in (20, 32):
        return False, "witness v0 requiere 20 o 32 bytes"
    return True, f"SegWit v{witver}"


@dataclass
class BtcCheck:
    ok: bool
    reason: str = ""
    kind: str = ""
    address: str = ""


def validate_btc_address(address: str) -> BtcCheck:
    addr = address.strip()
    if not addr:
        return BtcCheck(False, "vacía", address=addr)
    if addr.lower().startswith("bc1"):
        ok, info = validate_bech32_btc(addr)
        return BtcCheck(ok, info if not ok else "válida", info, addr)
    if addr[0] in "13":
        ok, info = validate_base58_btc(addr)
        return BtcCheck(ok, info if not ok else "válida", info, addr)
    return BtcCheck(False, "formato no reconocido (se espera 1, 3 o bc1)", address=addr)
