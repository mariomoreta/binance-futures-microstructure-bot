# Plan acotado — Contexto BTC compartido V1 (2026-10-26, base `3c2e7ab`)

Autorizado por el operador 2026-10-26: "comenzar contexto BTC compartido. Sin
conexiones publicas." Objetivo: mostrar el movimiento del token junto al de
BTC con datos disponibles en el mismo instante. **Contexto informativo, NO
senial, NO filtro automatico de entrada, NO rentabilidad.**

## 1. Alcance (bounded slice)

- Mismo venue (Binance USD-M), mismo intervalo, usado del canal de velas,
  round-trip existente; SIN colector nuevo y SIN calculo economico en el
  navegador.
- Bloque versionado NUEVO y ADITIVO `market-btc-context/v1` (no toca
  `market-indicators/v1` ni su lista `declined`; el bloque de indicadores
  sigue declinando derivar contexto de las velas DEL PROPIO payload — el
  contexto llega por un bloque hermano con fuente propia declarada).
- Alineacion de ambas series POR `open_time_ms` (rejilla), nunca por posicion
  del arreglo; solo velas CERRADAS conocidas en T.
- Causa declarada por fila y por bloque: fuente, disponibilidad, frescura y
  cobertura; falta de BTC o hueco → `UNKNOWN(BTC_...)` con motivo, sin
  arrastrar valores viejos silenciosamente.
- El identificador de la comparacion es el RANGO de la sesion del token; la
  suscripcion BTC vive en el MISMO hub compartido (`KlineStreamHub`,
  refcount por `(symbol, interval)`, un solo socket combinado). Si el token
  es BTC: no hay segunda suscripcion y no hay bloque (no hay comparacion
  consigo mismo).
- Coste real: la adquisicion de BTC en este slice es **cache + WS del canal
  existente, `client=None`, 0 upstream REST**. El REST de tramos faltantes de
  BTC NO se implementa en este slice (ventana publica requiere autorizacion
  explicita); el numero de paginas que necesitaria NO es fijo (depende del
  tramo faltante) y se documenta como regla, no como cifra.

## 2. Contrato `market-btc-context/v1` (resumen causal)

```
contract_version="market-btc-context/v1", availability="CLOSED_CANDLES_ONLY"
identity{symbol(token), interval, interval_ms, source(token)}
context{
  symbol:"BTCUSDT", venue:"binance", market_type:"usd_m_futures",
  interval, interval_ms,
  reuses_token_subscription: bool (true solo si token==BTC; sin bloque en ese caso),
  live_subscription: bool, reason: null|"MAX_SUBSCRIPTIONS"|...
  sources: ["cache", "ws_kline"]   // proveniencia REAL de lo usado
  horizon_candles: 5
  timeframe{aligned_by:"open_time_ms", token_window{first,last},
            btc_observed{first,last}, expected_grid, present_grid, gaps[[a,b]]}
  freshness{btc_last_closed_open_ms, btc_last_available_at_ms, age_ms,
            lagging: bool, threshold_ms: interval_ms}
  acquisition{rest_upstream_requests: n REAL, mode:"cache+ws"|"cache",
              note:"paginas del tramo faltante si REST autorizado; no fijo"}
}
definitions[{ret_btc_bps_5, ret_diff_bps_5}], supported[...],
series[{open_time_ms(token), available_at_ms = max(btc, token),
        values{ret_btc_bps_5, ret_diff_bps_5}, unknown{...}}]
normalized{base_open_time_ms (primera rejilla comun conocida), 
           series[{open_time_ms, token_pct, btc_pct}]} | null
generated_at_ms
```

Indicadores (formula sobre velas cerradas de BTC en la MISMA rejilla):
- `ret_btc_bps_5` = `10000·ln(close_t^BTC / close_{t−4}^BTC)` (bps); 5 velas
  cerradas, 4 saltos, validado por TIEMPO.
- `ret_diff_bps_5` = `velocity_bps_5(token) − ret_btc_bps_5` (bps), etiquetada
  "diferencia de retornos"; NO se llama alpha ni rentabilidad.
- `normalized` = pct desde base comun `100·(close_t/close_base − 1)` para
  token y BTC (backend calcula; unidad "% desde base").

Motivos UNKNOWN (nunca 0): `BTC_MISSING` (sin velas BTC en absoluto),
`BTC_GAP_IN_WINDOW`, `BTC_INSUFICIENT_CANDLES`, `BTC_LAGGING` (BTC atras del
cierre esperado en la rejilla), `MISSING_CLOSE`, `INVALID_PRICE`,
`INVALID_BASE`. `ret_diff_bps_5` hereda primero el motivo del indicador del
token (`velocity_bps_5`) si existe; si no, el motivo `BTC_*`.

## 3. Cambios backend (reutilizando lo existente)

1. `src/microstructure_probe/kline_btc_context.py` (NUEVO): funcion pura
   `compute_btc_context(...)`; sin I/O.
2. `market_explorer.series_payload`: si token≠BTC, lee BTC del cache con el
   MISMO rango (`read_stored`, client=None → 0 upstream) y añade el campo
   aditivo `context_btc`.
3. `market_stream_service._serve_stream`: ventana de la sesion BTC paralela
   (cache snapshot + hub refcount por suscriptor), frame SSE nuevo
   `event: context` recalculado cuando cierra token O BTC; snapshot SSE añade
   `context_btc`. BTC provisional/gap no se reenvian al navegador; los
   huecos de BTC aparecen como unknown por rejilla. Al desmontar, los DOS
   consumidores se dan de baja (cerrar la vista libera solo sus
   consumidores).
4. Frames: `snapshot.context_btc` + `event: context` (aditivos; el resto del
   contrato market-stream/v1 no cambia).

## 4. Cambios frontend (solo lectura del backend)

- `market-chart-contract.ts`: tipos + `sanitizeContextBtc` +
  `parseContextBtc` (guard de identidad del payload) + `applyStreamContextBtc`
  (union por fila, nuevo gana, `normalized` DEL BLOQUE MAS NUEVO) + badge
  propio `market-chart-btc-context` con unidades (`retBTC ±nn.nnbps`,
  `diff ±nn.nnbps`).
- `market-stream.ts` / `use-market-stream.ts`: campo `btc_context` en
  snapshot/view y listener `context` con guard de identidad.
- `buildMarketChartModel`: `model.context_btc` parseado.
- Visualizacion minima NUEVA `components/market-lab/BtcCompareStrip.tsx`
  (SVG puro, sin dependencias): dos lineas normalizadas (%) sobre la base
  comun declarada, leyenda "token %" / "BTC %", aviso "contexto informativo;
  no es senial ni rentabilidad". El precio absoluto NO se superpone. Badge =
  valores al cursor coherentes con el backend.

## 5. Aceptacion (pruebas)

Backend (`test_kline_btc_context.py` + extensiones en
`test_kline_indicators.py`/`test_market_stream.py`): formulas a mano;
alineacion temporal (arreglos reordenados no cambian valores); invariancia
ante futuros distintos; huecos → motivo; warmup; BTC ausente; BTC atrasada
(lagging) sin arrastrar viejos; token==BTC → sin bloque y sin 2a suscripcion;
cierre BTC actualiza el frame `context`; desconexion libera ambos
consumidores; dos sesiones comparten la suscripcion BTC (refcount);
0 upstream REST medido (ledger 0, mode cache+ws real).
Frontend: sanitizacion/identidad/fusion/badge/strip; bloques corruptos o de
otra identidad descartados enteros. `tsc`/`eslint` 0.
Navegador: demo local (`scripts/btc_context_public_demo.py`, seed + fake WS
loopback + guardia DNS): badge coherente con los frames, strip visible con
base declarada, hueco de BTC → UNKNOWN visible, actualizacion incremental sin
reload, cambio de simbolo/intervalo limpia el contexto, una sola conexion
combinada y suscripcion BTC no duplicada (health + log del fake), 0 publicas
(browser_external 0, ledger 0). Capturas: token vs BTC + hueco BTC.
Restauracion canonica al terminar (patron de la demo anterior).

## 6. Fuera de alcance / rollback

- Sin estrategia, sin seniales, sin paper prospectivo, sin ordenes, sin
  optimizacion, sin pagos, sin movil. Desktop only.
- Rollback: quitar campo aditivo `context_btc`/frames `context`, el strip y
  el modulo; `market-indicators/v1` queda intacto; no hay migracion ni datos
  persistidos nuevos.
