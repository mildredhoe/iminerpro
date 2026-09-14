# MinerPro ⛏️

Deja todo **listo para minar criptomonedas de verdad**: **BTC o XMR**, en **local**
(tu equipo) o en la **nube** (plataformas por API).

- **No mina si tú no se lo pides.** No hay arranque automático ni procesos ocultos.
- **XMR local**: usa XMRig, que MinerPro descarga del **release oficial** y verifica
  con **SHA-256** antes de ejecutar.
- **BTC local**: conecta tu minero (ASIC, cgminer/bfgminer, cualquier Stratum) a partir
  de una plantilla de comando. MinerPro no empaqueta mineros de SHA-256d.
- **Nube (solo lectura)**: estadísticas reales de pool por wallet y conexión a NiceHash
  (API v2, HMAC). No compra contratos ni mueve fondos.
- **Real, no demo**: hashrate y shares salen de la API local del minero; pending/paid
  salen de la API pública de la pool.

> Mina solo en equipos de tu propiedad o con permiso explícito. Consume electricidad y
> calienta el hardware.

## Instalación

```bash
# desde el repo local
cd minerpro_oficial
uv venv .venv && uv pip install -e .

# o instalable como herramienta
pipx install .
```

## Uso

```bash
minerpro doctor                       # detecta hardware y mineros (no mina)
minerpro coins                        # BTC vs XMR: qué aplica en local y en nube
minerpro pools --coin BTC             # pools reales con su fee
minerpro wallet <direccion>           # valida XMR o BTC (checksum real)

# Ver qué haría, SIN ejecutar nada
minerpro plan -c XMR -w <tu_xmr>
minerpro plan -c BTC -w <tu_btc> --miner-cmd "cgminer -o {url} -u {user} -p {pass}"

# Nube
minerpro cloud providers              # catálogo con nivel de riesgo
minerpro cloud connect nicehash       # guarda API key en el llavero
minerpro cloud status nicehash        # balance real (solo lectura)

# Minar de verdad (lo decides tú)
minerpro mine -c XMR -w <tu_xmr>                 # TUI en vivo con XMRig
minerpro mine -c BTC -w <tu_btc> --miner-cmd "..."
minerpro mine -c XMR -w <tu_xmr> --dry-run       # solo muestra el plan

# Balance real que la pool reporta para tu wallet
minerpro poolstats --wallet <tu_xmr> --pool SupportXMR
```

## Estado

- ✅ Detección de hardware, CLI, perfiles, validación de wallets XMR y BTC.
- ✅ XMR local con XMRig gestionado (descarga + SHA-256 + config + API + TUI).
- ✅ BTC local vía minero externo Stratum (genera y muestra el comando).
- ✅ Nube: stats de pool por wallet + cliente NiceHash API v2 + catálogo con riesgo.
- ⏳ Histórico en SQLite, estimador de ganancia, backend nativo Apple Silicon, binarios
  y distribuidores (brew/winget/`curl | sh`).

Ver `PLAN.md` para el detalle y los criterios de aceptación.

## Seguridad

- XMRig se descarga **solo** del release oficial de GitHub y se verifica por SHA-256.
- Las API keys se guardan en el llavero del sistema (o archivo `0600` si no hay keyring).
- Los "contratos de cloud mining" se marcan como riesgo **ALTO** y no se automatizan.
- Las estimaciones de ganancia se etiquetan como estimaciones.
