"""NiceHash — marketplace de hashrate (nube).

Autenticación (API v2), según el demo oficial nicehash/rest-clients-demo:
  message  = key \\0 xtime \\0 xnonce \\0 \\0 org_id \\0 \\0 method \\0 path \\0 query [\\0 body]
  X-Auth   = key + ":" + HMAC_SHA256(secret, message)
  headers  = X-Time, X-Nonce, X-Auth, X-Organization-Id, X-Request-Id

Este módulo SOLO lee (cuentas, rigs, órdenes). No compra ni cancela nada.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .base import CredentialField, Platform, StratumEndpoint, register

BASE_URL = "https://api2.nicehash.com"
KEY_ID = "nicehash_api_key"
KEY_SECRET = "nicehash_api_secret"
KEY_ORG = "nicehash_org_id"


def sign_message(
    key: str, xtime: str, xnonce: str, org_id: str, method: str, path: str, query: str = "", body: str = ""
) -> bytes:
    """Construye el mensaje exacto que se firma (mismo layout que el demo oficial)."""
    message = bytearray(key, "utf-8")
    for part in (xtime, xnonce, "", org_id, "", method, path, query):
        message += b"\x00"
        message += bytearray(part, "utf-8")
    if body:
        message += b"\x00"
        message += bytearray(body, "utf-8")
    return bytes(message)


def signature(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


@dataclass
class NiceHashClient:
    key: str
    secret: str
    org_id: str = ""

    @classmethod
    def from_store(cls) -> "NiceHashClient | None":
        from .. import secrets

        key = secrets.resolve(KEY_ID, "MINERPRO_NICEHASH_KEY")
        sec = secrets.resolve(KEY_SECRET, "MINERPRO_NICEHASH_SECRET")
        if not key or not sec:
            return None
        return cls(key, sec, secrets.resolve(KEY_ORG, "MINERPRO_NICEHASH_ORG") or "")

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = urlencode(sorted(params.items())) if params else ""
        body_json = json.dumps(body) if body else ""
        xtime = str(int(time.time() * 1000))
        xnonce = str(uuid.uuid4())
        msg = sign_message(self.key, xtime, xnonce, self.org_id, method.upper(), path, query, body_json)
        headers = {
            "X-Time": xtime,
            "X-Nonce": xnonce,
            "X-Auth": f"{self.key}:{signature(self.secret, msg)}",
            "X-Organization-Id": self.org_id,
            "X-Request-Id": str(uuid.uuid4()),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
        r = httpx.request(method, url, headers=headers, content=body_json or None, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"NiceHash {r.status_code}: {r.text[:300]}")
        return r.json()

    # -- solo lectura -------------------------------------------------------- #
    def accounts(self) -> dict:
        return self.request("GET", "/main/api/v2/accounting/accounts2/")

    def rigs(self) -> dict:
        return self.request("GET", "/main/api/v2/mining/rigs2")

    def my_orders(self, algorithm: str = "SHA256", limit: int = 20) -> dict:
        ts = int(time.time() * 1000)
        return self.request(
            "GET",
            "/main/api/v2/hashpower/myOrders",
            {"algorithm": algorithm, "limit": limit, "ts": ts, "op": "LT"},
        )

    def pools(self) -> dict:
        return self.request("GET", "/main/api/v2/pools/")

    def markets(self) -> dict:
        return self.request("GET", "/main/api/v2/mining/markets/")


NICEHASH = register(
    Platform(
        id="nicehash",
        name="NiceHash",
        kind="marketplace de hashrate (nube)",
        coins=["BTC", "XMR"],
        url="https://www.nicehash.com",
        keys_url="https://www.nicehash.com/my/settings/keys",
        key_steps=[
            "Crea una cuenta en nicehash.com y verifica tu correo.",
            "Entra a Mi cuenta → Settings → API Keys (el enlace de abajo).",
            "Pulsa 'Create new API key' y ponle un nombre (ej: MinerPro).",
            "Marca SOLO permisos de lectura: 'Mining' (ver rigs) y 'Wallet' (ver balance).",
            "Copia el API Key y el API Secret (el secret se muestra una sola vez).",
            "Copia también el 'Organization ID' que aparece arriba del botón de crear.",
        ],
        api_permissions=[
            "Mining: lectura (rigs y hashrate)",
            "Wallet: lectura (balance y pagos)",
            "NO habilitar: Withdrawal, Exchange ni permisos de escritura",
        ],
        warnings=[
            "Nunca habilites retiros (Withdrawal) en una API key que uses aquí.",
            "Guarda el secret al momento de crearlo: no se vuelve a mostrar.",
        ],
        fields=[
            CredentialField("nicehash_api_key", "MINERPRO_NICEHASH_KEY", "API Key", secret=True),
            CredentialField("nicehash_api_secret", "MINERPRO_NICEHASH_SECRET", "API Secret", secret=True),
            CredentialField(
                "nicehash_org_id",
                "MINERPRO_NICEHASH_ORG",
                "Organization ID",
                secret=False,
                help="Aparece sobre el botón 'Create new API key'",
            ),
        ],
        stratum=[
            StratumEndpoint(
                coin="XMR",
                algo="RandomX (randomxmonero)",
                host="randomxmonero.auto.nicehash.com",
                port=9200,
                tls_port=443,
                username_template="{wallet}",
                notes=(
                    "Apuntas XMRig aquí y NiceHash paga en BTC. Confirma el host exacto en "
                    "https://www.nicehash.com/stratum-generator"
                ),
            ),
            StratumEndpoint(
                coin="BTC",
                algo="SHA-256 (sha256asicboost, solo ASIC)",
                host="sha256asicboost.auto.nicehash.com",
                port=9200,
                tls_port=443,
                username_template="{wallet}",
                notes="Requiere ASIC; un CPU no produce nada rentable aquí.",
            ),
        ],
        notes=(
            "Como 'nube' aquí funciona al revés que un contrato: tú pones el hardware "
            "(o apuntas tu minero) y NiceHash te compra el hashrate. La API sirve para mirar."
        ),
    )
)
