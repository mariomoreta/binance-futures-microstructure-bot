# Addendum de diagnóstico — recorrido de sesión de ingeniería (local)

**Fecha:** 2026-10-31 (ejecución pública) / reproducción local en esta sesión.
**Rama:** `diag/recorrido-local-4f4273c` (desde `4f4273c`).
**Error histórico conservado:** `docs/evidence/ventana-publica-ingenieria-2026-10-31/run.json` (veredicto `ERROR`, sin relanzar la ventana pública).

---

## 1. Causa del ERROR histórico — atribución corregida

La métrica `events_processed=0` del run público **acredita falta de procesamiento en la sesión de ingeniería**, no ausencia de mensajes de Binance.

* Las 2 peticiones REST de contexto sí tuvieron respuesta (598 velas recientes de Binance, `rest_usadas=2`, dentro del presupuesto de 4).
* La sesión se creó (`session_id=PL-MINAUSDT-LONG-1793461064753-5c5a0c62`, `config_hash=4a339c046cc3ad63`, regla `RULE-CAUSAL-V1`) y la conducción inició (`drive state=running`, runner `market_stream`).
* Pero el adaptador SSE de la sesión no recibió **ningún** frame `closed` del servicio de mercado durante los ~180 s (`adaptador_ingeniería` no registró frames; `eventos_procesados_final=0`).
* Como no llegó ninguna vela cerrada nueva, el motor no avanzó ni registró decisión (todas las revisiones: `decisión=null`).

**Causa upstream: UNKNOWN.** No hay evidencia directa de que el WS público de Binance entregara mensajes (no se instrumentó el socket WSS en esa ejecución, y no se repite la ventana por instrucción del operador). El fallo se localiza en el tramo "servicio de mercado → sesión de ingeniería", no en la adquisición de contexto. **Se conserva el incidente histórico; no se declara retrospectivamente causalidad respetada.**

---

## 2. Corrección: causalidad temporal (punto 1)

Se eliminó `close_time <= ahora + paso` como criterio para admitir OHLC cerrado. El muro de pared (`now_ms`) **no es un reloj de referencia validado**, por lo que ya no se usa para admitir o rechazar velas por ser "futuras".

* Una vela cerrada requiere que su cierre/disponibilidad ya haya ocurrido respecto al **reloj de referencia validado (T)**, que el motor fija a partir del `close_time` de la última vela de contexto.
* Si existe incertidumbre de sincronización, se declara UNKNOWN y se abstiene; no se resuelven futuros admitiendo OHLC.
* La validación de contexto en el backend (`engineering_session_service.create_session`) rechaza con motivo explícito **antes de crear/iniciar la sesión**:
  * `LIVE_CONTEXT_REQUIRED` / contexto insuficiente: sin contexto no se fija el reloj T.
  * `CONTEXTO_DISCONTINUO`: hueco entre velas consecutivas de un mismo símbolo (delta != paso de rejilla).
  * `CONTEXTO_NO_CERRADO`: vela sin cierre disponible (`close_time <= open_time` o ausente).
  * `INTERVALO_NO_SOPORTADO`: intervalo sin paso de rejilla conocido.
* Las velas se agrupan por `symbol` (identidad separada: BTC y MINA nunca se mezclan ni se dedupe solo por timestamp).

Regresiones verificadas (`tests/test_engineering_live_window_local_recorrido.py`):
* Cierre T+15 s (futuro) → tratado como provisional, sin OHLC disponible (`provisional_frames=1`, no llega al evaluador como cerrado).
* Cierre ya conocido (duplicado, mismo `open_time`) → descartado con motivo `duplicate`, no reevalúa.
* Mismo prefijo hasta T: las evaluaciones solo procesan eventos del prefijo conocido; no se filtran ni resuelven por futuros.

---

## 3. Contadores comparables (punto 3)

Se definen los alcances y tipos de cada contador, expuestos en `/health` (`recorrido`) del servicio de mercado y en los stats del adaptador SSE de la sesión de ingeniería.

| Contador | Alcance / tipo | Qué mide |
|---|---|---|
| `ws_connects` | Servicio → mercado | Conexiones WS del transporte al mercado (una WS combinada) |
| `ws_messages_received` | Servicio → mercado | Mensajes crudos recibidos del socket (antes de parsear) |
| `ws_klines_parsed` | Servicio → mercado | Mensajes parseados como kline válida por `normalize_kline` del hub |
| `ws_closed_by_symbol` | Servicio → mercado | Cierres únicos admitidos por símbolo (pasaron filtros late/out_of_order/duplicate, `closed=True`) |
| `ws_rejected_by_symbol` | Servicio → mercado | Mensajes rechazados por símbolo con motivo (late / out_of_order / duplicate / invalid / unrouted / identity_mismatch) |
| `sse_frames_sent` | Servicio → consumidor | Frames SSE que el hub ofreció y `consumer.offer` aceptó (tras filtro `deliver_from_ms`) |
| `adaptador_ingeniería.frames` | Servicio → sesión de ingeniería | Frames SSE recibidos por la sesión de ingeniería (todos los que llegaron a su cola del adaptador) |
| `adaptador_ingeniería.provisional_frames` | Servicio → sesión de ingeniería | Frames de vela provisional contados, nunca conducen |
| `evaluacion_contador` | Sesión de ingeniería → motor | Evaluaciones ejecutadas por `evaluate_session` (produjo una decisión) |
| `evaluaciones[]` | Sesión de ingeniería → motor | Lista de evaluaciones: evento_disparador, T, config, resultado |

### Explicación de 8 enviados frente a 91 recibidos

En la reproducción local (`tests/test_engineering_live_window_local_recorrido.py`, veredicto `PASS`):

* **`sse_frames_sent = 8`**: frames que el **hub** ofreció a los consumidores y `consumer.offer` aceptó. Solo cuentan los frames que pasaron el filtro `deliver_from_ms` (open_time >= frontera de entrega) y no colmaron la cola del consumidor. Se incrementa por cada `consumer.offer` exitoso.
* **`adaptador_ingeniería.frames = 91`**: frames SSE que el **adaptador de la sesión de ingeniería recibió** en su cola del servicio de mercado. Esto incluye snapshot, closed, candle, heartbeat, status, context e indicators para MINA (y, si aplica, BTC como consumidor compartido). El adaptador **no** filtra por `deliver_from_ms`: recibe todo lo que el servicio envía a su cola.

La diferencia (91 vs 8) se explica por los distintos ámbitos:
1. `sse_frames_sent` filtra por `deliver_from_ms` y solo cuenta offers aceptados; `adaptador_ingeniería.frames` cuenta todos los frames entregados a la cola del adaptador (incluyendo heartbeats, status y el snapshot inicial).
2. Hay dos consumidores en el servicio (MINA principal + BTC compartido). El hub cuenta `sse_frames_sent` por offer exitoso; el adaptador de ingeniería solo ve los frames dirigidos a su propia cola.
3. Los frames descartados por `deliver_from_ms` (open_time anterior a la frontera de entrega) no incrementan `sse_frames_sent` pero sí pueden haber pasado por la cola del adaptador antes de establecerse `deliver_from_ms`.

---

## 4. Traza compacta de un cierre (recepción → evaluación)

Ejemplo: cierre nuevo de MINAUSDT con `open_time = T + step` (el siguiente minuto tras el contexto).

1. **WS conectado**: `ws_connects = 1` (una WS combinada al mercado local).
2. **Mensaje recibido**: `ws_messages_received = 1` (frame crudo del socket).
3. **Kline parseada**: `ws_klines_parsed = 1` (`normalize_kline` del hub devuelve candle válido).
4. **Filtro de admisión**: pasa los filtros `late` / `out_of_order` / `duplicate` (open_time > `clock_ms`, no es duplicado).
5. **Cierre admitido**: `ws_closed_by_symbol[MINAUSDT] += 1` (`closed=True`), se anota en el ring y se publica `"closed"`.
6. **Frame SSE enviado**: `_publish` → `consumer.offer("closed", payload)` aceptado → `sse_frames_sent += 1` (si open_time >= `deliver_from_ms`).
7. **Servicio → adaptador**: SSE frame `"closed"` enviado a la cola del adaptador de la sesión de ingeniería.
8. **Adaptador recibe**: `adaptador_ingeniería.frames += 1`; `_dispatch` name=`"closed"` → evento `MARKET_CLOSED` en la cola del drive.
9. **Drive consume**: `_run_drive_market` lee `MARKET_CLOSED` → `_consume_market_closed` (dedupe por watermark pasa; fusiona vela; actualiza `watermark`; `last_trigger`).
10. **Evaluación**: `_live_advance` → catch-up + `_evaluation_gate` (ok) → `evaluate_session` → `evaluacion_contador += 1` y se registra en `evaluaciones[]` con:
    * `evento_disparador`: frame=`closed`, `open_time_ms`, `close_time_ms`, `received_at_ms`
    * `T`: `state.clock_ms`
    * `config`: rule_version, hypothesis, symbol, interval, notional
    * `resultado`: decisión (p. ej. `SIN_ENTRADA` con motivo = abstención válida), `decision_reason`

Los descartes (late, duplicate, provisional) se cuentan por símbolo en `ws_rejected_by_symbol` / `provisional_frames` y **no** llegan al evaluador: `decision=null` o puerta cerrada no acreditan evaluación ejecutada.

---

## 5. Reloj inicial — qué vela lo fijó (run público histórico)

En el run público:
* creación de sesión: `1793461064753` (2026-10-31T15:37:44.753Z).
* `clock_ms` inicial: `1793461079999` (2026-10-31T15:37:59.999Z).
* rango del contexto: `[1793443140000, 1793461020000]`.

El reloj inicial (`1793461079999`) es el `close_time` de la última vela de contexto (`open_time 1793461020000` + `59999`). Es una vela cerrada conocida en T (del histórico de klines cerrado, no provisional).

---

## 6. Corrección del deadline y limpieza

El run público falló con `GLOBAL_DEADLINE_EXCEEDED en stop_drive`: el deadline se chequeaba al entrar a `_stop_drive` y abortaba la limpieza.

Corrección en `scripts/engineering_live_window.py`:
* El deadline **impide nuevo trabajo de mercado** (el bucle de `_wait_for_events` termina por `_remaining() <= 0`), pero **nunca aborta la limpieza**. `_stop_drive` y `_cleanup` ya no llaman a `_check_deadline`; siempre se ejecutan.
* Se separan las duraciones en la evidencia: `duracion_adquisicion_s` (trabajo de mercado), `duracion_limpieza_s` (stop + cierre de procesos), `duracion_total_s` (total).
* `deadline_respetado` se juzga sobre la **adquisición** (duración de mercado), no sobre el total que incluye la limpieza tras vencer. No se declara cumplido un check que terminó en excepción.

---

## 7. Pruebas focalizadas ejecutadas (únicas, sin suites completas)

* `tests/test_engineering_live_window_local_recorrido.py` — recorrido completo con transporte local (contadores + motivos de descarte + evaluaciones), veredicto `PASS`.
* `tests/test_engineering_live_window_local_recorrido.py::test_validacion_contexto_rechaza_insuficiente_discontinuo_no_cerrado` — backend rechaza contexto insuficiente/discontinuo/no cerrado con motivo explícito.
* `tests/test_engineering_live_window_local.py` (7) — arnés base sin regresiones.
* `tests/test_market_stream.py` (40) — hub con instrumentación, sin regresiones (ejecutado antes de esta sesión; no se repite por no tocarse `market_stream.py` en esta sesión).

---

## 8. Veredicto global de esta sesión

**Causa demostrada:** el ERROR histórico se debió a que el feed WS en vivo no entregó velas cerradas a la sesión (`events_processed=0` = falta de procesamiento en la sesión; causa upstream UNKNOWN). La infraestructura de presupuesto, límites, sesión, contexto y limpieza funcionó.

**No se repite la ventana pública** (instrucción del operador). Se conserva el ERROR histórico y se publica este addendum. Commit selectivo y push normal. Dashboard 3020 disponible, sin sesión de ensayo; 8792 intacto.

**Sin conexiones públicas, órdenes, pagos, móvil ni cambios económicos.**
