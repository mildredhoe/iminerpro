# Conectar plataformas (NiceHash y Binance)

MinerPro trabaja con las plataformas en **dos niveles**:

| Nivel | Qué permite | Cómo se activa |
|---|---|---|
| **Lectura** (por defecto) | Balance, rigs, workers, órdenes, ganancias, mercado | Cualquier API key de lectura |
| **Acciones** | Crear pool, comprar/recargar/cancelar órdenes, reventa de hashrate | `allow_write` en el cliente **más** `--confirm` en el comando |

Los comandos que gastan dinero **nunca** se ejecutan sin `--confirm`: sin ese flag,
MinerPro te muestra exactamente qué haría y se detiene.

No hay endpoints de retiro en MinerPro. Nunca habilites `Withdrawal` en tus claves.

---

## NiceHash (marketplace de hashrate)

**Qué es:** tú pones el hardware (o apuntas tu minero) y NiceHash te compra el hashrate,
pagándote normalmente en BTC. También funciona al revés: **compras hashrate** a otros
mineros para que minen hacia tu pool (cloud mining real). Soporta RandomX (XMRig) y
SHA-256 (ASIC).

### 1) Obtener las credenciales

1. Crea una cuenta en <https://www.nicehash.com> y verifica tu correo.
2. Entra a **Mi cuenta → Settings → API Keys**:
   <https://www.nicehash.com/my/settings/keys>
3. Pulsa **Create new API key** y ponle un nombre (ej. `MinerPro`).
4. Marca **solo permisos de lectura**: `Mining` (ver rigs) y `Wallet` (ver balance).
5. Copia el **API Key** y el **API Secret** (el secret se muestra una sola vez).
6. Copia además el **Organization ID** que aparece justo arriba del botón de crear.

### 2) Dónde pones las claves

**Opción A (recomendada), interactiva y en el llavero del sistema:**

```bash
minerpro cloud connect nicehash
```

Te pide API Key, API Secret y Organization ID, y los guarda cifrados (Keychain en macOS,
DPAPI en Windows, Secret Service en Linux).

**Opción B, archivo `.env`** (en la raíz del proyecto o en `~/.minerpro/.env`):

```ini
MINERPRO_NICEHASH_KEY=...
MINERPRO_NICEHASH_SECRET=...
MINERPRO_NICEHASH_ORG=...
```

Puedes empezar desde `.env.example`.

### 3) Verificar

```bash
minerpro cloud status nicehash     # balance real (solo lectura)
```

### 4) Empezar a minar apuntando tu minero

```bash
minerpro cloud stratum nicehash -c XMR -w <tu_btc_de_nicehash>
```

Te muestra el host, puerto y usuario. Ejemplo para XMR:
`randomxmonero.auto.nicehash.com:9200`, usuario = tu dirección de depósito de NiceHash,
password `x`. Puedes generar el `config.json` de XMRig sin ejecutar nada:

```bash
minerpro cloud stratum nicehash -c XMR -w <tu_btc> --write-xmrig
```

> Confirma siempre el host exacto en el generador oficial:
> <https://www.nicehash.com/stratum-generator>

### 5) Ver el mercado (sin claves)

```bash
minerpro cloud market --algo SHA256          # order book en vivo
minerpro cloud market --algo RANDOMXMONERO   # precio del hashrate de RandomX
```

Lee el order book público de NiceHash: precio, mercado, velocidad y cuántos rigs tiene
cada orden. Sirve para decidir a qué precio comprar antes de tocar nada.

### 6) Comprar hashrate (cloud mining real)

Comprar hashrate significa pagar BTC a otros mineros para que minen hacia **tu pool**.
Es la forma "nube" más transparente: ves el mercado y decides.

```bash
# 1. Vista previa y confirmación de las acciones (no ejecuta nada sin --confirm)
minerpro cloud market -a SHA256
minerpro cloud rigs                     # qué está reportando tu cuenta
minerpro cloud orders -a SHA256         # tus órdenes existentes

# 2. Registrar la pool de destino en NiceHash (una vez)
minerpro cloud pool-add --name supportxmr --algo SHA256 \
    --host pool.supportxmr.com --port 3333 --username <tu_wallet> --confirm

# 3. Crear la orden
minerpro cloud buy --algo SHA256 --market EU --price 0.0001 \
    --amount 0.001 --limit 1 --pool-id <id> --confirm

# 4. Gestionarla
minerpro cloud refill --order-id <id> --amount 0.001 --confirm
minerpro cloud cancel --order-id <id> --confirm
```

Sin `--confirm`, `pool-add`, `buy`, `refill` y `cancel` te muestran qué harían y salen
con código 1. Nadie gasta BTC por accidente.

---

## Binance Pool / Cloud Mining

**Qué es:** pool de Binance (BTC, BCH, LTC, ETC…) con API para ver tus workers y tus
ganancias, más el historial de cloud mining. **No mina Monero.**

### 1) Obtener las credenciales

1. Inicia sesión en <https://www.binance.com> y completa la verificación si te la pide.
2. Ve a **Perfil → Gestión de API**:
   <https://www.binance.com/en/my/settings/api-management>
3. Pulsa **Crear API** → **Generada por el sistema** y ponle etiqueta (ej. `MinerPro`).
4. Verifica con tu app de autenticación (2FA).
5. En la API recién creada, habilita **solo `Enable Reading`** (lectura).
6. En **Restricciones de IP**, agrega tu IP pública (muy recomendado).
7. Copia la **API Key** y el **Secret Key** (el secret se muestra una vez).

**Nunca** habilites retiros ni trading en esta clave.

### 2) Dónde pones las claves

```bash
minerpro cloud connect binance
```

o en `.env`:

```ini
MINERPRO_BINANCE_KEY=...
MINERPRO_BINANCE_SECRET=...
```

### 3) Verificar

```bash
minerpro cloud status binance     # cuentas de minería y hashrate (solo lectura)
```

MinerPro usa estos endpoints oficiales de Binance (todos de lectura, con firma
HMAC-SHA256 en el query y header `X-MBX-APIKEY`):

| Uso | Endpoint |
|---|---|
| Estado de la cuenta | `GET /sapi/v1/mining/statistics/user/status` |
| Cuentas de minería | `GET /sapi/v1/mining/statistics/user/list` |
| Workers | `GET /sapi/v1/mining/worker/list` |
| Detalle de worker | `GET /sapi/v1/mining/worker/detail` |
| Ganancias del pool | `GET /sapi/v1/mining/payment/list` |
| Coins/algoritmos | `GET /sapi/v1/mining/pub/coinList`, `/pub/algoList` |
| Cloud mining | `GET /sapi/v1/asset/ledger-transfer/cloud-mining/queryByPage` |

### 4) Empezar a minar en Binance Pool (BTC, ASIC)

```bash
minerpro cloud stratum binance -c BTC --account MiningBTC --worker rig1
```

Te da `sha256.poolbinance.com:8888` (respaldo `:443`) y el usuario `MiningBTC.rig1`
(«cuenta de minería».«worker»).

### 5) Ver tus workers y ganancias

```bash
minerpro cloud workers  -a sha256d --account MiningBTC
minerpro cloud earnings -a sha256d --account MiningBTC --coin BTC
minerpro cloud status binance        # resumen de cuentas de minería
```

### 6) Reventa de hashrate (acción, requiere escritura)

Puedes reasignar parte de tu hashrate a otra cuenta de pool. Es una acción que modifica
tu cuenta, así que el cliente exige `allow_write` y el comando (si se usa desde la API
en tu código) debe confirmarse explícitamente. Usa la API de Binance con cuidado:

- `POST /sapi/v1/mining/hash-transfer/config` (crear)
- `POST /sapi/v1/mining/hash-transfer/config/cancel` (cancelar)
- `GET /sapi/v1/mining/hash-transfer/config/details/list` (listar)

```python
from minerpro.platforms.binance import BinanceClient

client = BinanceClient.from_store(allow_write=True)   # explícito
client.resale_list()                                  # solo lectura
```

---

## Seguridad (aplica a todas las plataformas)

- Claves de **lectura** por defecto. Nunca habilites retiros ni trading.
- Solo habilita escritura si vas a comprar hashrate (NiceHash) o reasignar hashrate
  (Binance), y aun así todo pasa por `--confirm`.
- Restringe por IP cuando la plataforma lo permita (Binance sí).
- Con `keyring` instalado, las claves van al llavero del sistema; si no, a
  `~/.minerpro/secrets.json` con permisos `0600`.
- `.env` está en `.gitignore`: no lo subas a git.
- MinerPro no compra contratos de cloud mining ni automatiza pagos. El catálogo
  (`minerpro cloud providers`) marca los contratos genéricos como riesgo **ALTO**.

## Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `NiceHash ... Invalid UUID string` | El Organization ID no es un UUID. Cópialo de la página de API Keys. |
| `Binance -2008 Invalid Api-Key ID` | API Key equivocada o de testnet; genera una nueva. |
| `Binance -2015 Invalid API-key, IP, or permissions` | Falta restringir/agregar tu IP o no habilitaste `Enable Reading`. |
| Faltan credenciales | Usa `minerpro cloud connect <plataforma>` o define las variables en `.env`. |
