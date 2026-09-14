"""Validación y utilidades de wallets.

Para Monero se implementa la verificación completa de checksum CryptoNote:
la dirección es base58(network_byte || spend_pubkey(32) || view_pubkey(32) || checksum(4))
donde checksum = keccak_256(payload)[:4].
"""

from __future__ import annotations

from dataclasses import dataclass

# Alfabeto base58 de CryptoNote
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}

# Redes Monero: byte de red -> nombre
MONERO_NETWORKS = {
    18: "mainnet",         # 0x12
    19: "mainnet subaddr", # 0x13
    42: "testnet",         # 0x2a
    53: "stagenet",        # 0x35
    24: "mainnet integrated",
}


# --------------------------------------------------------------------------- #
# Keccak-256 (padding 0x01, como CryptoNote; no es SHA3-256)
# --------------------------------------------------------------------------- #
_KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_KECCAK_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rotl(x: int, n: int) -> int:
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(state: list[int]) -> None:
    for rnd in range(24):
        # theta
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        # rho + pi
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(state[x + 5 * y], _KECCAK_ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ (
                    (~b[(x + 1) % 5 + 5 * y] & _MASK) & b[(x + 2) % 5 + 5 * y]
                )
        # iota
        state[0] ^= _KECCAK_RC[rnd]


def keccak_256(data: bytes) -> bytes:
    """Keccak-256 con padding 0x01 (usado por CryptoNote/Monero)."""
    rate = 136  # 1088 bits
    state = [0] * 25
    # padding
    pad_len = rate - (len(data) % rate)
    if pad_len == 1:
        padded = data + b"\x81"
    else:
        padded = data + b"\x01" + b"\x00" * (pad_len - 2) + b"\x80"
    for off in range(0, len(padded), rate):
        block = padded[off : off + rate]
        for i in range(0, rate, 8):
            state[i // 8] ^= int.from_bytes(block[i : i + 8], "little")
        _keccak_f(state)
    out = b""
    for i in range(25):
        out += state[i].to_bytes(8, "little")
    return out[:32]


# --------------------------------------------------------------------------- #
# Base58 CryptoNote (bloques de 8 bytes <-> 11 caracteres)
# --------------------------------------------------------------------------- #
_ENC_BLOCK_SIZES = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11}
_DEC_BLOCK_SIZES = {v: k for k, v in _ENC_BLOCK_SIZES.items()}
_FULL_ENCODED_BLOCK = 11


def _decode_block(block: str) -> bytes:
    size = _DEC_BLOCK_SIZES.get(len(block))
    if size is None:
        raise ValueError(f"largo de bloque base58 inválido ({len(block)})")
    num = 0
    order = 1
    for ch in reversed(block):
        digit = _B58_INDEX.get(ch)
        if digit is None:
            raise ValueError(f"carácter no válido en base58: {ch!r}")
        num += order * digit
        order *= 58
    if size < 8 and (1 << (8 * size)) <= num:
        raise ValueError("bloque base58 fuera de rango")
    return num.to_bytes(size, "big")


def b58_decode(s: str) -> bytes:
    if not s:
        return b""
    full, rem = divmod(len(s), _FULL_ENCODED_BLOCK)
    if rem and rem not in _DEC_BLOCK_SIZES:
        raise ValueError(f"largo base58 inválido ({len(s)})")
    out = bytearray()
    for i in range(full):
        out += _decode_block(s[i * _FULL_ENCODED_BLOCK : (i + 1) * _FULL_ENCODED_BLOCK])
    if rem:
        out += _decode_block(s[full * _FULL_ENCODED_BLOCK :])
    return bytes(out)


@dataclass
class WalletCheck:
    ok: bool
    reason: str
    network: str | None = None
    address: str = ""


def validate_monero_address(address: str) -> WalletCheck:
    """Valida una dirección Monero completa (longitud + base58 + checksum)."""
    addr = address.strip()
    if not addr:
        return WalletCheck(False, "vacía", address=addr)
    if len(addr) != 95:
        return WalletCheck(False, f"largo inválido ({len(addr)}, se esperan 95)", address=addr)
    try:
        raw = b58_decode(addr)
    except ValueError as e:
        return WalletCheck(False, str(e), address=addr)
    if len(raw) != 69:
        return WalletCheck(False, f"bytes decodificados inválidos ({len(raw)}, se esperan 69)", address=addr)
    payload, checksum = raw[:65], raw[65:]
    expected = keccak_256(payload)[:4]
    if checksum != expected:
        return WalletCheck(False, "checksum inválido (dirección mal escrita)", address=addr)
    net_byte = payload[0]
    net = MONERO_NETWORKS.get(net_byte)
    if net is None:
        return WalletCheck(False, f"byte de red desconocido ({net_byte})", address=addr)
    return WalletCheck(True, "válida", network=net, address=addr)


def looks_like_monero(address: str) -> bool:
    return validate_monero_address(address).ok
