"""Plataformas conectables (NiceHash, Binance Pool, ...)."""

from . import binance, nicehash  # noqa: F401  (registran sus plataformas al importar)
from .base import Platform, all_platforms, get, register  # noqa: F401
