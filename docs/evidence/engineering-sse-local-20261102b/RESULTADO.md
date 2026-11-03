# Corrección local del tramo HUB → SSE → adaptador → cierre admitido → T → evaluación

Fecha: 2026-11-02 · Base: `4e141a7` (`diag/recorrido-local-4f4273c`)
Origen: **LOOPBACK determinista** (servidores/sesiones de prueba locales; cero
Binance, cero ventana pública, sin red externa).

## 1. Diagnóstico basado en evidencia (ventana `eng-run-public-20261102c`)

Cada timeout, dónde se configura y qué midió en la ventana:

| Reloj | Configuración | Archivo/línea (base 4e141a7) | Lectura del 20261102c |
| --- | --- | --- | --- |
| Conexión HTTP + espera entre lecturas del SSE | `SSE_READ_TIMEOUT_S = 10.0` (un solo `urlopen(timeout=…)`: cubre connect y `readline()`) + backoff `SSE_BACKOFF_MAX_S=5.0` | `src/microstructure_probe/engineering_session_service.py` | 5 cortes: `connect_errors=0` ⇒ fueron de **fase LECTURA**, no de conexión; sin motivo registrado en stats |
| Heartbeat del HUB | `asyncio.wait(..., timeout=5.0)` → heartbeat SSE garantizado cada ≤5 s | `src/microstructure_probe/market_stream_service.py` (`_serve_stream`) | El HUB implicado tenía heartbeats; los cortes = HUB sin bytes ≥10 s en esos ciclos |
| Silencio de mercado (puerta) | `live_silence_ms` (default 120_000) medido ENTRE disparos (`feed_gap_ms`) | `_evaluation_gate` / `_record_feed_gap` | Sin evaluación ejecutada (gate aplicada y resultado solo en memoria) |
| Disconexión del motor (respaldo) | `DISCONNECT_MAX_SILENCE_MS = 10 min` | `paper_lab_engine.py` | No llegó a actuar |
| Deadline global | `--deadline` del arnés (`_check_deadline` en cada fase) + `--max-seconds` del servicio | `scripts/engineering_live_window.py`, `market_stream_service.py` | Respetado (adquisición 174.5 s < 180 s) |
| Silencio del evaluador | `STALE_MAX_AGE_MS=5 h` (frescura) | `paper_lab_engine.py` | No actúa a 60 s |

Hallazgos verificables (evidencia `docs/evidence/engineering-live-public-20261102c/`):

1. **Contador falso (defecto confirmado):** `drive["events_processed"]` nunca
   se incrementa en `_run_drive_market` → la salud y el veredicto del arnés
   leen `0` eterno en el transporte `market_stream`, incluso con rev 2 con
   `clock_ms` avanzado y UN cierre admitido (session `candles[0]`,
   `received_at=1793669342018`). El "avance de clock sin eventos" era este
   defecto de medición: la rev 2 proviene de la admisión legítima de un
   cierre real del feed (merge + catch-up) en la MISMA pasada de
   `_live_advance`; no hay transición oculta ni defecto del motor.
2. **5 cortes TimeoutError = desconexiones de LECTURA** (`connect_errors=0`).
   Con heartbeats garantizados cada ≤5 s y tope de lectura 10 s (2×),
   una lectura estable no se corta indebidamente: el corte solo procede
   ante HUB sin bytes ≥10 s (coincide con 5 `ws_connects` del HUB: churn
   del WS público + ciclos sin datos entregados). El cliente no tenía
   motivo registrado → no distinguible en evidencia → corregido.
3. **Puerta sin registro duradero:** una puerta rebotada (`last_gate`) vivía
   solo en memoria y no quedaba auditable en el drive.
4. **Falso PASS del arnés:** `_verdict` bastaba con sesión creada +
   revisiones presentes (rev 0 captada) para PASS con evaluaciones 0 y
   cierres 0.

## 2. Reproducción local (adaptador productivo, loopback)

`tests/test_engineering_service_market_stream.py` — 11/11 PASS (8
existentes + 3 nuevas):

- `test_adapter_stable_heartbeat_read_is_not_cut`: heartbeats cada 0.3 s
  (tope reducido a 1 s ⇒ >3 periodos de riesgo) → **0 desconexiones**;
  el heartbeat es señal de vida (frames/last_frame), nunca evento y nunca
  conduce.
- `test_adapter_silence_classifies_read_timeout_and_reconnects_bounded`:
  silencio real > tope → desconexión con motivo `READ_TIMEOUT`
  (`connect_errors=0`, evento `DISCONNECTED.reason`), reconexión acotada
  (backoff 0.5 s) y cancelación efectiva (hilo termina ≤3 s tras stop).
- `test_reconnect_recovers_pending_close_once_with_counters`: corte por EOF
  → reconexión → snapshot de recuperación admite el cierre PENDIENTE UNA
  vez (`watermark`), misma C1 no reevaluada (`duplicates_ignored` +3
  exactos: contexto×2 + C1), C2 duplicado no produce segunda evaluación ni
  revisión nueva ni efectos económicos; 2 evaluaciones vinculadas
  (evento/T/config_hash/decisión `SIN_ENTRADA`/motivo);
  `events_processed` y `cierres_admitidos` ahora ≥6/>=2 (comparables, mismo
  alcance; los mensajes WS y los frames SSE NO son unidades equivalentes —
  se registran por separado: `transport_events`/`stats.frames` vs
  `cierres_admitidos`).

Contadores por alcance registrados (drive público): `events_processed`
(consumidos), `transport_events`, `cierres_admitidos`, `evaluacion_contador`,
`counters.{duplicates_ignored,bad_candles,disconnects,provisional_ignored,…}`,
`watermark`, `stats.{frames,disconnects,reconnects,connect_errors,
last_disconnect_reason,last_frame_at_ms}`.

## 3. Corrección mínima (sin relajar causalidad ni límites)

- `SSE_READ_TIMEOUT_S` NO aumentado (10 s = 2× heartbeat del HUB): la
  lectura estable ya está protegida; solo se separa la causa
  (`READ_TIMEOUT` / `EOF` / `READ_ERROR` / `CONNECT_ERROR`) y se publica
  `DISCONNECTED.reason` a la conducción.
- `drive["events_processed"]`: incremento real por evento consumido en
  `_run_drive_market` (paridad con el transporte local de prueba).
- `drive["cierres_admitidos"]`: nuevo contador de admisiones reales
  (snapshot `appended` y `closed` admitidos), único con autoridad para
  "cierre nuevo admitido POR la sesión".
- `drive["gates_rechazadas"]` (acotado a 8): puertas rebotadas duraderas
  con causa (p.ej. `FEED_SILENCE`, `GRID_GAP`) — sin decisión inventada.
- `evaluaciones[*]`: añade `session_id` y `config_hash` (vínculo de
  identidad de cada evaluación).
- HUB (`market_stream_service.py`): `_write_sse` con `wait_for(drain,
  30 s)` → `SSE_WRITE_STALL`: un receptor que no drena se corta y libera su
  consumidor en vez de colgar el stream sin heartbeats (no afecta el bucle
  de eventos ni otros receptores). Heartbeats, detección de silencio,
  reconexión con backoff y cancelación conservadas.
- El motor (`paper_lab_engine.py`) no se tocó.

## 4. Veredicto del arnés (eliminado el falso PASS)

`scripts/engineering_live_window.py`:
- `_wait_for_events` registra `cierres_admitidos_traza`, `watermarks`,
  `cierres_admitidos_final` y `watermark_final`.
- `_verdict` exige, además de todo lo previo (sesión, config_hash,
  presupuestos, límites, DBs):
  - `cierres_admitidos_final > 0` ⇒ si no: `FAIL sin_cierre_nuevo_admitido`;
  - `evaluaciones_final` no vacía ⇒ si no: `FAIL sin_evaluacion_ejecutada`;
  - última evaluación vinculada a evento disparador, T, `rule_version`,
    decisión no-null y motivo no-null ⇒ si no: `FAIL
    evaluacion_sin_vinculo_completo`;
  - `config_hash` de la evaluación == `config_hash` de la sesión creada ⇒
    si no: `FAIL evaluacion_config_hash_distinta`;
  - `SIN_ENTRADA` con motivo puntúa como evaluación válida (PASS);
  - sin revisiones en absoluto queda `UNKNOWN` (bloqueo de evidencia, no
    violación de contrato).
- Regresión de la forma observada:
  `tests/test_engineering_window_verdict_rules.py` — 6/6 PASS
  (forma 20261102c exacta → FAIL; cierre sin evaluación → FAIL;
  SIN_ENTRADA con motivo → PASS; sin vínculo → FAIL; config_hash distinta →
  FAIL; sin revisiones → UNKNOWN).

## 5. Pruebas y regresión ejecutadas (resultados)

| Suite | Resultado |
| --- | --- |
| `tests/test_engineering_service_market_stream.py` | 11/11 (incluye las 3 nuevas de fiabilidad SSE) |
| `tests/test_engineering_window_verdict_rules.py` | 6/6 |
| `tests/test_engineering_live_window_local_recorrido.py` + `test_engineering_context_closed.py` | 9/9 (recorrido integrado WS→servicio→SSE→adaptador→evaluación con proveedores loopback + contexto cerrado/pid-files) |
| `tests/test_engineering_clock_readiness.py` + `test_engineering_clock_budget.py` + `test_market_stream.py` | 72/72 |

Recorrido local integrado: ciclo completo de conducción (hello → snapshot →
cierres → T → decisión → entrada → gestión → salida por stop →
`SESSION_CLOSED`) con vínculo de identidad ya comprobado en
`test_drive_live_full_cycle_entry_and_stop_exit` (`decision_evidence.adapter`
y `body["config_hash"] == created["session"]["config_hash"]`), más la
recuperación tras corte y reconexión de la prueba nueva.

Sin cambios de estrategia, presupuestos ni ventana pública. Evidencia
histórica de `20261102c` intacta; esta corrección no reescribe ese FAIL:
aclara su causa (falso cero por contador muerto + puertas sin registro) y
deja el tramo reproducible localmente.
