# MinerPro — Plan de construcción (BTC y XMR · local y nube)

> Estado: **Fase 0 y Fase 1 hechas**. El proyecto queda *listo* para minar, pero **no
> arranca ningún minero por sí solo**: el usuario decide y ejecuta `minerpro mine`.

## 0. Qué revisé y qué encontré

| Artefacto | Qué es | Veredicto |
|---|---|---|
| `~/minerpro/miner.py` | TUI ANSI en Python que **simula** minado | Es el **diseño a replicar** (header, stream, banner, stats); su lógica es demo |
| `~/moneromining/mxmr` | Binario Rust de **minero real** RandomX Apple Silicon (TUI ratatui, web UI, solo/p2pool). `selftest` pasa los 4 vectores; `info` detecta M2 4P+4E | Base técnica del backend nativo. **Su fuente no está en disco**; se reconstruye en Fase 5 |
| `~/telegram_miner` | Canal + bot de ventas + scraper | Fuera de alcance (lo pediste así) |
| `~/Downloads/*.pdf` | Guías de XMRig y cloud mining ya escritas | Reutilizables como onboarding/ayuda in-app |

## 1. Objetivo

Un proyecto descargable donde cualquiera pueda, con pocos pasos:

1. Elegir **BTC** o **XMR**.
2. Elegir **local** (su equipo) o **nube** (plataformas por API).
3. Dejar todo **listo**: wallet validada, pool elegida, configuración generada, comando exacto.
4. Cuando el usuario quiera, arrancar el minado real con un comando.

Regla: **MinerPro no mina solo**. Nunca arranca en segundo plano ni al instalar.

## 2. Arquitectura

### 2.1 Capas
- `coins.py` — modelo de moneda. Hoy: **XMR** (RandomX) y **BTC** (SHA-256d), cada una
  con qué motores locales/nube aplican y una nota honesta de realidad.
- `wallet.py` — validación **Monero** completa (base58 CryptoNote + checksum Keccak-256).
- `btc.py` — validación **Bitcoin** completa (base58check + bech32/bech32m).
- `engines/` — motores intercambiables:
  - `xmrig.py` — **XMR local**: descarga el binario oficial, verifica SHA-256, genera
    `config.json`, lo lanza y lee hashrate/shares por su API HTTP local.
  - `external.py` — **BTC local**: ejecuta el minero del usuario (ASIC, cgminer/bfgminer,
    cualquier Stratum) desde una plantilla de comando. No lo empaquetamos.
  - `base.py` — interfaz común (`prepare/start/stop/stats/logs`).
- `pools/` — registro de pools reales (XMR: SupportXMR, MoneroOcean, HashVault, p2pool;
  BTC: CKPool Solo, Public Pool, Braiins) + clientes de stats por wallet.
- `platforms/` — **plataformas conectables** (registro + guía + cliente):
  - `nicehash.py` — API v2 con firma HMAC-SHA256 (layout del demo oficial), balance,
    rigs, órdenes y **stratum** (`randomxmonero.auto.nicehash.com:9200`).
  - `binance.py` — Binance Pool / Cloud Mining con firma HMAC en el query string y
    header `X-MBX-APIKEY` (workers, ganancias, cloud-mining ledger) y stratum
    (`sha256.poolbinance.com:8888`).
  - `catalog.py` — catálogo de plataformas/contratos con **nivel de riesgo**.
- `stratum.py` — arma el destino (host, puerto, usuario) para apuntar el minero.
- `secrets.py` — API keys en el llavero del sistema (Keychain/DPAPI/Secret Service);
  fallback a archivo `0600`; también lee variables `MINERPRO_*`.
- `config.py` — perfiles + carga de `.env` (cwd y `~/.minerpro/.env`).
- `tui.py` — dashboard Rich con datos reales.
- `cli.py` — comandos: `doctor`, `coins`, `pools`, `wallet`, `install`, `plan`,
  `poolstats`, `cloud ...`, `mine [--dry-run]`.

### 2.2 Qué significa "nube" aquí (real y honesto)
1. **Plataformas conectables por API**, en dos niveles:
   - **Lectura** (por defecto): balance, rigs, workers, órdenes, ganancias y el order
     book público de NiceHash (`minerpro cloud market`, sin claves).
   - **Acciones** (opt-in): registrar pool, comprar/recargar/cancelar órdenes de hashrate
     en NiceHash y reventa de hashrate en Binance. Requieren `allow_write` en el cliente
     **y** `--confirm` en el comando: sin `--confirm` no se ejecuta nada.
   - Cada plataforma trae su **guía paso a paso** (`minerpro cloud guide <id>`) con las
     URLs oficiales, los permisos exactos y **dónde se pegan las claves** (llavero o `.env`).
2. **Stats de pool por wallet** (SupportXMR, MoneroOcean, HashVault, ckpool): pending/paid reales.
3. **Catálogo de proveedores** con fee, modelo y **nivel de riesgo** (los "contratos" se
   marcan **ALTO**: ahí viven las estafas tipo Ponzi).

MinerPro **no retira fondos, no firma contratos de terceros y no arranca el minado solo**.
Las acciones que gastan dinero pasan siempre por confirmación explícita del usuario.

## 3. Estructura del repo

```
minerpro_oficial/
├── pyproject.toml            # paquete instalable (pipx / uv)
├── src/minerpro/
│   ├── cli.py  coins.py  wallet.py  btc.py  hardware.py  config.py  secrets.py  tui.py
│   ├── stratum.py
│   ├── engines/{base,xmrig,external}.py
│   ├── pools/{registry,stats}.py
│   └── platforms/{base,nicehash,binance,catalog}.py
├── docs/plataformas.md       # cómo obtener y colocar las API keys
└── tests/                    # 24 tests (wallets, motores, firmas, stratum)
```

## 4. Estado por fase

| Fase | Estado | Qué falta |
|---|---|---|
| 0 · Fundación (CLI, hardware, perfiles) | ✅ hecha | — |
| 1 · Minado local real (XMRig gestionado + TUI) | ✅ hecha | — |
| 2 · Persistencia + histórico (SQLite) | ⏳ | guardar series de hashrate/shares |
| 3 · Stats de pool + estimación honesta | 🟡 parcial | cliente XMR hecho; falta BTC y estimador |
| 4 · Nube: NiceHash + Binance, lectura y acciones | 🟡 avanzada | conectores, acciones con `--confirm` y onboarding hechos; falta probar con credenciales reales |
| 5 · Backend nativo Apple Silicon (`mxmr`) | ⏳ | reconstruir core RandomX (`randomx-rs`) |
| 6 · Distribución (binarios, brew, winget, `curl \| sh`) | ⏳ | empaquetado PyInstaller + CI |

## 5. Cómo se usa (flujo pensado)

```bash
minerpro doctor                       # qué hardware tengo (no mina)
minerpro coins                        # BTC vs XMR, local vs nube
minerpro plan -c XMR -w <wallet>      # qué haría, sin ejecutar nada
minerpro plan -c BTC -w <wallet> --miner-cmd "cgminer -o {url} -u {user} -p {pass}"
minerpro mine  -c XMR -w <wallet>     # recién aquí se mina de verdad
```

## 6. Seguridad, legal y ética
- Minar solo en equipos propios; MinerPro nunca arranca minado solo.
- XMRig se baja **solo** del release oficial y se verifica por SHA-256.
- API keys en el llavero; nunca en logs.
- Los "contratos de nube" se muestran como riesgo ALTO y no se automatizan.
- Las estimaciones se etiquetan como estimaciones.

## 7. Riesgos
| Riesgo | Mitigación |
|---|---|
| Fuente de `mxmr` perdida | Fase 5 la reconstruye; mientras, XMRig cubre XMR local |
| Antivirus marca mineros (PUA) | Descarga oficial + verificación + explicación in-app |
| BTC en PC no es rentable | Se muestra la realidad y se ofrece lotería/nube, sin promesas falsas |
| `~/.git` es de otro repo (`MHV-medusa`) | `minerpro_oficial/` es repo independiente |
