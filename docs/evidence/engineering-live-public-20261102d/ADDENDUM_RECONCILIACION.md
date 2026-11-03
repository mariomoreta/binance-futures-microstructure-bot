# Addendum de reconciliación — ventana pública `eng-run-public-20261102d`

Base: `88c5d2c` (`diag/recorrido-local-4f4273c`) · Fecha: 2026-11-03 · Origen: evidencia existente en `docs/evidence/engineering-live-public-20261102d/` (sin Binance, sin repetir ventana, sin nuevas conexiones públicas, sin cambios de código).

Este addendum aclara dos precisiones del informe original (`RESULTADO.md`) sin rebajar criterios del veredicto y sin convertir una aclaración documental en campaña de pruebas.

---

## 1. Conexiones y reconexiones (reconstrucción capa por capa)

### 1.1 Qué mide cada contador (verificado en código)

| Capa | Contador | Origen en código | Valor en la ventana | Semántica |
|---|---|---|---|---|
| HUB / servicio de mercado (WS) | `socket.reconnects` | `market_stream.py:275` (`socket_reconnects`, incrementa en `on_socket_closed(error)` **solo si hay error**) | **0** | Reconexiones del socket WS del mercado **por error**. |
| HUB / servicio de mercado (WS) | `ws_connects` | `market_stream.py:289` (`ws_connects`, incrementa en `on_socket_open`, incluida la inicial) | **4** | Aperturas de socket WS acumuladas (1 inicial + reaperturas). |
| Arnés (`_verdict`) | `reconexiones_max` | `engineering_live_window.py:1389-1390` lee `hj.get("socket").get("reconnects")` del `/health` del mercado | **0** | Contador que rige el límite autorizado ("Hasta 3 reconexiones acumuladas (monitoreo /health socket.reconnects)"). |
| Adaptador SSE (cliente ingeniería) | `disconnects` / `reconnects` | `engineering_session_service.py:405,462-463` (stats propios del adaptador) | **3 / 3** | Desconexiones y reconexiones del cliente SSE al leer el mercado. |
| Adaptador SSE (cliente ingeniería) | `connect_errors` | `engineering_session_service.py` | **0** | Sin errores de fase de conexión HTTP. |
| Arnés | `consumidores_max` | lee `hj.get("consumers")` = `total_consumers()` del hub | **2** | Máximo de consumidores SSE simultáneos (límite 3). |

### 1.2 Reconstrucción autoritativa

- **Conexión WS inicial:** 1 apertura en el arranque del servicio de mercado (`on_socket_open`, :457).
- **`ws_connects=4`:** 4 aperturas de socket WS acumuladas en total. La diferencia (`4 − 1 = 3`) son **reaperturas de socket**, no necesariamente "reconexiones por error". Como demuestra el código, `ws_connects` cuenta toda apertura (`on_socket_open`), mientras que `socket_reconnects` solo cuenta cierres **con error** (`on_socket_closed(error)` con `error` truthy, :475). Por tanto **`ws_connects − 1 ≠ reconexiones`**; no son equivalentes.
- **Cierres por falta de consumidores:** no hay evidencia de que el socket WS del mercado se cerrara por falta de consumidores. `release_idle` libera suscripciones, no el socket. El socket se mantuvo.
- **Adaptador SSE:** 3 desconexiones de lectura (`last_disconnect_reason=READ_TIMEOUT`, "_SseReadTimeout: sin bytes durante 10s") y 3 reconexiones, con `connect_errors=0`. Son del cliente SSE (capa de lectura), no del socket WS del mercado.
- **Sesión SSE del adaptador:** inició `started_at_ms=1793674533059`, se conectó `connected_at_ms=1793674655721` (~122 s después, tras sus propias reconexiones), último frame `last_frame_at_ms=1793674696978`.

### 1.3 Qué leyó el arnés y si cumple el límite autorizado

El arnés declaró `reconexiones_max=0` porque leyó `socket.reconnects` del `/health` del mercado, que es exactamente el contador autorizado ("Hasta 3 reconexiones acumuladas (monitoreo /health socket.reconnects; aborto si > 3)", `engineering_live_window.py:19-20`).

- Límite autorizado de reconexiones WS: **0 ≤ 3** → **CUMPLIDO**.
- Límite de consumidores SSE simultáneos: **2 ≤ 3** → **CUMPLIDO**.
- WS simultáneas: diseño del hub usa 1 conexión combinada (`engineering_live_window.py:17-18`); `ws_connects=4` es acumulado, no simultáneo.

### 1.4 Queda como UNKNOWN

- Timestamps exactos de cada una de las 4 aperturas WS y de cada cierre individual del socket (no hay log línea-a-línea de `on_socket_open`/`on_socket_closed` con marca por evento).
- Si las 3 reaperturas adicionales (`ws_connects=4`) fueron cierres limpios o reaperturas del bucle de transporte/backoff del mercado.

> Conclusión punto 1: el límite autorizado se cumplió. El `reconexiones_max=0` es correcto para el contador autorizado (`socket.reconnects` del mercado); los `disconnects=3/reconnects=3` pertenecen al adaptador SSE (capa distinta) y no se suman ni se confunden.

---

## 2. Señal pendiente frente a fill ejecutado (secuencia autoritativa)

### 2.1 Decisión #2 (revisión 8, `at_ms=1793674621326`, estado `en_espera`)

Campo exacto de evidencia: `evidence.revisiones[2]` y `config.decision_evidence` de la sesión (`docs/evidence/engineering-live-public-20261102d/sessions/paper-lab-sessions/PL-MINAUSDT-LONG-1793674533011-ff05e947.json`).

| Campo | Valor |
|---|---|
| Tipo de evento | `decision_evidence` + revisión 8 |
| Evento disparador | `closed`, open `1793674560000`, close `1793674619999`, received `1793674620707`, `available_at=1793674560000` |
| T (reloj de evaluación) | `1793674560000` (open de la vela #2) |
| `evaluated_at_ms` / `evaluation_wall_ms` | `1793674620710` |
| Decisión | `ENTRADA_SIMULADA` |
| Motivo | "Senal de entrada en T pero sin fill posible en el prefijo conocido: run_backtest no admite operacion con datos disponibles en T. Senal pendiente de fill." |
| `n_prefix_candles` / `n_fully_known_candles` | 2 / 1 (solo 1 vela plenamente conocida al evaluar: la #1) |
| `entry_px` / `entry_fill_*` en la decisión | `0.0` / `entry_fill_px=None, entry_fill_ms=None, entry_fill_qty=None, entry_fill_cost=None` |
| `admit_risk` / `risk_reason` | `False` / "Precio de entrada no positivo: admision denegada." |
| Gate | `ok=True`, `cause=None`, freshness `END_OF_DATA` (espera normal del feed) |

**Interpretación:** en el instante de la decisión #2 solo se conocía plenamente 1 vela (la #1, cerrado). La vela #2 estaba abierta (`ohlc_known=False`), por lo que **no hubo fill en el momento de la decisión**: `entry_fill_*=None`, `entry_px=0.0`. La decisión fue una **señal pendiente de fill** (`kind=protection`), no una entrada ejecutada.

### 2.2 Fill posterior (revisión 10, `at_ms=1793674680716`, estado `abierta`)

Evidencia explícita: `session.events[2]`, `kind="entry"`.

| Campo | Valor |
|---|---|
| Tipo de evento | `entry` (fill) |
| Instante (`at_ms`) | `1793674620000` |
| Precio | `0.05564` (label "Entrada LONG @ 0.06") |
| Cantidad | `17972.68152408` |
| Notional | `1000.0` |
| Stop | `0.052858` (`stop_config=0.0` en detalle, stop aplicado 0.052858) |
| `source` | `run_backtest` |
| `fill_basis` | `model_approximation` ("fill con precio conocido tras la decisión; bid/ask/profundidad no observados; funding/costes no observados=UNKNOWN") |
| Revisión de sesión | 10 (`clock_ms=1793674620000`, `cursor=3`) |

**Vela que se volvió disponible para ejecutar:** vela #3 (`open_time_ms=1793674620000`, `open=0.05564`, `close_time_ms=1793674679999`, `available_at=1793674620000`, `received_at=1793674680362`). El `entry_px=0.05564` coincide exactamente con el open de la vela #3. Coherente con la lógica del motor (`paper_lab_engine._next_reveal_index` / `_mark_at_open`: al revelar el open de una vela se conoce el cierre de la anterior y se marca la posición no realizada).

### 2.3 Estado final de sesión y posición al detener la conducción

| Campo | Valor |
|---|---|
| `status` | `abierta` (conducción detenida por parada del arnés, no por fallo) |
| `clock_ms` | `1793674620000` |
| `revision` | `10` |
| `cursor` | `3` |
| `position.open` | `true` |
| `position.direction` | `LONG` |
| `position.entry_px` | `0.05564` |
| `position.entry_qty` | `17972.681524083393` |
| `position.entry_cost` | `1000.0` |
| `position.entry_ms` | `1793674620000` |
| `position.stop_px` | `0.052858` |
| `position.mark_px` / `mark_ms` | `0.05564` / `1793674620000` |
| `position.unrealized_net` | `-0.8` |
| `events` (sesión) | 3: 2 de decisión (`protection`) + 1 de entrada (`entry`) |

### 2.4 Tabla cronológica reconciliada

| Instante (ms) | Etapa | Evento / acción | T / clock | Precio | Qty | Notional | Rev. | Estado sesión |
|---|---|---|---|---|---|---|---|---|
| 1793674500000 | Señal #1 | Decision `SIN_ENTRADA` (protection, esperando datos) | 1793674500000 | — | — | — | 4 | `sin_iniciar` |
| 1793674560000 | Señal #2 | Decision `ENTRADA_SIMULADA` pendiente de fill (protection) | 1793674560000 | trigger `0.0557` | — | — | 8 | `en_espera` |
| 1793674620000 | Fill ejecutado | Entrada LONG @ 0.06 (entry, `kind=entry`) | 1793674620000 | `0.05564` (open vela #3) | `17972.68152408` | `1000.0` | 10 | `abierta` |
| 1793674680716 | Congelación | Parada de conducción (sesión abierta) | 1793674620000 | mark `0.05564` | — | — | 10 | `abierta` |

> Conclusión punto 2: **no hay contradicción**. La decisión #2 fue "pendiente de fill" (no se ejecutó fill al evaluar por falta de datos: `entry_fill_*=None`). El fill se materializó después (`events[2]`, `kind=entry`, `at_ms=1793674620000`, precio `0.05564` = open de la vela #3 disponible). El `position.open=true` está **respaldado por el evento `entry` explícito**, no inferido solo de `position.open`. El fill es `model_approximation` (paper-lab): `bid/ask/profundidad/funding/costes no observados = UNKNOWN`. No se inventó salida, comisión ni realizado.

---

## 3. Veredicto reconciliado

| Dimensión | Estado | Criterio |
|---|---|---|
| PASS funcional (recepción + evaluación) | ✅ | 3 cierres nuevos admitidos, T avanzó `1793674499999 → 1793674620000`, 2 evaluaciones ejecutadas y vinculadas (evento/T/config_hash/decisión/motivo), `eventos_procesados_final=95` (contador corregido). |
| Cumplimiento de límites | ✅ | Reconexiones WS `socket.reconnects=0` (≤3), consumidores SSE 2 (≤3), HTTP upstream 2/7 (≤7), cero escrituras en DBs canónicas, sin órdenes reales. |
| Estado paper realmente acreditado | ✅ | Posición simulada con evento `entry` explícito, `fill_basis=model_approximation`, costes `UNKNOWN`, sin orden real en Binance. |
| **Veredicto global reconciliado** | **PASS** | Todos los criterios obligatorios cumplidos, sin rebajar criterios. Sesión queda abierta y congelada. |

---

## 4. Conclusión y siguiente bloque

Ambas precisiones quedan explicadas con la evidencia existente:
1. `reconexiones_max=0` es correcto para el contador autorizado (`socket.reconnects` del mercado); los `disconnects=3/reconnects=3` son del adaptador SSE (capa distinta) y no se suman.
2. `ENTRADA_SIMULADA` pendiente de fill y `position.open=true` son coherentes: el fill se materializó tras la decisión (`events[2]`, `kind=entry`) al disponerse la vela #3; está respaldado por evento explícito.

No se modifica código ni se añade funcionalidad (no hay error en el evaluador/instrumentación que corregir; es una aclaración de capa). No se repite la ventana ni se conecta a Binance.

**Siguiente bloque de producto propuesto (no implementar en esta reconciliación):** llevar el recorrido ya acreditado (sesión, evaluaciones vinculadas, estado paper) al **control visible del dashboard** (Dashboard V2), de modo que la traza de ejecución pública sea observable en la interfaz en lugar de solo en archivos de evidencia. Este bloque se aborda en una tarea posterior con su propia autorización.

---

### Rutas de evidencia consultadas
- `docs/evidence/engineering-live-public-20261102d/evidence.json` (traza completa: `revisiones`, `evaluaciones`, `adaptador_ingenieria`, `recorrido_servicio`, `verdict_reasons`, `create`, `start`).
- `docs/evidence/engineering-live-public-20261102d/sessions/paper-lab-sessions/PL-MINAUSDT-LONG-1793674533011-ff05e947.json` (sesión: `config.decision_evidence`, `events`, `candles`, `position`, `status`, `clock_ms`, `revision`).
- `docs/evidence/engineering-live-public-20261102d/service_logs/engineering-stdout.txt`, `service-stdout.txt`.
- Código: `scripts/engineering_live_window.py` (líneas 1383-1415, 19-20), `src/microstructure_probe/market_stream.py` (líneas 270-289, 452-475, 809-863), `src/microstructure_probe/engineering_session_service.py` (líneas 405, 462-463).
