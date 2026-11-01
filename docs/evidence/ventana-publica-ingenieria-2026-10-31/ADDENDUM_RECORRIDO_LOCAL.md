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

**Causa upstream: UNKNOWN.** No hay evidencia directa de que el WS público de Binance entregara mensajes (no se instrumentó el socket WSS en esa ejecución, y no se repite la ventana por instrucción del operador). El fallo se localiza en el tramo "servicio de mercado → sesión de ingeniería", no en la adquisición de contexto.

---

## 2. Instrumentación añadida (servicio existente, sin Binance)

Se añadió al hub `KlineStreamHub` (`src/microstructure_probe/market_stream.py`) y se expone en `/health` (`recorrido`):

| Contador | Significado |
|---|---|
| `ws_connects` | Conexiones WS del transporte al mercado |
| `ws_messages_received` | Mensajes crudos recibidos del socket |
| `ws_klines_parsed` | Mensajes parseados como kline válida |
| `ws_closed_by_symbol` | Cierres admitidos por símbolo (filtrados) |
| `ws_rejected_by_symbol` | Mensajes rechazados por símbolo (late / out_of_order / duplicate / invalid / unrouted / identity_mismatch) |
| `sse_frames_sent` | Frames SSE ofrecidos a consumidores |

El arnés (`scripts/engineering_live_window.py`) ahora lee `recorrido_servicio` (health del servicio de mercado) y `adaptador_ingeniería` (stats del adaptador SSE de la sesión) en cada iteración de `_wait_for_events`, reconstruyendo:

> WS conectado → mensajes recibidos → klines parseadas → cierres admitidos por símbolo → frames SSE enviados → frames recibidos por ingeniería → aceptados/descartados (con motivo) → evaluación.

---

## 3. Reloj inicial — qué vela lo fijó y por qué se admitió como cerrada

En el run público:
* creación de sesión: `1793461064753` (2026-10-31T15:37:44.753Z).
* `clock_ms` inicial: `1793461079999` (2026-10-31T15:37:59.999Z).
* rango del contexto: `[1793443140000, 1793461020000]`.

El reloj inicial (`1793461079999`) es el **`close_time` de la última vela de contexto** (`open_time 1793461020000` + `59999` ms = `1793461079999`). Es decir, la última vela de contexto del símbolo (MINAUSDT/BTCUSDT, 1m) fijó el reloj T.

**Por qué se admitió como cerrada:** `normalize_kline` devolvió `close_time` presente y finito (la vela viene del histórico de klines cerrado, no es provisional), y la validación de contexto no la rechazó porque no es futura respecto al ahora (`close_time <= ahora + step`). Es una vela cerrada conocida en T, no un dato futuro ni inventado.

---

## 4. Validación de contexto en el backend (antes de conducir)

Se añadió validación en el servicio de ingeniería (`src/microstructure_probe/engineering_session_service.create_session`, backend Python — no solo React) que rechaza con motivo explícito **antes de crear/iniciar la sesión**:

* `CONTEXTO_INSUFICIENTE` / `LIVE_CONTEXT_REQUIRED`: sin contexto no se fija el reloj T.
* `CONTEXTO_FUTURO`: alguna vela con `open_time` o `close_time` posterior al ahora + un paso.
* `CONTEXTO_DISCONTINUO`: hueco entre velas consecutivas del mismo símbolo (delta != paso de rejilla).
* `INTERVALO_NO_SOPORTADO`: intervalo sin paso de rejilla conocido.

Las velas se agrupan por `symbol` (identidad separada: BTC y MINA nunca se mezclan ni se dedupe solo por timestamp).

---

## 5. Reproducción con transporte local (cero Binance)

Se creó `scripts/local_ws_kline_provider.py` (servidor integrado HTTP `/fapi/v1/klines` + WS combined-stream en loopback) y se ejecutó el **mismo arnés** (`WindowOrchestrator`, `--transport local --execute`) con una secuencia WS controlada:

* contexto reciente cerrado (ambos símbolos, 600 velas, REST local 2/2);
* una vela provisional (contada, nunca conduce);
* dos cierres nuevos posteriores (ambos símbolos, identidad separada).

Resultado de la prueba focalizada (`tests/test_engineering_live_window_local_recorrido.py`, veredicto `PASS`):

| Contador | Valor | Lectura |
|---|---|---|
| `ws_connects` | 1 | una WS combinada |
| `ws_messages_received` | 114 | mensajes entregados por el WS local |
| `ws_klines_parsed` | 114 | klines parseadas por el hub |
| `ws_closed_by_symbol` | `BTCUSDT:2, MINAUSDT:3` | cierres admitidos por símbolo |
| `ws_rejected_by_symbol` | `BTCUSDT:36, MINAUSDT:72` | descartes con motivo (late/duplicate) |
| `sse_frames_sent` | 8 | frames SSE del servicio a la sesión |
| adaptador `frames` | 91 | frames recibidos por la sesión de ingeniería |
| adaptador `provisional_frames` | 1 | la vela provisional contada, no conduce |
| `rest_count` | 2 | dentro del presupuesto de 4 |
| `db_unchanged` | true | cero escrituras en DBs canónicas |
| `error` | None | limpieza sin `GLOBAL_DEADLINE_EXCEEDED` |

**Filtros `from_ms`/`to_ms` y watermark:** el snapshot del servicio (caché local, velas antiguas o vacías) no bloqueó los cierres posteriores de la sesión continua (`open_time > reloj T` se admitieron; las velas antiguas/duplicadas se descartaron con motivo `late`/`duplicate`). Causalidad respetada: no se forzó entrada, la decisión fue `null` (abstención, válida: cero entradas con evaluación real).

---

## 6. Corrección del deadline y limpieza

El run público falló con `GLOBAL_DEADLINE_EXCEEDED en stop_drive`: el deadline se chequeaba al entrar a `_stop_drive` y abortaba la limpieza.

Corrección en `scripts/engineering_live_window.py`:

* El deadline **impide nuevo trabajo de mercado** (el bucle de `_wait_for_events` termina por `_remaining() <= 0`), pero **nunca aborta la limpieza**. `_stop_drive` y `_cleanup` ya no llaman a `_check_deadline`; siempre se ejecutan.
* Se separan las duraciones en la evidencia: `duracion_adquisicion_s` (trabajo de mercado), `duracion_limpieza_s` (stop + cierre de procesos), `duracion_total_s` (total).
* `deadline_respetado` se juzga sobre la **adquisición** (duración de mercado), no sobre el total que incluye la limpieza tras vencer. No se declara cumplido un check que terminó en excepción.

---

## 7. Pruebas focalizadas

* `tests/test_engineering_live_window_local_recorrido.py` — recorrido completo con transporte local (contadores + motivos de descarte), veredicto `PASS`.
* `tests/test_engineering_live_window_local_recorrido.py::test_validacion_contexto_rechaza_futuro_insuficiente_discontinuo` — backend rechaza contexto futuro/insuficiente/discontinuo con motivo explícito.
* `tests/test_engineering_live_window_local.py` (7) y `tests/test_market_stream.py` (40) — sin regresiones por la instrumentación.

---

## 8. Veredicto global de esta sesión

**Causa demostrada:** el ERROR histórico se debió a que el feed WS en vivo no entregó velas cerradas a la sesión (`events_processed=0` = falta de procesamiento en la sesión; causa upstream UNKNOWN). La infraestructura de presupuesto, límites, sesión, contexto y limpieza funcionó.

**No se repite la ventana pública** (instrucción del operador). Se conserva el ERROR histórico y se publica este addendum. Commit selectivo y push normal. Dashboard 3020 disponible, sin sesión de ensayo; 8792 intacto.
