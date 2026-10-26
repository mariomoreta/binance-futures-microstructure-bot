# Indicadores compartidos V1 — inventario, subconjunto elegido y contrato (2026-10-25)

Objetivo del bloque (autorizado por el operador): **primera integración
vertical** de indicadores compartidos en `/market-lab`, con el backend como
única autoridad de cálculo y la misma salida versionada para gráfico y futuro
evaluador. Desktop exclusivamente, presupuesto cero, sin conexiones públicas.

## 1. Inventario de cálculos existentes y sus fuentes

Clasificación verificada en código (no por nombre de archivo):

| Cálculo | Estado en el proyecto | Fuente real | ¿Vive en el canal de velas de `/market-lab`? |
|---|---|---|---|
| Retornos log | **Implementado (live)** — `src/microstructure_probe/returns.py` (P1-04, buckets de 10 s, 1m…24h) | mark price WS | No: el canal de velas no tiene mark price |
| Velocidad / aceleración | **Implementado (live)** — `momentum.py` (P1-05, sobre la serie de retornos + ranking) | mark price WS | No |
| Volumen relativo | **No estaba implementado** (los baselines existentes son de flujo, en `flow.py`) | — (solo posible sobre velas) | NUEVO: `rel_volume_10` |
| Flow/delta comprador-vendedor | **Implementado (live)** — `flow.py` (P1-06, horizontes 10 s…15 m, baseline de flujo) | aggTrade WS | **Fuente ausente.** NO derivable de OHLC → declinado |
| VWAP | **Implementado (live)** — `market_structure.vwap_record` (P1-08, con flow + mark price) | aggTrade WS + mark price | Aproximación nueva sobre velas: `vwap_typical_10` (NO es el VWAP de negociación) |
| Spread | **Implementado (métrica)** — `metrics.spread_bps` + `book.py` (P1-07) | libro de órdenes WS | **Fuente ausente.** NO derivable de OHLC → declinado |
| Profundidad | **Implementado (live)** — `book.py` (P1-07, top-N, imbalance, slope) | libro de órdenes WS | **Fuente ausente** → declinado |
| Open interest | **Implementado (live)** — `open_interest.py` (P1-07, REST poll de `/fapi/v1/openInterest` + tracker en memoria) | REST público de OI | **Fuente no conectada** al canal de velas → declinado |
| Contexto BTC | Vivo por símbolo (motores P1); el canal de velas no trae el segundo símbolo | velas/precio BTCUSDT (fuente requerida) | Declinado en V1: la fuente no está en este canal. Las SOLICITUDES realmente necesarias no son un coste fijo (“+N upstream”): dependen de lo ya almacenado — 0 si BTCUSDT ya está en caché, y si falta, solo las páginas del tramo faltante que calcule el propio plan; separar fuente requerida de solicitudes necesarias evita presentar un coste como inevitable |

Regla estructural: **nunca** se deriva flujo comprador/vendedor, spread,
profundidad u OI a partir de OHLC. Lo que falta de fuente es `declined`
con motivo explícito en el bloque versionado — no un cero ni un
sustituto de aproximación.

## 2. Subconjunto mínimo elegido (compatible con las velas disponibles)

Definiciones completas (fórmula, unidades, ventana, calentamiento,
timestamp de disponibilidad y comportamiento ante huecos): contrato
`market-indicators/v1`, sección 11 de
`docs/MARKET_EXPLORER_CONTRACT_V1.md`. Resumen:

- `log_return_bps` — `10000·ln(close_t/close_{t−1})` (bps).
- `velocity_bps_5` — **retorno acumulado sobre la trayectoria de las últimas
  CINCO VELAS CERRADAS**: `10000·ln(close_t/close_{t−4})`. Necesita
  exactamente **5 cierres cerrados contiguos** (t−4..t) y acumula
  **4 saltos de intervalo**; NO es el "retorno de cinco intervalos completos"
  (ese sería t−5→t y requeriría 6 cierres). La ventana se valida por TIEMPO
  (rejilla de `open_time`), no por posiciones del arreglo (test anclado).
- `rel_volume_10` — volumen de la vela vs media de las 10 anteriores cerradas (ratio).
- `vwap_typical_10` + `vwap_dev_bps_10` — VWAP aproximado por precio típico
  ponderada por `base_volume` y desviación del close (precio quote / bps).

Elegidos por: (a) ser derivables de velas OHLCV cerradas sin inventar datos,
(b) no duplicar la semántica de los motores en vivo (aproximaciones distintas,
declaradas), (c) cubrir la terna mínima retornos/velocidad/volumen que el
futuro evaluador comparará con las columnas almacenadas en el caché.

No elegidos en V1: volatilidad realizada (distinta ventana, sin validar),
rango/swings/breakout (estructura ya vive en `market_structure.py` con
semántica de bloques del feed), flow/spread/depth/OI/BTC (fuente ausente).

## 3. Backend como autoridad

- Cálculo únicamente en el backend (`kline_indicators.py`) dentro de
  `series_payload`: el mismo JSON alimenta el gráfico y (más adelante) al
  evaluador. El navegador NO recalcula.
- Confirmados solo sobre velas cerradas; la vela provisional queda EXCLUIDA
  del bloque (`provisional_policy`, `"PROVISIONAL_EXCLUDED"`), separado por
  diseño: no hay indicadores provisionales en V1.
- `available_at_ms` = `open_time + interval_ms` (disponibilidad al cierre).
- Hueco/warmup/volumen ausente → `unknown{...}` con motivo; nunca 0
  (test: sin ceros inventados).
- Sin lookahead (test de perturbación futura).
- Bloque declina los cinco cálculos sin fuente con `declined[{name, reason}]`.

## 4. Integración en `/market-lab`

- El payload `market-series/v1` lleva el bloque opcional `indicators`
  (aditivo, el resto del contrato no cambia).
- El gráfico `market-chart/v1` publica `indicators: MarketIndicatorsBlock | null`
  (antes `never[]`); un bloque con versión/identidad/filas inválidas se
  descarta completo (null).
- Badge junto al gráfico (`market-chart-indicators`): versión, valores y
  UNKNOWN(motivo) de la vela bajo el cursor; vela provisional →
  "vela provisional excluida"; sin fila → "sin fila para la vela bajo el
  cursor"; sin bloque → "ninguno (ausente)".
- Cambio de símbolo/intervalo: el modelo se reemplaza completo; un bloque de
  otra identidad no puede colarse (guard de identidad en parse y en fusión).
- `mergeEarlierSeries` une filas validadas de ambos bloques (fila más
  reciente gana; `per_block_payload_windows` sin recálculo en el navegador).
- El feed de stream RECALCULA los indicadores en el backend al confirmarse
  una vela (ver §4bis abajo); hasta 2ffdede era una limitación declarada.

## 4bis. Actualización incremental por cierre (market-stream/v1, aditivo)

Limitación previa (declarada y verificada en 2ffdede): los indicadores solo
se calculaban al consultar histórico; una vela que cerraba por el stream
actualizaba velas pero no el bloque. Implementación mínima reutilizando el
servicio existente (sin contratos nuevos, sin estrategia, sin Binance):

1. **Snapshot** (`market_stream_service._snapshot`): el evento `snapshot`
   del SSE pasa a incluir el campo aditivo `indicators` — el MISMO bloque
   que ya calcula `series_payload` con `allow_fetch=False` y `client=None`
   (0 upstream).
2. **Cierre** (`_serve_stream`): la conexión lee velas del hub; al
   confirmarse un cierre (`event: closed`) reemplaza la vela en la ventana
   de LA SESIÓN (velas cerradas del snapshot + cierres del stream, dedup
   por `open_time`), recalcula el bloque y emite un frame SSE
   `event: indicators` nuevo con el bloque `market-indicators/v1`
   (`identity.source = "ws_kline"`) ANTES del frame `closed`. La vela
   provisional JAMÁS entra: no se añade a la ventana y por tanto no
   recalcula ni altera el último valor confirmado (test SSE de extremo a
   extremo anclado). Un fallo de cálculo no rompe el stream (frame omitido).
3. **Frontend**: `useMarketStream` añade el listener `indicators`
   (identidad por símbolo/intervalo de la conexión) y `mergeStreamIntoSeries`
   aplica `applyStreamIndicators`: sanitización de filas + guard de
   identidad + unión de filas (nuevo gana) — sin recálculo del navegador y
   sin recarga. Un bloque corrupto o de otra identidad se descarta entero.
4. **Semántica invariante**: las filas de velas ya cerradas no cambian
   después del cierre (ventanas fijas t−k..t); un bloque nuevo solo AÑADE la
   fila de la vela recién cerrada o la completa. Los `unknown` anteriores no
   se "reparan" con el stream: siguen declarados.

Badge con UNIDAD visible: `ret ±nn.nnbps`, `vel ±nn.nnbps`, `relvol n.nnnx`,
`vwapdev ±nn.nnbps` (vwap_typical_10 no es `supported`; unidad precio quote
conocida por símbolo, no impuesta en el badge).

## 5. Pruebas con datos locales (zero network)

Backend `tests/test_kline_indicators.py` (19): fórmulas exactas
hand-calculated; sin lookahead; exclusión de provisional y frontera de
cierre; huecos/warmup con motivo y sin ceros; volumen ausente en vela y
baseline; listas supported/declined + definitions; integración real de
`series_payload` sobre `MarketCache` temporal. Reconstrucción temporal:
ventanas validadas por tiempo y no por posición del arreglo
(`test_velocity_window_is_temporal_not_positional`);
recalculo incremental: `tests/test_market_stream.py` (34: sesión: provisional
excluida, hueco→GAP_IN_WINDOW, warmup→INSUFICIENT_CANDLES, intervalo
inválido omitido; SSE extremo a extremo: snapshot con bloque y frame
`indicators` por cierre, provisional sin frame).
Frontend: `market-indicators.test.ts` (19: incl. bloque del stream:
unión por identidad, identidad ajena descartada, corrupto intacto, payload
sin bloque lo recibe) + integrales en
`price-chart-market.test.tsx` (2, badge bajo cursor y sin bloque) +
anclado en `market-chart-contract` (13) + `market-stream-contract`
(bloque del stream cierra velas en el payload; ajeno no se mezcla).
`tsc` 0, `eslint` 0.
Evidencia con transporte local y `client=None` (0 upstream):
`docs/evidence/indicators-v1-2026-10-25.json`.

## 6. Qué queda pendiente (declarado)

- Volatilidad realizada, rango y estructura sobre velas cerradas: requiere
  decisión de ventana/semántica (no la heredada del feed).
- `build_recovery`: si se le conecta el gate del ledger (tarea vecina del
  bloque anterior), los indicadores del payload de reparación serán
  idénticos por construcción.
- Fuente de aggTrades/libro/OI en el canal de velas: fuera de alcance hasta
  nueva autorización (presupuesto y arquitectura).
