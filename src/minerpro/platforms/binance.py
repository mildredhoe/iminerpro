"""Binance Pool / Binance Cloud Mining — API firmada (HMAC-SHA256).

Firma (estilo Binance): se firma el query string exacto con HMAC-SHA256(secret) y
se agrega como `&signature=...`; la API key va en el header `X-MBX-APIKEY`.

Endpoints usados (todos GET, solo lectura):
  /sapi/v1/mining/pub/coinList
  /sapi/v1/mining/pub/algoList
  /sapi/v1/mining/statistics/user/status
  /sapi/v1/mining/statistics/user/list
  /sapi/v1/mining/worker/list
  /sapi/v1/mining/worker/detail
  /sapi/v1/mining/payment/list                         (ganancias de pool)
  /sapi/v1/asset/ledger-transfer/cloud-mining/queryByPage   (cloud mining)

No hay operaciones de escritura: MinerPro no retira, no compra y no mueve fondos.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .base import CredentialField, Platform, StratumEndpoint, register

BASE_URL = "https://api.binance.com"
KEY_ID = "binance_api_key"
KEY_SECRET = "binance_api_secret"


def sign_query(params: dict, secret: str) -> str:
    """Devuelve el query string con la firma HMAC-SHA256 agregada."""
    query = urlencode(params)
    digest = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return f"{query}&signature={digest}"


@dataclass
class BinanceClient:
    key: str
    secret: str
    recv_window: int = 5000

    @classmethod
    def from_store(cls) -> "BinanceClient | None":
        from .. import secrets

        key = secrets.resolve(KEY_ID, "MINERPRO_BINANCE_KEY")
        sec = secrets.resolve(KEY_SECRET, "MINERPRO_BINANCE_SECRET")
        if not key or not sec:
            return None
        return cls(key, sec)

    def _get(self, path: str, params: dict | None = None) -> dict:
        full = dict(params or {})
        full["timestamp"] = int(time.time() * 1000)
        full["recvWindow"] = self.recv_window
        query = sign_query(full, self.secret)
        r = httpx.get(
            f"{BASE_URL}{path}?{query}",
            headers={"X-MBX-APIKEY": self.key, "Accept": "application/json"},
            timeout=20,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Binance {r.status_code}: {r.text[:300]}")
        return r.json()

    # -- minería (pool) ------------------------------------------------------ #
    def coins(self) -> dict:
        return self._get("/sapi/v1/mining/pub/coinList")

    def algorithms(self) -> dict:
        return self._get("/sapi/v1/mining/pub/algoList")

    def status(self) -> dict:
        return self._get("/sapi/v1/mining/statistics/user/status")

    def accounts(self) -> dict:
        return self._get("/sapi/v1/mining/statistics/user/list")

    def workers(self, algo: str, user_name: str, page: int = 1) -> dict:
        return self._get(
            "/sapi/v1/mining/worker/list",
            {"algo": algo, "userName": user_name, "pageIndex": page, "sort": 0, "sortColumn": 0},
        )

    def worker_detail(self, algo: str, user_name: str, worker_name: str) -> dict:
        return self._get(
            "/sapi/v1/mining/worker/detail",
            {"algo": algo, "userName": user_name, "workerName": worker_name},
        )

    def earnings(self, algo: str, user_name: str, coin: str = "BTC", page_size: int = 20) -> dict:
        return self._get(
            "/sapi/v1/mining/payment/list",
            {"algo": algo, "userName": user_name, "coin": coin, "pageIndex": 1, "pageSize": page_size},
        )

    # -- cloud mining -------------------------------------------------------- #
    def cloud_mining_history(self, days: int = 30, size: int = 100) -> dict:
        end = int(time.time() * 1000)
        start = end - days * 24 * 3600 * 1000
        return self._get(
            "/sapi/v1/asset/ledger-transfer/cloud-mining/queryByPage",
            {"startTime": start, "endTime": end, "current": 1, "size": size},
        )


BINANCE = register(
    Platform(
        id="binance",
        name="Binance Pool / Cloud Mining",
        kind="exchange + pool + cloud mining",
        coins=["BTC"],
        url="https://www.binance.com",
        keys_url="https://www.binance.com/en/my/settings/api-management",
        key_steps=[
            "Inicia sesión en Binance y completa la verificación si te la pide.",
            "Ve a Perfil → Gestión de API (enlace de abajo) → 'Crear API'.",
            "Elige 'Generada por el sistema' y ponle una etiqueta (ej: MinerPro).",
            "Verifica con el código de tu app de autenticación (2FA).",
            "En la API recién creada habilita SOLO 'Enable Reading' (lectura).",
            "En 'Restricciones de IP' agrega tu IP pública (recomendado).",
            "Copia la API Key y el Secret Key (el secret se muestra una vez).",
        ],
        api_permissions=[
            "Enable Reading (lectura): obligatorio para consultar pool y cloud mining",
            "Restricción de IP: agrega tu IP pública",
            "NO habilitar: retiros (Withdrawals) ni Spot/Futures trading",
        ],
        warnings=[
            "Nunca habilites retiros en la API key. MinerPro solo lee.",
            "Binance Pool no mina Monero (XMR): para XMR usa NiceHash o una pool XMR.",
        ],
        fields=[
            CredentialField("binance_api_key", "MINERPRO_BINANCE_KEY", "API Key", secret=True),
            CredentialField("binance_api_secret", "MINERPRO_BINANCE_SECRET", "Secret Key", secret=True),
        ],
        stratum=[
            StratumEndpoint(
                coin="BTC",
                algo="SHA-256 (ASIC)",
                host="sha256.poolbinance.com",
                port=8888,
                tls_port=443,
                username_template="{account}.{worker}",
                notes=(
                    "El usuario es 'nombre de tu cuenta de minería'.'nombre del worker' "
                    "(ej: MiningBTC.rig1). Respaldo en el puerto 443."
                ),
            ),
        ],
        notes=(
            "La API de Binance cubre tres cosas: tu cuenta de pool (workers y ganancias), "
            "el historial de cloud mining y la lista de monedas/algoritmos soportados."
        ),
    )
)
