"""NiceHash — marketplace de hashrate (nube), API v2.

Autenticación (según el demo oficial nicehash/rest-clients-demo):
  message  = key \\0 xtime \\0 xnonce \\0 \\0 org_id \\0 \\0 method \\0 path \\0 query [\\0 body]
  X-Auth   = key + ":" + HMAC_SHA256(secret, message)
  headers  = X-Time, X-Nonce, X-Auth, X-Organization-Id, X-Request-Id

MinerPro usa DOS clientes:

* `PublicNiceHash`  → mercado en vivo, sin claves (markets, algorithms, orderbook,
  simplemultialgo, buy info). Es lo que usa `minerpro cloud market`.
* `NiceHashClient`  → cuenta privada con firma HMAC. Por defecto `allow_write=False`
  (solo lectura: balances, rigs, órdenes, pools). Para crear/comprar/cancelar órdenes
  hay que pasar `allow_write=True`, y el CLI además exige `--confirm`.
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


# --------------------------------------------------------------------------- #
# Firma
# --------------------------------------------------------------------------- #
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


class NiceHashWriteDisabled(PermissionError):
    """Se intentó una acción que mueve fondos sin habilitar escritura."""


# --------------------------------------------------------------------------- #
# Cliente público (sin claves)
# --------------------------------------------------------------------------- #
def public_get(path: str, params: dict | None = None, timeout: float = 20.0) -> dict | list:
    query = urlencode(sorted(params.items())) if params else ""
    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    r = httpx.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"NiceHash {r.status_code}: {r.text[:300]}")
    return r.json()


@dataclass
class PublicNiceHash:
    """Mercado en vivo de NiceHash. No requiere API keys."""

    def markets(self) -> list:
        return public_get("/main/api/v2/mining/markets/")

    def algorithms(self) -> list:
        data = public_get("/main/api/v2/mining/algorithms/")
        return data.get("miningAlgorithms", [])

    def algorithm(self, algo: str) -> dict | None:
        algo = algo.upper()
        for item in self.algorithms():
            if item.get("algorithm", "").upper() == algo:
                return item
        return None

    def multialgo_info(self) -> list:
        data = public_get("/main/api/v2/public/simplemultialgo/info/")
        return data.get("miningAlgorithms", [])

    def paying_by_algo(self) -> dict[str, dict]:
        out = {}
        for item in self.multialgo_info():
            out[item["algorithm"].upper()] = {
                "title": item.get("title", item["algorithm"]),
                "paying": float(item.get("paying", 0) or 0),
                "speed": float(item.get("speed", 0) or 0),
            }
        return out

    def buy_info(self) -> list:
        data = public_get("/main/api/v2/public/buy/info/")
        return data.get("miningAlgorithms", [])

    def active_orders(self, algo: str) -> list:
        data = public_get("/main/api/v2/public/orders/active2/", {"algorithm": algo.upper()})
        return data.get("list", [])

    def best_price(self, algo: str) -> float | None:
        orders = self.active_orders(algo)
        prices = [float(o.get("price", 0) or 0) for o in orders if o.get("price")]
        return min(prices) if prices else None


# --------------------------------------------------------------------------- #
# Cliente privado
# --------------------------------------------------------------------------- #
@dataclass
class NiceHashClient:
    key: str
    secret: str
    org_id: str = ""
    allow_write: bool = False

    @classmethod
    def from_store(cls, allow_write: bool = False) -> "NiceHashClient | None":
        from .. import secrets

        key = secrets.resolve(KEY_ID, "MINERPRO_NICEHASH_KEY")
        sec = secrets.resolve(KEY_SECRET, "MINERPRO_NICEHASH_SECRET")
        if not key or not sec:
            return None
        return cls(key, sec, secrets.resolve(KEY_ORG, "MINERPRO_NICEHASH_ORG") or "", allow_write)

    def _require_write(self) -> None:
        if not self.allow_write:
            raise NiceHashWriteDisabled(
                "Esta acción mueve fondos y la escritura está desactivada. "
                "Se habilita explícitamente con allow_write=True y `--confirm` en el CLI."
            )

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

    # -- lectura ------------------------------------------------------------- #
    def accounts(self) -> dict:
        return self.request("GET", "/main/api/v2/accounting/accounts2/")

    def rigs(self) -> dict:
        return self.request("GET", "/main/api/v2/mining/rigs2")

    def my_orders(self, algorithm: str = "SHA256", limit: int = 20) -> dict:
        return self.request(
            "GET",
            "/main/api/v2/hashpower/myOrders",
            {"algorithm": algorithm, "limit": limit, "ts": int(time.time() * 1000), "op": "LT"},
        )

    def pools(self) -> dict:
        return self.request("GET", "/main/api/v2/pools/")

    def markets(self) -> list:
        return self.request("GET", "/main/api/v2/mining/markets/")

    def algorithms(self) -> list:
        return self.request("GET", "/main/api/v2/mining/algorithms/").get("miningAlgorithms", [])

    def orderbook(self, algorithm: str) -> list:
        return self.request("GET", "/main/api/v2/hashpower/orderBook/", {"algorithm": algorithm})

    # -- acciones (mueven fondos) ------------------------------------------- #
    def create_pool(
        self, name: str, algorithm: str, host: str, port: int, username: str, password: str = "x"
    ) -> dict:
        self._require_write()
        return self.request(
            "POST",
            "/main/api/v2/pool/",
            body={
                "name": name,
                "algorithm": algorithm,
                "stratumHostname": host,
                "stratumPort": port,
                "username": username,
                "password": password,
            },
        )

    def create_order(
        self,
        *,
        market: str,
        algorithm: str,
        price: float,
        limit: float,
        amount: float,
        pool_id: str,
        order_type: int = 0,
    ) -> dict:
        """Crea una orden de compra de hashrate (gasta BTC de tu cuenta)."""
        self._require_write()
        algo = None
        for item in self.algorithms():
            if item.get("algorithm", "").upper() == algorithm.upper():
                algo = item
                break
        if algo is None:
            raise RuntimeError(f"algoritmo desconocido en NiceHash: {algorithm}")
        return self.request(
            "POST",
            "/main/api/v2/hashpower/order/",
            body={
                "market": market,
                "algorithm": algorithm.upper(),
                "amount": amount,
                "price": price,
                "limit": limit,
                "poolId": pool_id,
                "type": order_type,
                "marketFactor": algo["marketFactor"],
                "displayMarketFactor": algo["displayMarketFactor"],
            },
        )

    def cancel_order(self, order_id: str) -> dict:
        self._require_write()
        return self.request("DELETE", f"/main/api/v2/hashpower/order/{order_id}")

    def refill_order(self, order_id: str, amount: float) -> dict:
        self._require_write()
        return self.request(
            "POST", f"/main/api/v2/hashpower/order/{order_id}/refill/", body={"amount": amount}
        )

    def set_price_and_limit(
        self, order_id: str, *, price: float, limit: float, algorithm: str
    ) -> dict:
        self._require_write()
        algo = None
        for item in self.algorithms():
            if item.get("algorithm", "").upper() == algorithm.upper():
                algo = item
                break
        if algo is None:
            raise RuntimeError(f"algoritmo desconocido en NiceHash: {algorithm}")
        return self.request(
            "POST",
            f"/main/api/v2/hashpower/order/{order_id}/updatePriceAndLimit/",
            body={
                "price": price,
                "limit": limit,
                "marketFactor": algo["marketFactor"],
                "displayMarketFactor": algo["displayMarketFactor"],
            },
        )


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
            "Para mirar datos: marca 'Mining' (lectura) y 'Wallet' (lectura).",
            "Para COMPRAR hashrate (órdenes): marca 'Mining' con permiso de escritura.",
            "Nunca marques 'Withdrawal': MinerPro no retira fondos.",
            "Copia el API Key, el API Secret y el Organization ID de arriba del botón.",
        ],
        api_permissions=[
            "Mining: lectura para rigs/órdenes; escritura solo si vas a comprar hashrate",
            "Wallet: lectura (balance y pagos)",
            "NO habilitar nunca: Withdrawal",
        ],
        warnings=[
            "Comprar hashrate gasta BTC real de tu cuenta de NiceHash.",
            "Nunca habilites retiros (Withdrawal) en una API key que uses aquí.",
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
            "Dos formas de usar NiceHash: (1) apuntas tu minero y te pagan por tu hashrate; "
            "(2) compras hashrate a otros mineros para que mine hacia tu pool (cloud mining real). "
            "MinerPro hace ambas, y la compra siempre pide confirmación explícita."
        ),
    )
)
