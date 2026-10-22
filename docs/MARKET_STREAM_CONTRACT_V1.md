# Contrato: actualización continua de velas (`market-stream/v1`)

Fecha: 2026-10-22. Base: `469e282`. Estado: **contrato definido antes de implementar**;
la implementación se documenta aparte en `CURRENT_STATE`. La ventana Binance viva
**no está autorizada** en este bloque: este contrato se valida con transporte
simulado y queda preparado para una autorización separada.

Ámbito: dashboard V2 de escritorio, presupuesto cero, **observación**. No hay
órdenes, capital, paper con datos vivos, estrategias ni indicadores nuevos. El
monitor del bot (`probe.py`) y sus suscripciones canónicas **no se modifican**.

---

## 1. Identidad

| Campo | Valor |
|---|---|
| `contract_version` | `market-stream/v1` |
| `venue` | `binance` |
| `market_type` | `usd_m_futures` |
| `api_family` | `fapi` |
| `transport` | websocket público `wss://fstream.binance.com/market/stream?streams=…` |
| `stream_name` | `<symbol>@kline_<interval>` (símbolo **minúsculas en el cable**) |
| `source` | `ws_kline` (stream) · `cache` (snapshot leído del almacén existente) |
| `symbol` | canónico en mayúsculas dentro del sistema (`BTCUSDT`) |
| `interval` | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` (mismo conjunto que el explorador; `1M` excluido) |
| `session_id` / `run_id` | `null`: no es una sesión ni una corrida |

El endpoint `/market` es obligatorio: en el esquema vigente de Binance los
klines pertenecen a *Market*, y una conexión sin ruta solo recibe *Public*
(`Important WebSocket Change Notice`). Se descarta `/ws/<stream>` en favor de
`/stream?streams=` porque el conjunto de suscripciones cambia en caliente y
porque el modo combinado es el recomendado por el propio exchange.

## 2. Tiempos (todos en milisegundos Unix UTC)

| Nombre | Origen | Semántica |
|---|---|---|
| `open_time_ms` (`k.t`) | venue | apertura de la vela; `t + interval_ms - 1 = T` |
| `close_time_ms` (`k.T`) | venue | último ms de la vela (inclusivo) |
| `event_ms` (`E`) | venue | cuándo el exchange generó el evento |
| `received_ms` | local (reloj de pared) | cuándo el servicio leyó el mensaje del socket |
| `available_ms` | local | `= received_ms`: no hay fuente primaria distinta; se declara así y no se inventa un “venue publish time” |
| `closed_known_ms` | local | `= received_ms` del mensaje con `x=true` |
| `generated_at_ms` | local | cuándo el backend construyó el payload |

Unidades explícitas en cada payload: `{"unit":"ms","epoch":"unix_utc"}`. La
conversión a segundos ocurre **solo** en la frontera de Lightweight Charts
(`Math.floor(ms/1000)`), nunca en el backend.

`age_ms = generated_at_ms - received_ms` de la **última actualización del
símbolo/intervalo suscrito**. No existe un “last update” global: un mensaje de
otro símbolo no puede rejuvenecer este estado.

## 3. Vela provisional y vela cerrada

- `x=false` → **provisional**: OHLC reales observados hasta ese instante,
  `closed=false`, `close_time_ms=null` (el cierre aún no está confirmado).
- `x=true` → **cerrada**: `closed=true`, `close_time_ms = T`, y la vela queda
  **bloqueada**: cualquier `x=false` posterior con el mismo `open_time` se
  descarta (nunca se reabre una vela cerrada).
- No se fabrican OHLC: si falta `o/h/l/c` o no son numéricos, el mensaje se
  rechaza y se cuenta (`invalid`), no se rellena.
- Volumen: `base_volume` desde `k.v` (unidad = activo base) y `quote_volume`
  desde `k.q` (unidad = quote). Si el mensaje no los trae, quedan `null`; nunca
  `0`.

## 4. Orden, deduplicación y mensajes atrasados

Clave de una vela: `(symbol, interval, open_time_ms)`. Reglas, aplicadas en este
orden:

1. **Ruta por stream**: un mensaje cuyo `stream` no corresponde a ninguna
   suscripción activa se descarta (`unrouted`).
2. **Identidad**: `data.s` y `data.k.i` deben coincidir con la suscripción; si
   no, se descarta (`identity_mismatch`).
3. **Atrasado**: si `open_time_ms < closed_through_ms` (última vela cerrada
   conocida) → se descarta y se cuenta `late`.
4. **Fuera de orden dentro de la vela**: si el mismo `open_time` llega con
   `event_ms` menor que el último `event_ms` aplicado → se descarta
   (`out_of_order`).
5. **Cierre**: `closed=true` gana siempre y sella `closed_through_ms`.
6. **Duplicado**: mismo `open_time` y mismo OHLC/volumen → se responde con el
   último estado conocido pero no se re-emite a los consumidores (`duplicate`).
7. **Orden de entrega**: los consumidores reciben eventos en orden de
   `open_time` ascendente y, dentro de la vela, en orden de `event_ms`.

Cada evento entregado lleva `seq` monótono **por suscripción**, para que el
navegador pueda detectar un salto (indicaría un consumidor que perdió eventos).

## 5. Snapshot + stream sin huecos

Alta de un consumidor para `(symbol, interval)`:

1. Se crea/refuerza la suscripción (refcount) y se activa el **buffer**.
2. Se envía `hello` con identidad, política de frescura y límites.
3. Se toma el **snapshot** del almacén existente (`market_cache` + canónico,
   `allow_fetch=false`, misma ventana que pidió el navegador). El servicio **no**
   vuelve a pedir REST para el snapshot: el explorador ya lo adquirió y lo dejó
   en caché. Si el almacén no tiene la ventana, el snapshot se declara
   `NO_COVERAGE` y no se inventa nada.
4. Se fija `deliver_from_ms = observed.end_ms` (última vela del snapshot) y se
   vacía el buffer: se entregan las velas con `open_time >= deliver_from_ms`,
   deduplicadas por `open_time`, **cerrada gana sobre provisional**.
5. A partir de ahí, cada mensaje del socket se entrega de inmediato.

El buffer está acotado (`PENDING_MAX=256` por suscripción). Si se desborda
durante el handshake, se descarta lo más antiguo, se emite `gap` con
`reason="BUFFER_OVERFLOW"` y el consumidor debe considerarse en recuperación: se
prefiere declarar el hueco a fingir continuidad.

## 6. Conexión, frescura y estados

Presupuesto de frescura (documentado, no “LIVE por socket abierto”):

| Estado | Condición (para el símbolo/intervalo **solicitado**) |
|---|---|
| `CONNECTING` | handshake en curso o aún sin primer mensaje del stream |
| `RECEIVING` | socket conectado **y** `age_ms <= FRESH_MS` (10 000 ms) |
| `STALE` (OBSOLETO) | `FRESH_MS < age_ms <= STALE_MS` (60 000 ms) |
| `RECOVERING` | hay una reparación REST de huecos en curso (puede convivir con `RECEIVING`) |
| `DISCONNECTED` | socket caído **o** `age_ms > STALE_MS` |

`LIVE` (etiqueta visible) exige **las cuatro** condiciones:

1. `connection.state == "RECEIVING"`;
2. socket conectado;
3. la última actualización pertenece al `(symbol, interval)` solicitado;
4. `age_ms <= FRESH_MS`.

Si cualquiera falla, la UI no escribe `LIVE`: escribe el estado real y la
antigüedad. Un socket abierto sin datos frescos no es LIVE.

Los estados se calculan en el backend y el navegador **solo** los presenta; no
los recalcula a partir de su propio reloj salvo el `age_ms` visible (que se
recalcula localmente para la cuenta atrás y se etiqueta como tal).

## 7. Errores y recuperación

- **Socket**: reconexión con backoff exponencial `1s → 30s` y **jitter ±25 %**.
  Tras 20 fallos consecutivos se deja de reintentar y el estado queda
  `DISCONNECTED` con `reason="RETRY_BUDGET_EXHAUSTED"`; se reanuda cuando un
  consumidor vuelve a pedir el stream (nueva suscripción).
- **`serverShutdown`** (evento del exchange) y **corte a las 24 h** de la
  conexión: se reconecta de inmediato, sin backoff largo.
- **Huecos**: al reconectar y al detectar un salto entre velas cerradas
  (`next.open_time != prev.open_time + interval_ms`), se pide REST acotado con
  `history_client.paginate_klines` (`max_pages=2`, `limit=500`). Resultado:
  `complete`, `partial` o `failed`, siempre publicado como evento `gap`.
  Una reparación parcial **no** se oculta: la UI muestra el tramo faltante.
- **Mensajes inválidos**: se cuentan (`invalid`, `unrouted`, `identity_mismatch`,
  `late`, `out_of_order`, `duplicate`) y se exponen en `/health`. No se
  reintentan ni se “arreglan”.
- **Consumidor lento**: cola de 256 eventos; si se llena, se cierra ese
  consumidor (reconectará y rehará snapshot) en vez de bloquear el hub.
- **Servicio detenido**: el BFF responde `available=false`; el navegador
  conserva el histórico REST y muestra “servicio de datos detenido”.

## 8. Presupuesto

| Recurso | Límite |
|---|---|
| Conexiones WS al exchange | **1** (compartida, modo combinado) |
| Streams simultáneos | **6** (`MAX_SUBSCRIPTIONS`) |
| Consumidores (pestañas/SSE) | **12** en total, **4** por stream |
| Mensajes de control al exchange | ≤ 2/s (límite oficial 10/s) |
| Mensajes por stream | kline ≈ 1–2/s (documentado por Binance; se **mide** en la ventana viva) |
| Memoria por stream | anillo de 300 velas cerradas + 1 provisional + cola de 256 eventos ≈ 60–90 KB |
| Memoria total del servicio | ≤ 2 MB con los 6 streams llenos |
| Disco por actualizaciones | **0** (no se persiste ninguna actualización) |
| REST de recuperación | ≤ 6 peticiones/min, 2 páginas por reparación, 500 velas/página |
| Reintentos de recuperación | 0 bucle: un fallo se publica como hueco |
| Retención | solo memoria; al liberar la suscripción se descarta el anillo |

Conexión de navegador: 1 `EventSource` por pestaña/gráfico; al cerrar la pestaña
el BFF aborta el upstream y el servicio decrementa el refcount.

## 9. Ciclo de vida y separación

- **Servicio de datos** (`market_stream_service.py`): arranque y parada
  explícitos (`--port`, `--stop`, PID en `data/market-stream/service.json`).
  Escucha **solo** en `127.0.0.1`.
- **Monitor del bot**: proceso distinto, suscripciones intactas. Abrir un
  gráfico no lo arranca ni lo detiene.
- **Sesiones paper**: sin cambios; el stream no escribe sesiones ni resultados.
- **Estado de conexión del navegador**: se deriva de los eventos del servicio;
  no se deduce de la existencia de un socket.

Cerrar la última pestaña de un stream no cierra el servicio; libera la
suscripción tras `IDLE_GRACE_S=30`. Ver el catálogo no suscribe nada. Abrir un
gráfico no abre posiciones, no inicia simulación y no añade el símbolo al
universo.

## 10. Almacenamiento

- **No se persiste ninguna actualización** del stream (ni velas provisionales ni
  cerradas): no hay escrituras nuevas en `data/`.
- El snapshot usa el almacén existente en modo lectura (`market_cache` +
  `historical.db`). El REST de reparación escribe en la caché del explorador
  **solo** mediante el escritor existente (`market_cache.upsert_klines`), y solo
  velas cerradas recuperadas; nunca en `microprobe.db` ni `historical.db`.
- Retención: memoria, por suscripción, liberada al quedarse sin consumidores.
- Sin migraciones ni borrados: no se toca evidencia ajena.

## 11. Eventos SSE (`Content-Type: text/event-stream`)

| Evento | Contenido |
|---|---|
| `hello` | `contract_version`, `identity`, `policy` (frescos/obsoletos), `limits`, `service` (pid, started_at_ms) |
| `snapshot` | `window`, `candles[]`, `observed{}`, `coverage{}`, `source`, `generated_at_ms` |
| `candle` | vela provisional (`closed=false`) con `seq`, `event_ms`, `received_ms` |
| `closed` | vela cerrada (`closed=true`, `close_time_ms`) |
| `gap` | `expected_from_ms`, `expected_to_ms`, `status`, `missing[]`, `requests`, `reason` |
| `status` | `connection.state`, `socket{}`, `last_message_ms`, `last_kline_open_ms`, `age_ms`, `live`, `reason` |
| `heartbeat` | `now_ms`, `last_message_ms`, `age_ms`, `connection.state` (cada 5 s) |
| `error` | `code`, `detail` (p. ej. `MAX_CONSUMERS`, `INVALID_INTERVAL`) |

`retry: 5000` en el primer chunk. El navegador limita sus reintentos
(`MAX_CLIENT_RETRIES=6`) y después muestra `DESCONECTADO` sin fingir conexión.

## 12. Métricas (`GET /health`)

`connection{state, since_ms, attempts, reconnects, last_error}`, `streams[]`
(`symbol`, `interval`, `consumers`, `messages`, `last_received_ms`,
`last_kline_open_ms`, `closed_through_ms`, `gaps`, `recoveries`,
`invalid/late/out_of_order/duplicate`), `counters` globales, `limits`,
`started_at_ms`, `pid`. Sin secretos y sin datos de cuenta.

## 13. Fuera de contrato

Indicadores, señales, objetivos, órdenes, capital, paper con datos vivos,
estrategias, optimización, móvil, REA, Antislop. Nada de esto se implementa ni se
simula aquí.

## 14. Ruta de retirada

1. Quitar `<MarketStreamBadge/>`/hook de `ContractExplorer.tsx`.
2. Borrar `frontend/src/app/api/v1/market-stream/`, `frontend/src/lib/market-stream.ts`
   y `frontend/src/lib/use-market-stream.ts`; revertir la rama `stream` de
   `PriceChart.tsx` (el modo Paper y `paper-chart/v1` no dependen de ella).
3. Borrar `src/microstructure_probe/market_stream_service.py`,
   `market_stream.py`, `scripts/market_stream_service.py` y
   `tests/test_market_stream.py`.
4. Borrar `data/market-stream/` (PID/log del servicio propio).
5. No hay migración de datos: no existe almacenamiento nuevo que retirar.
6. Borrar `scripts/market_stream_window.py`, `tests/test_market_stream_window.py`,
   `frontend/src/app/api/v1/market-stream/route.test.ts` y
   `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md`.

## 15. Verificación de la cadena real

La ventana que recorre `Binance → hub → servicio SSE → BFF → gráfico` está
descrita en [`MARKET_STREAM_LIVE_WINDOW_PLAN.md`](MARKET_STREAM_LIVE_WINDOW_PLAN.md):
presupuesto, comandos, capturas DOM, reglas de parada y semántica
`PASS`/`FAIL`/`UNKNOWN`. El script `scripts/market_stream_window.py` reutiliza
este servicio (no crea otro) y separa adquisición de veredicto. Hasta que esa
ventana se ejecute con autorización, la recepción real de Binance permanece
`UNKNOWN`.

