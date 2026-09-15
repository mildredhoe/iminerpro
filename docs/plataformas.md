# Conectar plataformas (NiceHash y Binance)

MinerPro se conecta a plataformas **solo para leer** (balances, workers, ganancias) y
para **armar el destino Stratum** con el que tu minero empieza a minar. Nunca retira,
compra ni mueve fondos, y **nunca arranca el minado solo**.

Todos los comandos verifican la conexión y avisan con claridad si falta algo.

---

## NiceHash (marketplace de hashrate)

**Qué es:** tú pones el hardware (o apuntas tu minero) y NiceHash te compra el hashrate,
pagándote normalmente en BTC. Soporta RandomX (XMRig) y SHA-256 (ASIC).

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

---

## Seguridad (aplica a todas las plataformas)

- Claves **solo de lectura**. Nunca habilites retiros ni trading.
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
