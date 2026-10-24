# Cierre F-CHART-BINANCE-04 — evidencia separada por planos (2026-10-24)

Base de partida `965ab87`. El veredicto medido de la ventana real sigue siendo
**`FAIL`** y su evidencia no se reescribe. Este documento separa cuatro planos
que la entrega anterior mezclaba, y añade la evidencia controlada posterior
(sin Binance) que demuestra la corrección.

## 1. Recepción real y `LIVE` — acreditado por la captura #1 (Binance real)

| Dato | Valor |
|---|---|
| Ventana | `2026-10-24T00:47:04Z` → `00:48:27Z` (83,46 s de 180 s) |
| Captura #1 | `00:47:46Z` — `docs/evidence/market-stream-window-2026-10-23-dom-1.json` |
| Identidad | `Binance USD-M · BTCUSDT · 1m · market-stream/v1` |
| Estado del panel | `RECIBIENDO` + `LIVE`, 299 velas, `nav=1`, `reload=0` |
| Cadena | 1 WS combinada, 1 intento, 0 reconexiones, 96 eventos BTCUSDT + 14 MINAUSDT |
| BFF | 96 eventos con identidad `BTCUSDT/1m` |

Esto acredita **recepción real** y que la UI mostró `LIVE` en su momento. No
acredita el cierre ni el aviso de desconexión (planos 3 y 4).

## 2. Captura #2 — fuera de la ventana (no válida para `LIVE`)

`00:48:29Z`, `docs/evidence/market-stream-window-2026-10-23-dom-2.json`: misma
identidad, 303 velas, paginación `300→303` sin error, **pero el servicio ya
estaba parado** (la espera de 20 s expiró durante la paginación). El check
`dom_state_live` falla y así queda registrado. No se promociona a `PASS`.

## 3. Desconexión final — sin `LIVE` pero sin el aviso esperado

`00:50:06Z`, `docs/evidence/market-stream-window-2026-10-23-dom-stop.json`:
`DESCONECTADO`, `no LIVE`, 303 velas conservadas, **sin**
`explorer-stream-down`. Check `dom_after_stop` en rojo.

**Causa demostrada (código, antes de la corrección):**

1. El BFF devolvía `upstream.body` en crudo: no declaraba fin ni error del
   upstream, no emitía causa y no abortaba el upstream al cancelar el cliente.
2. El hook, ante `onerror`, solo incrementaba `attempts` (sin cambio visible) y
   `LIVE` se derivaba de un `status` congelado: sin mensajes nuevos, el panel
   podía seguir pareciendo vivo o quedarse mudo sin causa hasta agotar 6
   reintentos (≈30 s) o para siempre si el SSE del BFF seguía abierto.

## 4. Consumidor residual — la parada forzada no prueba la liberación

`consumers_tras_cerrar = 1` era el propio navegador (pestaña abierta). Es un
consumidor legítimo mientras la página vive; **no** se presenta la parada
forzada del proceso como prueba de liberación correcta. La liberación se mide
en el plano 5, con el servicio vivo.

## 5. Evidencia controlada posterior (sin Binance)

Transporte: WS falso local en `127.0.0.1:8799` + servicio real en `8791`
(`--base-url` al WS falso) + BFF real en `3020`. Cero contacto con Binance.

### 5.1 Liberación del consumidor (BFF/servicio, `ZZZUSDT` 1h)

`docs/evidence/market-stream-controlled-disconnect-2026-10-24.json`:

| Medición | Resultado |
|---|---|
| Cliente abre y recibe `event: candle` | sí (`HTTP/1.1 200 OK`) |
| Consumidores con el cliente abierto | 1 |
| Cliente cierra; servicio **sigue vivo** | consumidores **0 en 14 ms** (`wall 15 ms`) |
| Servicio se detiene (`POST /shutdown` 200) | EOF en el cliente en **6025 ms** |
| Frame de causa | `event: error` con `code=STREAM_UPSTREAM_ERROR` |
| Servicio | exit 0; `/health` rechazado después |

### 5.2 DOM real del panel (navegador, `ETHUSDT` 1h, transporte controlado)

`docs/evidence/market-lab-controlled-disconnect-2026-10-24.json` +
`market-lab-controlled-live-2026-10-24.png` / `...-down-2026-10-24.png`:

| Momento | Panel |
|---|---|
| Con el feed controlado | `RECIBIENDO`, `LIVE`, 300 velas, consumidores 1, socket conectado |
| 12 ms después de `POST /shutdown` | `DESCONECTADO`, `no LIVE`, causa visible (`TypeError: UND_ERR_SOCKET · reintento 2`) |

El histórico y el catálogo se interceptaron en el navegador con payloads
sintéticos para no tocar REST de Binance. **Esta captura `LIVE` es de transporte
controlado: no acredita recepción real** (eso es el plano 1). Inspección visual:
`NOT_REVIEWED` (modelo de texto; sin proveedor de visión).

### 5.3 Frescura local (hook, pruebas unitarias)

`frontend/src/test/use-market-stream.test.tsx` (10/10): con temporizadores
falsos, 11 s de silencio retiran `LIVE` (`STALE` + causa de frescura) y 61 s
pasan a `DISCONNECTED`; `onerror` y un `event: error` con código muestran la
causa de inmediato, sin esperar a agotar reintentos.

### 5.4 Paginación `300→303` (copia de la caché, sin red)

`docs/evidence/pagination-300-303-2026-10-24.json`:

| Escenario | Petición antigua (`to = borde reciente`) | Petición nueva (`to = borde - paso`) |
|---|---|---|
| Bloque anterior **no** almacenado | 302 devueltas, **302 solapan**, 0 nuevas | 0 devueltas (no hay historia) |
| Bloque anterior almacenado | 602 devueltas, 302 solapan, 300 nuevas | **300 devueltas, 0 solapan** |

El merge conserva el extremo reciente (última apertura `1792802820000`). El
`300→303` medido en la ventana = 300 cargadas + 3 actualizaciones del stream, no
un bloque nuevo: exigir `+300` era un criterio equivocado. La corrección pide el
bloque estrictamente anterior y antepone por `open_time` sin reemplazar.

## 6. Pruebas ejecutadas (focalizadas, sin repetir la suite completa)

| Suite | Resultado |
|---|---|
| `tests/test_market_stream.py` | 29/29 (incluye liberación inmediata al cerrar el SSE) |
| `tests/test_market_stream_window.py` | 25/25 |
| `frontend` route BFF + hook + explorador | 28/28 |
| `market-chart-contract.test.ts` | 13/13 (incluye 300→303 y bloque agotado) |
| `tsc --noEmit` / `eslint` (archivos tocados) | 0 / 0 |
| `next build` + `/market-lab` | OK, `BUILD_ID=XozH8PXJA4yZR59XphpyH`, HTTP 200 |

## 7. Desviaciones declaradas

- Durante el diagnóstico se arrancó dos veces el servicio **sin** `--base-url`
  (una para inspeccionar el DOM y otra para una sonda SSE): abrió el WS público
  de Binance ~9 s y ~30 s respectivamente. Sin claves, sin API privada, sin
  órdenes. No es una ventana de aceptación y **no se usa como evidencia**; el
  resto de pruebas controladas usó el WS falso local.
- Una página `/market-lab` con `0GUSDT` 1h seleccionado (catálogo real, sin
  interceptar) encadenó **12 peticiones REST públicas** a `/fapi/v1/klines`
  entre `01:43:47Z` y `01:44:18Z`, que **añadieron 3.552 velas** a la caché
  derivada `data/market-cache/market_cache.db` (`0GUSDT` 1h pasó de 47 a 3.599
  filas) y 12 filas a `market_fetch_ledger`. No se perdió ninguna fila previa:
  el bloque descargado es historia anterior. El cliente exacto que disparó la
  cadena queda `UNKNOWN`. Las DBs canónicas (`microprobe.db`, `historical.db`)
  **no** se tocaron (mtime 2026-10-15); la caché es derivada y las velas son
  historia real de Binance, no datos inventados. Se hizo
  `wal_checkpoint(TRUNCATE)` para dejarla consistente. El veredicto y la
  evidencia de la ventana no cambian (se midieron antes).
- Riesgo residual detectado, no corregido en este bloque: una sola interacción
  puede encadenar varias descargas de "anteriores" (12 medidas, ~3,5k velas) en
  lugar de una. Queda en `docs/TASK_QUEUE.md`.
- El primer `npm run build` se detuvo con el aviso de seguridad de Next.js; el
  mismo comando se reintentó y completó. No se ejecutó `next upgrade`.
