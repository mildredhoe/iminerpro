"""Cliente de NiceHash API v2 (solo lectura). Firma HMAC-SHA256.

Docs: https://www.nicehash.com/docs/  (X-Auth = key:signature:nonce)
No realiza compras ni cambios: solo consulta cuentas, rigs y mercado.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

BASE_URL = "https://api2.nicehash.com"
KEY_ID = "nicehash_api_key"
KEY_SECRET = "nicehash_api_secret"
KEY_ORG = "nicehash_org_id"


def _sign(secret: str, api_key: str, nonce: str, method: str, path: str, query: str, body: str) -> str:
    message = (
        f"{api_key}\x00{nonce}\x00{method}\x00{path}\x00{query}\x00{body}"
    )
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def auth_header(api_key: str, secret: str, method: str, path: str, query: str = "", body: str = "") -> str:
    nonce = str(int(time.time() * 1000)) + "-" + hashlib.sha256(f"{api_key}{time.time_ns()}".encode()).hexdigest()[:8]
    sig = _sign(secret, api_key, nonce, method, path, query, body)
    return f"{api_key}:{sig}:{nonce}"


@dataclass
class NiceHashClient:
    api_key: str
    secret: str
    org_id: str | None = None

    @classmethod
    def from_store(cls) -> "NiceHashClient | None":
        from .. import secrets

        key = secrets.load(KEY_ID)
        sec = secrets.load(KEY_SECRET)
        if not key or not sec:
            return None
        return cls(key, sec, secrets.load(KEY_ORG))

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = urlencode(sorted(params.items())) if params else ""
        raw_body = json.dumps(body) if body else ""
        headers = {
            "X-Auth": auth_header(self.api_key, self.secret, method, path, query, raw_body),
            "X-Request-Id": hashlib.sha256(f"{path}{time.time_ns()}".encode()).hexdigest()[:16],
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.org_id:
            headers["X-Organization-Id"] = self.org_id
        url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
        r = httpx.request(method, url, headers=headers, content=raw_body or None, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"NiceHash {r.status_code}: {r.text[:300]}")
        return r.json()

    # -- consultas de solo lectura ----------------------------------------- #
    def accounts(self) -> dict:
        return self.request("GET", "/main/api/v2/accounting/accounts")

    def rigs(self) -> dict:
        return self.request("GET", "/main/api/v2/mining/rigs2")

    def my_orders(self, limit: int = 20) -> dict:
        return self.request(
            "GET",
            "/main/api/v2/hashpower/myOrders",
            {"limit": limit, "ts": int(time.time() * 1000)},
        )
