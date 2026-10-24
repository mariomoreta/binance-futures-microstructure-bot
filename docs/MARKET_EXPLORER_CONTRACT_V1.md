# Contrato: explorador de contratos USD-M e histórico paginado (`market-catalog/v1`, `market-series/v1`, `market-chart/v1`)

Fecha: 2026-10-21. Base: `9689f3e`. Ámbito: dashboard V2 de **escritorio**, presupuesto
cero, observación. Implementa el paso 4 de `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`
(búsqueda de contratos + histórico paginado) y **no** implementa el paso 4b
(feed vivo/continuo), ni indicadores, ni paper prospectivo, ni órdenes.

Este documento describe lo que el código hace hoy. Donde algo no existe se dice
`UNKNOWN` o «no implementado»; no se describe como implementado.

## 1. Alcance

Incluye:

- catálogo de contratos Binance **USD-M Futures** (`/fapi/v1/exchangeInfo`) cacheado
  y con refresco acotado;
- búsqueda por símbolo o `baseAsset`, con identidad, tipo de contrato, estado y
  motivos explícitos de exclusión;
- histórico de velas **cerradas por REST público** (`/fapi/v1/klines` y
  `/fapi/v1/markPriceKlines`), leído primero de lo almacenado y adquirido solo el
  bloque que falta;
- paginación hacia atrás por bloques de tamaño fijo, conservando el encuadre;
- gráfico reutilizado de Lightweight Charts con contrato `market-chart/v1`.

No incluye (y no debe interpretarse como hecho):

- websocket, suscripciones, monitor, feed continuo, «vela viva»;
- indicadores, señales, objetivos o marcas de operación sobre datos de mercado;
- elegibilidad como recomendación (solo describe `PERPETUAL + TRADING + USDT`);
- escritura en las bases canónicas (`data/microprobe.db`,
  `data/historical/historical.db`);
- móvil, Flutter, ejecución ni capital.

**Abrir un símbolo solo visualiza.** No abre posición, no inicia el monitor y no
añade el símbolo al universo del bot.

## 2. Fuentes reutilizadas vs. capacidades nuevas

| Reutilizado (sin reconstruir) | Uso |
|---|---|
| `src/microstructure_probe/discovery.py` | criterio de elegibilidad ya existente (`PERPETUAL`, `TRADING`, quote `USDT`) y lectura de `exchangeInfo` |
| `src/microstructure_probe/history_client.py` | `exchange_info()`, `paginate_klines()`, `earliest_bar()`, limitador de peso, timeout y política 429/418 |
| `src/microstructure_probe/history_store.py` | almacén canónico de velas: `historical_klines`, `historical_mark_klines`, `historical_coverage`, `historical_gaps` |
| `frontend/src/lib/historical-db.ts` y lectores `price-series`/`historical-coverage` | lectura de lo ya almacenado |
| `lightweight-charts@5.2.1` + `frontend/src/lib/paper-chart-contract.ts` | gráfico y contrato `paper-chart/v1` (intacto para fixtures) |

| Nuevo | Qué aporta |
|---|---|
| `src/microstructure_probe/market_cache.py` | sqlite **aislado** del explorador: catálogo, velas, ledger de peticiones, episodios de catálogo |
| `src/microstructure_probe/market_explorer.py` | autoridad de catálogo, cobertura, plan de bloque faltante, adquisición acotada y payloads |
| `scripts/market_explorer.py` | CLI `--action catalog|series` que invoca el BFF |
| `frontend/src/lib/explorer-bridge.ts` | `spawnSync` + comprobación de origen |
| `frontend/src/app/api/v1/market-contracts/route.ts`, `.../market-series/route.ts` | BFF de solo lectura |
| `frontend/src/lib/market-explorer.ts` | cliente, ventanas y etiquetas |
| `frontend/src/lib/market-chart-contract.ts` | `market-chart/v1` (unión con `paper-chart/v1`) |
| `frontend/src/components/chart/PriceChart.tsx` | gráfico generalizado; `paper-lab-live/PaperChart.tsx` queda como fachada |
| `frontend/src/components/market-lab/ContractExplorer.tsx` | búsqueda, estados y paginación en `/market-lab` |

## 3. Contratos de datos

### 3.1 `market-catalog/v1`

```
contract_version, venue="binance", market_type="usd_m_futures", api_family="fapi",
endpoint="/fapi/v1/exchangeInfo", spot_included=false,
available, reason (CATALOG_NOT_CACHED|null), eligible_only, query,
results[{symbol, base_asset, quote_asset, margin_asset, contract_type, status,
         onboard_ms, price_precision, tick_size, eligible, exclusion_reasons[],
         fetched_at}],
result_count, truncated,
catalog{entries, fetched_at_ms, age_ms, stale, endpoint},
refresh{refreshed, reason, entries?, fetched_at_ms?, age_ms?, requests, detail?},
times{unit:"ms", epoch:"unix_utc"}, generated_at_ms, notes[]
```

- `eligible = contract_type=="PERPETUAL" and status=="TRADING" and
  quote_asset=="USDT"`; el resto se muestra **con motivos**
  (`contract_type=…`, `status=…`, `quote_asset=…`), nunca se oculta.
- `stale` se calcula **después** del refresco: un catálogo recién pedido nunca se
  anuncia desactualizado.
- Un primer refresco **no emite** eventos de listado/baja (no hay snapshot previo
  del que inferirlos). Los diffs posteriores comparan el catálogo completo, no una
  página de 500.

### 3.2 `market-series/v1`

```
contract_version, venue="binance", market_type="usd_m_futures", api_family="fapi",
source="klines"|"mark_klines", endpoint, symbol, interval, interval_ms,
contract{…}|null,
requested{from_ms,to_ms}, observed{start_ms,end_ms},
candles[{open_time_ms, close_time_ms|null, open, high, low, close,
         base_volume|null, quote_volume|null, trade_count|null, provisional,
         fetched_at_ms, storage:"canonical"|"cache"}],
coverage{state: COVERED|PARTIAL|NO_COVERAGE, observed_start_ms, observed_end_ms,
         expected_bars, actual_bars, gap_count|null, gaps[[from,to]],
         absent_ranges[[from,to]], exhausted_before, earliest_available_ms, note},
volume{available, base_asset, quote_asset, fields[], reason|null},
freshness{state:"HISTORICAL_ON_DEMAND", newest_open_ms, newest_close_ms,
          fetched_at_ms, age_ms, provisional, note},
fetch{allowed, performed, status, error|null, requests, pages, retries, failures,
      detail|null, bars_stored, retry_after_ms},
budget{used_in_window, max_requests_per_window, window_ms,
       max_pages_per_request, max_page_limit, concurrency},
storage{canonical_rows, cache_rows, canonical_error|null},
times{unit:"ms", epoch:"unix_utc"},
labels{mode:"HISTORICAL_ON_DEMAND", live:false, banner:"HISTORICO / CONSULTA BAJO DEMANDA"},
generated_at_ms, notes[]
```

Reglas:

- **Orden y unicidad:** una fila por `(symbol, interval, source, open_time)`;
  orden ascendente por `open_time`. El merge canónico+caché deduplica quedándose
  con la fila más reciente.
- **Provisional:** la vela cuyo `open_time + interval_ms > now` publica
  `provisional=true` y `close_time_ms=null`. Nunca se inventa el cierre.
- **Volumen:** solo si la fuente lo publica. `klines` → `base_volume` (unidad =
  `base_asset`) y `quote_volume` (unidad = quote). `mark_klines` → sin volumen
  (`available=false` con motivo). Un volumen ausente no se rellena con 0.
- **Cobertura:** `gaps` son huecos reales entre dos velas observadas;
  `absent_ranges` son tramos solicitados sin ninguna vela almacenada;
  `exhausted_before` indica que se alcanzó el comienzo del histórico del contrato
  (probado con `earliest_bar`, cacheado). Los tres casos se muestran distinto y no
  se interpolan.
- **Frescura:** `freshness.*` describe la **adquisición**, no un feed. No existe
  «última actualización en vivo» porque no hay conexión continua.

### 3.3 `market-chart/v1` (frontend)

`PriceChartModel = PaperChartModel | MarketChartModel`, discriminados por
`contract_version`. Para `market-chart/v1`:

- `identity{venue, market_type, symbol, interval, interval_ms, contract}`;
- `candles{closed[], provisional[], unusable}` ya ordenadas/deduplicadas en el
  navegador (segunda barrera: si llega un payload raro no se dibuja basura);
- `volume` (barras) y `volume_status`/`volume_unit`/`volume_reason`;
- `coverage`, `times`, `capabilities{live:false, can_fetch_earlier,
  earlier_from_ms, limits[]}`, `markers` (solo `provisional`), `operation:null`,
  `indicators:[]`, `notes[]`.

Invariantes del componente:

- `identity.session_id=null` y `operation=null`: no puede aparecer una marca de
  Paper Lab. `paperMarkersLeaked(model)` devuelve `[]` (prueba explícita).
- ms → segundos con `Math.floor(ms/1000)` solo en la frontera de la biblioteca.
- `fitContent` **solo** en el primer encuadre (o al pulsar «Ajustar»), y se
  difiere mientras el contenedor no tenga ancho real. Las actualizaciones no
  reencuadran.
- Al anteponer un bloque anterior se lee `getVisibleLogicalRange()` y se desplaza
  el rango por el número de velas antepuestas: el usuario conserva su zoom.
- Un cambio de símbolo/intervalo invalida la petición anterior con
  `AbortController` + número de secuencia: una respuesta tardía se descarta.

## 4. Política de consulta y caché

| Parámetro | Valor | Dónde |
|---|---|---|
| Catálogo TTL | 6 h (`CATALOG_TTL_MS`) | `market_cache.py` |
| Peticiones por refresco de catálogo | 1 (`exchangeInfo`) | `market_explorer.refresh_catalog` |
| Intervals explorables | `1m, 5m, 15m, 1h, 4h, 1d` (`1M` excluido: mes calendario no tiene ms fijos) | `market_explorer.EXPLORABLE_INTERVALS` |
| Intervals del selector de la UI | `1m, 15m, 1h, 4h, 1d` (predeterminado `1h`; `5m` sigue disponible por API pero no se ofrece en el selector) | `ContractExplorer.tsx` (`INTERVALS`) |
| Tamaño de bloque de la UI | 300 velas (`EXPLORER_PAGE_BARS`) | `frontend/src/lib/market-explorer.ts` |
| `page_limit` aceptado | 50–1000 en el BFF (la CLI recorta a ≤1000); la UI envía 300 | BFF + `scripts/market_explorer.py` |
| `pages` por petición | 1–2 | `MAX_PAGES_PER_REQUEST=2` |
| Concurrencia | 1 (secuencial) | `MAX_CONCURRENCY=1` |
| Timeout por petición | 20 s | `REQUEST_TIMEOUT_S` |
| Presupuesto rolling | 30 peticiones / 60 s (ventana móvil, por proceso y caché) | `MAX_FETCH_REQUESTS_PER_WINDOW` |
| 429 | respeta `Retry-After`, presupuesto de 2 y aborta | `history_client.py` |
| 418 | aborta de inmediato, sin reintentos | `history_client.py` |
| Reintentos del explorador | 0 (el bloque fallido se reporta; no hay bucle) | `market_explorer.fetch_block` |
| Auto-carga de bloque anterior | solo tras interacción real (crosshair), borde izquierdo a ≤3 velas, una petición por `earliest_from_ms` | `PriceChart.tsx` |
| Estado ante error | HTTP 200 con las velas ya almacenadas + `fetch.error`/`fetch.detail` | `series_payload` |

Validación del BFF: `symbol` `^[A-Z0-9]{2,32}$`, `interval` en el conjunto,
`source` en `klines|mark_klines`, `bars` 50–1000, `pages` 1–2, `page_limit`
50–1000, `from_ms ≤ to_ms`; origen permitido (`127.0.0.1:3020`,
`localhost:3020`, `null`); `Cache-Control: no-store`. Errores de validación → 400;
`FORBIDDEN_ORIGIN` → 403; fallo interno del puente → 502.

## 5. Almacenamiento

- Ruta: `data/market-cache/market_cache.db` (override
  `MICROPROBE_MARKET_CACHE_DB`). `data/` ya está ignorado por git: no se añaden
  artefactos versionados ni se toca `.gitignore`.
- Tablas: `cache_meta`, `contract_catalog`, `market_klines`,
  `market_fetch_ledger`, `contract_events`.
- `MarketCache` **rechaza** rutas canónicas (`data/microprobe.db`,
  `data/historical/historical.db`).
- La lectura canónica es **solo lectura** (`sqlite3` en modo consulta, errores
  reportados en `storage.canonical_error`); el explorador nunca escribe allí.
- Crecimiento medido tras la verificación: 598 velas, 931 contratos, 316 KB. Cada
  bloque añade ≤300 filas por símbolo/intervalo. No hay poda automática: el
  límite es explícito y la retirada, manual (§9).

## 6. UI

- Vive en `/market-lab`, como sección «Contract explorer», separada del selector
  de fixtures de Paper Lab.
- Estados: `catálogo: consultando | 931 contratos [· desactualizado] | no
  disponible | error`, carga, vacío, sin cobertura, error de serie, aviso de
  adquisición detenida (presupuesto/rate limit/transporte) y «Cargar anteriores»
  deshabilitado al llegar al inicio del histórico.
- Etiquetas literales: `HISTÓRICO / CONSULTA BAJO DEMANDA`, «no es LIVE», «sin
  websocket ni monitor», «volumen en la unidad declarada», «buscar no es una
  recomendación».
- Accesibilidad: `<form>` con `<label>`, `aria-live` para el resultado de la
  búsqueda, tabla con `caption` y cabeceras `scope="col"`, `aria-pressed` en el
  botón de selección, `role="alert"` en errores y `role="img"` + `aria-label`
  descriptivo en el gráfico.

## 7. Mapa de aceptación

| Caso | Dónde se prueba |
|---|---|
| A. Buscar y seleccionar contrato | `frontend/src/test/contract-explorer.test.tsx` («A: busca, selecciona…») |
| B. Histórico ordenado sin duplicados | `frontend/src/test/market-chart-contract.test.ts` («ordena, deduplica…») |
| C. Página anterior conservando el rango visible | `price-chart-market.test.tsx` («al anteponer…») + `contract-explorer.test.tsx` («C: pide el bloque anterior…») |
| D. Cambio de símbolo/intervalo sin contaminación | `contract-explorer.test.tsx` («D: descarta respuestas tardías…», «D: cambiar la temporalidad…») + `contract-explorer-intervals.test.tsx` (1m en histórico y suscripción, cierre de la suscripción previa, sin LIVE con el servicio detenido) |
| E. Error, rate limit y falta de cobertura | `contract-explorer.test.tsx` («E: …») |
| F. Volumen con unidad | `market-chart-contract.test.ts` + `price-chart-market.test.tsx` |
| G. Recuperar sesión paper sin crear fixture | `frontend/src/test/paper-lab-initial-recovery.test.tsx` |
| H. Encuadre inicial correcto | `price-chart-market.test.tsx` («ajusta el encuadre inicial una sola vez…», «difiere el encuadre…») |

Backend: `tests/test_market_explorer.py` (catálogo, elegibilidad, caché, merge
canónico, plan de bloque, cobertura, presupuesto, 429, errores, CLI).

## 8. Límites conocidos

- **Sin feed continuo.** La vela «actual» es la última barra publicada por REST en
  el momento de la consulta; no se actualiza sola y puede quedar desfasada
  mientras la pestaña está abierta. Reconsultar vuelve a pedir el bloque más
  reciente.
- **`1M` no soportado** (mes calendario): el cálculo de huecos dejaría de ser
  exacto.
- **Huecos reales del canónico.** Al fusionar con `historical.db`, los tramos que
  esa base tiene incompletos aparecen como `gaps` (p. ej. 43 huecos de 1h en
  MINAUSDT, 2026-09-27→2026-10-09). No se rellenan ni se ocultan.
- **Caché acotada, sin poda automática.** Uso intensivo durante semanas exige
  borrar `data/market-cache/` (§9).
- **Sin indicadores.** El backend no produce indicadores para este flujo; el
  contrato los declara `[]` en vez de calcularlos en el navegador.
- **Sin inspección visual por modelo** en este bloque (proveedor de visión sin
  autenticación): la verificación es DOM/HTTP + geometría + capturas locales.

## 9. Ruta de retirada

1. Borrar `frontend/src/components/market-lab/ContractExplorer.tsx` y su
   `.module.css`; quitar `<ContractExplorer/>` de `frontend/src/app/market-lab/page.tsx`.
2. Borrar `frontend/src/app/api/v1/market-contracts/` y `.../market-series/`,
   `frontend/src/lib/market-explorer.ts`, `frontend/src/lib/explorer-bridge.ts` y
   `frontend/src/lib/market-chart-contract.ts`.
3. `PriceChart.tsx` puede quedarse con la rama `paper` únicamente (el contrato
   `paper-chart/v1` y sus testids no dependen del explorador); si se retira el
   modo mercado, `PaperChart.tsx` vuelve a ser el componente real.
4. Borrar `scripts/market_explorer.py`, `src/microstructure_probe/market_explorer.py`
   y `src/microstructure_probe/market_cache.py`, y `tests/test_market_explorer.py`.
5. Borrar el directorio `data/market-cache/` (caché propia, no evidencia de
   terceros). No requiere migración: nada canónico depende de él.
6. Retirar las pruebas `frontend/src/test/{market-chart-contract,market-explorer,price-chart-market,contract-explorer}.test.*`
   y la sección de este documento en `CURRENT_STATE`/`FEATURE_BACKLOG`.
7. Feed continuo: borrar `src/microstructure_probe/market_stream.py`,
   `src/microstructure_probe/market_stream_service.py`,
   `scripts/market_stream_service.py`, `scripts/market_stream_window.py`,
   `frontend/src/app/api/v1/market-stream/`,
   `frontend/src/lib/{market-stream,use-market-stream,stream-bridge}.ts` y
   `frontend/src/test/{market-stream-contract,use-market-stream}.test.*`; quitar
   el panel de estado de `ContractExplorer.tsx` y la serie provisional de
   `PriceChart.tsx`. Borrar `data/market-stream/` (PID file) y detener el
   servicio. Nada canónico depende de él y no hay datos que migrar.

## 10. Extensión 2026-10-21 — feed continuo (`market-stream/v1`)

Este contrato cubre el **histórico** por REST. El feed continuo es un contrato
aparte, versionado e independiente: `docs/MARKET_STREAM_CONTRACT_V1.md`.

- Una sola conexión combinada (`/market/stream?streams=…`) compartida por todos
  los consumidores, con refcount por `(symbol, interval)`.
- El snapshot se lee del mismo almacén con `allow_fetch=False`: el explorador
  sigue siendo el único que adquiere histórico. Si no hay cobertura se publica
  `NO_COVERAGE` y no se dibuja nada.
- Reconciliación `subscribe → buffer → snapshot → flush` sin huecos ni
  duplicados; desbordamiento declarado como `gap`.
- `market-chart/v1` gana un bloque opcional `stream` (estado, frescura, huecos);
  `capabilities.live` **sigue siendo `false`**: LIVE se declara en el bloque del
  feed y exige frescura real, no un socket abierto.
- Sin persistencia de actualizaciones (anillo en memoria, 0 bytes en disco) y
  reparación REST acotada que se publica como `complete|partial|failed`.
- Probado con transporte controlado; **no verificado con Binance**. La ventana
  viva está en `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` y requiere autorización.
