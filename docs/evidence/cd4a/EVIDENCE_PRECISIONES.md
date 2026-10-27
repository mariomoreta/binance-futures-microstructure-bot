# Precisiones de evidencia — Chrome DevTools MCP (cd4a)

Cierra tres precisiones pendientes de la evidencia inicial (`5aabcbb`).

## 1. Backend sin peticiones públicas — estado: UNKNOWN (no cero)

La allowlist del navegador (`--allowed-url-pattern=http://127.0.0.1:*/*`)
controla **solo al navegador**, no al backend. Para acreditar el plano backend
se usa el ledger + guard existentes, no se asume cero.

Evidencia del ledger (`data/market-cache/market_fetch_ledger`):
- `market_fetch_ledger` existe con 98 filas, columnas `at_ms`, `symbol`,
  `interval`, `source`, `requests`, `retries`, `failures`, `status`, `note`,
  `execution_id`, `detail`.
- `LedgerAttemptGate` + `reserve_fetch_attempt` implementados en
  `src/microstructure_probe/market_cache.py` y
  `src/microstructure_probe/market_explorer.py`: cada intento HTTP reserva 1
  cupo **ANTES** del transporte; denegado → fila `budget_blocked`
  (`requests=0`) + `UpstreamBudgetExceeded` sin abrir socket.
- 14 filas con `execution_id` no nulo; 15 filas con `detail` que contiene
  URLs públicas de `fapi.binance.com` (sesiones de verificación REST acotada
  autorizadas en fechas previas, no de la carga actual de este diagnóstico).
- Todas las filas tienen `status='ok'`.

Red del navegador en la carga actual de `/market-lab`: 167 peticiones, todas
a `127.0.0.1:3020`, 0 hosts públicos (verificado con `list_network_requests`).

**Declaración:** para la carga actual de este diagnóstico no hay monitoreo
directo del tráfico de red del backend (solo del navegador). El ledger y el
guard existen y funcionan, pero no se puede afirmar "cero peticiones públicas
del backend en esta carga" sin monitoreo directo del tráfico de backend.
**Estado: UNKNOWN** (no se declara cero).

## 2. Qué gráfico se inspeccionó — estado: verificado y diferenciado

### Gráfico inspeccionado inicialmente (NO es el explorador de contratos)
En `/market-lab`, el combobox "Select symbol" tenía `value="BTCUSDT" selected`.
La sección mostraba "Historical Market Lab" / "BTCUSDT persisted price sequence"
con 100 samples, last saved mark 81961.5, observed change +1.271%, y una
imagen "BTCUSDT historical mark price chart". Este es el **gráfico histórico
de mark price** (PriceChart sobre datos persistidos en SQLite, solo lectura,
sin indicadores de flujo ni contexto BTC).

### Explorador de contratos con velas + market-indicators/v1 + market-btc-context/v1
Petición real al BFF: `GET /api/v1/market-series?symbol=MINAUSDT&interval=1m&source=klines&bars=300`
(respuesta HTTP 200, solo localhost).

Payload `market-series/v1` contiene:
- **`indicators` (market-indicators/v1)**: `contract_version="market-indicators/v1"`,
  `supported=["log_return_bps","velocity_bps_5","rel_volume_10","vwap_dev_bps_10"]`,
  `declined=[flow_delta(AGGTRADES_SOURCE_REQUIRED),
  spread_bps(ORDER_BOOK_SOURCE_REQUIRED), depth(ORDER_BOOK_SOURCE_REQUIRED),
  open_interest(OI_REST_POLL_REQUIRED), btc_context(SECOND_SYMBOL_KLINES_REQUIRED)]`,
  298 filas. Primera fila con valores:
  `open_time_ms=1793042400000, values={log_return_bps:-3.121099}`,
  `unknown={velocity_bps_5:INSUFICIENT_CANDLES, ...}`.
- **`context_btc` (market-btc-context/v1)**: `contract_version="market-btc-context/v1"`,
  `identity={symbol:MINAUSDT, interval:1m, source:klines}`,
  `context={symbol:BTCUSDT, venue:binance, market_type:usd_m_futures,
  same_asset_as_token:false, sources:[cache], acquisition:{rest_upstream_requests:0,
  mode:cache}}`,
  298 filas. Primera fila con valores:
  `open_time_ms=1793042580000, values={ret_btc_bps_5:-2.59836,
  ret_diff_bps_5:-9.891884}, unknown={}`.
- `coverage={state:COVERED, actual_bars:299, expected_bars:299, gap_count:0}`.

Para BTCUSDT, `context_btc` es `None` por diseño (`TOKEN_IS_BTC`: no se compara
uno consigo mismo, no hay segunda suscripción).

**Diferenciación:** el gráfico de mark price histórico (PriceChart, SQLite,
100 samples) es distinto del explorador de contratos con velas
(market-series/v1 + market-indicators/v1 + market-btc-context/v1, 298 velas,
indicadores y contexto BTC versionados por el backend).

## 3. Mensajes de consola — estado: verificado (carga actual)

Carga limpia de `/market-lab` (`ignoreCache=true`): **1 mensaje total**.
- Errores: 0
- Warnings: 0
- Informativos: 0
- Issues: 1 — `msgid=156 [issue] A form field element should have an id or name attribute (count: 3)` (campo de formulario sin id/nombre; accesibilidad, no afecta funcionamiento).

Los 40 mensajes de la captura previa (`market-lab-02-btcusdt-selected.txt`)
no son verificables en esta sesión: la página se recargó y el navegador no los
retiene entre navegaciones. Del sample de esa captura previa se observaban
principalmente `[warn]` sobre CSS preload no usado (recursos de Next.js), sin
errores de bloqueo de red.

**Capturas generadas ≠ inspección visual:** no hay proveedor de visión
disponible; la revisión visual queda PENDIENTE.
