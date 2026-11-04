## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `bf974f2`)

Corregida la semántica de costes en `PnLPanel.tsx`: ya no se deduce ejecución
mediante `costs.entry_fees_executed > 0` ni equivalentes. Ahora se usa el
estado autoritativo de entrada/salida y la disponibilidad real del dato:
- Fill ejecutado y coste conocido cero → muestra `0.00` (nunca guion ni inventado).
- Coste ausente → `UNKNOWN` con motivo explícito.
- Estimación conocida → muestra importe + "(estimación, no ejecutada)".
- Sin estimación → `UNKNOWN`; no se convierte null en cero al sumar.
Regresiones focalizadas en `tests/test/format.test.ts` y nueva
`tests/test/pnl-panel.test.tsx` (8 pruebas de costes).

Aceptación local A-J verificada desde navegador real (Playwright, DOM/red):
11/11 PASS. Evidencia en `docs/evidence/dashboard-EFHI-20261103/`
(capturas DOM, respuestas del backend, aceptación-summary.json).

Despliegue: dashboard 3020 con build verificado (BUILD_ID
`GBp6Bco5KjQW6IZ14dJA8`, árbol frontend
`2bcdd8fc5882ff648f397fda5f8cd07b7cc32989` = HEAD:frontend). Servicio
preexistente 8792 (pid 31124) preservado. Servicio 8797 (residual de prueba)
detenido. `opencode.json` fuera de commits.

Activación pública (Binance) queda deshabilitada en este bloque.

## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `ead35d2`)

Corregida la semántica de costes en `PnLPanel.tsx`: ya no se deduce ejecución
mediante `costs.entry_fees_executed > 0` ni equivalentes. Ahora se usa el
estado autoritativo de entrada/salida (`entered` desde `position.open`,
`exitExecuted` desde `result.exit_executed`) y la disponibilidad real del dato:
- Fill ejecutado y coste conocido cero → muestra `0.00` (nunca guion ni inventado).
- Coste ausente → `UNKNOWN` con motivo explícito.
- Estimación conocida → muestra importe + "(estimación, no ejecutada)".
- Sin estimación → `UNKNOWN`; no se convierte null en cero al sumar.
Regresiones focalizadas en `tests/test/format.test.ts` y nueva
`tests/test/pnl-panel.test.tsx` (8 pruebas de costes).

Aceptación local A-J verificada desde navegador real (Playwright, DOM/red):
11/11 PASS. Evidencia en `docs/evidence/dashboard-recorrido-visible-20261103/`
(capturas DOM, respuestas del backend, aceptación-summary.json).

Despliegue: dashboard 3020 con build verificado (BUILD_ID
`3DorSLli3Q-s6NkA-vUq-`, árbol frontend
`5fc18d379a709217c4ce10d1e9eb73ccd059c9db` = HEAD:frontend). Servicio
preexistente 8792 (pid 31124) preservado. Servicio 8797 (residual de prueba)
detenido. `opencode.json` fuera de commits.

## Recorrido visible en dashboard V2 - /market-lab implementado (2026-11-03, base `2e3830a`)

Implementado en rama `dash-v2-04-recorrido-visible` (no integrada a main). Lleva al dashboard
el recorrido backend ya acreditado (ventana pública `eng-run-public-20261102d`, PASS):
sesión → datos nuevos → evaluación con decisión y motivo → señal pendiente → posición paper.

Aceptación local A-J verificada desde el navegador real (Playwright, DOM/red, 11/11 PASS):
A. Abrir dashboard: no inicia procesos ni sesión (GET puro de lectura).
B. Iniciar demostración: un solo arranque y una sola sesión (demo loopback + servicio de ingeniería).
C. Datos nuevos: gráfico y evaluación cambian sin recargar (SIN_ENTRADA apareció en T).
D. SIN_ENTRADA con motivo visible en el panel de última evaluación.
E. Señal pendiente y fill diferenciados (indicador: fill ejecutado / señal pendiente / decisión de abstención).
F. Backend y UI coinciden: identidad, T, regla, decisión y posición.
G. Recarga recupera la misma sesión sin duplicar entradas/evaluaciones.
H. Detener sesión congela la conducción y conserva la posición abierta (sin salida inventada).
I. Fuente caída: chip de fuente declara origen y causa.
J. Limpieza: procesos propios terminados, archivos ajenos intactos.

Semántica de costes corregida: cero conocido se muestra como cero; valor ausente → UNKNOWN con
motivo; coste hipotético conocido → estimación claramente no ejecutada. Sin cambios de cálculos

económicos. Regresiones focalizadas en tests/test/format.test.ts.

Despliegue: dashboard 3020 con build verificado (BUILD_ID Wm9NjmROE3wO2OEpej10M, árbol frontend
92116fedd163974e020cac0b6d78251a7618bac9 = HEAD:frontend). Servicio preexistente 8792
(pid 31124) y archivos ajenos preservados. `opencode.json` fuera de commits.

Activación pública (Binance) queda deshabilitada / no disponible en este bloque.

## Recorrido visible en el dashboard V2 - /market-lab (2026-11-03, base `4b35d2c`)

Implementado en rama `dash-v2-04-recorrido-visible` (no integrada a main):
- /market-lab muestra la sesión de ingeniería ya acreditada (sesión → datos nuevos →
  evaluación con decisión y motivo → señal pendiente → posición paper).
- Fuente identificada explícitamente: DEMOSTRACIÓN LOCAL (datos simulados, productor
  WS loopback + servicio de mercado --transport local) vs BINANCE PÚBLICO (no activado
  en este bloque; claramente no disponible al abrir la vista ni iniciar la demostración).
- Estado separado: servicio de ingeniería, conexión de datos y sesión son paneles
distintos.
- Última evaluación: evento disparador, T, regla, decisión y motivo (panel dedicado).
- Señal pendiente separada de fill ejecutado (indicador de texto + gráfico).
- Costes/funding ausentes → UNKNOWN con motivo, nunca cero.
- Error, silencio o desconexión visibles; datos antiguos nunca rotulados como actuales.
- Abrir la página o GET no arranca procesos; cerrar la pestaña desconecta al observador
  sin detener el backend; recarga recupera la misma sesión sin duplicar entradas.
- Detener sesión congela la conducción y conserva la posición abierta; no inventa salida.
- Servicio preexistente 8792 y dashboard 3020 preservados; `opencode.json` fuera de commits.

## Reconciliación de la ventana pública `eng-run-public-20261102d` (2026-11-03, base `88c5d2c`)

## Reconciliación de la ventana pública `eng-run-public-20261102d` (2026-11-03, base `88c5d2c`)

Aclaraciones documentales sobre evidencia existente (sin Binance, sin repetir ventana, sin cambios de código):
- Conexiones/reconexiones: `reconexiones_max=0` del arnés mide `socket.reconnects` del `/health` del mercado
  (contador autorizado: <=3). `ws_connects=4` son aperturas de socket WS acumuladas (no equivalen a
  reconexiones; `ws_connects - 1 != reconexiones`). El adaptador SSE registró `disconnects=3 / reconnects=3`
  (capa distinta, lectura SSE), `connect_errors=0`. Límite de consumidores SSE: 2 (<=3). Todo dentro del
  presupuesto autorizado.
- Señal vs fill: la decisión #2 (`ENTRADA_SIMULADA`, T=1793674560000, rev 8) fue "pendiente de fill"
  (`entry_fill_* = None`). El fill se materializó tras la decisión (`events[2]`, `kind=entry`,
  at_ms=1793674620000, precio 0.05564 = open de la vela #3 disponible), respaldado por evento explícito,
  `fill_basis=model_approximation`, costes UNKNOWN.
- Veredicto reconciliado: PASS (recepción+evaluación, límites, estado paper acreditado), sin rebajar criterios.
  Véase `docs/evidence/engineering-live-public-20261102d/ADDENDUM_RECONCILIACION.md`.

## Ventana pública única `eng-run-public-20261102d` - PASS de aceptación (2026-11-03, base `d307fc7`)

Ejecutada UNA sola vez (autorización acotada), run_id NUEVO (nunca reutilizado de
`eng-run-public-20261102c`, presupuesto agotado 7/7), 180 s deadline, 7/7 HTTP
upstream, 1 WS combinada MINAUSDT+BTCUSDT 1m, 3 consumidores SSE máx., 3
reconexiones máx., cero escrituras en DBs canónicas, sin órdenes reales.

Resultado: **PASS** — cadena completa acreditada:
- Sesión creada (create_ok) con config_hash 4a339c046cc3ad63, regla RULE-CAUSAL-V1.
- 3 cierres NUEVOS admitidos POR la sesión (watermark 1793674500000 → 1793674560000 → 1793674620000), T avanzó de 1793674499999 a 1793674620000.
- 2 evaluaciones ejecutadas y vinculadas (evento/T/config_hash/decisión/motivo):
  #1 SIN_ENTRADA con motivo (abstención válida), #2 ENTRADA_SIMULADA con motivo.
- `eventos_procesados_final: 95` (contador corregido, ya no falso cero).
- Presupuesto 2/7 HTTP upstream, ledger 7/7, consumidores 2, reconexiones 0, DBs intactas.
- Limpieza: procesos propios terminados, 8791/8797 libres, 8792 (pid 31124) y 3020 intactos.
- Sesión queda abierta y congelada (posición paper-lab simulada, sin orden real; sin salida inventada).

Evidencia: `docs/evidence/engineering-live-public-20261102d/` (RESULTADO.md es el punto de entrada; evidence.json tiene la traza completa).

SHA del arnés: `3ef9e5f45a90a8ca…` · BUILD_ID servido: `t4z0bfKQ_kIP9qv1WHCKR` · árbol frontend `1f6f0500…` = HEAD:frontend.

## Corrección local del tramo HUB → SSE → adaptador → admisión → evaluación (2026-11-02, base `4e141a7`)

## Corregido tramo HUB → SSE → adaptador → admisión → evaluación (2026-11-02, base `4e141a7`)

Corrección LOCAL (loopback, sin Binance, sin ventana pública) del tramo que
rompió la ventana `eng-run-public-20261102c`:

- Diagnóstico con relojes separados: `SSE_READ_TIMEOUT_S=10.0` de
  `engineering_session_service.py` cubre conexión HTTP Y espera entre
  lecturas (heartbeat del HUB garantizado cada ≤5 s ⇒ 2×; los 5 cortes
  TimeoutError de la ventana fueron de FASE LECTURA: `connect_errors=0`);
  silencio de mercado en la puerta (`live_silence_ms`, `feed_gap_ms` entre
  disparos); deadline global del arnés (`--deadline`) + `--max-seconds` del
  servicio. No se aumentó ningún límite: el corte del silencio con
  heartbeats ausentes es correcto.
- Defecto de medición confirmado y corregido: `drive["events_processed"]`
  NUNCA se incrementaba en `_run_drive_market` → falso cero eterno en
  transporte `market_stream`. El "avance de clock sin eventos" de la ventana
  pública era ESTE defecto: la rev 2 provenía de la admisión legítima de un
  cierre real (merge + catch-up en la misma pasada de `_live_advance`),
  no de una transición oculta. Sin cambio en el motor.
- Adaptador: desconexiones clasificadas (`READ_TIMEOUT`/`EOF`/`READ_ERROR`,
  `DISCONNECTED.reason` a la conducción) sin ánimo de límites.
- Conducción: contadores reales y comparables por alcance:
  `events_processed` (consumidos), `cierres_admitidos` (admisiones POR la
  sesión, watermark), `counters.{duplicates_ignored,bad_candles,…}`,
  `gates_rechazadas` (puertas rebotadas duraderas, acotado 8) y
  `evaluaciones[*].session_id/config_hash`.
- HUB (`market_stream_service.py`): drain del receptor acotado (30 s →
  `SSE_WRITE_STALL`): un receptor colgado se corta y libera consumidor
  en vez de dejar el stream sin heartbeats. Heartbeats, silencio, backoff
  y cancelación conservados.
- Arnés veredicto: exige cierres admitidos > 0 y evaluación vinculada
  (evento/T/config_hash/decisión/motivo; `SIN_ENTRADA` con motivo sigue
  siendo válida). Sesión creada + revisiones presentes NO bastan; sin
  revisiones = UNKNOWN. Falsos motivos: `sin_cierre_nuevo_admitido`,
  `sin_evaluacion_ejecutada`, `evaluacion_sin_vinculo_completo`,
  `evaluacion_config_hash_distinta`.
- Reproducción local (adaptador productivo, productor SSE loopback):
  lectura estable con heartbeats NO cortada (0 desconexiones, 3 periodos de
  riesgo); silencio real → `READ_TIMEOUT` + reconexión acotada + cancelación
  efectiva; corte y reconexión con recuperación del cierre pendiente UNA vez
  (watermark; duplicados y provisionales sin efectos económicos
  duplicados).
- Pruebas: 98 PASS totales (`test_engineering_service_market_stream.py` 11,
  `test_engineering_window_verdict_rules.py` 6, recorrido local integrado +
  contexto cerrado 9, reloj/presupuesto/mercado 72). Evidencia nueva (origen
  loopback): `docs/evidence/engineering-sse-local-20261102b/`.

## Ventana pública única `eng-run-public-20261102c` - FAIL de aceptación: EVALUACION_NO_ALCANZADA (2026-11-02, base `a11c02e`)

## Ventana pública única `eng-run-public-20261102c` - FAIL de aceptación: EVALUACION_NO_ALCANZADA (2026-11-02, base `a11c02e`)

Se ejecutó UNA ventana pública autorizada con el arnés corregido
(`scripts/engineering_live_window.py` — SHA real en
`docs/evidence/engineering-live-public-20261102c/preflight.json`).
Presupuesto consumido exactamente: ledger `execution_id=eng-run-public-20261102c`
con 7/7 filas (5 `/time` + 2 klines, `limit=300`, `endTime=1793669219999`,
0 reintentos, 0 `budget_blocked`). Sin relanzamientos; 0 escrituras en DBs
canónicas (hash-igualadas antes/después); 8792, 3020 y `opencode.json`
intactos.

- ACREDITADO: sesión creada con identidad
  (`PL-MINAUSDT-LONG-1793669229096-9d935300`, `config_hash=4a339c046cc3ad63`,
  regla `RULE-CAUSAL-V1` fija pre-conexión); referencia de reloj público
  válido (`public_sincronizado`, offset −7.125 ms, RTT 360 ms, 5/5 muestras);
  contexto cerrado no-futuro correcto con el camino corregido en a11c02e
  (600 velas, 300/símbolo, contiguas, último cierre admitido
  1793669219999 ≤ referencia 1793669228291, vela en curso excluida fila a
  fila, `cierre_no_ocurrido:0`, REST 2/2); WS pública saludable (237
  mensajes, 0 reconexiones, **3 cierres nuevos admitidos POR EL HUB**:
  BTCUSDT 2, MINAUSDT 1, 237 frames SSE enviados); consumidores ≤2; adquisición
  174.5 s < 180 s; limpieza completa (pid-files propios eliminados, 8791/8797
  libres, pid-file 8792 intacto, DBs canónicas sin cambios); posición
  `open=false` sin fills ni salidas inventadas.
- NO ACREDITADO: cierre nuevo admitido **por la sesión**
  (`events=[]`, `eventos_procesados=0`), avance de T por evento, evento
  disparador y evaluación con decisión y motivo
  (contador 0; `result=null`; sesión quedó `sin_iniciar`, rev 2 con
  `clock_ms=1793669280000` sin evento registrado → causa UNKNOWN).
- CAUSA (clasificada): fallo del arnés/servicios locales en el adaptador SSE
  del servicio de ingeniería: frames 60/237, 5 desconexiones por
  `TimeoutError: timed out`, conexión efectiva recién a
  `1793669374186` (~147 s tras `started_at_ms=1793669229149`). No es fallo
  upstream de Binance y NO es el defecto de contexto corregido en a11c02e.
- Veredicto del arnés: PASS interno (sus checks); veredicto global de
  aceptación: **FAIL** (`EVALUACION_NO_ALCANZADA`). `SIN_ENTRADA` no aplica:
  no hubo eventos procesados con los cuales abstenerse.
- Evidencia: `docs/evidence/engineering-live-public-20261102c/`
  (`RESULTADO.md`, `summary.json`, `evidence.json`, `preflight.json`,
  `post_state.json`, `ledger-run-id.json`, sesión persistida, logs de
  servicio y del arnés).

## Corrección del contexto cerrado del arnés + aislamiento de pid-files (2026-11-02, base `f033c06`)

## Corrección del contexto cerrado del arnés + aislamiento de pid-files (2026-11-02, base `f033c06`)

Corregido en código (sin ejecutar ninguna ventana pública) el defecto que
causó el FAIL de `eng-run-public-20261102b`. Cambios en
`scripts/engineering_live_window.py` (SHA-256
`97bec590dc46aadde60b213afe5fdf8ae684b5dab088f59f4b6fefeab3bead9b`):

- `_reference_now_ms` (nuevo): la referencia temporal del modo `public` sale
  del reloj del servicio de ingeniería con validez comprobada
  (`clock.source == public_sincronizado`, `available` True, `offset_ms`
  finito y `age_ms` presente); nunca el reloj del navegador, sin tolerancia
  positiva de un intervalo. El check `clock_fuente_verificada`
  (`_verify_clock`) ahora se ejecuta de verdad en el modo `public` (estaba
  definido pero sin cablear).
- `_context_window` (nuevo): pide UNA ventana que termina en la última vela
  cuyo cierre ya ocurrió (`open + step - 1 <= referencia`; el cierre
  exactamente igual a la referencia se admite).
- `_load_recent_context(reference_ms)`: valida CADA fila recibida (REST y
  caché derivada): `close_time` ausente, posterior a la referencia (vela en
  curso) u OHLC de caché capturado antes del cierre se excluyen con
  diagnóstico; REST sobrescribe lo almacenado por apertura; identidad por
  símbolo y continuidad se conservan; sin descargas automáticas adicionales
  (máx. `MAX_REST_REQUESTS_PER_RUN` por corrida, reserva preenvío
  `LedgerAttemptGate`).
- `_prepare_context` + `_validar_contexto_cerrado` (nuevos): validación
  defensiva ANTES de crear sesión que replica y no relaja la del backend
  (`CONTEXTO_INSUFICIENTE / NO_RECIENTE / DISCONTINUO / FUERA_VENTANA /
  FUTURO`); si tras filtrar falta contexto, aborta con motivo explícito sin
  crear sesión.
- Aislamiento de pid-files: `market_stream_service.py` acepta `--pid-file`;
  el arnés pasa `sessions_dir/market-service.json` y
  `sessions_dir/engineering-service.json` (exclusivos de la corrida). La
  limpieza borra SOLO esos archivos; `data/market-stream/service.json`
  (servicio 8792) no se toca ni se reconstruye.

Verificación local (cero Binance, proveedores loopback): nuevas pruebas
`tests/test_engineering_context_closed.py` — 7 PASS (fila en curso
excluida aunque la respuesta la incluya; cierre exactamente igual a la
referencia admitido; contexto insuficiente aborta con motivo sin crear
sesión y sin descargas extra; proveedor local respeta el rango pedido con
contexto cerrado y contiguo; pid-file ajeno preexistente idéntico
antes/después incluso ante fallo; servicio real escribe su pid-file
exclusivo sin reconstruir el por defecto) — y la regresión completa
`tests/test_engineering_live_window_local_recorrido.py` (2 PASS: recorrido
local WS → servicio → SSE → evaluación). Regresiones adicionales:
`tests/test_engineering_clock_readiness.py` +
`tests/test_engineering_clock_budget.py` (32 PASS) y
`tests/test_market_stream.py` (40 PASS).

Los proveedores locales de pruebas (`scripts/local_kline_provider.py`,
`scripts/local_ws_kline_provider.py`) ahora respetan EXACTAMENTE el rango
pedido (primera apertura `>= startTime`; no devuelven la vela anterior al
rango), requisito para demostrar contexto reciente cerrado y contiguo.

`tests/test_engineering_live_window_local.py` sigue sin recomponerse tras el
cambio de firmas del arnés actual (falla en el mismo punto que antes del
cambio: fixture `Args` sin los atributos actuales); no se toca en esta
entrega.

Pendiente con autorización propia: ventana pública NUEVA con run_id NUEVO
(no reutilizar `eng-run-public-20261102b`, presupuesto agotado 7/7) para
acreditar sesión → cierre nuevo → T → evaluación con decisión y motivo.

## Ventana pública única — FAIL por contexto con vela en curso (2026-11-02, base `d2ca1cb`)

Se ejecutó **una sola** ventana pública autorizada (run_id
`eng-run-public-20261102b`, deadline 180 s) con el arnés
`scripts/engineering_live_window.py` (SHA-256 `32429af0ec82da0e717a98793c2c8d31eb2b22428998be6f3ff7e246edc6b4e5`),
transporte `public` y reloj `public`, contra 8791/8797 aislados, sin tocar
8792 ni el dashboard (3020, BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR`, árbol
frontend `1f6f0500cb9115fa5c9d44e07be2c5524bdee690`).

Veredicto global: **FAIL**. El arnés registra `ERROR` porque la excepción
abortó antes de `_verdict()`, pero la causa es un fallo determinista de
contrato, no de Binance: `_load_recent_context` incluyó en el contexto la
vela del minuto en curso (no cerrada) y el servicio la rechazó
correctamente con `VALIDATION_ERROR: CONTEXTO_FUTURO` (BTCUSDT,
`open_time=1793642700000`, cierre `1793642759999` > referencia
`1793642709475`). **No se creó sesión**; no hubo conducción SSE,
evaluaciones, decisión ni posición.

Lo que sí quedó acreditado: reloj público válido antes de crear sesión
(`public_sincronizado`, 5/5 muestras, `offset_ms=-60.40`, `rtt_ms=368.11`)
y HTTP disponible mientras el reloj no estaba listo (transiciones en
`evidence.json`); presupuesto exacto **7/7** en el ledger compartido
(5 `/time` + 2 `klines`, 0 bloqueos pre-envío, `retry=0`, `limit=300`, sin
paginación); limpieza completa (procesos terminados, 8791/8797 cerrados,
8792 y 3020 intactos); DBs canónicas sin cambios (SHA-256 idéntico). El
pid-file compartido `data/market-stream/service.json`, sobrescrito por el
8791 del arnés, se restauró con la identidad viva del 8792 (`pid=31124`,
`port=8792`, reportada por su `/health`); el contenido previo exacto es
UNKNOWN (no se capturó en el preflight).

No hubo relanzamiento. El presupuesto de ese run_id está agotado. Siguiente
acción requerida: corregir `_load_recent_context` para excluir velas con
`close_time_ms` posterior a la referencia, añadir prueba local y **pedir
nueva autorización** con un run_id nuevo. Evidencia completa:
`docs/evidence/engineering-live-public-20261102b/` (`RESULTADO.md`,
`summary.json`, `preflight.json`, `evidence.json`, `post_state.json`,
`ledger-run-id.json`, logs del arnés y de ambos servicios).

## Modo «Demostración local — datos simulados» + reconciliación por evidencia (2026-10-28, base `643e0b9`)

Entregado y verificado de forma ACOTADA (arranque coordinado, readiness y
parada; no repite la aceptación larga): el operador puede recorrer
`/market-lab` → «Iniciar demostración» → «Iniciar sesión» desde la UI sin
comandos ni variables manuales. La demo arranca EXCLUSIVAMENTE recursos
propios identificados y acotados (productor WS loopback determinista con
parada automática, servicio de mercado canónico en 8791 con
`--transport local` y `--max-seconds`, servicio de ingeniería 8797 con
identidad verificada), con duración/memoria acotadas (45 min default) y SIN
Binance, sin 8792 y sin transporte público. «Iniciar sesión» comprueba la
fuente ANTES de crear la sesión: sin fuente → `FUENTE NO DISPONIBLE` y sin
sesión huérfana; la parada de la demo detiene solo recursos con identidad
doble verificada (manifest + pid-file) y deja la pérdida de feed registrada
DENTRO de la sesión; luego «Detener sesión» aplica la política de posición.
El controlador del servicio ahora RECONCILIA el pid-file solo con evidencia
verificable (health canónico + sessions_dir canónico + pid vivo + línea de
comandos del SO); sin la cadena completa rechaza sin adoptar ni matar.
Evidencia: `docs/evidence/engineering-local-demo-2026-10-28/summary.json`
(BUILD_ID `wF9Xf3Orb5Af7vgwp8_f4`, dashboard 3020 en producción): **14/14
checks PASS de la verificación integrada E2-gridgap**, más 22/23 de la
verificación acotada original (corrida 3).
- PASS: A1–A4, B1–B3, D1–D6, E1, **E2 (decisión `ENTRADA_SIMULADA` en clock
  1793073120000, close 0.06291285 > entry_px 0.06285; fill simulado
  entry_qty=15895, entry_cost=1000, entry_ms=1793073180000; gestión con
  mark_px/mfe_pct/mae_pct; cierre por regla horizon con exit_executed=true;
  34 velas contiguas, sin GRID_GAP, sin FEED_SILENCE)**, F1–F4, F3, G1,
  H1–H3.
- Causa raíz del GRID_GAP original (resuelta): `anchor_open` del productor
  se fijaba a `current_open` en vez de a `start_open`; fix:
  `anchor_open = start_open`, `BACKFILL_PACE_S=1.0`, plomado de
  `from_ms`/`to_ms` al servicio de mercado. Detalles:
  `ENGINEERING_SESSION_BACKEND_V1.md` §11.7–§11.8 y
  `docs/FEATURE_BACKLOG.md` (entrada modo demo 2026-10-28).

## Entrega utilizable del transporte live local + identidad de la evidencia (2026-10-28, base `efa7700`)

Factual: dashboard canónico `http://127.0.0.1:3020` ACTIVO en producción
(BUILD_ID `0-HCAplwLhRPpYHuuAPC2`, árbol `efa7700`), páginas verificadas,
sin sesiones de ensayo. Identidad de la evidencia de aceptación
aclarada: se corrió sobre árbol SIN commitear encima de `90b3c9b`
(`git_sha=90b3c9b` es solo el HEAD al arrancar; la implementación probada
es la publicada en `b85f389`+`5c9f409`+`557a1a8`, arnés en `e775cfd`).

Servicios verificados (ninguno tocado): 8797 (pid 29096) canónico,
ready/identificable — su pid-file estaba corrupto por una corrida efímera
y se reconcilió al valor real (29096/8797) sin tocar el proceso; 8792
(pid 33104) es `market_stream_service.py --transport local --base-url
ws://127.0.0.1:9999` (LOCAL, no Binance) y NO se usa como fuente; 8791
(fuente configurada de 8797) está CAÍDO.

Condición al pulsar «Iniciar sesión» en `/market-lab`: la sesión se crea
(contexto del cache local) y la conducción queda con error VISIBLE
(`CONNECT_ERROR`/puertas de feed/`TRANSPORT_LOST`) porque 8791 está caído;
sin fallback silencioso a 8792. Demo local viva exige fuente loopback
propia + 8791 `--transport local`. Recorrido completo y BUILD_IDs en
`docs/ENGINEERING_SESSION_BACKEND_V1.md` §11.6.

Próximo objetivo declarado: adaptar y verificar este mismo recorrido con
datos públicos (8791 `--transport public`), con presupuesto y autorización
separados. NO completo: selector multiactivo, riesgo completo, paper
prospectivo, estrategia rentable.

## Transporte `market_stream` en vivo de ingeniería: aceptación local PASS (2026-10-28, base `90b3c9b`)

Factual: la sesión de ingeniería consume en vivo el
`market-stream-service/v1` (SSE loopback) — backend
(`engineering_session_service.py`: gates de feed vivo + consumo de
snapshots + avance live) y frontend (`EngineeringSession.tsx` /
`session-lab.ts` / `engineering-service-manager.ts` con runner
`market_stream`). Aceptación íntegra en navegador real (3020) con
productor SSE local determinista:
`docs/evidence/engineering-live-local-2026-10-28/summary.json` (corrida
379,9 s; abstención → FEED_SILENCE → señal 1.0520 → fill 1.0525 →
reinicio del servicio de mercado → salida por stop 1.0300 → cerrada;
12/12 checks; 8 reconexiones; 0 peticiones externas; net −16,59
simulado; `trial_sessions: []`; 3020 restaurado; 8792/8797 intocables).
Tests 92 passed; frontend verificado sin cambios pendientes.

Correcciones incluidas: (1) defecto del explorador canónico —
`read_stored` devolvía la CABEZA del rango con caches >5000 velas;
arreglado por COLA con regresión nueva (también afectaba al gráfico
canónico con caches grandes); (2) arnés local determinista
(`scripts/engineering_live_local_acceptance.py`) con backfill
multi-frontera, limpieza de sesiones de ensayo por corrida y
`LIMITS["entrada"]` 200 s (cadencia real del guion).

Limitaciones declaradas (no bloquean el estado local): recepción de
Binance NO acreditada (todo loopback); reparación REST inexistente en
local; churn WS ~9 s tolerado; ciclo SSE de 10 s del adaptador en
silencio. Detalle en `docs/ENGINEERING_SESSION_BACKEND_V1.md` §11.

## Inicio explícito completo desde la UI + defecto SSE corregido (2026-10-28, base `0bf96c6`)

Evidencia: `docs/evidence/engineering-explicit-start-2026-10-28/acceptance-summary.json` (casos A–G, navegador real). Detalle en `docs/ENGINEERING_SESSION_BACKEND_V1.md` §10.

1. **«Iniciar sesión» es inicio completo explícito:** con 8797 detenido, el
   click comprueba el servicio (GET consulta pura) y, si está abajo, el BFF
   genera la instancia canónica (`scripts/engineering_session_service.py`,
   sin gestor paralelo), espera readiness con límite y verifica identidad
   triple (child.pid == pid-file == /health.pid). Nunca reutiliza ni detiene
   PIDs desconocidos; fallo de arranque → banner claro y sin huérfanos ni
   sesión creada. Abrir la página NO inicia nada (chip de estado: checking /
   starting / ready / down / error).
2. **Doble clic → una sola sesión:** guardia síncrona en el componente
   (el `disabled` de React no es síncrono entre clicks; el hallazgo inicial
   creó 2 sesiones y un artefacto de archivo vacío no reproducible — causa
   UNKNOWN, `load_session` lo rechaza con `IDENTITY_UNCERTAIN`).
3. **Default de sesiones dedicado (y corrección de bug):** el `ROOT` del
   servicio apuntaba a `src/` (default previo roto); ahora default
   `data/engineering-session/sessions`, sin colisión con el controlador
   anterior; sesiones existentes sin migrar.
4. **Defecto SSE del panel de flujo RESUELTO (causa reproducida):** dos
   cortes convergentes — `AbortSignal.timeout(30_000)` del BFF (cada SSE
   moría a los 30 s) y `bodyTimeout` por defecto de undici (30 s sin chunk
   con el servicio 8792 mudo). Arreglo sin tocar 8792: agente undici
   `bodyTimeout: 0` + `headersTimeout` acotado, cancelación propagada por
   `req.signal`, y reconexión del panel con la MISMA identidad conservando
   la causa visible; desmontar/cambiar símbolo libera el consumidor. Ventanas
   de verificación 78 s + 40 s con 0 errores de consola y 0 "failed to pipe".
5. **Tests:** servicio 9/9 (nuevo: default dedicado); frontend vitest
   611 passed + 1 skip (nuevos: 4 de arranque/servicio + 3 de reconexión del
   panel); `tsc`/`eslint` 0 errores.
6. **Servicios al cierre:** 8797 detenido (sin pid-file; dir dedicado sin
   sesiones de ensayo, archivadas en evidencia); dashboard 3020 sirviendo
   `FQGAqw1wwcXIMQqei_fRA` (PID 14492); 8792 preexistente intocado
   (fuente aggTrade local sin inyectar ~26 h: el panel marca «datos
   obsoletos» honestamente).

## Acceso operativo verificado — sesión/servicio separados (2026-10-28, base `5f24807`)

Verificación de acceso desde el estado entregado (8797 detenido), con la
pestaña del operador y un servicio explícito. Evidencia:
`docs/evidence/engineering-backend-2026-10-28/operational-access-2026-10-28.json`.
Detalle completo en `docs/ENGINEERING_SESSION_BACKEND_V1.md` §8.

1. **Arranque manual declarado deliberado:** abrir `/market-lab` no inicia
   procesos; con 8797 detenido, «Iniciar sesion» muestra error visible sin
   duplicados ni escaneo (BFF proxy puro). El botón NO es inicio completo;
   el operador levanta el servicio con el CLI canónico (`--sessions-dir`
   dedicado: el default colisiona con el controlador anterior).
2. **Semántica separada y verificada:** detener la SESIÓN = política de
   posición (`detenida`, posición preservada, sin salida inventada);
   cerrar la PESTAÑA = solo desconecta el observador (el backend cerró la
   sesión solo: rev 7→31→38); detener el SERVICIO = termina drives en
   memoria y NUNCA muta el estado económico en disco ( sesión en disco
   `abierta`, sin evento de salida, recuperable y reanudable tras reinicio).
3. **Recorrido del operador probado:** iniciar (`1 POST create + 1 POST
   control + GETs`) → sesión activa → cierre/reapertura de pestaña →
   recuperación correcta (net 4.944281) → detener servicio con drive
   corriendo → estado en disco intacto → reinicio → recuperar → «Detener
   sesion» → `detenida` rev 12 sin salida inventada.
4. **Servicios al cierre:** 8797 detenido y directorios de sesiones de
   ensayo eliminados; dashboard canónico 3020 sirviendo
   `r5poURhuj3RQc4CjC6Kyz` (PID 29508); 8792 preexistente sin tocar.
   Defecto abierto del panel de flujo ERR_INCOMPLETE_CHUNKED_ENCODING:
   impacto = el stream del panel se aborta en algunos re-render; sin
   atribuirle fallos de esta sesión.
5. **Publicación:** `feat/ingenieria-autonoma` pushed (normal); 
   `review/o1-funcional-v2-observacion` estaba en `9a24308` (ancestro
   estricto) → integrado por fast-forward autorizado (sin reset/force).

## Autonomía de la sesión de ingeniería en backend (2026-10-27/28, base `0aa98f5`, rama `feat/ingenieria-autonoma`)

La sesión de ingeniería ya se conduce **desde un servicio backend Python
residente** (`engineering-session-service/v1`, puerto 8797 por defecto), no
desde un temporizador del navegador. El navegador es SOLO observador (GET
de estado cada 800 ms; iniciar/parar vía control). Distinción con el modo
anterior: replay-autoavance (React timer + `/step` spawnSync, base
`9a24308`) vs autonomía en backend (servicio residente reutilizando
`paper_lab_engine`, sin motor paralelo; detalle en
`docs/ENGINEERING_SESSION_BACKEND_V1.md`).

1. **Servicio:** `src/microstructure_probe/engineering_session_service.py` +
   CLI `scripts/engineering_session_service.py` (start/stop, `--pid-file`,
   `POST /shutdown`). Endpoints uniformes `GET /sessions/{id}` y `POST
   control` devuelven `{session, drive}` (drive hermana). Causas de
   conducción: `SESSION_CLOSED`, `END_OF_TRANSPORT`, `OPERATOR_STOP`,
   `SESSION_STOPPED`, `DRIVE_EVENT_LIMIT`, `DRIVE_ERROR:*`.
- **Semántica de abstención corregida:** `SIN_ENTRADA` = abstención
   temporal (reevalúa en cada evento nuevo; entrada confirmatoria sin
   intervención, probada determinísticamente en tests); `DESCARTADO` =
   descarte terminal (no reabre). El evaluador solo recibe el prefijo
   revelado (REVEAL, sin OHLC en eventos de transporte, sin velas futuras
   en el dict público — corrección de causalidad en `session_to_public_dict`).
2. **Aceptación en navegador real (PASS)**, evidencia
   `docs/evidence/engineering-backend-2026-10-27/` (eng-01…eng-13 +
   `acceptance-summary.json`): S1 ciclo autónomo completo (solo 2 POST:
   create+start, resto GET); S2 **cerrar pestaña no detiene la conducción**
   (revisión 33→38, `SESSION_CLOSED`) y reabrir recupera sesión cerrada con
   panel de exportación; S3 detener con posición abierta → `detenida` sin
   salida inventada (`OPERATOR_STOP` visible); S4 prefijo B → cerrada por
   horizonte (net_pnl 4.944281, kinds protección=2/entrada=1/marca=1/
   salida=1; tras recuperación 24 GET / 0 POST). Nota honesta: con la caché
   real de MINAUSDT ambos prefijos admitían entrada; no se fabricó
   abstención en datos reales (separación temporal/terminal probada en
   tests).
3. **Pruebas:** backend `tests/test_engineering_session_service.py` 8/8;
   frontend `engineering-session.test.tsx` 8/8; Python completo **1530
   passed / 2 skipped** (3 fallos PREEXISTENTES de la base corregidos:
   causalidad del dict público; presupuesto de benchmark interno de la
   ventana en `scripts/market_stream_window.py`); frontend 604 passed / 1
   skipped; `tsc`/`eslint` 0.
4. **Operativo restaurado:** dashboard canónico 3020 sirviendo el build
   nuevo `r5poURhuj3RQc4CjC6Kyz` (PID 29508; reemplazó el BUILD_ID previo
   `GC5lmJU9kuk4F0d3Z7WxI`); instancia de aceptación del servicio (8797)
   PARADA y sus directorios de sesión de prueba eliminados; servicio de
   flujo PREEXISTENTE en 8792 sin tocar (otro dueño, no iniciado ni
   detenido por este bloque); sin Binance público, 0 upstream, 0 órdenes.
   Error de consola preexistente NO a cargo del bloque:
   ERR_INCOMPLETE_CHUNKED_ENCODING en `/api/v1/market-flow/stream` (SSE de
   otro panel).

## Estado operativo canónico restaurado (2026-10-26, HEAD `3c2e7ab`)

Tras el trabajo del bloque de contexto BTC compartido, el dashboard canónico
se restauró en 127.0.0.1:3020 con entorno limpio (sin `MICROPROBE_*` ni
`MARKET_EXPLORER_*`), frontend recompilado (`next build`) y el servidor previo
detenido:

1. **Servidor final canónico:** node en `127.0.0.1:3020`, env limpio,
   `next build` aplicado, banner `Ready`, BUILD_ID servido
   `Bibj_gkaZK9si2ABtSsAb` (SHA fuente del árbol `3c2e7ab`; frontend del
   commit `3c2e7ab`). `/market-lab` y `/` = HTTP 200. Catálogo canónico
   servido solo desde caché (932 contratos, TTL 6 h vigente):
   **0 huellas públicas** (`market_fetch_ledger` sin crecimiento por las
   consultas de verificación).
2. **Servicio de datos local detenido:** `/api/v1/market-stream/status`
   → `available:false` (ECONNREFUSED); sin escuchas en 8792 ni 65375; el
   único proceso `next` del sistema es el canónico. Evidencia del bloque
   anterior intacta en `docs/evidence/indicators-v1-public-2026-10-25/`;
   evidencia del bloque actual en
   `docs/evidence/btc-context-public-2026-10-26/`; DBs canónicas solo
   leídas en la verificación (el constructor del cache prohíbe DBs
   canónicas).
3. **Acreditaciones, separación explícita:**
   - Indicadores `market-indicators/v1`: **PASS con transporte local**
     (fake WS en loopback, caché de ensayo, guardia DNS del navegador).
   - Recepción incremental Binance de indicadores: **todavía no
     acreditada** (la demo no acredita Binance real; ventana requiere
     autorización explícita).
   - Inspección visual: realizada por el agente sobre las capturas y
     consistente con el DOM; **estado: complementaria del DOM, no
     equivalente (DOM ≠ visual)**.

## Contexto BTC compartido `market-btc-context/v1` (2026-10-26, base `3c2e7ab`)

Bloque ADITIVO e independiente de `market-indicators/v1` (documentado en
`docs/SHARED_INDICATORS_V1.md` §6 y `docs/BTC_CONTEXT_V1_PLAN.md`):
muestra el movimiento del token junto al de BTC sobre velas CERRADAS
alineadas por `open_time_ms`. Contexto informativo: no es señal, no es filtro
de entrada y la diferencia de retornos no es "alpha" ni rentabilidad.

1. **Backend:** `src/microstructure_probe/kline_btc_context.py`
   (`compute_btc_context`): `ret_btc_bps_5` y `ret_diff_bps_5` sobre la
   rejilla del token, sin lookahead, `unknown` con motivo `BTC_*` (nunca
   cero ni arrastre), base común declarada para la normalización.
2. **Integración REST:** `series_payload` gana el campo aditivo
   `context_btc` (client=None → **0 upstream REST**; cuando el token es BTC
   no se emite). El navegador no recalcula.
3. **Integración stream:** `market_stream_service` gana el frame SSE
   `event: context` (recalculado al cerrar token o BTC) y la suscripción BTC
   vive en el mismo hub combinado (refcount, sin duplicar).
4. **Frontend:** `market-chart-contract.ts` (`sanitizeContextBtc`,
   `parseContextBtc`, `applyStreamContextBtc`, badge con unidad),
   `market-stream.ts`, `use-market-stream.ts` (listener `context`),
   `PriceChart.tsx` (badge junto al de indicadores + tira normalizada
   `BtcCompareStrip`).
5. **Pruebas con transporte local:** 13 pruebas de unidad del módulo +
   integración `series_payload`; 6 pruebas SSE del servicio (snapshot,
   frame por cierre de token y de BTC, suscripción compartida/no
   duplicada, símbolo=BTC sin bloque, intervalo inválido); demo
   `scripts/btc_context_public_demo.py` → **PASS 12/12**, 0 peticiones
   públicas (browser_external 0, ledger 0), 1 carga de página, sin recarga
   en actualizaciones, capturas en
   `docs/evidence/btc-context-public-2026-10-26/`.
6. **Acreditaciones:** bloque **PASS con transporte local**; recepción
   incremental Binance real NO acreditada (requiere ventana de operador).

## market-indicators/v1: hilo incremental por cierre + demo de entrega del navegador (transporte local) PASADA (2026-10-25, base `2ffdede`)

Cierre del bloque indicadores sobre la integración del 2026-10-25
(`09632f4`): contrato verificado, recalculo incremental en el servicio,
demo de navegador con transporte local. Todo con **0 llamadas Binance**
(fake WS en loopback, guardia DNS en el navegador, ledger 0). Desktop.

1. **Contrato verificado (no se dobló):** `velocity_bps_5` = 5 velas
   cerradas (t−4..t, 4 saltos), ventana validada POR TIEMPO (rejilla de
   `open_time`) — `test_velocity_window_is_temporal_not_positional`.
   Contexto BTC: fuente requerida vs solicitudes realmente necesarias (0 si
   ya está en cache; nunca "+N upstream" fijo). Huecos del grid → UNKNOWN
   declarado (`GAP_IN_WINDOW`/`INSUFICIENT_CANDLES`), nunca reparado.
2. **Recalculo incremental backend** (`src/microstructure_probe/
   market_stream_service.py`): `snapshot` SSE lleva el MISMO bloque
   (`series_payload(allow_fetch=False)`); en cada `closed` el servicio
   fusiona la vela por `open_time` (continuidad temporal, no posiciones),
   recalcula con `kline_indicators` y emite `event: indicators` ANTES de
   `closed`; la vela provisional NUNCA entra a la ventana de sesión.
   Frontend (`market-chart-contract.ts`/`market-stream.ts`/
   `use-market-stream.ts`): `applyStreamIndicators` sanitiza, guarda
   identidad y une filas (nuevo gana) SIN recalcular ni recargar. Badge con
   UNIDADES (`ret ...bps · vel ...bps · relvol N.xxx · vwapdev ...bps`).
3. **Demo de entrega PASSED (navegador con transporte local; sin Binance
   real)** (`scripts/indicators_v1_public_demo.py` →
   `docs/evidence/indicators-v1-public-2026-10-25/`): veredicto PASS,
   15/15 verificaciones DOM contra el backend real (1 carga de página;
   valores del badge = fila del backend al cursor; fila GAP →
   `UNKNOWN(GAP_IN_WINDOW)`; el cierre actualiza el badge sin
   reload; provisional excluido; cambio BTCUSDT→MINAUSDT limpia valores sin
   recarga), 0 solicitudes Binance probadas (browser_external 0, ledger 0),
   BUILD_ID `e_lib1MO18w7gv6PJG2rm`, URL servida `http://127.0.0.1:3020`
   (puerto servido durante la corrida; el finally detiene el arbol con
   taskkill /T a partir de la correccion de esta sesion). Capturas
   `shot-1h-values.png`,
   `shot-1m-close.png`, `shot-mina-values.png`: revisión visual del
   operador aparte (la demo no la sustituye; DOM ≠ visual).
4. **Lección de infraestructura (importante):** los primeros fallos de la
   demo NO eran código: un `next start` huérfano de una corrida previa
   vivía en 3020 con el cache de OTRA ejecución y envenenaba el payload de
   comparación (precios deterministas iguales, huecos en otras filas). La
   demo ahora valida la identidad del dashboard (aborta con 3020 ocupado,
   `EADDRINUSE` o sin banner Ready propio). Ver DECISIONS 2026-10-25.
5. **Pruebas de cierre:** backend 171 PASS (kline/explorer/history_client/
   budget/market_stream; `test_kline_indicators` 19, `test_market_stream`
   34); frontend 592 PASS/1 skipped; `tsc --noEmit` 0; `eslint` 0 en los
   archivos tocados. COMMIT del bloque (ver TASK_QUEUE).

## Indicadores compartidos V1: primera integración vertical (2026-10-25, base `09632f4`)


Inventario verificado de los motores de Fase 1 y su integración como
indicadores compartidos sobre velas cerradas en `/market-lab`. Documentado en
`docs/SHARED_INDICATORS_V1.md`; contrato en la §11 de
`docs/MARKET_EXPLORER_CONTRACT_V1.md`. Sin Binance (0 llamadas; datos locales,
`client=None`), sin estrategia, sin señales, sin optimización, desktop.

1. **Inventario (implementado/fuente):** retornos log y velocidad/aceleración
   viven en los motores P1-04/P1-05 sobre mark price WS; flow/delta en
   P1-06 sobre aggTrade WS; spread/profundidad en P1-07 sobre libro WS; OI en
   P1-07 sobre REST público de OI; VWAP en P1-08 sobre flow + mark price.
   El volumen relativo NO estaba implementado. Ninguna de esas fuentes viaja
   en el canal de velas `/market-lab`, así que flow/spread/profundidad/OI y
   contexto BTC quedan DECLINADOS con motivo (`declined[]`), nunca derivados
   de OHLC ni servidos como cero.
2. **Subconjunto elegido v1** (`market-indicators/v1`, backend único autoridad,
   solo velas cerradas del rango del propio payload): `log_return_bps`,
   `velocity_bps_5`, `rel_volume_10` (nuevo), `vwap_typical_10` +
   `vwap_dev_bps_10` (aproximación por precio típico y `base_volume`,
   declarada como NO siendo el VWAP de negociación de P1). Fórmulas,
   unidades (bps/ratio/precio), ventana, calentamiento, disponibilidad
   (`available_at_ms = open_time + interval_ms`) y huecos
   (`GAP_IN_WINDOW`/`INSUFICIENT_CANDLES`/`MISSING_VOLUME`/`NO_PREVIOUS_CANDLE`,
   nunca 0) en el contrato; sin lookahead (anclado por test) y sin
   indicadores provisionales (la vela en formación se EXCLUYE, no se estima).
3. **Integración /market-lab:** payload `market-series/v1` lleva el bloque
   opcional `indicators`; el gráfico `market-chart/v1` lo publica como
   `MarketIndicatorsBlock | null` (guard de versión/identidad: un bloque de
   otro símbolo/intervalo o corrupto se descarta entero); badge junto al
   gráfico con valores y UNKNOWN(motivo) de la vela bajo el cursor; cambio
   de símbolo/intervalo reemplaza el modelo completo (sin arrastre);
   `mergeEarlierSeries` une filas validadas de ambos bloques sin recalcular
   en el navegador; el feed de stream no recalcula nada.
4. **Precisiones documentales de la pasada anterior:** (a) `execution_id`
   es etiqueta de atribución por ejecución/petición (`bff-<uuid>` por cada
   petición del dashboard, o el que pase el CLI), no el id de corrida
   (run id O1/O2) y no el ámbito de compartición: el presupuesto se comparte
   en la ventana móvil de 60 s del archivo del ledger, filtrada SOLO por
   tiempo, sin `execution_id`, símbolo ni proceso; (b) la automatización del
   lado navegador YA está implementada (`scripts/market_stream_local_acceptance.py`,
   PASS×2 en loopback el 2026-10-24) y lo pendiente es solo ejecutarla en
   una ventana Binance real con `--transport public` y autorización
   explícita del operador.

Pruebas: backend `tests/test_kline_indicators.py` (18) + suites del
explorador en verde (56); frontend `market-indicators.test.ts` (15),
`price-chart-market.test.tsx` 11/11, `market-chart-contract` 13/13,
`contract-explorer` 12/12 — `tsc` 0, `eslint` 0. Evidencia local:
`docs/evidence/indicators-v1-2026-10-25.json` (0 upstream; series continua,
con hueco/volumen ausente y `mark_klines` sin volumen).

## Presupuesto REST upstream: alcance verificado y corregido (2026-10-25, base `309aee1`)

Verificación informativa del bloque anterior (`1b36647`/`309aee1`), solicitada
por el operador, con **transporte local** y sin abrir Binance (0 llamadas
Binance; servidor HTTP en 127.0.0.1 para los procesos). Alcance verificado en
`309aee1` y su **corrección aplicada reutilizando mecanismos existentes**:

1. **Compartido entre procesos**: el contador con presupuesto efectivo vive en
   `market_fetch_ledger` (SQLite) y ya era compartido, pero se registraba
   DESPUÉS de la petición (postenvio). CORREGIDO: nueva reserva transaccional
   `reserve_fetch_attempt` (CHECK + INSERT en una transacción
   `BEGIN IMMEDIATE`): cada intento HTTP reserva 1 cupo ANTES de enviarlo, así
   que dos procesos concurrentes no pueden superar el límite.
2. **Cada intento (páginas y reintentos) reserva antes del transporte**: nuevo
   `LedgerAttemptGate` conectado a `HistoryClient` como `attempt_gate`. La
   denegación lanza `UpstreamBudgetExceeded` (nueva subclase con
   `RateLimitExceeded`) antes de abrir socket; el intento bloqueado queda
   auditado en el ledger con `requests=0` (no consume). Sin la puerta el
   registro por intento era lista en memoria (`upstream_requests`) que
   moría con el proceso.
3. **Registros persistidos por execution_id**: `market_fetch_ledger`
   ampliado con columnas `execution_id` y `detail` (ALTER idempotente; las
   filas históricas quedan `NULL` = UNKNOWN, no se reescriben). La fila se
   cierra tras el intento con resultado, reintento, duración, endpoint y
   rango reales (JSON en `detail`). Un CLI sin `--execution-id` deja
   `NULL` (UNKNOWN) — no se inventa identidad.
4. **Camino real dashboard → BFF → CLI**: CORREGIDO. `market-series` y
   `market-contracts` generan `--execution-id bff-<uuid>` por petición y el
   CLI lo propaga (`build_client(cache, execution_id)` con puerta al ledger).
   El límite sigue siendo el existente: 30/min compartido, recortado por el
   CLI (nuevo `--max-upstream`) y el `pages ≤ 2` del BFF. El "2 upstream" del
   arnés de ventana era y sigue siendo un techo del navegador, no un límite
   del backend (`F-CHART-BINANCE-04` visible en el JSON de evidencia).
5. **Defecto latente corregido**: el limitador per-instancia de peso
   (`_window_weight`) no acumulaba peso (verificado en `309aee1` con el test
   ya fallado `test_third_request_blocked_before_send`: nunca bloqueaba más
   que esperas). Se restauró la acumulación en el éxito; sigue siendo
   autopacing de peso Binance, NO presupuesto compartido de intentos.

**Alcance que sigue fuera de este control** (documentado, sin cambios): la
reparación REST del servicio de stream (`build_recovery` en
`market_stream.py`) usa su propio cliente sin puerta al ledger compartido; el
catálogo con gate igualmente queda al default 30/min; `--api-base` solo
admite `http://127.0.0.1|localhost` (sin red pública).

**Pruebas focalizadas**: `tests/test_budget_scope_shared.py` (10) — dos
procesos reales del CLI concurrentes comparten límite=2 (2 upstream), un
tercer intento bloqueado antes del transporte (0 hits nuevos), los reintentos
(500→reintento) consumen 2 cupos y además bloquean al tercer
proceso, las filas sobreviven a cada proceso y reconstruyen el consumo por
`execution_id` (`requests_sum` exacto); carrera de 3 contendientes con
límite=2: 2 concedidas/1 denegada. `tests/test_history_client_budget.py`
(5, corregido el test que reclamaba bloqueo imposible) +
`tests/test_market_explorer.py` + `tests/test_market_stream_budget.py` +
`tests/test_market_stream*.py` + `tests/test_history.py`:
**147 passed** (`pytest -k "explorer or history_client or budget or
market_stream"`). Frontend: `tsc` 0, `eslint` 0, vitest explorador 48/48.
Migración aplicada a `data/market-cache/market_cache.db` real y verificada con
`--no-fetch` (0 upstream). Evidencia:
`docs/evidence/rest-budget-scope-2026-10-25.json`.


## Segunda ventana real ejecutada (2026-10-24 14:04Z, base `2f2f9ea`): cadena correcta, aceptación FAIL (F-CHART-BINANCE-04)

Ejecutada **una sola** ventana autorizada el 2026-10-24 entre `14:04:37.065Z` y
`14:05:43.957Z` (66,89 s de 180 s), base `2f2f9ea`, BUILD_ID
`y_fx2dQ35CUiQeOHtUhfl` servido por PID 32712, intervalo `1m`, símbolos
`BTCUSDT` + `MINAUSDT`, una conexión WS combinada (`--transport public`, 1
intento, 0 reconexiones) y tres consumidores SSE (navegador + BFF + servicio).
Sin monitor, sin paper, sin órdenes, sin móvil.

**Cadena medida (real).** 58 mensajes / 58 aplicados / 2 cierres; 46 eventos de
vela `BTCUSDT` y 12 `MINAUSDT`; 38 actualizaciones provisionales de la misma
apertura; cierre `1792850640000` y siguiente vela `1792850700000`; BFF con 46
eventos e identidad `BTCUSDT/1m`; 0 huecos; pico de consumidores 3 y residual 1;
parada limpia (exit 0, puerto 8791 cerrado, PID file eliminado, `/health`
rechazado); DBs canónicas intactas. La paginación del navegador subió el gráfico
de 300 a 600 velas con identidad preservada, pero terminó después del `hold` de
20 s. 2 peticiones REST públicas de velas (inicial de 299 + paginación de 300);
el catálogo se sirvió de caché (`catalog_fetched_at_ms` 13:53:27Z, sin
`exchangeInfo` en la ventana).

**Veredicto medido: `FAIL` (exit 1), `acquired=true`.** Fallan
`consumers_released` (la desconexión del navegador no se ejecutó en los 20 s),
`browser_reconnected` (sin liberación previa no acredita reconexión),
`dom_state_live` y `dom_update_fresh` (captura #2 `OBSOLETO`/`no LIVE`, 35 s
después de la parada), `dom_pagination_preserved` (error de frescura) y
`dom_after_stop` (sin aviso `explorer-stream-down`); falta `dom_candles_grew`
(la captura #1 llegó ~2 s después del cierre). La cadena real sí llegó al
gráfico; el fallo es del procedimiento de captura/liberación, no de los datos.
`visual_review=NOT_REVIEWED`.

**Hallazgo abierto.** El lado navegador (capturas, paginación, desconexión y
reconexión) debe automatizarse y acotarse dentro de la ventana, o separarse en
fases; el `hold` de 20 s no cubre una paginación lenta. El aviso de servicio
detenido sigue dependiendo de que el BFF cierre el SSE o de que el hook
reconsulte `/status`. No se repite la ventana sin autorización explícita.
Evidencia: `docs/evidence/market-stream-window-2026-10-24.json` y sus tres DOM.

## Ventana viva ejecutada una vez: cadena real hasta el navegador, veredicto FAIL por la evidencia DOM (2026-10-24, F-CHART-BINANCE-04)

Ejecutada **una sola** ventana autorizada el 2026-10-24 entre `00:47:04Z` y
`00:48:27Z` (83,46 s de 180 s), base `4956dee`, BUILD_ID
`eiXlHvN4lJBLWcuOopsh_` servido por PID 33960, intervalo `1m`, símbolos
`BTCUSDT` + `MINAUSDT`, una conexión WS combinada y tres consumidores SSE
(navegador + BFF + servicio). Sin monitor, sin paper, sin órdenes, sin móvil.

**Cadena medida (real, no simulada).** Un solo intento de socket, **0
reconexiones**; contadores del servicio con `messages=applied` sin descuadre;
96 eventos de vela de `BTCUSDT` y 14 de `MINAUSDT`; 50 actualizaciones
provisionales sobre la misma apertura; **cierre confirmado** de la vela
`1792802820000` y **siguiente vela** `1792802880000`; `BFF` entregó 96 eventos
con identidad `BTCUSDT/1m`; 0 huecos; pico de consumidores **3** y residual
**1** (el navegador) al cerrar. Cadencia medida (no asumida): mediana 418 ms,
mínimo 250 ms, máximo 12041 ms. Parada limpia: exit 0, puerto 8791 cerrado, PID
file eliminado, `/health` rechazado; `microprobe.db` y `historical.db` con mtime
2026-10-15 11:46:27 (intactas); `market_cache.db` sí cambió (caché aislada del
explorador por la paginación REST, comportamiento esperado).

**Evidencia DOM (navegador real, Chromium de escritorio).** Captura #1 a las
`00:47:46Z`: `Binance USD-M · BTCUSDT · 1m · market-stream/v1`, `RECIBIENDO`,
`LIVE`, 299 velas, `nav=1`/`reload=0`. Captura #2 a las `00:48:29Z`: misma
identidad, 303 velas y paginación `300→303` con identidad preservada y sin
error, **pero ya con el servicio parado** (`DESCONECTADO`/`no LIVE`). Captura
#3 a las `00:50:06Z`: `DESCONECTADO`, `no LIVE`, 303 velas conservadas, sin
aviso de "servicio detenido".

**Veredicto medido: `FAIL` (exit 1).** `acquired=true`; los 19 checks de cadena,
servicio, presupuesto y DBs pasan (`dom_identity`, `dom_update_fresh`,
`dom_candles_grew` 299→303, `dom_pagination_preserved`, `dom_no_reload` también).
Fallan solo dos checks obligatorios del navegador:
`dom_state_live` (la captura #2 llegó 7 s después de la parada: la espera de
20 s expiró mientras se completaba la paginación) y `dom_after_stop` (no
apareció el aviso `explorer-stream-down` porque el `EventSource` del BFF siguió
abierto y no se agotaron los reintentos ni se reconsultó `/status`). **No es un
fallo de datos**: la cadena real llegó al gráfico; es un fallo del procedimiento
de captura y del aviso de servicio detenido.

**Hallazgos abiertos.** (1) La paginación subió el contador `300→303` mientras
la caché creció ~45 KB: el bloque anterior no se reflejó como +300 en pantalla;
requiere análisis aparte. (2) El aviso "servicio detenido" no aparece si el
servicio muere con la página abierta. (3) La espera de 20 s es insuficiente si
la paginación se hace después del cierre. **No se repite la ventana** sin nueva
autorización explícita.

## Ventana viva por el camino real — preparada y probada sin Binance (2026-10-22, F-CHART-BINANCE-04)

Prepara (sin ejecutar) la ventana que demuestra datos Binance recorriendo la
cadena real `Binance → hub → servicio SSE → BFF → /market-lab`. Base `a2d0824`
(rama `review/o1-funcional-v2-observacion`). Escritorio, presupuesto cero,
observación. **La conexión continua a Binance sigue sin abrirse.**

**Corrección de diseño.** El script anterior hablaba directamente con el hub y
saltaba HTTP/SSE. Ahora `scripts/market_stream_window.py` **reutiliza** el
servicio existente `scripts/market_stream_service.py`: lo arranca, espera
`/health`, abre un consumidor SSE por símbolo contra el servicio y otro contra el
BFF `/api/v1/market-stream`, y lo para. No hay segundo servicio ni segundo
gestor; el script solo orquesta y recoge evidencia.

**Presupuesto propuesto.** 1 conexión WS combinada; 2 streams (`BTCUSDT` del
trío + `MINAUSDT` fuera del trío); intervalo `1m`; duración máxima 180 s;
`--hold-seconds 20` tras aceptar; `--max-messages 1200`; `--max-events 6000`;
`--max-reconnects 3`; 3 consumidores SSE (2 al servicio, 1 al BFF); `bars=300`;
snapshot desde el almacén existente sin REST; 1 paginación manual; reparación de
huecos acotada ya contemplada; sin persistencia.

**Adquisición separada del veredicto.** `evaluate_acceptance` es una función pura
y probada: `PASS` exige cadena completa **y** evidencia DOM; cadena completa sin
DOM (o sin BFF) → `UNKNOWN`; cero mensajes, identidad incorrecta, BFF caído,
hueco sin reparar, cierre sucio o DB canónica tocada → `FAIL`; adquisición
interrumpida antes del cierre → `UNKNOWN`. La revisión visual es un campo aparte
y nunca sustituye a DOM ni a Binance.

**Evidencia controlada (sin Binance).** `tests/test_market_stream_window.py`
20/20: evaluador (cero mensajes, presupuesto agotado, aborto, DOM ausente,
DOM contradictorio, hueco, identidad, BFF omitido/caído, parada sucia, DB tocada),
`--finalize` y **cadena completa controlada** con un WS local que imita el mensaje
combinado de Binance, arrancando el servicio real como subproceso.
`docs/evidence/market-stream-window-loopback-2026-10-22.json` registra esa
ejecución: `ACCEPTANCE_REACHED`, `acquisition_finished=true`, servicio parado,
puerto cerrado, PID file eliminado, `verdict=UNKNOWN` por falta de BFF/DOM y
`transport.origin=loopback_test`. BFF: 5/5 en
`frontend/src/app/api/v1/market-stream/route.test.ts` (reenvío SSE, 503
`STREAM_SERVICE_DOWN`, rechazo de identidad/ventana/origen). Focalizado backend
`tests/test_market_stream.py` + nuevo: 48/48; `tsc --noEmit` 0; `eslint` 0.

**Servido.** Preflight real contra el dashboard ya servido: `/market-lab` 200,
`BUILD_ID` `n6FZutTsk5m8FFilTlxIo` presente en el HTML, `/status` 200 con
`available=false` (servicio detenido, correcto), puerto 8791 libre. No se
reconstruyó el frontend (solo se añadió una prueba).

**Seguridad y limpieza.** `data/microprobe.db` y `data/historical/historical.db`
conservan tamaño y mtime `2026-10-15 11:46:27`. No se arrancó el monitor, no se
crearon sesiones Paper Lab, no hay procesos ni listeners residuales. El servicio
continúa **detenido**.

`NEXT`: autorizar (o no) la ejecución de `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md`
con los tres comandos ya fijados y registrar el resultado como verificado con
Binance solo si se mide.

## Actualización continua de velas en el explorador de mercado (2026-10-21, F-CHART-BINANCE-03)

Vela en formación actualizándose sin recargar la página en `/market-lab`, sobre
el explorador ya entregado. Base `469e282` (rama
`review/o1-funcional-v2-observacion`); encadena el bloque anterior
`F-CHART-BINANCE-02` (`25c8c8c`, `25a0f01`). Escritorio, presupuesto cero,
observación. Sin indicadores nuevos, sin selección automática, sin paper con
datos vivos, sin riesgo/estrategias/optimización, sin órdenes, sin capital, sin
pagos, sin móvil, sin REA. **La conexión continua a Binance no se ha abierto**:
la ventana viva está preparada y requiere autorización aparte.

**Contrato antes de implementar.** `docs/MARKET_STREAM_CONTRACT_V1.md` (14
secciones: identidad `(venue, symbol, interval)`; tiempos UTC en ms con unidad
declarada; provisional vs cerrada; orden/dedupe/mensajes tardíos; snapshot +
stream con buffer y reconciliación; estados y frescura; errores y recuperación;
tabla de presupuesto; ciclo de vida y separación de planos; almacenamiento y
retención; eventos SSE; `/health`; fuera de alcance; camino de retirada).

**Backend (autoridad).** `src/microstructure_probe/market_stream.py`:
`KlineStreamHub` (suscripciones con refcount, anillo de 300 velas cerradas por
suscripción, contadores, detección de huecos, reparación REST acotada) y
`BinanceKlineTransport` (una sola conexión combinada a
`wss://fstream.binance.com/market/stream?streams=…`, backoff 1 s → 30 s con
jitter ±25 %, presupuesto de 20 fallos, `serverShutdown`, frames de control
≤ 2/s). `src/microstructure_probe/market_stream_service.py`: servidor SSE en
loopback (biblioteca estándar, sin dependencias nuevas) con `/health`,
`/stream` y `/shutdown`; snapshot desde el almacén existente con
`series_payload(allow_fetch=False)` (no duplica REST ni inventa velas); PID file
`data/market-stream/service.json`. Scripts `scripts/market_stream_service.py`
(arranque/parada explícitos) y `scripts/market_stream_window.py` (ventana viva:
sin `--execute` solo imprime el plan). La suscripción canónica del bot no se
tocó y el monitor no se arranca al abrir una página.

**Frontend (solo presenta).** BFF `GET /api/v1/market-stream` (proxy SSE con
validación de símbolo/intervalo/rango y 503 `STREAM_SERVICE_DOWN` si el servicio
está parado) y `GET /api/v1/market-stream/status` (siempre 200 con
`available`). `market-stream.ts` (tipos `market-stream/v1`, fusión por
`open_time` donde la cerrada gana sobre la provisional, `LIVE` calculado con las
cuatro condiciones), `use-market-stream.ts` (una `EventSource` por gráfico,
sin reabrir al paginar, cierre al desmontar, tope de 6 reintentos),
`PriceChart.tsx` (serie propia ámbar translúcida para la vela en formación;
actualización incremental de la cola sin reescribir cerradas) y
`ContractExplorer.tsx` (panel de estado: fuente/identidad, estado, LIVE, última
actualización recibida, velas en pantalla, huecos, aviso de servicio detenido).

**Estados separados.**

- **Implementado:** feed continuo bajo demanda con conexión compartida,
  snapshot+stream coordinados, provisional/cerrada real, reconexión con backoff,
  reparación de huecos acotada y declarada, frescura y estados honestos,
  presupuesto y límites, panel de estado y aviso de servicio detenido.
- **Probado con transporte controlado (sin Binance):** backend
  `tests/test_market_stream.py` **28/28** (A snapshot+novedades concurrentes sin
  huecos ni duplicados; B provisional → cierre → nueva; C cambio de
  símbolo/intervalo sin contaminación; D tardíos/duplicados/inválidos/identidad;
  E desconexión → obsolescencia → estado honesto; F reparación completa,
  parcial y fallida; G dos consumidores y liberación con gracia; H recarga sin
  suscripciones duplicadas; I servicio detenido sin falso LIVE; más URL/backoff,
  frames de control y HTTP/SSE en puerto efímero). Suite backend completa
  `pytest tests -q` **1405 passed, 2 skipped**. Frontend
  `market-stream-contract.test.ts` + `use-market-stream.test.tsx` +
  `price-chart-market.test.tsx` (serie provisional y no reescritura de
  cerradas) + `contract-explorer.test.tsx`; suite completa **538 passed + 1
  skipped (539)**; `tsc --noEmit` 0 errores; `eslint src` 0 errores y 5 warnings
  preexistentes; `next build` OK.
- **Servido:** BUILD_ID **`n6FZutTsk5m8FFilTlxIo`**, PID **18112**,
  `http://127.0.0.1:3020`. Se paró únicamente la instancia identificada
  (PID 32104, `next start -p 3020`, comprobando antes `job_state.json=completado`,
  0 procesos Python y puerto libre) y se reconstruyó. HTTP 200 en `/market-lab`,
  `/overview` y `/paper-lab-live` con el BUILD_ID servido.
- **Verificado con Binance:** **NO**. No se abrió ninguna conexión continua. La
  ventana acotada (1 conexión, 2 símbolos, 1 min, 400 mensajes) está descrita en
  `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` y su script solo se ejecutó en modo
  plan. Por tanto la recepción real, la cadencia de la vela en formación y la
  confirmación de cierre **no** están verificadas: no se declaran.

**Comprobación en navegador (DOM/red, sin PASS visual).** `/market-lab` servido:
`MINA` → `MINAUSDT` (PERPETUAL/TRADING/elegible) → 299 velas con 1 provisional y
`COVERED`; panel de feed con `DESCONECTADO · servicio detenido`, `no LIVE`,
`sin mensajes`, `299 cargadas · 1 provisional` y el aviso de servicio detenido.
Red observada: **1** petición `market-series`, **1** `market-stream/status`,
**0** intentos de `EventSource` (el estado dijo `available:false`), y el proxy
`/api/v1/market-stream` responde **503** `STREAM_SERVICE_DOWN` si se fuerza. El
histórico sigue visible y **no** se declara LIVE: caso I verificado en el
navegador. Sin inspección por modelo de visión (sigue sin proveedor): no hay
PASS visual.

**Smoke del servicio local (sin suscriptores, sin Binance).** Arrancado en
`127.0.0.1:8799`: `/health` 200 con `socket.connected=false`, `attempts=0`,
`streams=[]`, `consumers=0` y `persistence=MEMORY_ONLY`; PID file escrito con el
PID real. `--stop` devolvió 200, borró el PID file, liberó el puerto y no dejó
procesos Python. **El servicio continuo queda detenido.**

**Presupuesto y no contaminación.** Esta sesión hizo 2 peticiones REST de velas
(la del navegador y una comprobación explícita), 0 reintentos, 0 fallos; el
ledger acumulado del caché aislado queda en **25 peticiones, 0 reintentos, 0
fallos** (`market_klines` 1795 filas, `market_cache.db` 442 368 B). `data/
historical/historical.db` y `data/microprobe.db` siguen con mtime
**2026-10-15 11:46:27** (sin escrituras). No se persisten actualizaciones del
feed (crecimiento en disco del feed: 0). No se crearon sesiones Paper Lab ni se
tocó su motor.

## Accesos directos V2 — 2026-10-21 (F-NAV-V2-ACCESS-01)

La navegación incorpora `Mercado / Gráficos` -> `/market-lab` en Terminal, `Paper Lab — Simulación` -> `/paper-lab-live` y `Replay histórico` -> `/paper-lab` en Laboratorios. Se elimina el rótulo ambiguo Future workspace para estas capacidades existentes. ContractExplorer aparece antes del contenido histórico previo en /market-lab. Se preservan rutas y motores.

Verificado: navigation.test.tsx 4/4, tsc --noEmit y eslint de los dos archivos exit 0; next build exit 0 (13 advertencias de tracing preexistente en rutas no modificadas). BUILD_ID `3ThnqxocDEmcursE2ZYpu`, servidor propio PID 32104 (sustituye solo PID 16164 tras revalidar PID+creation time+comando y ausencia de monitor/Python). HTTP /overview, /market-lab, /paper-lab-live y /paper-lab 200; enlaces exactos y BUILD_ID comprobados en HTML servido. El cambio de navegación es de bajo impacto; backend y DB no cambiaron, no se repite su suite. Inspección visual/clics de navegador NO realizada: no hay herramienta de navegador disponible para esta sesión; verificación por pruebas de componente y HTML servido, sin PASS visual.

ESTADO DEL OBJETIVO VIVO: estos accesos NO implementan streaming. Mercado consulta histórico REST bajo demanda; Paper Lab usa fixtures; Replay reproduce histórico. El usuario reitera el objetivo de buscar contratos Futures elegibles y verlos actualizarse en vivo. Pendiente: adaptar feed existente, gestión compartida de suscripciones, vela provisional/cerrada, reconexión y reparación de huecos, frescura visible e indicadores backend compartidos; pruebas controladas y ventana acotada. No suscribir todo el universo a máxima resolución por pestaña ni confundir catálogo completo con seguimiento permanente. Abrir gráfico nunca abre una operación. Contrato rector: [ACUERDOS_GRAFICO_BINANCE_V1](ACUERDOS_GRAFICO_BINANCE_V1.md). Sin adquisición, monitor, paper prospectivo, órdenes, pagos, móvil ni gates en este cambio.

## Explorador de contratos USD-M e histórico paginado bajo demanda (2026-10-21, F-CHART-BINANCE-02)

Sección «Contract explorer» en `/market-lab` con búsqueda de contratos Binance **USD-M Futures** e histórico por REST público **bajo demanda**. Base `9689f3e`. Escritorio, presupuesto cero, observación. Sin websocket, sin monitor, sin feed continuo, sin paper prospectivo, sin órdenes, sin indicadores y sin móvil. No se tocaron reglas, umbrales, costes, funding ni la mecánica canónica de `backtest_offline`; `paper-chart/v1` y sus testids se conservan intactos.

**Backend.** `src/microstructure_probe/market_cache.py` (sqlite aislado en `data/market-cache/market_cache.db`, override `MICROPROBE_MARKET_CACHE_DB`; rechaza rutas canónicas), `market_explorer.py` (catálogo, elegibilidad con motivos, cobertura, plan del bloque faltante, adquisición acotada, payload `market-series/v1`) y `scripts/market_explorer.py` (CLI `catalog|series`). Reutiliza `discovery.py` (criterio PERPETUAL/TRADING/USDT), `history_client.py` (`exchange_info`, `paginate_klines`, `earliest_bar`, limitador, 429/418) y **lee** `data/historical/historical.db` sin escribir. Presupuesto: catálogo TTL 6 h y 1 petición por refresco; bloques de 300 velas, `pages ≤ 2`, concurrencia 1, timeout 20 s, 30 peticiones/minuto en ventana móvil, 0 reintentos propios.

**Frontend.** BFF `GET /api/v1/market-contracts` y `GET /api/v1/market-series` (validación de símbolo/intervalo/fuente/rango, origen permitido, `no-store`), cliente `market-explorer.ts`, contrato `market-chart/v1` (`market-chart-contract.ts`) y componente `PriceChart.tsx` generalizado por unión discriminada: `PaperChart.tsx` pasa a ser una fachada para no romper importaciones ni testids. `ContractExplorer.tsx` añade búsqueda, estados y paginación. La vela no cerrada se marca `provisional` con `close_time_ms=null`; el volumen solo se dibuja si la fuente lo publica, con unidad declarada; `operation=null`/`session_id=null` y guarda explícita contra marcas de Paper Lab.

**Correcciones incluidas en Paper Lab.** (a) El selector de persistencia ya se renderiza en la pantalla inicial, así que una sesión guardada se puede listar y recuperar **sin crear otra fixture** (antes exigía seleccionar una fixture primero). (b) El encuadre inicial se difiere hasta que el contenedor tiene ancho real y solo se aplica una vez; las actualizaciones y los bloques antepuestos ya no reencuadran. Ambas con prueba nueva; la recuperación se verificó además con clic real sobre el build servido (solo `GET` de lista y de sesión: 0 mutaciones).

**Estados separados.**
- **Implementado:** catálogo cacheado con búsqueda y motivos; histórico leído de canónico+caché, adquisición del bloque faltante y paginación; cobertura con huecos/ausencia/fin de histórico; gráfico de mercado sin indicadores ni marcas de operación; errores y presupuesto explícitos en la UI; correcciones (a) y (b).
- **Probado:** backend completo `pytest tests -q` **1375 passed, 2 skipped** (33 subtests); focalizado `tests/test_market_explorer.py` **41/41** (incluye regresión de «primer refresco sin eventos inventados» y de diff sobre catálogo completo >500). Frontend `vitest run` **520 passed + 1 skipped (521)**; `tsc --noEmit` 0 errores; `eslint src` 0 errores y 5 warnings preexistentes (ninguno en archivos nuevos); `next build` OK.
- **Servido:** build `9xXiQvrFIA0YaC3Vc_61F`, PID 16164, `http://127.0.0.1:3020/market-lab`, HTTP 200. Reemplazó únicamente la instancia identificada del proyecto (listener 27612 / lanzador 24664) tras comprobar `job_state.json=completado`, ausencia de procesos Python activos y puerto libre. Logs en `%TEMP%\opencode\dashboard-start.{out,err}.log`.
- **Inspección visual:** DOM/geometría/HTTP y capturas locales. **No** hubo inspección por modelo de visión (OpenRouter sin autenticación; NVIDIA 401), así que **no se declara PASS visual**. Evidencia objetiva sustitutiva: 7 `<canvas>` en el gráfico, 6.688 muestras opacas en el canvas principal (papel) y recuento de píxeles de color de vela con `bounding box` 220–1380 × 520–698 (mercado); tras paginar, la diferencia entre capturas es de 11.189 píxeles (1,6 % del área), compatible con «no reencuadre».

**Verificación REST acotada (2026-10-22T02:00–02:10Z).** Ledger del propio caché: **16 peticiones públicas, 0 reintentos, 0 fallos**; 4 de catálogo (`exchangeInfo`) y 12 de velas (BTCUSDT 5, MINAUSDT 7).

| Consulta | Peticiones | Resultado |
|---|---|---|
| Catálogo `exchangeInfo` | 1 por refresco (4 en total, incluidos los forzados de verificación) | 931 contratos; `stale=false`; 0 eventos de listado/baja espurios tras la corrección |
| BTCUSDT 1h, bloque de 300 | 1 (ventana actual) + 1 (bloque anterior) | 299 velas `COVERED` sin huecos; 299 → 556 al paginar; última vela `provisional` |
| MINAUSDT 1h, bloque de 300 | 1 (ventana actual) + 1 (bloque anterior) | 299 `COVERED`; 556 velas con **43 huecos reales** del canónico (`PARTIAL`) |

Caché resultante: 598 velas, 931 contratos, 316 KB, 0 eventos. Sin escrituras en `data/historical/historical.db` ni en `data/microprobe.db` (solo lectura; sus mtimes siguen en 2026-10-15). Sin sesiones paper nuevas: `/api/v1/paper-lab/sessions` respondió solo a `GET`.

| Caso | Evidencia |
|---|---|
| A. Buscar y seleccionar | Navegador: `MINA` → 1 fila `MINAUSDT` (PERPETUAL/TRADING/elegible) → «Ver histórico» → 1 petición. Prueba `contract-explorer.test.tsx`. |
| B. Histórico ordenado sin duplicados | `market-chart-contract.test.ts`: orden ascendente, dedupe por `open_time` (gana la última), provisional separada. |
| C. Bloque anterior sin perder el rango | Navegador: 299 → 556 velas con `setVisibleLogicalRange` desplazado +2 velas en la prueba; diferencia de píxeles 1,6 %. |
| D. Cambio de símbolo/intervalo | Pruebas con promesas diferidas: la respuesta vieja (BTC 1h) llega después de la nueva (ETH 1h) y se descarta; `4h` anula la de `1h`. |
| E. Error, rate limit, sin cobertura | UI muestra `SERIES_UNAVAILABLE`, `RATE_BUDGET_EXHAUSTED` («no se reintenta en bucle») y «Sin cobertura» sin rellenar datos; HTTP 400 para `interval=1M`, 403 para origen ajeno. |
| F. Volumen con unidad | `base_volume + quote_volume · base MINA/BTC` en la ficha; `mark_klines` declara `available=false` con motivo. |
| G. Recuperar sesión sin nueva fixture | Pantalla inicial lista 4+ sesiones; seleccionar una carga el estado y dibuja el gráfico (`48 contexto · 3 cerradas · 0 solo-open`), con 0 `POST`. |
| H. Encuadre inicial correcto | Prueba: `fitContent` una sola vez con ancho real, diferido con ancho 0 (se aplica al recibir `ResizeObserver`), y nunca en updates ni al anteponer. |

**Triage `npm audit` (frontend).** 5 vulnerabilidades **high**, todas en la cadena de desarrollo `eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces` (ReDoS en herramientas de lint, no en el bundle servido). `npm audit --omit=dev` → **0**. La «corrección» que ofrece npm es un downgrade a `eslint-config-next@14.2.35` (`isSemVerMajor`), incompatible con Next 16: **no se aplica**; se documenta como residual.

**Límites y residuales.** Sin feed continuo: la última vela no se refresca sola y la vista no es LIVE. `1M` excluido (mes calendario). Los huecos del canónico se muestran como huecos (p. ej. 43 en MINAUSDT) y no se rellenan. Caché sin poda automática (retirada manual documentada). Sin indicadores ni objetivos. Sin inspección visual por modelo. 5 vulnerabilidades altas de dev sin abordar por decisión razonada. Suite frontend con un fallo intermitente preexistente en `backtest-guard-regressions` (barrier de concurrencia, 23 s) que pasa en aislamiento; no se tocó ese código.

**Siguiente (no ejecutado, requiere autorización separada).** Adaptar el feed existente a contrato vivo (websocket, reconexión, huecos, indicadores compartidos) y evaluar el preflight/almacenamiento de una ventana pública continua. No se autoriza ejecución ni capital.


## Gráfico Paper Lab interactivo con Lightweight Charts y contrato `paper-chart/v1` (2026-10-21, F-CHART-BINANCE-01)

Contrato versionado e interfaz de gráfico **sobre fixtures**. Base `ac716d35ac5844fa25bf79d6e8d7e1b497ab1858`. Sin Binance vivo, sin monitor ni adquisición, sin paper prospectivo, sin órdenes, pagos, optimización ni móvil. No se reabrió Backtest ni `control.guard`; no se tocaron reglas, umbrales, costes, funding ni la corrección económica de F-PAPER-03.

**Contrato.** `paper-chart/v1` en `frontend/src/lib/paper-chart-contract.ts`, documentado en `docs/PAPER_CHART_CONTRACT_V1.md`. Identidad `source="fixture"`, `venue=null`/`venue_status="UNKNOWN"`, `market_type="simulated_futures"`, símbolo, intervalo, `session_id` y `fixture_id`. Tiempos en ms Unix UTC con reloj de simulación explícito; la biblioteca recibe segundos mediante `floor(ms/1000)` y el ms exacto se conserva en el modelo, los IDs y el detalle. Velas cerradas vs. solo-open (`high/low/close/close_time_ms=null`, nunca ceros); el adaptador re-filtra por `clock_ms`, ordena y deduplica. `volume=null`/`UNKNOWN`, `indicators=[]`, objetivo `UNKNOWN`.

**Backend.** `session_to_public_dict` publica `event_id` estable `session_id:ev:<índice>:<kind>:<at_ms>`; los eventos de decisión (`protection`) usan tiempo de simulación (`signal_at_ms`) en todas sus ramas, no reloj de pared; la hora de pared queda en `evaluated_at_ms` y `updated_at_ms`. `PaperCandle.high/low/close/close_time_ms` son nullable y se añaden `available_at`/`received_at` opcionales. La economía no cambia.

**Frontend.** `Lightweight Charts 5.2.1` exacto (Apache-2.0, TradingView, aviso en `frontend/THIRD_PARTY_NOTICES.md` y `frontend/THIRD_PARTY_LICENSES/`; `fancy-canvas@2.1.0` MIT). Componente reutilizable `PaperChart.tsx` con import dinámico solo cliente, `autoSize`, limpieza de suscripciones/plugins/chart, actualización incremental y reinicio completo al cambiar de sesión. Marcadores de señal/entrada/salida, líneas informativas de entrada/stop/salida/pendiente, zoom/pan/ajuste y cursor fecha·precio. Entrada y stop salen de `position.entry_px`/`position.stop_px`; la salida solo con `exit_executed=true`; `open_at_end` no produce salida ni realizado. Se eliminó el `LiveChart` anterior. No se dibujan volumen, indicadores, objetivos ni niveles ausentes.

**Estados separados.**
- **Implementado:** contrato v1, adaptador, componente, integración en la pantalla, marcadores/líneas, estados FIXTURE/SIMULACIÓN, reloj, cobertura, ajuste y lectura de cursor; `event_id` y tiempos de simulación en el backend.
- **Probado:** backend focalizado 38/38; suite completa `python run_tests.py -q` 1290 OK (2 skipped); frontend `npm test` 484 passed + 1 skipped; `tsc --noEmit` 0; `eslint src` 0 errores y 5 warnings preexistentes. Pruebas nuevas: contrato (identidad, ms→s, sin futuros, solo-open, deduplicación, operación, `open_at_end`), wiring del componente con biblioteca mockeada y eventos públicos (`event_id`/tiempo de simulación).
- **Servido:** build `PPE-Io-M4ivYg3dvJRqwh`, PID 27612, `http://127.0.0.1:3020/paper-lab-live`, HTTP 200. Se reemplazó solo el listener anterior (31640) tras comprobar `runtime running=false/COMPLETED`, job `completado` y ausencia de trabajos activos. Logs fuera de `.next`.
- **Inspección visual:** DOM/geometría/HTTP y capturas locales; **no** hubo inspección por modelo de visión (proveedor sin autenticación), así que **no se declara PASS visual**. Capturas: `.playwright-mcp/paper-chart-{A-inicio,B-pendiente,C-fill,D-cierre-auto,E-open-at-end,F-recuperacion,G-cambio-sesion,H-zoom}.png`.

**Navegador de escritorio (1440×900, build final, controles reales).**

| Caso | Evidencia |
|---|---|
| A. Inicio sin futuros | Sesión `PL-BTCUSDT-LONG-1792631052590-413d566e`: 48 contexto, 0 cerradas, 0 solo-open; reloj 2026-09-08T21:59:59.999Z; ventana 10:00→21:45; sin entrada/stop/salida. |
| B. Señal pendiente | 2× `Paso a paso` → EN ESPERA; 1 cerrada + 1 solo-open; señal y “entrada pendiente (no ejecutada)”; sin fill ni stop efectivo. |
| C. Fill | `Entrar` → ABIERTA; entrada 78,537.18, stop 78,144.49; rev. 9; sin salida. |
| D. Cierre automático | Fixture stop: `PL-BTCUSDT-LONG-1792631699330-f0747528`; ABIERTA 101.00/95.95 → 1 paso → CERRADA rev. 11; salida stop 95.95 @1788929100000; bruto -50, fees 0.975, spread+slip 0.585, funding null, neto/realizado -51.560000000000116, `open_at_end=false`; sin salida 80. |
| E. Fin de datos abierto | Sesión A: 10 pasos más → CERRADA con 11 cerradas + 1 solo-open; `open_at_end`; sin marcador de salida; “No realizado”; `realized_net=null`. |
| F. Refresco/recuperación | Recarga real de la página y carga de la sesión C desde persistencia: ABIERTA, entrada 78,537.18, stop 78,144.49, sin salida. |
| G. Cambio de sesión | Carga de `PL-BTCUSDT-LONG-1792627398136-5241b33a` (cerrada): gráfico 101.00/95.95/salida 95.95; sin rastros de 78,537.18/78,144.49. |
| H. Zoom/pan/ajuste/cursor | Rueda: inicio 17:00→17:30; arrastre: 16:45→04:00; `Ajustar`: 16:00→04:45; cursor `2026-09-08T23:15:00Z · 100.00`; canvas 1188×340. |

**Límites y residuales.** Solo fixtures (sin venue Binance real); sin volumen, indicadores ni objetivo porque el backend no los produce; stops/objetivos arrastrables diferidos; el selector de persistencia solo se renderiza cuando ya hay una sesión, así que recuperar tras un refresco exige seleccionar una fixture primero y luego cargar la sesión guardada; tras pasos incrementales el ajuste inicial puede omitir la primera vela de contexto hasta pulsar `Ajustar`; `npm` reporta 5 vulnerabilidades altas (no abordadas en este bloque); el lockfile se parcheó preservando su formato, sin reescritura masiva. Sin móvil/Flutter.

**Siguiente (no ejecutado).** Reutilizar `paper-chart/v1` para búsqueda de contratos, histórico paginado y adaptación del feed existente; después, evaluación prospectiva versionada. No se autoriza ventana Binance ni ejecución.



Corrección económica cerrada en `src/microstructure_probe/paper_lab_engine.py` sobre la base `5572ee3` (commit inicial del bloque: `d48a224`). No se tocó `backtest_offline` (autoridad canónica), ni reglas de señal, umbrales, costes o funding. Sin Binance, monitor, paper prospectivo, órdenes, pagos, móvil ni Lightweight Charts.

**Defecto reproducido (LONG, 15m).** Fixture: V0 `t=0 O100 H102 L99 C101`; V1 `t=900000 O101 H103 L90 C102`; V2 `t=1800000 O80 H85 L75 C82`; `close_time = open + 899999`; notional 1000, referencia 100, stop config 95, `stop_distance_pct=5`, horizonte 3h, fee 5 bps, spread 1 bps, slippage 2 bps. En `d48a224` Paper Lab cerraba en el gap de V2 a 80 y publicaba stop 95; `run_backtest` cerraba en 95.95 a `1800000`. Causa: el bloque ad-hoc de gap/rango de `step_forward` preemptaba a la autoridad y trataba el OHLC de una vela como conocido en su `close_time_ms`, colapsando la revelación de open y cierre.

**Corrección.**
- Un paso revela el `open_time_ms` de la siguiente vela de operación; en ese instante se conoce el cierre de la anterior, pero no el OHLC de la revelada (se publica `null` hasta su cierre).
- Se elimina el bloque ad-hoc y `_finalize_stop_exit`; `_run_backtest_at_clock` (prefijo conocido, `known_close_cutoff=clock`) resuelve stop, gap, horizonte y fin de datos. El stop de la vela de entrada se resuelve antes que el gap posterior.
- `PaperPosition.stop_px` y el evento de entrada publican el stop efectivo `entry × (1 ∓ pct)`; el `stop_px` del config queda como referencia de señal/veto pre-trade.
- `open_at_end` usa la marca conocida por la autoridad; no inventa salida, comisión ni realized.
- `can_step` permite el paso final de fin de datos; el frontend muestra `position.stop_px`/`position.entry_px` y el gráfico ignora velas sin OHLC (evita la escala en 0).

**Paridad canónica vs Paper Lab (mismo cutoff).**

| Campo | `run_backtest` | Paper Lab |
|---|---|---|
| Entrada | 101.00 | 101.00 |
| Stop que gobierna | 95.95 | 95.95 |
| Salida | 95.95 @ 1800000 | 95.95 @ 1800000 |
| Motivo | stop | stop |
| Bruto | -50.00 | -50.00 |
| Fees | 0.975 | 0.975 |
| Spread+slip | 0.585 | 0.585 |
| Funding | UNKNOWN (`None`) | UNKNOWN (`None`) |
| Neto / realizado | -51.56 / -51.56 | -51.56 / -51.56 |

Además: SHORT entrada 99, stop 103.95, salida 103.95 @ 1800000, neto -51.64; gap legítimo (sin stop previo) salida al open 90; continuación sin stop termina en `open_at_end` con marca 105 y `realized_net=null`. Todos contrastados contra `run_backtest` con el mismo cutoff.

**Pruebas.** Motor 30/30 e integración A–E 5/5 (focalizadas); suite completa `python run_tests.py -q` 1290 OK (2 skipped), exit 0; frontend `npm test` 471 passed + 1 skipped, `tsc --noEmit` exit 0. Nuevas regresiones: LONG/SHORT con orden temporal, continuación/fin de datos y `live-chart` con vela solo-open.

**Navegador real (controles).** `http://127.0.0.1:3020/paper-lab-live`, build `MzvbhIwIOPI7PNIKJlAve`, PID 24060, servido tras comprobar `runtime running=false/COMPLETED`, `frontend/.backtest-runs/eval-census-v2-trio/job_state.json=completado` y ausencia de procesos Python activos (sin trabajos activos), reemplazando solo la instancia identificada. Sesión `PL-BTCUSDT-LONG-1792627398136-5241b33a`; fixture nueva `btc_long_stop_order`. Secuencia con clics reales: seleccionar → `Paso a paso` ×2 (`sin_iniciar`→`en_espera`, ENTRADA_SIMULADA) → `Entrar` (ABIERTA, entrada 101.00, stop 95.95, rev 9) → `Paso a paso` ×1 (CERRADA, rev 11, reloj 2026-09-09T04:45:00Z) sin pulsar `Cerrar posicion`. Resultado: salida stop 95.95 (no 80), bruto -50.00, costes +1.56, funding UNKNOWN, neto realizado -51.56; eventos Entrada @04:30 y Salida stop @95.95 (sin marca intermedia 80). Gráfico: `Entrada 101.00`, `Stop 95.95`, `Cierre 95.95`; eje 103.00/96.50/90.00.

**HTTP.** `GET /api/v1/paper-lab/sessions/PL-BTCUSDT-LONG-1792627398136-5241b33a` → 200; `status=cerrada`, `revision=11`, `stop_px=95.94999999999999`, `exit_px=95.94999999999999`, `exit_ms=1788929100000`, `exit_executed=true`, `fees=0.975`, `slip=0.585`, `funding=null`, `net=realized=-51.560000000000116`, `open_at_end=false`, `can_step=false`; `authoritative` del cierre también 95.95 @ 1788929100000.

**Inspección visual.** Capturas locales en `.playwright-mcp/paper-lab-stop-order-{pending,open,closed,closed-full,closed-chart}.png`. No hubo proveedor de visión disponible (OpenRouter sin autenticación; NVIDIA 401), así que **no se declara inspección visual por modelo**: se verificó DOM/geometría (1280×720, sin overflow horizontal, sin texto recortado, etiquetas de nivel con caja) y HTTP. Las capturas quedan para revisión humana.

**Anti Slop (estado separado, sin cambios).** Sigue instalado/registrado y con descubrimiento verificado; la ejecución end-to-end de `/antislop` continúa **PENDIENTE** y no se reintentó en este bloque. No se usó para esta corrección económica ni se declara validación funcional por estilo.

**Siguiente.** Contrato de datos/tiempos/IDs y Lightweight Charts según `docs/ACUERDOS_GRAFICO_BINANCE_V1.md` (no instalado). Sin reabrir móvil.

## Piloto Anti Slop en OpenCode (opcional) — 2026-10-21 (F-TOOL-ANTISLOP-01)

Integración local y opcional de Anti Slop (`miqdadbadjuber/anti-slop`, commit `439a2ef5b9dd0ebe74e8113ff43f5928d0fe2a6a`, versión `3.2.21`, licencia MIT) como revisión de **presentación y comentarios**. No es puerta funcional y no sustituye pruebas, causalidad, seguridad, economía ni rentabilidad.

- Instalado solo en este repositorio: `.opencode/skills/antislop/` (núcleo, `VERSION`, `LICENSE` y condiciones locales) y `.opencode/skills/antislop-code/`. No se instalaron `antislop-ui`, `antislop-copywriting`, `antislop-human` ni `antislop-layoutmobile`; no se ejecutó el instalador; no se tocó configuración global, proveedores, modelos ni permisos.
- Comando bajo demanda `/antislop <archivo o alcance>` en `.opencode/commands/antislop.md`: auditoría sin editar por defecto, `during` solo con instrucción explícita, máximo 5 hallazgos con ubicación/regla/motivo/propuesta, sin barrido del repositorio, sin fijar modelo y sin subagentes.
- Precedencia del proyecto: no elimina explicaciones de causalidad, concurrencia, seguridad, costes, funding, unidades o limitaciones; no acorta documentación técnica por longitud; no toca lógica, nombres, imports, umbrales, estrategias ni pruebas; no exige otro `DESIGN.md` ni prohíbe rejilla, colores direccionales o niveles del gráfico.
- Verificación real en OpenCode `v2.0.32`: tras escribir los archivos, la sesión activa recibió las skills `antislop` y `antislop-code` en su lista disponible **sin reiniciar**, y `/api/command` del proyecto devuelve `antislop` con su descripción. Descubrimiento y registro observados, no supuestos.
- Ejecuciones headless de prueba (`opencode run --standalone "/antislop <archivo>"`): en ambas el agente cargó el núcleo con la herramienta `skill` y **no editó ningún archivo**. La primera (`scripts/paper_lab_session.py`) no terminó en 300 s y derivó a buscar `settings.json`/`antislop.md`; se endureció el comando con precedencia explícita. La segunda (`docs/COMMANDS.md`) terminó en error de proveedor (`Endpoint is unavailable`, exit 1). La entrega final del comando queda **no verificada** y así se declara.
- Revisión piloto entregada en esta sesión sobre `src/microstructure_probe/dashboard.py` (archivo publicado y estable, sin editar): 2 hallazgos (banners decorativos y una etiqueta redundante) y 5 comentarios técnicos que deben conservarse. Detalle, hashes y retirada en `docs/ANTISLOP_PILOT.md`.
- Límites vigentes: sin CI, sin hooks, sin dependencia del runtime del bot, sin ahorro de tokens medido. Un PASS de Antislop no acredita causalidad, seguridad, economía ni rentabilidad.

## Estado vigente del objetivo gráfico — 2026-10-21 (F-CHART-BINANCE-01)

[Acuerdos de gráfico Binance V1](ACUERDOS_GRAFICO_BINANCE_V1.md) reúne búsqueda de contratos Binance Futures, histórico paginado, velas vivas, indicadores backend compartidos y eventos de operaciones. REQUISITOS ACORDADOS; implementación del gráfico Lightweight Charts y aceptación viva PENDIENTES. Abrir un símbolo no abre una operación ni arranca el monitor; servicio detenido implica histórico/estado desconectado.

Base revisada: `2a17088` (funcional `1892c23`). Hay Backtest/replay y un MVP Paper Lab sobre fixtures. El informe de cierre declara HTTP integrado y conflictos 409; la revisión de código conservó tres bloqueos: _run_backtest_on_prefix usa todas las velas; controles de vigilancia/reevaluación no conectados (canStep/onDecide); salida stop paralela sin política gap canónica.

**Actualización 2026-10-21 (posterior a este párrafo, que se conserva):** los tres bloqueos están corregidos en código y verificados con pruebas focalizadas; ver "Correcciones Paper Lab: fill causal, controles reales y stop compartido" más abajo. Sigue sin equivaler a rentabilidad ni a paper Binance vivo, y la pasada de navegador sobre los controles queda pendiente de ejecución declarada.

Este registro tiene precedencia para este objetivo sobre cierres históricos contradictorios; conserva su historia. Cambio exclusivamente documental: sin ejecución de tests/corridas, cambios de código, rebuild, servicios ni gates. Siguiente: corregir esos tres bloqueos y demostrar el flujo; luego contrato/gráfico compartido. Selector, riesgo/caja/funding recurrente y evaluación prospectiva conservan pendientes propios.

## Correcciones Paper Lab tras verificación real en navegador (2026-10-21, sobre `3acf511`)

La revisión en navegador real (Chromium vía Playwright, no solo HTTP) del recorrido de controles encontró defectos que las pruebas de API no cubrían. Están corregidos y re-verificados; no cambian reglas, costes, umbrales ni el motor económico.

- **Crash al seleccionar una fixture (React #310).** `PaperLabLive` tenía un `return` temprano cuando no había sesión y dos `useMemo` después: el número de hooks cambiaba al crear la sesión y la página caía ("This page couldn't load"). Los hooks se ejecutan ahora antes del `return` con referencias estables (`EMPTY_CANDLES`, `clockForView`). Era la causa de los dos errores `react-hooks` que se habían declarado preexistentes; `eslint src/components/paper-lab-live` queda con 0 errores.
- **Cierre prematuro de la sesión.** El gate de "evidencia insuficiente" de `evaluate_session` usaba el prefijo fusionado (contexto + operación) mientras la señal evalúa solo velas de operación: con 48 velas de contexto y cero de operación la sesión se cerraba en la primera evaluación (SIN_ENTRADA) y `can_step` quedaba en `false`, sin poder avanzar. El gate usa ahora el prefijo de operación y la sesión permanece `sin_iniciar` (avanzable) hasta que exista evidencia real.
- **Cursor contado sobre la serie fusionada.** Al pasar de entrada pendiente a abierta, `step_forward` calculaba el cursor con el índice de la serie fusionada con el contexto: con 48 velas de contexto daba `cursor=50` sobre 8 velas de operación y desactivaba `can_step` justo al abrir. El cursor indexa ahora velas de operación (`reveal_idx + 1`, monótono) y la UI muestra "Paso 2 de 2". Se centralizó la fusión en `_merge_candles`.
- **Controles redundantes y texto suelto.** `SessionControls` renderizaba el literal `&& (` y un botón primario siempre presente ("Finalizada"/"Avanzar paso") que duplicaba o contradecía a "Paso a paso". Ahora el botón primario es solo "Entrar" cuando hay entrada pendiente y el avance tiene un único control explícito.
- **Prueba obligatoria estabilizada.** La regresión de `T=899999` comparaba `at_ms`/`evaluated_at_ms` de reloj de pared y fallaba si dos evaluaciones caían en milisegundos distintos. Se congela `_now_ms` durante la prueba (`monkeypatch`) en lugar de relajar la comparación.

**Recorrido verificado (SOLUSDT LONG, build `cqYJQQU1Vh-vQGU-6bioV`, PID 23688, `http://127.0.0.1:3020/paper-lab-live`):** crear → SIN_ENTRADA sin evidencia (sesión `sin_iniciar`, avanzable) → paso 1: ENTRADA_SIMULADA **pendiente** (`decision_at=1788920099999`, `available_at=1788920100000`, sin `entry_fill_px/qty/cost`) → paso 2: entrada ejecutada @ `143.355` en `1788920100000`, `cursor=2`, `can_step=true` → paso 3: marca @ `145.08` → "Cerrar posicion": `Salida manual @ 145.08042078` en `1788921899999`, `exit_executed=true`, `gross=12.036`, `fees=1.006018`, `spread_slip=0.6036108`, `funding=null (UNKNOWN)`, `realized_net=10.4263712`, `rev=8`. GET del backend devuelve el mismo estado.

**Límites declarados de las fixtures (sin cambiarlas):** con la decisión causal en el primer cierre, la fixture BTC LONG termina en fin de datos con posición abierta (`open_at_end=true`, `realized_net=null`, caso D) porque ninguna vela se abre después del horizonte; la fixture ETH SHORT se abstiene en el primer cierre (close 3462.07 > entry 3450) y su salida por stop no es alcanzable desde la UI. Stop, gap y horizonte quedan verificados por pruebas (`test_stop_gap_*`, `test_step_forward_salida_horizonte`) y por la integración CLI A–E, no por el recorrido de navegador.

**Pruebas tras estas correcciones:** motor 27/27 (5 ejecuciones consecutivas sin fallo de la regresión), integración A–E 5/5, frontend Paper Lab 67/67 en 4 archivos, `tsc --noEmit` limpio, `eslint src/components/paper-lab-live` 0 errores (2 warnings preexistentes en `ExportPanel`).

## Correcciones Paper Lab: fill causal, controles reales y stop compartido (2026-10-21, sobre `2a17088`)

Los tres bloqueos revisados sobre `2a17088` quedan corregidos en el árbol de trabajo (rama `review/o1-funcional-v2-observacion`), con pruebas focalizadas en verde. Motor y mecánica económica **no cambian de reglas**; cambia qué información recibe la evaluación y qué se expone al cliente.

- **Fill sin información futura (defecto 1).** `_run_backtest_on_prefix` recibía todas las velas en lugar del `prefix` conocido en T, de modo que la decisión en T podía resolverse con la apertura de una vela futura. Ahora solo se pasa el prefijo causal. `evaluate_session` registra `decision_at_ms` y `available_at_ms`; si no hay precio ejecutable conocido, la señal queda `ENTRADA_SIMULADA` / `en_espera` con **entrada pendiente** (`entry_fill_px`/`entry_fill_ms`/`entry_qty`/`entry_cost` = `null`), no un resultado autoritativo. `step_forward` revela la siguiente vela con `open_time_ms > base_clock`, avanza `cursor`/`clock_ms` de forma monótona y solo entonces rellena. Nuevo `_run_backtest_at_clock(state, clock_ms)` re-ejecuta el motor canónico sobre el prefijo conocido para resolver `horizon` y stop de forma causal durante los pasos. El guard de `_apply_entry` ya no exige que el cursor apunte a la vela de fill (el fill viene de `run_backtest`, no de `candles[cursor]`).
- **Controles reales (defecto 2).** El backend publica `can_step` (estado `sin_iniciar`/`en_espera`/`abierta` y `cursor < len(candles)`) y el frontend lo prefiere, con derivación local solo como respaldo: se puede avanzar mientras se vigila o se espera entrada, no solo con posición abierta. `onDecide` está conectado a `evaluateSessionApi` con `request_id` nuevo y `state.revision` esperada; tras un `step` la reevaluación automática es explícita y solo para `sin_iniciar`/`en_espera`.
- **Stop compartido (defecto 3).** La salida por stop ya no es un camino económico paralelo: `_finalize_stop_exit` reutiliza `_finalize_exit`, el mismo mecanismo canónico que usan gap, `_finalize_exit_from_bt` y `manual_exit` (fees, funding y net). La detección primero comprueba hueco: LONG con apertura ≤ stop dinámico / SHORT con apertura ≥ stop dinámico cierran **a la apertura** con `open_time_ms`; si no hay hueco se usa el cruce dentro de rango con `close_time_ms`. Se distinguen instante observado, instante de evaluación y convención de fill OHLC; funding ausente sigue `UNKNOWN`, nunca cero inventado.
- **Regresión obligatoria:** en `T=899999`, dos escenarios con apertura futura distinta (`900000`: 110 vs 50) producen **estado público idéntico** hasta T (se comparan excluyendo `session_id`/`created`/`updated`/`revision`/`input_hash`) y solo después rellenan al precio revelado (110 vs 50, tolerancia numérica).
- **Pruebas ejecutadas (árbol actual, 2026-10-21):** `tests/test_paper_lab_engine.py` 26/26; `tests/test_paper_lab_integration.py` (A–E vía CLI real con almacenamiento temporal aislado) 5/5; `frontend/src/test/paper-lab-live-api.test.ts` 9/9; `npx tsc --noEmit` limpio (exit 0). `tests/test_backtest_offline.py` 16/16 en la sesión previa. No se re-ejecutó la suite completa: el cambio está acotado a Paper Lab y no altera `backtest_offline`.
- **Deuda declarada:** dos errores de lint `react-hooks` por `useMemo` condicional en `frontend/src/components/paper-lab-live/PaperLabLive.tsx` (~324/330) son **preexistentes** (confirmado con `git stash` sobre la base) y no se tocaron aquí. La pasada real de navegador sobre crear → evaluar → avanzar → reevaluar → entrada → gestión → cierre **no se ejecutó** en esta sesión: la verificación de controles es por pruebas de componente/API, no visual. *(Superado por la sección superior: la pasada se ejecutó y esos dos errores eran el crash de orden de hooks; corregidos.)*

## Cinco defectos de Backtest V2 corregidos (2026-10-20, base `37bde91`)

Estado factual: los cinco defectos probados están corregidos y verificados;
commit/push pendientes de esta sesión (SHA final en la entrega).

## Correccion acotada Paper Lab: camino real dashboard → BFF → Python (2026-10-21, sobre ec0416a)

Correccion de defectos en el recorrido real cliente/BFF/backend de Paper Lab:

- **Reloj causal:** `evaluate_session` rechaza si falta `at_ms` y `clock_ms`;
  nunca usa hora actual. `create_session` fija `clock_ms` al close_time de la
  ultima vela. Cliente envia `at_ms` en evaluacion.
- **Sin informacion futura:** `session_to_public_dict` filtra velas a solo
  las conocidas en T (open_time_ms <= T); velas abiertas solo muestran open,
  nunca high/low/close finales.
- **Revision e idempotencia al navegador:** request_id en cada accion;
  conflictos devuelven HTTP 409 (no 500).
- **Fin de datos != cierre ejecutado:** mark_px nunca sustituye precio de
  salida; realized_net null si open_at_end; se distingue sesion terminada de
  posicion cerrada.
- **Pruebas:** 44 Python OK (28 motor + 5 integracion A-E + 16 backtest-offline);
  9 frontend vitest OK; tsc --noEmit limpio.

SHA inicial: ec0416a. SHA final: b914f2d (commit en review/o1-funcional-v2-observacion).

## Correccion acotada Paper Lab: camino real dashboard → BFF → Python (2026-10-21, sobre ec0416a)

Correccion de defectos en el recorrido real cliente/BFF/backend de Paper Lab:

- **Reloj causal:** `create_session` fija `clock_ms` al close_time de la
  ultima vela de contexto (no al final de la fixture). `evaluate_session`
  rechaza si falta `at_ms` y `clock_ms`; nunca usa hora actual. Cliente envia
  `at_ms` en evaluacion.
- **Sin informacion futura:** `session_to_public_dict` filtra velas a solo
  las conocidas en T en TODAS las respuestas publicas (incluido GET).
- **Revision e idempotencia al navegador:** request_id en cada accion;
  conflictos devuelven HTTP 409; BFF interpreta respuesta del CLI incluso
  con salida != 0.
- **Fin de datos != cierre ejecutado:** mark_px nunca sustituye precio de
  salida; realized_net null si open_at_end; se distingue sesion terminada
  de posicion cerrada.
- **Pruebas:** 44 Python OK (28 motor + 5 integracion A-E + 16 backtest-offline);
  9 frontend vitest OK; tsc --noEmit limpio; build de produccion Next.js exitoso.
  Desplegado en http://127.0.0.1:3020 (PID 29944). /paper-lab-live y /paper-lab
  sirven HTTP 200.

SHA inicial: ec0416a. SHA final: b914f2d.

1. **Bloqueo = ciclo de vida de UNA corrida.** `control.guard` (mutex corto por
   experimento, `O_EXCL`, obsoleto a 30 s) serializa adquisición, liberación y
   retención. `run.lock` solo se libera cuando el ejecutor de ESA corrida está
   verificablemente ausente (`GONE`) o es ajeno (`PROCESS_NOT_OWNED` /
   `PID_INSTANCE_MISMATCH`); `TIMEOUT` no libera por sí solo. Estado terminal +
   presupuesto vencido no equivalen a "proceso terminado": la identidad dudosa
   conserva la exclusión y nunca se mata un proceso no propio.
2. **Identidad nunca se confía de lo almacenado.** Se verifica contra el SO
   (`Get-CimInstance Win32_Process` en Windows, `/proc` en Linux, `ps` como
   respaldo): PID vivo + hora de creación (`ToFileTimeUtc`, sin el desfase de
   +4 h) + línea de comandos con `--run-id`/`--executor-token`. Ajena,
   reciclada, contradictoria o incompleta → `UNKNOWN`
   (`PROCESS_IDENTITY_UNKNOWN`), con exclusión conservada. Sin caché de
   evidencia de PID (el reciclado podía devolver evidencia vieja).
3. **Hashes declarados completos y vigentes.** `summary.json`, `trades.json` y
   `reconciliation.json` deben declarar sha256 válidos, presentes, completos y
   concordantes; falta/parcial/inválido/discordante → resultados no
   disponibles con causa explícita. Los hashes NUNCA se recomputan como
   declarados. Se validan además schema e identidad de corrida/experimento; una
   reconciliación ilegible no es integral; la caché de replay queda vinculada a
   la corrida y a los resultados verificados. `reconcile` usa compare-and-set
   (antes un write obsoleto podía clobar el `completado` del ejecutor tras una
   consulta CIM lenta).
4. **Retención conservadora.** Solo elimina terminal + (`GONE` | `NOT_OWNED` |
   `INSTANCE_MISMATCH`) o activo + `GONE`; evalúa CADA candidato (no solo
   `current.json`); preserva `_legacy`, el puntero actual, la corrida
   referenciada por el lock y los directorios no reconocidos; el modo reporte
   solo lee (`would_remove`/`skipped`) y no modifica estados ni borra.
5. **Hipótesis y placebo separados.** La UI muestra ambos por separado y nunca
   los suma como beneficio de estrategia; cualquier suma se etiqueta «suma
   aritmética de ledgers (control)» y «NO es cartera ni beneficio de una
   estrategia». Las marcas de abiertas quedan aparte; los agregados conservan
   `UNKNOWN` en vez de cero; 1x/2x/3x siguen siendo escenarios de costes.

Artefactos: `run_id` + `experiment_id` en los tres JSON (sin identidad →
`RESULT_IDENTITY_MISSING`); el ejecutor declara `identity: "declared"`;
`build_paper_lab_replay.py --run-id` emite `provenance.backtest_run_id` +
`backtest_run_id` y hashea `backtest_trades`.

Evidencia: `docs/evidence/BACKTEST_V2_DEFECT_REGRESSIONS_FAIL_BEFORE.txt`
(base `37bde91`, 7 fallos) y `..._PASS_AFTER.txt` (7 pasan);
`docs/evidence/BACKTEST_V2_E2E_BROWSER_EVIDENCE.md` + capturas de escritorio
`BACKTEST_V2_FIX_DESKTOP_*.png` (alcance escritorio vigente,
`docs/DESKTOP_FIRST_SCOPE_20261020.md`). Verificado: frontend 452 passed / 1 skipped;
`tsc --noEmit` limpio; `eslint` 0 errores (3 warnings preexistentes);
`next build` OK (`BUILD_ID=7IfLc2UBHcbIAl2WG0t91`); `python run_tests.py -q`
1290 OK (2 skips); barrera `tests=1290 ok=True prohibited={} blocked=0 ro=1
file_writes=0 hashes_equal=True data_diff/logs_diff vacíos`.
E2E navegador (build servido en 3020): corrida 1
`bt-eval-census-v2-trio-20261020213213876-614cf8ad` → `COMPLETADO`;
segunda corrida `bt-eval-census-v2-trio-20261020213645692-d701b7ef` →
`COMPLETADO` con resultados servidos; replay enlazado al run 200 con
`backtest_run_id` correcto; `TARGET_NOT_IN_RUN` 422, `RESULT_NOT_READY` 409,
`EXPERIMENT_NOT_ALLOWED` 400. Restos preexistentes no tocados: corridas
anteriores en `frontend/.backtest-runs/` y `backtest-results/_legacy/` (sin
`run_id` → no disponibles con causa explícita; no se borran).

## Backtest offline funcional en V2 + enlace a Paper Lab (2026-10-20, sin push aun)
La ruta `/backtest` deja de ser reservada y ejecuta UNA evaluacion offline
versionada (`eval-census-v2-trio`) sobre el paquete publicado
`docs/evidence/eval-census-v2-package/` (EVAL-CENSUS-V2, 33 archivos, sha256
verificado antes de correr): BTC/ETH/SOL, 15m+1h, todas las familias+baseline,
dev/oos, escalas 1x/2x/3x como ESCENARIOS DE COSTE (no apalancamiento).
Ejecutor `scripts/run_dashboard_backtest.py` con lista permitida incrustada;
single-flight, estado persistido (`pendiente`/`ejecutando`/`completado`/
`fallido`), proceso huerfano reconciliado a `fallido`. Identidad/estado
SEPARADOS del monitor Binance. Resultados en `frontend/.backtest-runs/`
(ignorado, fuera de datos operacionales/DBs); `trades.json` +
`reconciliation.json` deterministas (15765 trades; Σ net_pnl==total_net 1e-9,
56 celdas); `summary.json` difiere solo en reloj. `Abrir replay` carga ESA
operacion (event_id/group/segment/scale) via `build_paper_lab_replay.py
--trades-json`, conservando causalidad/costes/realizado-abierto; operacion no
soportada -> 422 con motivo, sin sustituir por un replay. Artefacto fijo
superseded: sha256 `72af8007...f172` (replay_id gana group+scale). No evalua
la estrategia completa de extremos (sin universo/liquidez/ranking causal);
matriz en `docs/EXTREMES_EVALUABILITY_MATRIX.md` (preparatoria, no la declara
hecha). Contrato `BACKTEST_READ_CONTRACT_V1.md` pasa de UNWIRED a WIRED;
`PAPER_LAB_PLAN_ETAPA5.md` documenta el enlace. Verificado: backend 1291 OK +
frontend 400/400 + `tsc --noEmit` limpio + `eslint` 0 errores (3 warnings
ajenos) + `next build` OK (`BUILD_ID=eBIlrCEoIFTWay0VAx6VA`); desde checkout
limpio el paquete publicado basta (trades=15765, reconciliacion=True).
Estado: los cinco correctivos y la corrección final de `control.guard` están commiteados+publiados en `3b6340d..<sha-final>`; dashboard re-servido en `http://127.0.0.1:3020` (PID 13868, `BUILD_ID=w1DMYZv7af8n2jO6vXlyp`, `next build` + `tsc --noEmit` + `eslint` OK, HTTP 200 en `/api/v1/runtime`, `/backtest` y `/paper-lab` renderizados en escritorio). Sin monitor ni backtest activo.

## MVP Paper Lab en caliente — ingeniería, reconducido (2026-10-20, commit 1f79d71)

Se recondujo el MVP del Paper Lab en caliente: el backend Python es ahora la
fuente de verdad y el frontend es un cliente de API delgado. Exclusivamente
para escritorio, sobre fixtures (sin Binance en vivo, sin órdenes reales,
sin capital real).

Artefactos nuevos:
- `src/microstructure_probe/paper_lab_engine.py` — motor de sesiones de
  ingeniería con orquestación incremental. La mecánica económica (entradas,
  salidas, costes, funding, stops, horizonte) se delega a
  `backtest_offline.run_backtest` (no segundo motor económico).
  Incluye: reloj de sesión, configuración versionada (config_hash),
  decisiones (VIGILANDO/SIN_ENTRADA/DESCARTADO/ENTRADA_SIMULADA),
  posiciones, fills, costes ejecutados vs estimados, eventos y resultados.
- `scripts/paper_lab_session.py` — CLI para operaciones de sesión
  (list/create/evaluate/get/step/exit/restart/stop) con validación de
  session_id contra traversal, escritura atómica y control de revisión
  (optimistic locking).
- `frontend/src/app/api/v1/paper-lab/sessions/route.ts` — GET listado +
  POST creación. `sessions/[session_id]/route.ts` — GET recuperación completa.
  `sessions/[session_id]/evaluate/route.ts` — POST evaluación de evidencia en T.
  `sessions/[session_id]/step|exit|restart|stop/route.ts` — POST acciones.
  Protección de origen (127.0.0.1:3020), confinamiento de directorio aislado.
- `frontend/src/lib/paper-lab-live.ts` — tipos compartidos y cliente de API
  (sin "use client", sin lógica de simulación).
- `frontend/src/components/paper-lab-live/` — componentes UI desktop-first:
  selector de fixtures, gráfico de velas con niveles, paneles de posición/P&L,
  registro de eventos, controles de sesión (con botones de decisión),
  persistencia, exportación JSON/CSV.
- `frontend/src/app/paper-lab-live/page.tsx` — página `/paper-lab-live`.
- `frontend/src/test/paper-lab-live-api.test.ts` — 9 pruebas de sessionView/
  format helpers.
- `tests/test_paper_lab_engine.py` — 23 pruebas del motor Python (entrada,
  stop con vela actual, horizonte, manual, open_at_end, reinicio, detención,
  persistencia, validación de identificadores, serialización roundtrip,
  idempotencia, conflicto de revisión, archivo ilegible, frescura stale/
  disconnect/end_of_data, invariancia causal).
- `tests/test_paper_lab_integration.py` — 5 pruebas de integración A–E vía CLI
  con almacenamiento temporal real: flujo completo (A), SIN_ENTRADA (B),
  datos obsoletos (C), fin de datos con posición abierta (D), acción duplicada
  sin duplicar operación (E).

Flujos verificados (motor Python CLI + HTTP real vs BFF):
- Entrada automática tras decisión ENTRADA_SIMULADA (backend evalúa evidencia
  en T mediante run_backtest). Demostrado vía HTTP: crear → evaluar sin señal
  (SIN_ENTRADA) → avanzar (revelar vela) → evaluar con señal
  (ENTRADA_SIMULADA) → step ejecuta entrada → step gestiona → step cierra por
  stop → GET recupera estado idéntico. Tiempos: decision_at=899999, entry_ms=900000
  (>= decision_at), exit_px=95.95, exit_reason=stop, exit_executed=true,
  realized_net=-51.56, total ~952ms.
- Salida por stop (precio distinto de la marca), por horizonte, manual.
- open_at_end: datos agotados con posición abierta → permanece no realizada,
  sin cierre inventado ni comisión de salida. Demostrado vía HTTP:
  exit_executed=false, realized_net=null, open_at_end=true,
  exit_fees_executed=0, posición sigue abierta, GET idéntico.
- Reinicio, detención, persistencia y recarga tras refresco.
- Identificadores con traversal rechazados.
- Control de revisión: acción duplicada con revisión obsoleta detectada.
- Conflictos HTTP reales: dos steps concurrentes misma revisión → uno 200,
  otro 409 REVISION_CONFLICT; sin entrada duplicada. Misma request_id con
  contenido distinto → 409 REQUEST_CONTENT_CONFLICT. Revisión obsoleta → 409.
  Sesión inexistente → 404 SESSION_NOT_FOUND.

Verificado: tsc --noEmit limpio, eslint 0 errores (warnings preexistentes),
next build OK (BUILD_ID=jhFu3mEN9yZAntBo_sWsC, servidor PID 31072 en
http://127.0.0.1:3020), 470 pruebas vitest pass (1 skip), 23 pruebas Python
del motor pass, suite completa python run_tests.py -q: 1290 OK / 2 skip /
exit 0. Rutas /api/v1/paper-lab/sessions* y /paper-lab-live sirven HTTP 200.

Estado: motor paper completo (Etapa 5) AÚN NO implementado. Este MVP es
pantalla de ingeniería sobre fixtures; la primera ventana con datos Binance
en caliente requiere autorización explícita y no se inicia aquí.

Cambio known_close_cutoff: `run_backtest` acepta `known_close_cutoff` opcional
(default `horizon_end`, compatible hacia atrás); solo velas con
close_time_ms <= cutoff se consideran OHLC conocido. Usado por la evaluación
causal del Paper Lab (se pasa `known_close_cutoff=at_ms`). Sin regresiones en
la suite.

Corrección contrato CLI/BFF (este bloque): las 5 routes del BFF
(evaluate, step, exit, restart, stop) + helper runPython parsean stdout Y
stderr del CLI Python, de modo que REVISION_CONFLICT / REQUEST_CONTENT_CONFLICT
se mapean a HTTP 409 incluso cuando el CLI sale con código ≠ 0. Verificado con
procesos reales concurrentes.

Se reprodujo y se resolvió en `frontend/src/lib/backtest-control.ts`:
- Identidad única por adquisición: `Guard` incluye `token` aleatorio (`randomBytes`) generado al adquirir, escrito en el guard y devuelto en el handle. Dos adquisiciones del mismo PID tienen tokens distintos.
- `inspectPidLiveness`: solo `ESRCH` acredita ausencia (`gone`). `EPERM` conserva exclusión (proceso existe, sin permisos). Otros errores devuelven `error` y conservan exclusión. PID inválido devuelve `error` y no autoriza retirada.
- `acquireGuard` retorna `AcquireResult` discriminado:
  - `{kind: "acquired", guard}` si se creó el guard (no existía previo).
  - `{kind: "rejected", reason: "OWNER_ALIVE"}` si el propietario vive (antigüedad no es muerte) (A).
  - `{kind: "rejected", reason: "GUARD_ORPHANED"}` si el propietario murió (ESRCH): se CONSERVA el guard huérfano, no se borra automáticamente (C).
  - `{kind: "rejected", reason: "IDENTITY_UNCERTAIN"}` si el guard es ilegible, falta token/PID, EPERM u otro error de inspección: se conserva la exclusión (D1-D5).
  - La identidad completa (pid + token) se verifica ANTES de consultar liveness: sin token es evidencia insuficiente (D2).
- `releaseGuard(Guard)` libera condicionada por identidad COMPLETA (mismo `pid`, mismo `token` y mismo `acquired_at_ms`). Una liberación antigua nunca borra el guard de una adquisición posterior (B).
- La carrera lectura→borrado del punto 1 se elimina: no hay `rmSync` automático en `acquireGuard`, por lo que A y B no pueden leer el mismo guard huérfano y borrarse mutuamente. La recuperación solo puede hacerse por mantenimiento con todos los participantes detenidos.

Pruebas dirigidas: `frontend/src/test/backtest-guard-regressions.test.ts` (A, B, C1, C2, D1-D5).
- Fail-before (código previo `3b6340d`): A (propietario vivo >30s perdía el guard), C (carrera lectura→borrado al recuperar), D (EPERM/error tratado como muerte) reproducían el defecto.
- Pass-after (con corrección): las 9 pasan:
  - A: propietario activo >30s → OWNER_ALIVE, no adquiere, conserva.
  - B: liberación tardía con token distinto → conserva guard de B (mismo PID).
  - C1: 6 procesos concurrentes sobre guard huérfano → todos GUARD_ORPHANED, 0 adquirieron, guard se conserva (barrera de inicio, no hay borrado automático).
  - C2: guard válido vivo (sección crítica del padre) + 6 procesos concurrentes → todos OWNER_ALIVE, exclusión durante toda la sección crítica, padre mantiene el guard vivo hasta completar la comprobación.
  - D1: guard ilegible → IDENTITY_UNCERTAIN, conserva. D2: sin token → IDENTITY_UNCERTAIN, conserva. D3: EPERM → IDENTITY_UNCERTAIN, conserva. D4: PID gone (ESRCH) → GUARD_ORPHANED, conserva (no borra). D5: error desconocido (EACCES) → IDENTITY_UNCERTAIN, conserva.
- No-regresión: `backtest-defect-regressions.test.ts` 7/7 + `backtest-control.test.ts` 41/41 + `backtest-guard-regressions.test.ts` 9/9 = 57 pruebas vitest, 0 fallos. `tsc --noEmit` limpio; `eslint` 0 errores (3 warnings preexistentes); `next build` OK (`BUILD_ID=w1DMYZv7af8n2jO6vXlyp`); dashboard servido en `http://127.0.0.1:3020` (PID 13868), HTTP 200 en `/api/v1/runtime`, `/backtest`, `/paper-lab`.
- No se introdujo otro gestor de tareas; no hay cambios en DBs, backups ni secretos. La inspección visual se limita a DOM/texto (no se declaró captura de PNG inexistente).


Cierre de la fase de evaluacion offline sobre censo same-grid. Evidencia:
docs/OFFLINE_EVAL_CENSUS_V2.md + artefacto publicado
frontend/src/data/census-eval-v2.json (sha256 2b74a841...d37060, 73051 B,
force-added a Git; limpio verifica artefacto/UI/build, no regenera desde
cero). Censo CENSUS-V1: 9320 detecciones, 9320 admitidas, 0 descartadas;
entry>=available 9314/9314 (6 tail-edge sin entry, honesto); 594 grupos
duplicados (+616 filas) contados, nunca tratados como independientes; 2831/2831
originales reproducidos; 6489 censo-unicos (2.3% del censo 15m estaba en piloto).
EVAL-CENSUS-V2: 5255 trades @1x (4055 15m + 1200 1h); 0 celdas elegibles
(ninguna supera al placebo Y sobrevive 2x). H1/H3 RECHAZADAS (18/18 15m +
6/6 1h negativas @1x). H2 fade RECHAZADO como metodologia (mejor s*<2 o n
insuficiente; anecdotas n=1 cercadas). H2 fade queda como HIPTESIS NUEVA,
no estrategia aprobada. Funding: 741 liquidaciones aplicadas en ventana (0
UNKNOWN-excluded en 60 celdas); 24/60 celdas con holdings de cola fuera de
calendario = uncovered/UNKNOWN (nunca cero). Placebo TIME-PLACEBO-v1 seed 42,
misma cobertura/costes; no presentado como distribucion (una realizacion).
HORIZON-GRID4-V1: degeneracion 1h/1h demostrada (entry==exit, bruto 0 por
construccion); separacion explicita experimento original (OFFLINE-EVAL-V1,
horizonte 1h por defecto) vs nuevo horizonte (4h/1h). No es optimizacion
validada: el flag --horizon-ms es aditivo, default preservado 1h.
Selector SELECTOR-EXTREME-V1: mecanismo probado con fixtures (tests
test_extreme_selector.py); cobertura de universe/liquidez UNKNOWN (sin
historico); ranking != entry; NO aprobado como senal.
QA visual 3020: historical-research con 2 bloques (OfflineEvalSection +
CensusEvalSection), 0 errores consola, captura
docs/evidence/VISUAL_QA_CENSUS_EVAL_V2.png. Defecto corregido: texto "0 cells
eligible for operation" duplicado en parrafo del censo (label del artefacto
+ componente). Verificado: backend 1202 OK (2 skips) + frontend 314/314 +
typecheck 0 + build OK + census-eval tests 4/4. V2 sirviendo 3020 PID 15480
(http://127.0.0.1:3020). Monitor detenido, watchers detenidos, sin corridas.
Resta: commit selectivo, push, entrega con SHA. Matriz A/B/C en
docs/OFFLINE_EVAL_CENSUS_V2.md seccion 7.

## Integracion objetivo movers extremos (2026-10-17, solo documental)
Integrada review/extreme-movers-objective-20261016 hasta 7a4e872 por
contenido sobre 004b300e: EXTREME_MOVERS_OBJECTIVE.md +
HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md restaurados verbatim; suplementos
portados a PRODUCT_GOAL/MASTER_PLAN/MARKET_DATA/POSITION_MANAGEMENT/
TASK_QUEUE/CURRENT_STATE/DECISIONS/FEATURE_BACKLOG (F-EXTREME-OBJECTIVE-01,
F-STRUCTURE-EXIT-01). Sin snapshots completos ni sobrescrituras; fase
activa, codigo, corridas, servicios y gates intactos. Planes sin parametros
aprobados; soportes/stops/Paper Lab conservan secuencia.

## Objetivo movers extremos preservado — suplemento documental 2026-10-16
Base revisada b748d22; no se infiere el estado de cambios locales concurrentes.
PRODUCT_GOAL ya contenia el objetivo bilateral. EXTREME_MOVERS_OBJECTIVE.md
lo conecta con selector causal, cobertura mas alla de BTC/ETH/SOL y
Backtest/Paper Lab. Solo documentacion; sin cambio de fase, codigo, corridas,
servicios ni gates. F-EXTREME-OBJECTIVE-01: objetivo reafirmado, implementacion
por verificar; la auditoria offline actual sigue su alcance autorizado.

## Paquete reproducible + causalidad + costes + protocolo (2026-10-17, sin corridas, sin push aun)
Paquete OFFLINE-EVAL-PACKAGE-V1 (manifiesto en
docs/evidence/OFFLINE_EVAL_PACKAGE_V1.md): replay completo en temp
reproduce input_hash y artefacto byte-identico (c051e888…287b3a);
IDs originales 1:1 (event_ids.json, 0 faltantes); zip fuera de Git
+ `scripts/reproduce_offline_eval.py`; limpio verifica
artefacto/agregacion sin canonico; reproduccion externa PENDIENTE.
Causalidad (OFFLINE_EVAL_CAUSAL_AUDIT_V2): formacion
prefijo-causal + invariancia 18/18; seleccion retrospectiva;
H1/H3/H2-legs no utilizables como senal, rebote UNKNOWN.
Costes (OFFLINE_EVAL_COST_BREAKEVEN_V1): s* 1.18–1.94,
12/12 negativas a 2x; comisiones por escenarios oficiales;
spread/slip UNKNOWN; pooled no cartera + baseline
TIME-PLACEBO-v1 propuesto. Protocolo prospectivo V1 solo
preparado (ninguna hipotesis elegible hoy; 4 pasos siguientes).
V2 historical-research con bloques reproducibilidad/causalidad/
breakeven (solo lectura). Tests nuevos: breakeven 7 + causalidad
3 (sinteticos) + agregacion 6/6 + frontend offline-eval 6/6 +
typecheck. Verificado: backend 1183 OK (2 skips preexistentes
symlink) + frontend 310/310 (52 files) + build OK (BUILD_ID
JbysVWGpy6brxyWqTf9FQ) + V2 3020 PID 25708
(127.0.0.1, `/overview` + `/historical-research` +
`/api/v1/offline-eval` + `/api/v1/runtime` 200, 0 errores
consola, 3 bloques nuevos visibles + captura
docs/evidence/VISUAL_QA_OFFLINE_EVAL_V2.png). DBs intactos
(mtimes 15/10). Resta: commit, push, entrega. V2 abierto 3020,
monitor detenido.

## Fix artefacto offline-eval publicado (2026-10-16, sin corridas, sin push aun)
Defecto: `@/data/offline-eval-v1.json` ignorado y ausente en GitHub (404
en limpio). Correccion: artefacto por force-add (114195 B, sha c051e888…
verificado byte-identico por `scripts/aggregate_offline_eval.py` desde los
replays en temp) + test agregador 6/6 + hashes funding reconciliados a
provenance + limitacion dataset declarada (historico canonico no
publicado; limpio verifica artefacto/UI/build, no regenera desde cero).
Resta: checkout limpio, commit, push, entrega. V2 abierto 3020, monitor
detenido.

## Offline entry/exit closeout V1 (2026-10-16, sin ventana forward, sin simulacion prospectiva, sin push aun)
Re-ejecucion offline en temp (export 476/498/584, seleccion
224+252/0, 256+241/1, 297+287/0, input_hash identicos al artefacto;
replays BTC 452 + ETH 457 + SOL 503 = 1412). Causalidad por operacion:
1412/1412 entry>=available, 0 violaciones, gap 1ms (tripletas en
docs/evidence/OFFLINE_EVAL_AUDIT_V1.json). Flujo 1558 fuente - 1 purga
(ETH H1 1790007300000) = 1557 admitidas - 145 solapes = 1412
(1410R + 2 marcas). Funding: 1 sostenida (+0.0894) + 1403 cubiertas quietas
+ 8 UNKNOWN (1404/1412 completas); "4 ventanas" anulado. Exposicion
intra-celda; pooled = suma aritmetica, no cartera. Unidades USDT/1000 USD:
bruta +1.88...+3.11/op, friccion ~1.60/op (comisiones ~1.00 + spread/slip
asumido ~0.60); costes supuestos. 12/12 celdas negativas a 2x.
Verificado: backend 1168/1168 + barrera exit 0 (0/0/0, 1 RO, hashes
iguales) + frontend 310/310 + typecheck + QA visual 3020 (overview +
historical-research con seccion, 0 errores). Servido 3020: PID 26976
(`next start -p 3020`), BUILD_ID 8ys8al-xhDgAYQyg8bz-T, runtime exact-uuid
con snapshot 4c76d94c…1303f9, /overview + /api/v1/offline-eval 200;
build incluye seccion offline-eval previa a la nota de alcance (sin
redeploy en este cierre). Resta: commit, push, entrega. V2
abierto 3020, monitor detenido.

## R3 vivo PASS brief 120s (2026-10-16, autorizada 1x, sin push aun)
probe-20261016T034423Z (UUID 4c76d94c…1303f9): 120s solicitados,
cierre natural COMPLETED duration-reached exit 0, contador
congelado 133s, PIDs muertos, supervisor/sentinel STOPPED sin
abortos, 0 python, sin journals. Capturador 5/5 (3 RUNNING +
2 post-cierre) con outcome terminal-captured y veredicto R3
PASS (exact-uuid + snapshot coincidente + current + detections
atribuidas; 0 eventos iniciales validos, 18/3 desde +60s).
Filas UUID 4/6/39/9 con deltas netos por retencion (flow_10s
4117->3636); tamanos invariantes; sin recovery. Evidencia JSON
+ resumen + 2 capturas V2. Resta: commit, push, entrega. V2
abierto 3020, monitor detenido.

## V2 08364ba publicado en 3020 (2026-10-16, deploy sin corridas)
Arbol 08364ba compilado (`npm run build` OK) y sirviendo en
http://127.0.0.1:3020 (PID 2868, BUILD_ID
v4Od5kTGmfyFhyzE-twPO; instancia anterior 23588 detenida, resto
de procesos intactos). Sin corrida activa (COMPLETED
probe-20261016T005550Z, proceso gone, 0 python, monitor
detenido). `/api/v1/runtime` incluye siempre
feed_attribution_method/feed_snapshot_run_id/
feed_snapshot_timestamp (en vivo: exact-uuid con UUID
4303b1c5…c62da86 en registro y snapshot, STALE por reloj,
valores de la evidencia sin forzar); `/overview` y `/system`
200, `/api/v1/detections` 10/2 con mismo run+UUID. Puerto 3020
y restricciones de origen intactas. R3 vivo NO cerrado: sigue
pendiente de captura en futura corrida autorizada.

## Atribucion exacta R3 (2026-10-16, sobre a2aebc5, sin push aun)
BFF expone method exact-uuid/temporal/none + snapshot_run_id +
timestamp (salud/umbrales/Start-Stop intactos); capturador solo
PASS con RUNNING verificado + UUID registro=snapshot + method
exact-uuid + current + detections atribuido. Temporal
HEALTHY/current sin UUID -> UNKNOWN; incompatible -> nunca
PASS. Suites locales: frontend 304/304, capturador 19/19,
export 6/6; sin Binance. Resta: commit, push, entrega. V2
abierto 3020, monitor detenido, sin corridas.

## Captura R3 v2 + causalidad de velas (2026-10-16, sobre 69d55ba, sin push aun)
R3 separado de adquisicion (exit 0 != PASS; HEALTHY/current
insuficientes): UUID tardio aprende/fija, ausencias registradas,
detections verificado antes de atribuir, identidades fijadas +
veredicto en informe; 6 tests R3 nuevos. Export con close_time/
as_of explicito (cadena 0 violaciones en trio 15m) + regresion
causal intra-vela + runner preserva tiempos (hash intacto).
Mapping PROPOSED + solo-mecanica intactos; sin P&L ni repeticion
del prep. Resta: suites, barrera, commit, push, entrega. V2
abierto 3020, monitor detenido, sin corridas.

## R3 capture + offline entry/exit prep (2026-10-16, push 69d55ba)
Reconciliado: matriz 10 PASS + 1 UNKNOWN (el "9 PASS" era error de
conteo) + UNKNOWN-vs-STALE por capas (controlador vs BFF).
Herramienta `scripts/capture_run_window.py` (solo GET runtime/
detections, learn-and-pin, +30/60/90 + terminal acotado, salida
protegida) + 10 tests locales verdes; comando listo para la
proxima ventana autorizada. Inventario `docs/ENGINE_ENTRY_EVAL_INVENTORY.md`: motor
v4.2 + runner reutilizados sin cambios; adaptador
`export_engine_inputs.py` (PROPOSED-P1-11C-map-v1 no aprobado);
prep mecanico en temp: 1558 eventos, hash 1358c7f05ee8474b, 692
trades @1x, economia RETENIDA (sin lectura). Faltan: mapping
aprobado, calendario funding realizado, costes medidos, purga.
Resta: suites, barrera, commit, push, entrega. V2 abierto 3020,
monitor detenido, sin nuevas corridas.

## Piloto brief probe-20261016T005550Z COMPLETADO (2026-10-16, autorizada 1x120s, push 48445f2)
UUID 4303b1c565354609a2d690141c62da86 auto-enlazado al registro;
120s solicitados, probe 122.377s, registro 131s congelado,
COMPLETED duration-reached code 0, PIDs muertos, leases STOPPED.
89360 msgs, 0 rechazos/reconnects/parse, 11/11 streams, reloj 1/1,
lags p50 ~171-175ms, dispatch sub-ms, research 54/0/0 STOPPED.
10 funding (BTC/ETH LOW, 2 episodios v1) + log con UUID unico.
Tablas: 54 filas UUID = research.writes (telemetry 4 con cap
1000); flow_10s neto -98 con 39 UUID (retencion concurrente).
V2 3020: barra + panel 10/2 con enlace exacto; feed mid-run en
vivo no capturado (R3 UNKNOWN, residual). Seguridad 0/0/0.
Resta: matriz en evidencia, commit, push, entrega. V2 abierto,
monitor detenido.

## V2 operativo en 3020 (2026-10-16, sobre d126141, sin corridas)
Unico dashboard principal http://127.0.0.1:3020 (PID 23588,
BUILD_ID u0ziTGs3Q12uEMZapEWf7 del arbol d126141): detenidas la
3020 obsoleta (sin /detections ni probe_run_id) y la 8093 propia;
requestAllowed intacto (solo 3020, sin CORS nuevos). Auth en vivo:
403 sin headers/evil, 400 con confirm erroneo previo a spawn;
mocks 59/59. Visual 3020: barra global + episodios 98/4 parcial
(tail-truncated, UNKNOWN) vs 245/13 reconstruccion completa del
fixture (no equivalentes). Registro COMPLETED/gone, 0 python.
Resta: commit selectivo, push, entrega. Monitor detenido.

## Trazabilidad stem<->UUID + episodios v1 (2026-10-16, push d126141)
link_probe_run_id fenced + probe_run_id en status + lector V2 con
enlace exacto y rechazo de incompatible; agrupacion v1
(bruto/episodio/update/nuevo) + BFF /detections + panel System
(eventos/episodios/UNKNOWN/research); regresion 245 retenidos -> 13
agrupados por regla (fixture completo; el lector BFF en vivo sobre
cola acotada muestra 98/4 parcial con limitacion
evidence-tail-truncated + enlace UNKNOWN por historico sin link).
Sin corridas, estrategias, umbrales,
calibracion, Start/Stop nuevos ni segundo gestor. Correccion
documental: episodios agrupados (no independencia), microprobe sin
byte-identidad (tamano estable + contenido modificado, sin hashes).
Verificado: backend 1139 + frontend 300/300 + barrera 0/0/1RO +
visual; commit d126141 + push. V2 en 3020, monitor detenido.

## Corrida autorizada observation-10m 600s COMPLETADA (2026-10-15, push 10cad5c + informe 67472e0)
probe-20261015T230630Z (UUID 893f24029cba4cff96eaba7c0af094d0,
verificado exacto por addendum):
600s solicitados, runtimeSeconds 602.615, 468162 msgs, 0.00%
rechazos, 0 reconnects, lags sanos (book p50 ~180ms), dispatch p50
~0.001-0.006ms, reloj -190ms/337ms, seguridad 0/0/0. Watchers 22+22
sin abortos, cierre natural duration-reached 23:16:41Z, PIDs muertos,
COMPLETED congelado 610s, sin journal, DBs 0B (246 writes a
historical.db research con UUID del run; delta por tabla UNKNOWN).
Funding 245 eventos = 13 episodios (artefacto, umbrales intactos).
Barra fiel en inicio/mitad/final. Evidencia informe + JSON +
addendum + capturas. Resta: commit selectivo, push, entrega.
V2 abierto, monitor detenido.

## Correccion atribucion del feed (2026-10-16, push 8c73de2)
Sin gracia pre-start (snapshot anterior a started_at nunca current);
run_id exacto priorizado en codigo (espacios distintos, rige temporal
conservadora + cruce runtime_seconds); regresion 20s A/B; UNKNOWN sin
certeza; previous-run distinguido de feed activo. Start/Stop,
umbrales e identidad intactos. V2 abierto, monitor detenido.

## Endurecimiento identidad UNKNOWN + feed estricto (2026-10-16, push 3f2fcea)
UNKNOWN = UNVERIFIED (nunca NOT-LIVE); owned/gone/replaced
distinguidos; solo terminal explicito cierra; verificacion expira a
30s sin lectura fresca. Feed HEALTHY solo con evidencia suficiente y
atribuible al run (si no, UNKNOWN o corrida anterior); gate 0.05 vs
display 0.5 reconciliados sin tocar umbrales; missing/silent/parse
revisados. Tests frontend 286/286 + feed 15 + propiedad intacta;
backend propiedad 67 verdes. V2 abierto, monitor detenido.

## Visibilidad global de corridas V2 (2026-10-16, push 3544ad6)
Barra global en todas las pantallas (estado, origen, run_id, inicio,
duracion prevista y restante vivo; feed/supervisor/sentinel por
separado con frescura; en terminal motivo, hora de cierre y duracion
congelada; registrado vs verificado). Stop con confirmacion para
cualquier corrida verificada del proyecto (dashboard/agent/direct),
backend verifica identidad/propiedad sin ampliar permisos. Tests:
backend 10 + frontend 266 verdes; fixtures y procesos aislados, cero
corridas Binance. Reconciliacion: 123.957s vs 133s sin contradiccion,
9 funding artefacto sin valor de senal, aborto previo con retraso
observado pero origen no aislado (correccion). Contratos y docs
actualizados. V2 abierto, monitor detenido (COMPLETED, PIDs muertos).

## Piloto brief COMPLETADO 20261015T102519Z (2026-10-15, autorizado, sin push aun)
Arranque V2 confirmado (492/12980/20736); 123.96s, 82161 msgs,
0 rechazos, lags sanos, dispatch p50 ~0.001ms (primera medicion),
yield combinado p50 ~0.6s; watchers 6+6 sin abortos; cierre natural
code 0, PIDs muertos, COMPLETED congelado 133s; sin hot journal;
V2 lee todo (price 12->51). Evidencia PILOT_BRIEF_20261015_COMPLETED
+ copia RECOVERY_CANONICAL aplicada. Dashboard abierto.

## Mantenimiento recovery APLICADO (2026-10-15, autorizado, sin push aun)
Pre verificado (SHA e773e51, cero escritores, V2 propio detenido por
identidad, registry ABORTED, hashes sin deriva, destino fuera del
repo). Apply PASS: backup real + restore + integrity ok + schema 10 +
conteos iguales + journal consumido. Hash resultante byte-identico
(rollback limpio). V2 reiniciado (PID 25684): readiness 6/6,
5 rutas 200. Monitor NO arrancado. Evidencia
DB_MAINTENANCE_APPLIED_20261015.txt.

## Ventana por registry + fixture hot real (2026-10-16, sin push aun)
Sonda lock eliminada (recuperaba el original pre-backup: forense).
Ventana = registry no-ACTIVO + re-hash pre-write (sin exclusion
sostenida declarada). Fixture hot REAL (magia valida, bloquea ro).
Spy: 1 sola apertura rw en origen (la _recover final). Barrera
pendiente. Sin aplicar, sin corridas. V2 abierto.

## Mantenimiento aplicable + deriva/discrepancia (2026-10-16, sin push aun)
--apply con backup real + re-verificacion pre-write + exclusion de
escritores + aplicado-vs-restaurado; backup verificado fuera del
repo e inexistente; regresiones de deriva/discrepancia (22 tests).
Barrera 1108 exit 0. Sin aplicar, sin corridas. V2 abierto.

## Correccion revision 2026-10-16 — metricas honestas + apply/backup (sin push aun)
dispatchDelayMs/yieldLagMs (nombres honestos) + test ruta real con
delay 300ms (3/3 estable); --apply con backup fuera de git +
protecciones realpath + fallos limpios (14 tests); informe
RECOVERY_REHEARSAL publicado (hot-rollback, intacto). Barrera 1100
exit 0. Sin aplicar al original, sin corridas. V2 abierto.

## Journal-recovery ensayado + atribucion queue/transit (2026-10-15, sin push aun)
Bloqueo resuelto por procedimiento propuesto (DB_MAINTENANCE_RECOVERY,
NO aplicado al original): ensayo en copia ok, diff 0, canonico
intacto. Instrumentacion arrival/queue/transit + 5 tests (umbral
intacto, sin corridas). V2 abierto (nuevo PID), cero auto-corridas.

## Post-mortem piloto brief 20261015T000730Z — ABORTED sano (2026-10-15, sin push aun)
Lanzado por V2 fuera de autorizacion registrada (agente no emitio).
Aborto timestamp-reject-rate 0.146136>0.05 a 00:08:34Z; PIDs muertos
verificados, seguridad 0/0/0. Rechazos = skew-guard bookTicker,
reloj sano, entrega degradada; umbral intacto. SQLite 503 por journal
caliente (error exacto preservado; journal intacto). Correcciones:
contador terminal congelado + readiness ABORTED terminal. Evidencia
PILOT_BRIEF_20261015_ABORT.txt. V2 abierto, cero auto-corridas.

## Cierre defectos pre-piloto 202/identidad/migracion (2026-10-14, review/o1-funcional-v2-observacion, sin push aun)
BotControl: 202 pendiente + reconcile (exito solo con confirmacion
explicita; 3 tests). host_process: `_run_text` (None/decode/ausente →
UNKNOWN) + expected-sin-real → False (15 tests, 7 fail-before; 8E+1F
previos verdes por la causa). Migracion en fixtures v9/v2 temporales
(cero contacto canonico). Barrera 1077 OK exit 0; frontend 255/255.
Piloto brief 120s pendiente de autorizacion, no iniciado.

## Revision pre-piloto sobre e887287 (2026-10-14, review/o1-funcional-v2-observacion, sin push aun)
Presupuestos separados (status 4200 / stop 8000 / start 65000ms) con
reconciliacion START_TIMEOUT_UNCERTAIN (202) + pre-check ALREADY_RUNNING
(sin segundo spawn); readiness por capability habilitada (no callable)
+ storage (bloqueo sin DB/disco<256MB; aviso 1GB/historico); presets
own-keys (prototipos rechazados); compat corregida (lectores admiten
9/10 y 2/3; prospective reporta schema real; ruta
data/historical/historical.db; base main v10/v3 verificada por
copia-temp, incremental 0 filas). Compat implementada != consumo vivo
(pendiente barrera final + QA visual + piloto brief autorizado).

## Bot + V2 observacion (2026-10-13, review/bot-dashboard-v2-observacion, sin push aun)
V2 checkpoint 27b7af5 (mas reciente; contiene DASH-V2-47) como interfaz
principal; Python SSR a LEGADO (sin semanticas contradictorias).
Matriz 10 funciones + funding en 3 niveles + ciclo/aceptacion + preflight
medido (docs/OBSERVATION_RUN_MATRIX|CYCLE|STORAGE_PREFLIGHT_CONTRACT).
Kronos/IA diferidos (F-KRONOS-01). V2 SELECT-only verificado; gates 2/9
vs backend v10/v3 (fail-closed). Vitest local 24/24; visual 27b7af5
PENDIENTE (sin servicios). Sin corridas reales, paper, ordenes ni gates.

## Entrega nueve archivos 6fd6091-base (2026-10-13; push review/entrega-nueve-archivos-6fd6091 completado en 3cbbb1c)
Base 6fd6091 (= remoto). Nueve archivos tecnicos: comparador+M6-M8 auto (10/10),
motor (cap uncovered al holding, calendario monocontrato, mark stale excluido,
fees salida a exit value; 1 assert legacy corregido y documentado), runner
(symbol preservado + manifiesto), tests R1-R7 (9/9), handoff 27b7af5 corregido
(lee historical.db real; gates historico-2/operacional-9 vs backend v10/v3).
Dirigidas 68/68 OK; barrera 1029 con 1F+8E preexistentes contrastados en
worktree de14ac1 (misma firma); aislamiento OK (0/0/0, hashes iguales).
Logs completos en docs/evidence/BARRIER_ENTREGA_NUEVE_*. Sin merge, sesiones,
paper, ordenes ni gates.

## Correccion tecnica de14ac1-base (2026-10-13, review/correccion-tecnica-de14ac1, sin push aun)
Base de14ac1 (= remote review/w-lumia-correccion-bc327f1; phase1 remote=local en
bc327f1; main intacto). Comparador: signo/posicion de inf + CSV vacio/ilegible
(INCOMPLETE exit 2), regresiones M1-M8 + SELF automatizadas
(scripts/regress_compare_cases.py, 10/10). Motor v4 aditivo: realizados vs
abiertas vs marcas, open_at_end fuera de metricas realizadas, costes de
salida hipoteticos separados, curva realizada por cierre efectivo; funding
qty x mark con identidad, dedup/rechazo duplicados, cobertura acotada,
gaps detectados, faltantes/fallback explicitos (contrato v4.1). Runner por
familia/ version (H3 ya no descartado), identidad por indice, demo H1/H2/H3.
Aislamiento: incidente v2->v3 reconciliado (aditivo, verificado read-only;
canonico intacto); incompatibilidad v10/v3 explicita + handoff 27b7af5
(docs/DASHBOARD_V2_27B7AF5_READ_HANDOFF.md; frontend/ intacto). Pendientes
que siguen: despliegue/operacion de lo corregido, OOS/calibracion/
rentabilidad, gates. Sin merge, sesiones, paper, ordenes.

## Cierre W/LUMIA documental — reproduccion aislada (2026-10-13; push phase1 bc327f1 completado)
Reproduccion de caso (DESCRIPTIVE/IN-SAMPLE): paquete en
`binance_case_study/` (12/12 hashes OK), re-ejecutado en copia temporal
(analyze 0, finish 0); coincidencia numerica parsed 0 diffs, bytes
difieren por serializacion; PNG NO inspeccionado (equivalencia visual no
declarada). Evidencia: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_*` + script
de comparacion. Distincion: reproduccion de casos != integracion
dashboard (campos/versionado/funding-calendario pendientes) !=
validacion financiera (sin OOS/calibracion/rentabilidad; gates intactos).
V2 exacto `27b7af59cb1e313169f49655161d66e043b5412d` = checkpoint
estatico frontend `dash-v2-03-token-detail` (Next.js bajo `frontend/`,
sin BFF/datos vivos); no confundir con el dashboard Python SSR del
backend (`dashboard.py`). Pendientes explicitos del prompt correctivo
anterior (NO resueltos por este cierre): funding, posiciones abiertas,
runner, incidente de aislamiento, schemas V2. Sin ordenes/paper/servicios.

## Correccion V2 + comparador (2026-10-13, review/w-lumia-correccion-bc327f1; push de14ac1 completado)
Addendum sobre el bloque anterior (historia preservada). V2 exacto
`27b7af59cb1e313169f49655161d66e043b5412d` (rama `dash-v2-03-token-detail`,
revisado con `git show`, sin tocar el checkout) SI tiene rutas BFF
(`frontend/src/app/api/v1/live-movers/route.ts` y hermanas) y adapters de
lectura SQLite (`frontend/src/lib/canonical-market.ts`, `historicalRead`
con BEGIN/COMMIT/ROLLBACK y fallback `available:false`): el "sin
BFF/datos vivos" del bloque anterior era erroneo. Integracion
PARCIALMENTE implementada (ruta de lectura existe) != feed
live/operacion verificados (la ruta declara alignment/freshness
UNVERIFIED y advierte que cobertura retenida no certifica liveness
presente). Comparador fortalecido (missing-masks primero, tipos y
especiales, sin omisiones silenciosas, exit 1/2, JSON UTF-8) con 5
regresiones en copias temporales. Reconciliacion: phase1 avanzo
bdc9ef2->bc327f1 con 21 commits (esta correccion anadio solo sus
propios); publicar no equivale a aceptar las correcciones anteriores.
Pendientes: funding, realizados/marcas, runner, aislamiento, schemas V2.
Sin merge/force-push, despliegues, sesiones, paper, ordenes ni gates.

## Mejoras funding/trazabilidad/dashboard/casos/evaluacion (2026-10-13, sin push aun)
Funding v4 por liquidaciones + linkage research v3 + dashboard con
semantica honesta + protocolo de casos (paquete ausente) + runner de
evaluacion por familias. INCIDENTE: historico canonico v2->v3 por
side-effect de test (aditivo, verificado intacto); corregido y con
barrera. Sin ordenes/paper/servicios; sin rentabilidad ni gates.

## Cierre correctivo R1-R7 (2026-10-13, rama review, sin push aun)
R1-R5 motor v3 (conocimiento estricto, marcas vs ejecuciones, gap-first,
orden stop-antes-fills, metricas demostradas); garantias v2 retiradas,
motor NO verificado causalmente. R6 cadenas v1-v8 a v10 en una init
(pins actualizados, error explicito en tablas ausentes). R7 resolver
HistoryStore unico en status/worker/retention. run_id UUID32 con garantia
probabilistica precisa. Suite 972/972 en sitio + barrera exit 0 (0/0/1RO,
hashes limpios); canonico intacto (schema v9, 221b33/ca6479/45c6a3,
375/225). Copia aislada pendiente. Sin rentabilidad/V2/Paper/ejecucion.

## Verificacion final (2026-10-12, sin push)
In-place: barrera P2 exit 0 sobre 950 tests (0 bloqueados, 0 efectivos,
1 RO mode=ro de supervision registrado aparte, hashes/inventarios
iguales). Copia aislada (git archive HEAD, sin data//logs/untracked):
Windows win32, Python 3.14.3, websockets 15.0.1, discovery unittest
canonico 950 ejecutados, 0 fallos, 1 skip esperado (migracion v9 sobre
copia canonica ausente), exit 0, sin crear data/ ni logs/. Plataforma
Linux no reproducida aqui (pendiente si se requiere). Evidencia:
docs/evidence/ISOLATED_RUN_950.txt. Commits locales (sin push):
motor, aislamiento, trazabilidad, documentacion + 2 fallouts de
verificacion (ruta absoluta en test, mkdir diferido). Trabajo ajeno y
untracked preexistentes intactos.

## Cierre correctivo P1-P4 (2026-10-12, sin push)
P1 motor offline v2 (7 defectos causales/contables corregidos; 10
regresiones fail-before 8F+2E sobre bdc9ef2, 26/26 pass-after; contrato
de lectura v2 sin cablear). P2 inyeccion minima Rutas B/C con defaults
intactos (barrera con buckets: 946 verdes, 0 bloqueados, 0 efectivos,
1 RO mode=ro separado, hashes/inventarios limpios). P3 linkage run_id
(schema v10; migracion probada en copia temporal v9 real; historicos
NULL=UNKNOWN sin backfill). P4 docs reconciliados (README/EVENT_LABELING/
ARCHITECTURE/TASK_QUEUE/PAPER_LAB/V2-addendum/cobertura BTC 1h). Suite
950/950 en sitio; copia aislada pendiente de corrida final. Sin
rentabilidad, V2, Paper Lab ni ejecucion. Veredicto final abajo.

## ETAPA 5 Paper Lab plan — DONE (2026-10-12, design only)
Six build items + entry gates specified; nothing implemented or started.
Plan: docs/PAPER_LAB_PLAN_ETAPA5.md. Canonical 932/932 OK with stable
hashes (221b33/ca6479/45c6a3).

## ETAPA 4 offline backtest prep — DONE (2026-10-12, prep only)
Isolated engine + 16 tests green + UNWIRED V2 read contract. Mechanics
smoke on fixtures executes (dev/OOS x 1x/2x/3x, monotone costs, counted
skips); no performance claim, no validation. Engine:
src/microstructure_probe/backtest_offline.py. Contract:
docs/BACKTEST_READ_CONTRACT_V1.md.

## ETAPA 3 research/backtest contract — DONE (2026-10-12, contract only)
H1/H2/H3 study contracts with per-family universe/confirmation/timing/
invalidation/no-trade/params/evidence blocks + versioned cost model +
replay limits + in-sample labeling mandate. No engine, no runs, no claims.
Report: docs/RESEARCH_BACKTEST_CONTRACT_ETAPA3.md.

## ETAPA 2 dataset readiness — DONE (2026-10-12)
Pure-read provenance (hashes unchanged): 225 fixture rows confirmed
(DOGEUSDT hot lifecycle detail=test) retained + explicit filter rule; 150
operational-probable with unknown per-row runs; prospective 66/228 clean of
markers; event studies 2831x6 exact with FORMATION_GAP usability correct by
design. Verdict: descriptive exploration only; no validation/trading claim.
Evidence: docs/evidence/DATASET_PROVENANCE_ETAPA2.json, report
docs/DATASET_READINESS_ETAPA2.md.

## ETAPA 1 test isolation — DONE (2026-10-12)
Barrier scripts/audit_test_isolation.py over the full suite: PREFIX 911/911
green WITH 61 swallowed default-factory attempts (test_probe x5,
test_host_telemetry x2, test_p14b_3 x4 methods) + 97 residual canonical
connects classified (rehydration/HistoryStore-reads/RO-URI) + 0-byte
logs/probe-runs sidecars from three test-side routes. Repro on temp:
10 bodies -> 4 obs + 54 rej rows, canonical untouched. Fixes are test-only
(isolated-probe helpers, evidence_dir, pc.repo_root patch; 5 new regression
tests, no production change). POSTFIX: 916/916 OK, zero prohibited hits,
zero file/registry writes, clean inventories, exit 0. Canonical
run_tests.py -q: 916/916 OK (162.068s), microprobe.db SHA256 stable
(221b33..fb86), historical.db + registry unchanged. Pure re-read: 375
universe rows, 225 detail='test', retained as-is. Complete-purity (zero
connects) NOT claimed: Routes B/C need production injection points
(deferred). Full evidence: docs/TEST_ISOLATION_ETAPA1_REPORT.md.

## Final proof and fixture-isolation checkpoint (2026-10-11)
Original proof correction: focused 1/1 and canonical 910/910 exit0 (184.479s).
A subsequent System read found 375 universe rows, 225 tagged detail='test',
rather than the earlier read of 366/222. Earlier canonical-suite preservation
claims do NOT hold across those test runs. Readonly GET hashes are a separate,
bounded check and remain equal.

Root route proven without touching the canonical DB: original HotSyncTest
calls the default persistence factory twice and writes three DOGEUSDT lifecycle
rows to an intercepted temporary store. test_universe_probe.make_probe now
injects a real initialized temporary PersistenceStore with cleanup per testcase.
All 11 module tests pass with the default factory forbidden, zero calls.
One added regression prevents fallback. No application source changes.
This establishes a test contamination route; it does not attribute every
historical tagged row. Existing canonical rows were retained without cleanup.

Final canonical: 911/911 application tests exit0. The preservation wrapper
exits1: microprobe.db SHA256 changed; historical.db and registry hashes equal.
Universe rows stayed375/225: HOT leakage fixed, whole-suite preservation FAILED.
A guarded subset audit (729 tests) records default-store accesses in test_probe,
test_host_telemetry and test_p14b_3_transport_freshness (six errors with factory
forbidden, swallowed persistence errors also observed). These remaining fixtures
are a BLOCKER for whole-suite isolation; no claim of complete purity is made.
See backend-isolated-final.json and default-store-audit.json.
Source notice remains until historical provenance is reviewed.
The 496-test frontend Python snapshot is historical validation, not the
current backend. Its old HOT fixtures must not be rerun against the canonical
store; reconcile the fixture isolation or run it in a fully isolated checkout.
FEATURES_IMPLEMENTED adds temporary HOT fixtures and fallback regression.
FEATURES_VERIFIED final 911 plus isolated original/after negative control.
DEFERRED_FEATURES retains remaining default-store test isolation, historical lineage and complete cutover.
No runs, traffic, orders, Start, retirement, main merge or gate advancement.


# CURRENT_STATE

## DASH-V2-71B reviewer correction — 2026-10-11
89232f7 independently reviewed: discovery/canonical 910, exit0. Strengthened
existing purity test (missing historical-byte assertion, no new logs, env
restoration); historical-tempfile mutation passed old proof and fails new.
No application source change. Final bytes do not certify readonly mode;
four HistoryStore init calls observed. See DASH_V2_71B_REVIEW_CORRECTIONS.md.
Full cutover/Start/gates unchanged; universe detail=test provenance pending.


## DASH-V2-69 — 2026-10-11 — extraction proof review
Exact c59c5ec extraction reviewed independently. Five helper bodies match; original Python 3.14 find_module blocker was ineffective despite four green tests. Existing H2 strengthened with find_spec plus deliberate negative control; four focused tests pass. No application source edits. V1 contract retirement section now closes extraction prerequisite while retaining parity/review/authorization requirements; no retirement performed. See DASH_V2_69_EXTRACTION_PROOF_REVIEW.md; canonical verification recorded there. Full cutover and operational readiness remain PARTIAL; Start/gates/main/DB/registry preserved.



## DASH-V2-62 - 2026-10-11 - disabled transactional launch corrected

User authorized the V2 reviewer to correct the backend branch directly, in an isolated checkout based on da231b9. R1-R5 and C1/C2 from frontend f63dd16 corrected: direct captured child identity, one lease evaluation, canonical supervise argv, strict finite verification/deadline, owned/gone/replaced/unknown rollback with final pure assessment, strict non-future freshness and explicit lock/evidence preflight effects. Added 29 tests; canonical 902/902 OK, 160.768s, exit 0; focused 52/52 OK. Fail-before: 15 of 18 initial methods failed (25 assertions/subtests). See DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md and docs/evidence/DASH_V2_62_LAUNCH_VERIFICATION.json. DONE bounded disabled preparation; no general operational PASS. Start/launch flag remain disabled; no new HTTP/CLI operation, market probes, longevity, SUCCESS_GATES or main merge. Original agent checkout/evidence preserved; backend remote will advance by normal fast-forward push. Next exact-SHA V2 checkpoint, enablement/real watcher startup association and runs remain separate.

Factual state as of 2026-10-06 (order refinement). Historical evidence:
`docs/PHASE_1_REPORT.md` (do not rewrite).

## Baseline (audited, preserved)

- Codebase: `src/microstructure_probe/` — `probe.py`, `detectors.py`, `metrics.py`,
  `telemetry.py`, `clock.py`, `config.py`, `models.py`, `__main__.py`.
  Plus root `run_tests.py` (P1-00; test tooling only, no app behavior change).
- Version: 0.2.0 (`pyproject.toml`). History: `157e85e` baseline + `d6801a5`
  brain checkpoint, branch `phase1/market-intelligence-dashboard`, published to
  private `mariomoreta/binance-futures-microstructure-bot` (origin/main +
  origin/phase1 in sync). Repo-local git identity configured per operator
  authorization; nothing global was changed.
- Mode: OBSERVE ONLY. `BOT_MODE=observe` enforced in code; any other value aborts.
  No authenticated clients, no order paths (covered by static test).
- Feeds (public, routed endpoints): `/public` (bookTicker, depth20@100ms),
  `/market` (aggTrade, `!markPrice@arr@1s`, `!forceOrder@arr`).
  Symbols: BTCUSDT, ETHUSDT, SOLUSDT (`config/probe.json`).
- Implemented: clock sync (5-sample midpoint median, ~10 min), gap/staleness
  detection (staleness only on cadenced streams; event-driven silence ≠ stale),
  raw/corrected event+transaction latency per stream/symbol, monotonic processing
  latency split (parse/metrics/detector), liquidation individual+10s-window
  detectors, funding percentile extremes with warm-up + non-independence note,
  10s-bucket volume z-score with warm-up + near-miss, telemetry
  (quantiles over last 20k samples; exact count/min/max/mean), JSON logs +
  `final_summary`.
- Phase 1B semantics: `E` = event time; `T` = trade/transaction time except
  markPrice where `T` = next funding time (NOT latency). Legacy global clamped
  lag kept labeled as legacy, not a gate metric.

## Verification (2026-10-06)

- Canonical: `python run_tests.py` from repo root → **144/144 PASS** (28 baseline
  + 32 persistence/sampling/v2 + 22 universe/returns + 24 dashboard + 38 P1-05).
- `--show-streams` → correct routed `/public` + `/market` URLs.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port-policy evidence; selection happens at P1-03 startup).

## P1-01 short transport validation — RESULT: PARTIAL (2026-10-06)

Run: `python -m microstructure_probe --duration 1800`, BOT_MODE=observe,
`runtimeSeconds: 1804.969`, exit 0. Evidence log (local, git-ignored):
`logs/p1-01/probe-1800s.log`. No keys, no orders, no capital, no private APIs.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`.
- Uptime: market 98.51% (1773.3s/1800.1s), public 95.05% (1711.0s).
  Attempts 60 (public 46, market 14), all succeeded.
- Reconnects: 58 total (public 45, market 13) — every one
  `ConnectionClosedError: no close frame received or sent`, retry 1s
  (backoff resets on success, so it never grew). ~1 drop per 31s average.
- Messages: 172,906 total. bookTicker 32.2/31.5/17.9 msg/s (BTC/ETH/SOL);
  depth ~2/s per symbol (cadence allows ~10/s); markPrice arrays 1563 of ~1800
  expected; forceOrder 421; aggTrade 5466/4709/3205.
- Delivery lag (corrected event lag): bookTicker p50 14.8–19.2s / p95
  45.6–53.8s; depth p50 ~14.7s / p95 ~50.4s; aggTrade p50 31.6–38.1s / p95
  73.5–75.6s; markPrice p50 35.0s / p95 75.9s; forceOrder p50 38.5s / p95 69.0s;
  max ~127s. Exchange-side E−T deltas are milliseconds (bookTicker p50 0ms),
  so the delay is entirely in the delivery path to this host, not Binance.
  Clock sync 3/3 ok (15/15 samples); offset drifted −231ms → −475ms; RTT
  610–943ms — slow/lossy path confirmed.
- Skew guard: `timestampRejected: 147417` (~85% of messages, |received−E| >
  5000ms, degraded from the first 30s summary onward). Rejected messages skip
  metrics+detectors, so detectors operated on survivors only.
- Gaps/silence: depth sequence gaps 50/49/49 (reconnect-driven, expected).
  Max observed silence: depth ≤28s, bookTicker ≤21.5s, aggTrade ≤16s,
  markPrice 12s. forceOrder silent up to 111s — event-driven, correctly NOT
  reported stale (Phase 1B fix works in practice).
- Errors: parse 0, payload 0, websocket errors = reconnects (58).
  Processing latency sub-ms (p50 ≤0.17ms) — probe CPU is fine.
- Detectors: 26 `extreme_funding_rate`, 0 liquidation, 0 volume. The 26 funding
  events are sampling artifacts (near-constant series ±1e-7…1e-5 evaluated on
  sparse post-rejection arrivals, first firing at the 30-sample warm-up edge),
  NOT signal validation. No threshold conclusion may be drawn from this run.
- Safety block in every summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.

Verdict reasoning: P1-01 as a measurement exercise succeeded (full
characterization obtained), but transport in THIS environment is unhealthy
(reconnect storm + 15–75s delivery lags + 85% skew-rejection). Therefore
PARTIAL: evidence recorded, P1-02/P1-03 (local builds) may proceed, but gates
G2–G4 cannot pass on this evidence and P1-10/P1-14 require re-validation in a
healthy network (tracked as `P1-01R` in `docs/TASK_QUEUE.md`).
`docs/PHASE_1_REPORT.md` historical evidence untouched.

## Phase 1 execution order (binding, refined 2026-10-06)

`P1-00` tooling ✅ → `P1-01` short transport validation (30–60 min, NOT 6h) →
`P1-02` persistence foundation → `P1-03` minimal dashboard (`/overview`,
`/system`) → `P1-04` universe+returns → `P1-05` velocity/rank → `P1-06`
volume/flow → `P1-07` book/OI → `P1-08` VWAP/vol/structure → `P1-09`
intelligence dashboard (`/movers`, `/symbol/:symbol`, raw features first) →
`P1-10` ≥6h soak with dashboard live → `P1-11` raw feature validation →
`P1-12` classifier v0 (BLOCKED until P1-11) → `P1-13` signal/extreme-move UI →
`P1-14` 24h calibration + gate evaluation. Full detail: `docs/TASK_QUEUE.md`.

Superseded: the earlier "soak first, persist nothing in Phase 1" sketch.
Persistence foundation is now explicitly a Phase 1 task (local, observe-only,
dashboard-feeding) — see `docs/DECISIONS.md`.

## P1-02 persistence foundation — RESULT: PASS (2026-10-06)

- Tech: stdlib SQLite (`sqlite3`), no new dependencies. Store:
  `data/microprobe.db` (project-local, git-ignored via `data/` + `*.db`).
- Schema v1 + version gate + column migration: `persistence_meta`,
  `telemetry_snapshots` (periodic `build_summary` output for the P1-03
  dashboard), `market_observations` (valid only, `is_valid` + symbol/stream
  indexes), `rejected_observations` (skew/parse rejects, reason + stream
  indexes). 9 indexes total.
- Write path (probe.py, all fire-and-forget with `persistence_error` logging,
  never breaking the probe): valid dict payloads → observations with
  normalized price/qty/E/T; markPrice arrays → single `MULTI` record (no
  longer dropped); skew-rejected payloads (dict or list) → rejections only;
  every summary (30s + final) → snapshot row.
- Invalid-data guarantee: the skew guard returns before the valid-write code,
  so rejected messages can only reach `rejected_observations`;
  `latest_observations()` hard-filters `is_valid = 1` (both proven by tests,
  including a probe-level skew test).
- Retention: snapshots ≤1000, observations ≤10000, rejections ≤1000 rows
  (instance-overridable); steady-state storage bounded (~10–20MB worst case).
- Non-blocking: writes run via `asyncio.to_thread` under a lock (single
  shared connection); smoke (2000 mixed msgs): schedule p50/p95
  0.021/0.039ms, full drain 9.2s off-loop. Per-insert retention DELETE is the
  dominant cost (~4.6ms) — fine at current rates; see risks.
- Restart: close() is idempotent; reopen replays schema gate and all rows
  survive (tested).
- Found and fixed during verification (were failing, 5 errors): missing
  `spread_bps_json` column + 19-vs-18 INSERT mismatch; `store_rejection_record`
  crashed with no running loop; real-summary legacy-lag dict vs REAL column;
  markPrice arrays never persisted; snapshots never wired to the probe.
- Known risks: (1) no write backpressure — sustained rates far above ~200/s
  queue tasks in memory (dashboard freshness lags, WS never blocks); P1-04
  sampling/aggregation is the planned remedy. (2) At full healthy-network
  bookTicker rates the 10k observation cap retains only recent minutes —
  sufficient for dashboard/P1-04 bootstrap, not archival history (Phase 2
  owns that).

## Project brain

- Live corrigendum (found during P1-03): snapshot writes starved behind bulk
  observation traffic on the shared executor (0 snapshot rows vs 9260
  observations in a live run). Fixed with a dedicated single-thread snapshot
  writer + regression test; 2 snapshots landed on the very next live run.
  See `docs/DECISIONS.md`.

## P1-03 minimal live dashboard — RESULT: PASS (2026-10-06)

- Stack: stdlib only (`src/microstructure_probe/dashboard.py`,
  `ThreadingHTTPServer`, server-rendered dark HTML, no new dependencies,
  version 0.3.0). Data only via P1-02 reads (`latest_telemetry`,
  `latest_observations`, `get_rejection_stats`, `storage_info`).
- Routes live: `/overview` (safety banner, connections, uptime, message
  activity, stale/silent, reconnects, gaps, rejections, snapshot age,
  detector counts labeled NOT trade signals), `/system` (per-stream table,
  rates, raw/corrected p50/p95, processing latency, clock, rejections,
  persistence, safety), `/api/health` (status/version/uptime/reachability/
  snapshot time/streams/BOT_MODE/safety/reasons), `/api/snapshot`.
  No buttons, no trading controls, no private-account data.
- Live instance: http://127.0.0.1:8091 (first candidate, was free),
  PID 10796, `logs/dashboard.pid`, health `ok` at startup, all routes
  HTTP 200, unknown route 404. Started via
  `python -m microstructure_probe.dashboard start`; left running (read-only,
  localhost — safe).
- Seed: 40s observe-only probe (exit 0) wrote 10k observations + 2 snapshots
  of real market data — no mock data anywhere. Seed window itself was healthy
  (0 reconnects, 0 skew-rejections), so the pages currently show HEALTHY;
  the model reports DEGRADED/STALE/UNKNOWN from persisted evidence when
  present (proven by tests, and P1-01-style degradation would surface the
  same way). Snapshot ages without a running probe — STALE chip after 120s
  is honest; continuous freshness arrives with the P1-10 soak feed.
- Found and fixed live: snapshot executor starvation (see DECISIONS).
- Tests: 66/66 (18 dashboard: health ok/degraded/stale/unknown, routes,
  empty-DB, banner values, no-controls, port skip/busy, PID live/dead/stale).

## P1-04 symbol universe + multi-timeframe returns — RESULT: PASS (2026-10-06)

- Universe: `universe.py`, active trio preserved (BTC/ETH/SOLUSDT, explicit
  enabled/source/reason/activated_at metadata); no expansion, no ranking.
  No new REST endpoint introduced (static-config source; exchangeInfo remains
  future work) — no Binance-docs verification owed.
- Engine: `returns.py` — mark-price log returns, 7 TFs, 10s buckets (≤9180),
  tolerance max(60s, tf/20), UNKNOWN never 0, no lookahead, late/invalid
  refused. Valid-path-only ingestion (rejected messages return before it).
- Backpressure: sampling gate (bookTicker/aggTrade/depth ≤1/s per symbol;
  markPrice/forceOrder ungated; counts in `sample_stats()`); dedicated
  snapshot writer kept; schema v2 (`price_samples`, `return_features`,
  migration tested). 106/106 tests.
- Live 360s attempt: harness session-end killed the detached probe at ~330s
  (11 periodic summaries, no final) — lesson: detached children die with the
  tool session; reran 240s blocking → clean exit 0 + `final_summary`.
  Mid-run API: all 3 symbols with real prices, 1m warmed first, longer
  horizons honestly unavailable; dashboard `ok` while fed, STALE/DEGRADED
  honestly after (DEGRADED currently live from persisted reconnects +
  rejection rate — P1-01 degradation surfacing as required).
- Clean-run evidence (244s, 11/11 streams, 0 stale, safety 0/0/0):
  5 reconnects, 11448 skew-rejects (~93%, lags p50 22–85s — degraded env);
  engine 46 samples/symbol over 25-min restored+live span, 0 invalid, 0 late,
  0 unknown-symbol; sampling accepted 36/dropped 858 counted;
  inflight high-water 345, drained to 0 — no unbounded queue growth.
  Rejects went to `rejected_observations` only (cap 1000); returns contain
  no rejected input by construction + unit test.
- Dashboard: Symbol Returns on `/overview` + `/api/features/returns` live;
  partial warmup renders values + "—", no movers/rank/states/controls.

## P1-05 dynamic discovery + velocity/acceleration/ranking — RESULT: PASS (2026-10-06)

- Discovery (`discovery.py`, public REST only, no keys): exchangeInfo +
  24hr tickers on `fapi.binance.com` (docs site unfetchable — behavior
  verified live instead). Live scan: 924 seen → 449 eligible → 475 filtered
  (PERPETUAL + TRADING + USDT + ≥1M quote-vol floor). Core trio preserved.
- HOT: 6 dynamic (USUSDT +41%, 龙虾USDT +35%, BR/ORCA/NMR/GRIFFAIN +31–41% —
  small sharp movers, not large caps) promoted after 2 votes, stable after;
  losers LYN −25%, MINA −24%; most-active BTC/ETH/SOL by volume (movement ≠
  volume demonstrated). No WS subscription changes (trio only); HOT proposed
  via API/dashboard/logs; dynamic resubscribe is a documented next step.
- Momentum (`momentum.py` on P1-04 series, `feature()` untouched): velocity =
  return-change per second (flat trends ≈ 0 — not renamed returns),
  timestamp-aware acceleration, None until warmed; live velocity_1m values
  (e.g. ETH +3.2e-6/s) with accel honestly None until 3 evaluations;
  ranks ±/ties/change/velocity/accel across the trio (ETH #1 climbing).
- Dashboard: three separated health blocks, Symbol Returns kept, new
  intelligence area (tiers, live momentum, discovery movers, event history),
  `/api/discovery` + `/api/features/momentum`; forceOrder never missing;
  reject labels split run-vs-retained; no movers route, no states, no controls.
- Persistence v3 (discovery snapshot REPLACE, universe_events ≤500, rank
  vectors REPLACE-per-metric; tested v1→v3 and v2→v3 migrations).
- Live windows: 360s detached run killed by tool-session end (~330s, lesson
  recorded — detached children die with the harness session) + clean 240s
  blocking run (exit 0, final_summary): 11/11 streams, 0 reconnects,
  0 skew-rejects (healthy window!), 143659 msgs, engine 91 samples/symbol
  over 89-min span, sampling accepted 1888/dropped 141k counted, inflight
  high-water 6 → 0, safety 0/0/0. Dashboard `ok` while fed, STALE/DEGRADED
  honestly after. 30 funding crossings judged non-signal artifacts as before.
- Tests: 144/144 (38 new). Unicode HOT symbol (龙虾USDT) flows through
  JSON/DB/HTML correctly; only legacy Windows-console display needed UTF-8.

- `AGENTS.md` + 20 docs under `docs/`. No strategy, engine, or safety code
  touched. `docs/PHASE_1_REPORT.md` preserved as-is.

## P1-06 volume + aggressive trade flow — RESULT: PASS (2026-10-07)

- Semantics verified against CURRENT official USD-M docs + live payloads:
  same-price/same-side 100ms aggregation (insurance/ADL excluded), `m`
  (true→aggressive SELL, false→aggressive BUY), `q` RPI-inclusive vs `nq`
  normal, `E` ordering key, `st: 1` live. Recorded in `docs/MARKET_DATA.md`.
- Engine (`flow.py`, NEW): every valid aggTrade ingested pre-sampling;
  trailing windows 10s/30s/1m/3m/5m/15m with exact per-horizon expiry;
  baselines 10s/30s/1m/5m on completed buckets (skips counted, z null on
  thin/zero-variance history); 1m-referenced acceleration; same-E accepted
  in arrival order (first live run proved `<=` undercounts ~35% BTC flow —
  fixed, re-validated to 4027/4027 accepted, 0 late, 0 invalid).
- Persistence v4 (additive, tested v1/v2/v3→v4): `flow_features` per symbol
  + bounded `flow_buckets` (168 rows/run); restarts restore closed buckets
  only — returns span grew across runs (9340s → 9970s), no double-count.
- Live windows (blocking, BOT_MODE=observe, exit 0, dashboard live):
  (a) 363s degraded-transport lesson run (2403 processed, 35% same-E lesson);
  (b) 363s HEALTHY run — 11/11 streams, 0 reconnects, 0 skew-rejects,
  clock 5/5: 4027/4027 valid aggTrades into the engine (BTC 2035 / ETH 1317
  / SOL 675), raw persistence kept 746 aggTrade (3281 sampled away — flow
  totals provably unaffected), 168/168 buckets persisted, engine latency
  p50 0.030ms / p95 0.069 / max 0.19, queue 0/0, inflight 6→0, safety 0/0/0.
  Snapshot BTC 1m: 408 trades, $2.61M notional, 85.9% aggressive buy,
  delta +$1.88M, ratio +0.72 (raw feature, no conclusion). Baselines
  honestly warming (6/30 samples → z null). HOT [] (one scan < 600s
  interval → votes 1/2, hysteresis honest). 37 funding crossings — same
  hypothesis-artifact class as before, no threshold conclusions (P1-11).
- Dashboard v0.5.0 live at http://127.0.0.1:8091 (restarted, PID 31436):
  flow table + BUY/SELL bars on /overview, DISCOVERY ONLY labels,
  `/api/features/flow` + `/api/features/volume` live (200), health `ok`
  while fed; no buttons/controls/signals.
- Tests: 190/190 (46 new: 44 flow + v3→v4 migration + same-E arrival).
  Two pre-existing version-3 assertions updated to v4 (migration, expected).

## P1-07 order book + open interest — RESULT: PASS (2026-10-08)

- Docs verified (current USD-M pages + live payloads): depth20@100ms = FULL
  top-20 snapshots (`U`/`u`/`pu` chain, `st: 1`, `ps` live); OI = public
  `GET /fapi/v1/openInterest` (`{symbol, openInterest base, time}` live);
  `openInterestHist` evaluated + deferred (single provenance). In MARKET_DATA.
- Book (`book.py`, NEW): every valid depth snapshot pre-sampling; best/mid/
  spread, top-1/5/10/20 sums, imbalances, microprice + displacement,
  LS-origin slopes + asymmetry, 5/10/25bps concentration (null when
  unspanned), crossed kept+counted, gap→DEGRADED-until-chained, no score.
- OI (`open_interest.py`, NEW): 60s bounded poller (worker thread, failures
  counted, WS untouched) + tracker (2000/symbol; 1m/5m/15m deltas+rug rates,
  1m accel, descriptive price/OI contexts, staleness honest).
- Persistence v5 (additive, tested v1/v2/v3/v4→v5): `book_features` latest
  only (never restored live), `oi_samples` + `oi_features`.
- Live 363s blocking run (exit 0, dashboard live): 11/11 streams, 1 public
  reconnect, 15992 skew-rejects (degraded bookTicker window — recorded
  honestly). BOOK 7309/7309 valid processed (0 invalid/late), latency p50
  0.15ms/p95 0.30/max 1.07, 1 gap/symbol all recovered, queue 0/0.
  OI 18/18 polls ok (0 failures, p50 380ms/max 7.6s absorbed). FLOW intact
  (5684 processed — P1-06 regression green). Sampling lossless to engines
  (depth persisted 739 vs 7309). Safety 0/0/0. Live book: spreads
  0.012/0.037/0.834bps, ask-heavy imbalances, micro ~0, SOL 55% conc@10bps
  (BTC/ETH honestly null — band unspanned). Live OI: BTC 96105.2 (+9.4/1m,
  +69.7/5m), ETH 2323727.6, SOL 8287311.7 with descriptive contexts only.
  99 funding crossings — same hypothesis-artifact class, no conclusions.
- Dashboard v0.6.0 at http://127.0.0.1:8091 (restarted, PID 27296): book +
  OI tables, NO LIVE FLOW/BOOK labels, `/api/features/book` +
  `/api/features/open-interest` live (200), health DEGRADED honestly
  (reconnect + retained rejects); no buttons/controls/signals.
- Tests: 239/239 (49 new: 48 book/OI + v4→v5 migration). Five v4
  assertions updated to v5 (migration, expected).

## P1-08 VWAP + volatility + structure — RESULT: PASS (2026-10-09)

- Zero new sources: VWAP from flow aggregates, vol/range/structure from
  persisted 10s mark buckets, mark reference (MARKET_DATA §P1-08).
- Engine (`market_structure.py`, NEW, stateless over peer state): VWAP
  1m/3m/5m/15m + displacement; raw `sqrt(sum(r²))` vol 1m/5m/15m/1h
  (≥5 returns + window−10s span, grid-coverage `warmed`); range + position
  + median/z expansion over completed blocks; confirmed pivots (30s delay),
  HH/LH/HL/LL, swing distances, prior-15m-block breakout tags. Resilience
  deferred (DECISIONS).
- Persistence v6 (additive, tested v1..v5→v6): `structure_features`
  REPLACE-per-symbol; continuity inherited, never fabricated.
- Live 372s blocking run (exit 0, dashboard live): 11/11 streams, 2 public
  reconnects, 57954 skew-rejects (degraded bookTicker window — honest).
  STRUCT 27 evals (9 summaries × 3), latency p50 0.84ms/p95 1.26, queue
  0/0. FLOW 4111 + BOOK 1737 + OI 15/15 intact (peer regressions green).
  Sampling lossless (aggTrade 172 vs 4111). Safety 0/0/0. Live: VWAP disp
  +0.7..+1.1bps (raw only); 1m vol UNKNOWN — fresh mark buckets starved
  by rejects, reported honestly; swings (incl. ETH HH) from restored
  history proving continuity; breakouts UNKNOWN (thin prior block).
  11 funding crossings — same hypothesis class, no conclusions.
- Dashboard v0.7.0 at http://127.0.0.1:8091 (restarted, PID 30344):
  structure table + `/api/features/vwap|volatility|structure` live (200),
  health DEGRADED honestly; no buttons/controls/signals.
- Tests: 277/277 (38 new: 37 structure + v5→v6 migration). Five v5
  assertions updated to v6 (migration, expected).

## P1-09 market-intelligence terminal — RESULT: PASS (2026-10-09)

- IA: `OVERVIEW` (market summary cards, top activity, compact live-core
  rows linking to token pages) → `MOVERS` (market table + 8 categories:
  24h gainers/losers/most-active, HOT, live velocity ±, acceleration,
  volume expansion, aggressive-flow leaders) → `/symbol/:symbol`
  (header + mark-price SVG chart + momentum/flow/book/OI/VWAP-vol-
  structure panels) → `SYSTEM` (all P1-03…P1-08 diagnostics + API index).
  Search (`/search` + `/api/search`, case-insensitive partial over the
  persisted universe, escaped, deterministic). Capability vocabulary
  LIVE/WARMING/DISCOVERY ONLY/STALE/DEGRADED/UNKNOWN UI-wide, tier
  orthogonal (neutral chips). No signals, no controls, no private data.
- Code: `dashboard.py` (routing/health/lifecycle, v0.8.0) +
  `dashboard_data.py` + `dashboard_components.py` + `dashboard_views.py`.
  Chart/CSV: `GET /api/symbol/:symbol/price[?range][.csv]` over P1-04
  `price_samples` (5m/15m/1h/4h/24h, ≤1000 pts, oldest-first, no futures,
  400/404 semantics). Book integrity copy: HEALTHY / Recovered N gaps /
  DEGRADED — gap active (no more `OK (1 gaps)`).
- Tests: 312/312 (35 new P1-09: routing/search/movers/token/chart-CSV/
  UI-regressions/unicode/escaping; 3 old overview-table assertions moved
  to `/symbol/:symbol` as intentional IA evolution; P1-04…P1-08 APIs green).
- Live 360s blocking run (exit 0, dashboard live, BOT_MODE=observe):
  11/11 streams, 0 reconnects, 0 skew-rejects (healthy window), uptime
  99.7%, corrected lags p50 ~180–260ms, clock 1/1 ok (−137ms/356ms RTT).
  FLOW 11086 events p50 0.03ms; BOOK 10274, 0 gaps; OI 18/18 polls ok;
  STRUCT 33 evals p50 ~1.05ms; returns 236 samples/symbol over 18.38M ms
  span, 0 invalid/late; discovery 924→481 eligible, HOT [] (one interval,
  votes 1/2 — honest); 140 funding crossings (same hypothesis-artifact
  class, no conclusions); safety 0/0/0. Evidence: `logs/p1-09/`
  (local, git-ignored).
- Dashboard live at http://127.0.0.1:8091 (restarted, PID 7564, v0.8.0):
  health `ok` while fed; all 22 routes 200 (pages 9–49ms, APIs 2–30ms);
  BTC chart 1h=44pts/5m=26pts; search `btc`→BTCUSDT; discovery-only
  龙虾USDT (+54.08%) page 200 with DISCOVERY ONLY — NO LIVE DEEP FEATURES
  and no fake panels; BTC page WARMING + HEALTHY integrity; CSV
  `text/csv timestamp,price`; forbidden-language scan clean on
  overview/movers/token pages. P1-01R transport re-validation still owed
  before P1-10 (this window was healthy but is not the gated 30–60 min
  P1-01R run).

## P1-01R transport re-validation — RESULT: PASS (2026-10-07)

Run: `python -m microstructure_probe --duration 2700`, BOT_MODE=observe,
`runtimeSeconds: 2702.262`, exit 0, attached blocking (no detached child).
Evidence (local, git-ignored): `logs/p1-01r/probe-2700s.log` (4.5MB raw
console) + `logs/p1-01r/transport-summary.json` (extracted final_summary)
+ `logs/p1-01r/dashboard-health.json`. No keys, no orders, no capital, no
private APIs. No application-code changes in this phase.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`,
  `silentStreams: ["!forceOrder@arr"]` only (event-driven, correctly
  not-stale).
- Uptime: market 99.964765% (2699.097s), public 99.965575% (2699.119s).
  Attempts 1/1 per endpoint, 0 failures.
- Reconnects: 0 total (market 0, public 0); websocket errors 0.
- Messages: 2,259,664 total. bookTicker 958k/773k/375k (BTC/ETH/SOL);
  depth ~26k/symbol; markPrice 2699 updates; forceOrder 519; aggTrade
  30457/31289/9179.
- Delivery lag (corrected event lag): p50 171–251ms across all streams
  (aggTrade ~171–174ms, bookTicker 175–216ms, depth ~175ms, forceOrder
  174ms, markPrice 251ms); p95 199–390ms; max ~3.2–3.4s rare outliers
  simultaneous across streams (one transient ~3.3s stall, auto-recovered,
  no reconnect). Exchange-side E−T is milliseconds (bookTicker p50 0ms,
  depth p50 1–4ms), so the sub-second path delay is the delivery path to
  this host, not Binance.
- Skew guard: `timestampRejected: 0` (0.0% — vs 85% in P1-01).
- Gaps/silence: depth sequence gaps 0/0/0. Max cadenced silence 2.85s;
  forceOrder silent up to 66.9s — event-driven, correctly NOT stale.
- Errors: parse 0, payload 0. Processing p50 sub-ms (parse/metrics/
  detector); full-processing p50 ≤2.4ms, p95 ≤22ms; isolated max spikes
  (one 464ms aggTrade) with all queues 0/0 — no backlog, probe CPU fine.
- Clock sync 5/5 ok (25/25 samples); offset −254ms; RTT 340ms.
- Engines (regression watch only, no semantic changes): returns 507
  samples/symbol over 21.58M ms span, 0 invalid, 0 late; FLOW 70925
  events p50 0.043ms queue 0/0; BOOK 77081 msgs 0 gaps 0 crossed p50
  0.19ms; OI 132/132 polls ok 0 failures; STRUCT 267 evals p50 1.93ms
  queue 0/0; persistence inflight high-water 43, drained to 0.
- Discovery: 924 seen → 482 eligible; HOT 6 promoted over multiple scans
  with votes (multi-scan hysteresis working as designed).
- Detectors: 3701 `extreme_funding_rate` (same hypothesis-artifact class
  as P1-01/P1-05 — near-constant series, NOT signal validation),
  2 `large_liquidation_individual` (ETH SELL, real counted observations),
  22 `volume_spike` (real hypothesis-threshold crossings). No threshold
  conclusion drawn from any of these.
- Safety block in final summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.
- Dashboard (v0.8.0, PID 7564, left running): `ok` while fed (53.7s
  snapshot age at check); post-run `/overview`, `/movers`, `/system`,
  `/symbol/BTCUSDT`, `/api/health` all 200 (20–51ms); health transitioned
  honestly to `stale` 134s after probe exit (snapshot age >120s chip).

Verdict reasoning: every P1-01R gate passes on the full 45-minute window
— full coverage, 0 reconnects, sub-second p50/p95 delivery lag, 0%
rejections, sub-ms-typical processing with drained queues, 5/5 clock sync.
The single ~3.3s transient stall is rare-outlier grade (p99 ≤1.1s worst
stream), not P1-01-grade degradation. Therefore PASS: transport is healthy
enough for the P1-10 ≥6h soak. `docs/PHASE_1_REPORT.md` untouched.

## P1-10 prolonged soak — RESULT: FAIL, truncated at 4.91h (2026-10-07)

Run: `python -u -m microstructure_probe --duration 21600` (requested
21600s), BOT_MODE=observe, started 2026-10-07 05:15:41 local. Evidence
(local, git-ignored): `logs/p1-10/probe-21600s.log` (52MB, UTF-16 —
PowerShell stdout-redirect capture, long JSON lines wrapped; reconstructed
by rejoining wrapped fragments, proven by 0 runtime drops). No
checkpoint/final-summary sidecar files were written; all metrics below come
from the 554 periodic summaries (every ~30–32s) parsed out of the raw log.

Continuity: ONE process (`startup` × 1, no restart). Last periodic summary
`runtimeSeconds: 17677.917` (81.8% of 21600); log wall span 05:15:41 →
10:10:37 (~17696s); NO `final_summary`; tail ends mid-stream on detector
lines with no shutdown/traceback and the process is gone — externally
killed between summaries, exit code UNKNOWN. Max inter-summary gap 62s, no
gap >120s: no evidence gap *within* the run, but the run itself is
truncated. Duration gate (≥21600s continuous) NOT met → FAIL per
docs/SUCCESS_GATES procedure (duration invalid). Dashboard was NOT
restarted (PID 7564, v0.8.0, uptime 63283s spanning the whole run).

Full-window (END, rt=17677.9s) transport:
- Coverage 11/11, missing [], stale [], silent `!forceOrder@arr` only
  (event-driven, correct). Uptime market 99.65% (17613.6s), public 97.08%.
- Reconnects 43 total (public 38, market 5); attempts 45 (public 39,
  market 6); websocket errors 43 (= reconnects). Jump +29 reconnects in the
  final 55 min (14 → 43) — closing-phase reconnect storm, nearly all public.
- Messages 15,341,473. bookTicker p50 ~190–200ms / p95 ~321–465ms
  (HEALTHY, P1-01R-grade); depth p50 ~182ms but p95 ~45–47s; aggTrade SPLIT:
  BTC p50 214ms vs ETH p50 152s / SOL p50 90s (P1-01-grade); markPrice p50
  253ms but p95 132s; forceOrder p50 205ms–1.2s, p95 ~158–159s; max ~265s.
  Exchange-side E−T stays milliseconds (bookTicker p50 0–1ms), so the delay
  is delivery-path, not Binance. Mixed verdict: bookTicker core stayed
  P1-01R-grade while aggTrade (ETH/SOL), depth-tail, markPrice-tail and the
  final hour regressed to P1-01-grade. Prolonged stalls: max observed
  silence 51–133s incl. 132.5s on cadenced bookTicker/depth — real stall
  episodes, not sampling noise.
- Skew guard: `timestampRejected: 742182` (~4.8% of messages; rejects by
  stream worst on bookTicker/aggTrade). Far better than P1-01's 85%, worse
  than P1-01R's 0%. +366k rejects landed in the final 55 min (376k → 742k).
- Depth gaps 33/32/32 (reconnect-driven, all recovered, `degraded: false`
  at END, crossed books 0 — final book integrity HEALTHY).
- Clock 30/30 syncs ok (150/150 samples), offset −413ms at END, RTT
  338ms; full-run offsets min −1001.6 / max +47.1 / median −241.6ms, RTT
  319.6–376.2ms (median 336.3). One ~1050ms offset discontinuity between
  sync 6 (−1001.6) and sync 7 (+47.1), then steady drift to −413 — sync
  never failed, recorded as drift, not a gate break.
- Processing sub-ms typical (parse/detector/metrics p50 ≤0.03ms); isolated
  max spikes (941ms bookTicker metrics, 1660ms SOL aggTrade processing,
  1098ms markPrice) with all engine queues 0/0 — absorbed, no backlog.

Engines (all alive at END, 0 invalid / 0 late everywhere):
- Returns: 1867 samples/symbol over 58,830,000ms span (16.34h incl.
  restored history), 0 invalid, 0 late. 1m/3m/5m/15m/1h/4h mature; 24h
  partial (16.34h/24h, honest).
- Flow: 502,191 events (BTC 222513 / ETH 228183 / SOL 51495 trades),
  latency p50 0.017ms / p95 0.085 / max 64.6, queue 0/0, 2103 completed
  10s-buckets/symbol (~5.8h live) — 15m maturity + volume baselines mature.
- Book: 388,570 msgs (130853/131465/126252), p50 0.19ms / p95 0.33,
  gaps 33/32/32 all recovered, crossed 0, integrity HEALTHY.
- OI: 813/813 polls ok (0 failures), latency p50 341ms / p95 3028 /
  max 10190 (slow polls absorbed); tracker 332 samples/symbol (271 total);
  1m/5m/15m + acceleration mature.
- Structure: 1659 evals, p50 5.9ms / p95 10.2, queue 0/0; pivots/HH-LH/
  HL-LL/breakout/range all evaluating (maturity inherited from 16.34h span).
- VWAP 1m/3m/5m/15m + volatility 1m/5m/15m/1h available (zero stays 0.0,
  distinct from unknown, per P1-08 contract).

Discovery/HOT (proposal/discovery only — no WS resubscribe, trio intact):
30 scans (600s cadence × 4.91h), seen 924 constant, eligible 486 → 496.
HOT 6-slot rotation with vote/dwell hysteresis working (26 promote/demote
events embedded in scan records; END set: AIN/MINA/AIOT/RLC/CAP/龙虾USDT;
earlier windows held NMR/GRIFFAIN/LYN/PHA — rotation, not flapping).

Dashboard long-run: all routes 200 during post-mortem
(`/overview` 49.6ms, `/movers` 12ms, `/system` 6.4ms, token pages 9–22ms,
`/api/health` 21.5ms, `/api/snapshot` 3.7ms, search 7.2ms). Health `stale`
honestly (snapshot 22520s old — probe dead, expected); was `ok`-while-fed
per 749 persisted snapshots. 9/9 movers categories render; discovery-only
honesty holds (AINUSDT page: DISCOVERY ONLY + NO LIVE DEEP FEATURES).
Chart: 4h MATURED during soak (16.34h span); 24h PARTIAL (16.34h/24h,
capped 1000 pts, restored-history dependent). Post-mortem trailing-4h
query returns 0 pts — honest staleness artifact (feed 6.25h old), not a bug.
Movers anomaly CONFIRMED by code inspection (`dashboard_views.py`
movers section: shared per-row `_v` overwritten by each later category
loop, so a symbol in several categories shows the last-assigned value in
every table — velocity/accel/vol-z/flow scales mixed). Recorded as a
P1-11A audit item; NOT fixed during closure.

Persistence (DB `data/microprobe.db`, schema v6, ~197MB at END; start size
not captured — unavailable, not guessed): snapshots 749 (cap 1000, holds;
min rt 32.19 / max rt 17677.917 — this run's 554 + prior runs retained),
observations 10000 (cap holds), rejections 1000 (cap holds), price_samples
5601 (16.34h span), flow_buckets 4710 bounded (600/597/304/69 per
size/symbol), oi_samples 996, return/flow/book/OI/structure features 3
each (REPLACE latest-only), discovery snapshot 1 (REPLACE), universe_events
46 (cap 500), rank snapshots 3. Write errors 0, lock errors 0, no snapshot
starvation (dedicated writer held), persistence inflight high-water 5063 →
final 0, drained to 0. Sampling gate intact (accepted 34k/40k/39k vs
dropped 468k/13.6M/349k aggTrade/bookTicker/depth; markPrice/forceOrder
ungated and fully ingested).

Resources: RSS/CPU NOT captured by the probe (UNAVAILABLE — do not infer
from DB size). Backpressure bounded everywhere (engine queues 0/0,
inflight 0, dashboard ms-grade post-mortem).

Errors (full 4.91h): websocket 43 (38 public + 5 market) CONCERNING in the
final hour (storm) / RECOVERED earlier; parse 0, payload 0, invalid engine
events 0, late events 0; timestamp rejects 742182 (~4.8%) CONCERNING
(final-hour concentration); persistence errors 0; SQLite errors 0; OI REST
failures 0/813; depth gaps 97 total, all recovered (RECOVERED); dashboard
HTTP errors 0 (post-mortem 200s); reconnects 43 CONCERNING. None BLOCKING
except the duration gate itself.

Detectors (telemetry only, NOT signals): `extreme_funding_rate` 16512 log
lines (crossings BTC 5417 / ETH 4960 / SOL 6095 — near-constant series:
175–176 valueChanges over 13519 samples; same hypothesis-artifact class,
no conclusions); `large_liquidation_individual` 25 (all SELL: 8/12/5);
`large_liquidation_window` 8 (1/4/3); `volume_spike` 102 (36/35/31). No
threshold tuned.

Safety: BOT_MODE=observe in startup + all 554 summaries; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, cancels 0, leverage changes
0, private/account endpoints 0, capital at risk 0, order paths absent
(static test green). NO VIOLATION.

Checkpoints (reconnects / rejects / msgs / gaps / flow / HOT):
START rt32: 0 / 0 / 16k / 0s / 349 / [] → T+1h: 6 / 125k / 3.07M / 3s /
108895 / 5 HOT → T+2h: 10 / 231k / 5.90M / 7s / 192706 / 6 HOT → T+3h:
10 / 231k (flat — healthy middle third) / 9.20M / 7s / 292131 → T+4h:
14 / 376k / 12.51M / 11s / 409250 → END rt17678: 43 / 742k / 15.34M /
33s / 502191. Drift story: healthy middle (T+2h→T+3h: 0 new reconnects,
0 new rejects over 3600s), degraded bookends, collapsing final hour.

Verdict reasoning: gate A (one continuous run ≥21600s) fails — 17677.9s
is the proven maximum, no final_summary, unclean externally-killed exit.
Per the closure rubric FAIL is forced ("duration invalid"); PARTIAL does
not apply (the run did not complete). Safety is clean, engines/persistence
/dashboard all behaved, but transport showed sustained P1-01-grade episodes
(aggTrade ETH/SOL p50 90–152s, final-hour storm). The 4.91h of evidence is
VALID for P1-11 raw-feature auditing (monotonic, gap-free summaries), but
P1-10 itself must be re-run (P1-10R) with a survivable launch before any
gate may pass. `docs/PHASE_1_REPORT.md` untouched.

## P1-11A raw feature + Movers integrity audit — RESULT: PASS (2026-10-07)

Used the valid P1-10 4.91h evidence (554 gap-free summaries, 15.34M msgs;
P1-10 stays FAIL on duration — not marked PASS). Baseline before work:
312/312 PASS. No strategy/backfill/classifier/subscription/signal/paper
work started.

Movers bug — FOUND, ROOT-CAUSED, FIXED NARROWLY: `render_movers`
(`dashboard_views.py`) shared one per-row `_v` across all 9 category loops
(last write won: symbols in several tables showed e.g. the flow value in
the gainers table). Source→render audited per category (DISCOVERY: 24h
gainers/losers → `change_24h_pct` sorted by signed 24h %, shown `+%.2f%%`;
quote-volume leaders → `quote_volume_24h`; HOT → "proposed". LIVE,
subscribed-only: velocity ± → `velocity_1m` (`%.3g/s`); acceleration →
`accel_1m` (`%.3g/s²`, sorted by |accel|); volume expansion →
`vol_z_1m` (`%+.2f z`); aggressive-flow → `flow_delta` (`%+.2f`, sorted by
|delta|)). Fix: per-category display keys passed to the renderer; sources,
sorts, units, formatters unchanged. Proven: new `MoversIntegrityTest`
(5 tests, unique fixtures) fails 4/5 on old code, passes 5/5 fixed.

Feature verdicts (END-state rows + START/END summaries; full scales in
`docs/FEATURE_MODEL.md`): returns 1m/3m/5m/4h live with sane log scales
(15m/1h/24h honestly UNKNOWN after the degraded finale); velocity/accel
scales 1e-6–1e-5 /s and 1e-7–1e-8 /s² with correct warming gates; flow all
6 horizons + baselines + accel present (ratios in [−1,+1], units USD
notional, BTC>ETH>SOL ordering); book spreads 0.012–0.86bps, imbalances in
[−1,+1], 0 crossed, gaps recovered; OI base-unit units verified with mixed
horizon signs and coherent anchors; VWAP ±4.6bps; vol warmed flags honest
(UNKNOWN ≠ 0); range positions in [0,1]; structure evaluating on 16.34h
span. No impossible values, no unit mismatches, no malformed transitions.
Funding crossings re-confirmed artifact-class (near-constant series).

Transport impact (healthy T+2h→T+3h vs degraded T+4h→END): 918 msg/s 0%
rejects 0 reconnects 0 gaps vs 867 msg/s 12.9% rejects 29 reconnects 64
gaps. Feature effect: returns span still grew (+360 vs +129 samples); flow
−6.5%; book ingest −64% (depth starved, integrity HEALTHY); structure
−19%; OI ISOLATED (0 failures both). Degradation starves honestly, never
corrupts — classifiers must take UNKNOWN/staleness as first-class input.

Design-only plans added (nothing implemented): BTC context + relative/
correlation/beta/lead-lag, exhaustion/absorption research, opportunity
lifecycle, backtest/paper sim costs (`docs/SIGNAL_RESEARCH_PLAN.md`);
P1-11B resolutions + P1-11C event studies with MFE/MAE/no-lookahead
(`docs/HISTORICAL_RESEARCH_PLAN.md`); roadmap P1-11A→…→P1-16 in TASK_QUEUE.
Tests after: 317/317 (312 + 5 new). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B historical data foundation — RESULT: PASS (2026-10-07)

Official docs first: developers.binance.com unfetchable here (empty
responses, same as P1-05) → all seven contracts verified LIVE against
fapi.binance.com (public, no keys, ~35 tiny requests) + OpenAPI enum
cross-check; recorded exactly in `docs/MARKET_DATA.md` (params, limits
1500/500/1000, weights measured ~1/1/20, intervals, startTime/endTime
edge behavior, 2400/min pool).

Built (stdlib only): `history_client.py` (conservative weights + adaptive
weight-header hard pause 2000/2400; retries budget 5 exp-backoff+jitter;
429 honors Retry-After budget 2 then abort; 418 aborts; forward pagination
with overlap-raise + skip-record; OI timestamp pagination; aggTrades fromId
helper) + `history_store.py` (separate `data/historical/historical.db`,
schema v1: klines WITH volume / mark klines WITHOUT volume columns /
OI as-served / coverage / run ledger / gaps) + `history.py` CLI (status /
fetch / verify; explicit symbols, 7d/25 defaults, no bulk mode).
Listing-aware (geneses recorded: BTC Sep-2019, MINA Feb-2023, ORCA
Dec-2024); CLOSED candles only; gaps stay UNKNOWN/GAP (no fill).

Pilot (bounded): 1h×30d klines ×5 syms (719 each), 15m×30d ×3 (2879),
1m×3d BTC (4319), 1h×30d mark ×3 (719) — all ratio 1.0, 0 gaps, 0 malformed;
5m×7d OI BTC hit the 500-row availability cap (~41.6h — documented
limitation); aggTrades confirmed recent-only (0.1 min). Resume re-run: 0
rows, 1 request (idempotent). 13 series stored. No backfill beyond pilot.

Minimal exposure: `/api/history/status` + `/api/history/:symbol`
(404-empty/unknown, 400-malformed) + HISTORICAL COVERAGE token card; no
Opportunities/Signals/Paper/Backtest UI. Storage tiers + prospective
flow/book retention + fidelity contract in HISTORICAL_RESEARCH_PLAN.md /
FEATURE_MODEL.md. Tests after: 353/353 (322 + 31 new mocked-HTTP history
tests). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B.1 probe lifecycle + dashboard run control — RESULT: PASS (2026-10-07)

Canonical manager `control.py` (registry `logs/probe_runtime.json` with
pid/ctime/started/mode/duration/expected-end/launcher/preset/evidence/
last-exit; CLI status/start/stop). Probe self-registers on EVERY direct
launch (`__main__`; refuses with exit 2 when another probe holds the
registry; COMPLETED/FAILED/STOPPED marked on exit; registry failures never
break collection). Single-instance refusal; stale-PID recovery to FAILED;
stop kills only the verified PID (bounded 10s wait). All control-started
probes get merged UTF-8 file logs (`logs/probe-runs/`, validation preset
`logs/p1-10r/`). Dashboard: `GET /api/control/probe/status` (process +
feed separated) + POST-only start/stop (localhost Host + local Origin +
per-process nonce; GET mutations 405; fixed argv, BOT_MODE forced observe,
no shell) + MARKET ENGINE header block on all pages (no `<button>`, 4s
polling, green/gray/amber/red). Modes: Continuous, 6 Hours, 6H Validation
(evidence mechanics — NOT an automatic P1-10R PASS).

Live-verified (short bounded only, no 6h started): dashboard START →
RUNNING PID 16336 (tasklist-confirmed) → feed STALE→ok honestly →
dashboard STOP killed only the probe (dashboard survived); external CLI
start (--duration 90/75) auto-discovered as RUNNING/launcher=agent in UI;
90s run self-marked COMPLETED duration-reached; CLI stop → STOPPED.
Tests after: 376/376 (353 + 23 new mocked lifecycle/API tests).
`docs/PHASE_1_REPORT.md` untouched.

## P1-11C historical event studies + prospective capture — RESULT: PASS (2026-10-07)

- Engine (`events.py`, NEW, research-only, no signals): formation uses
  bars with open_time <= T only; outcomes use open_time > T only (proven
  by no-lookahead tests incl. poisoned-future reruns). Reference price =
  closed bar close at/preceding T, labeled mark_close vs regular_close
  (never silently mixed). Fixed horizons 1m/3m/5m/15m/30m/1h; LONG-up
  MFE/MAE + SHORT-down mirror; time_to_MFE/MAE; predeclared invalidation
  only; path COMPLETE/PARTIAL/INVALID_GAP/INSUFFICIENT_HISTORY (never
  filled); formation/outcome gap exclusions; BTC synchronized lookup +
  relative_return = token − BTC; 30d as-of levels; HISTORICAL_TAKER_BUY_
  PROXY + ABSORPTION_PROXY labels; sample tiers
  INSUFFICIENT/EXPLORATORY/PRELIMINARY/LARGER_SAMPLE (quantity only).
- Definitions: 6 versioned HYPOTHESIS families (EXTENDED_GAINER/LOSER,
  MOMENTUM_ACCELERATION_UP/DOWN as HISTORICAL_MOMENTUM_PROXY, FAILED_
  HIGH/LOW_CANDIDATE); changing a threshold creates a new version; runs
  recorded with params/symbols/ranges/sources (deterministic reruns).
- Storage: historical DB schema v2 (additive over v1): event_definitions,
  event_study_runs, event_instances, event_feature_snapshots,
  event_outcomes + research_flow_10s/1m + research_book_1m (idempotent
  keys; retention cleanup batched/hourly, never per-tick).
- Recorder (`research_recorder.py`, NEW, probe-owned): starts with
  MarketProbe, drains (partials marked) on exit; same process/registry/
  launcher — no second manager. Bounded queue (drops counted, engine
  never stalls); DB failures degrade the recorder only (probe survives,
  tested). Flow semantics reuse validated P1-06 m-mapping read-only.
  Retention 7d/90d/90d configurable; measured estimate ~200B/row →
  ~66KB/day/symbol flow-10s + ~288KB/day/symbol each 1m table (~35MB for
  15 symbols at full retention).
- Live verification (canonical control plane, 150s → COMPLETED
  duration-reached, evidence `logs/probe-runs/probe-20261007T224304Z.log`):
  runtime 153.15s, flow 1722 events, book 4042 msgs, research writes 60
  (flow_10s 45 + flow_1m 9 + book_1m 6 rows), drops 0, errors 0,
  inflight 0, high_water 2, final_summary present. Dashboard restarted
  (PID 30984): /api/research/status + /api/events/studies +
  /api/events/studies/:def + /api/events/symbol/:sym all 200; control
  status/start/stop/external-detection intact; 6H-Validation preset
  verified compatible (forces 21600s, same registry/evidence path —
  NOT started).
- Pilot (bounded, stored bars only): 38 runs — 1h × (BTC/ETH/SOL/MINA/
  ORCA/NMR) × 6 families + 15m × trio GAINER/LOSER. NMR added by a
  justified 2-request extension (719 bars, ratio 1.0, ~144KB). Counts:
  GAINER 168 usable (mean fwd −0.04bps), LOSER 67 (−25.8bps), ACCEL_UP
  1170/1203 (+8.7bps), ACCEL_DOWN 1147/1184 (+4.4bps), FAILED_HIGH 18/19,
  FAILED_LOW 8/10. Sub-1h horizons on 1h bars share the next-bar outcome
  (resolution limitation, documented). No profitability/edge claim; small
  samples flagged INSUFFICIENT/EXPLORATORY.
- Tests: 408/408 (376 + 32 new: 18 events incl. no-lookahead/MFE-MAE/
  gaps/BTC/relativity/as-of/proxy/versioning/idempotency/no-autotune +
  14 recorder incl. buckets/quality/retention/queue-drops/isolation/
  lifecycle/no-second-process). `docs/PHASE_1_REPORT.md` untouched.

## P1-10R formal ≥6h soak re-run — RESULT: PASS (2026-10-08)

Run: ONE continuous WMI-detached process (PID 19084; parent chain
python → cmd → WmiPrvSE Session 0, independent of all agent shells),
`--duration 21600`, preset validation-6h, launcher
scheduler-6h-validation, BOT_MODE=observe. Started 2026-10-08T00:48:20Z,
final summary 2026-10-08T06:48:23Z: **21603.9s ≥ 21600s**. Registry
COMPLETED + duration-reached + exit 0; process exited (no orphan); 1
startup; 699 periodic summaries, max inter-summary gap 49.7s, 0 gaps
>120s. Evidence (local, git-ignored):
`logs/p1-10r/probe-20261008T0048Z.log` (33.3MB merged UTF-8) +
`logs/p1-10r/P1-10R_HANDOFF.md`. No app-code changes during the run
(proven: empty `git log` on src/tests/config since launch baseline).

Transport (vs P1-01R healthy precedent and P1-10 degraded finale):
- Coverage 11/11 all 6h, missing [], stale []. 19,004,903 messages
  (bookTicker 17.77M, depth 590k, aggTrade 595k, markPrice 42k,
  forceOrder 8.8k).
- Reconnects 10 total (public 4 × ConnectionClosed, market 6: 1
  ConnectionClosed + 5 opening-handshake TimeoutErrors with 2→30s
  backoff); attempts 12, parse 0, payload 0.
- Skew-rejects 143,624 (0.76%); uptime market 99.10% (21406s),
  public 99.95%.
- Corrected delivery lag p50 ~170–250ms every stream (P1-01R-grade);
  p95 sub-second except sparse forceOrder; p99 ≤0.66s (forceOrder
  excluded: event-driven). Rare single-message max outliers (~311–510s)
  with steady neighboring throughput — isolated, not episodes.
- Episodes (all auto-recovered, none hidden in averages): ~01:29–01:32Z
  (public reconnect, ~24k rejects); ~02:31–02:35Z (public reconnect,
  ~37k rejects); ~04:20–04:29Z (~9.5min: market handshake timeouts,
  6 market + 1 public reconnects, ~82k rejects, market-stream silence
  ≤192s). Final hour rt 18007→21590: 0 reconnects, 0 rejects, 3.07M
  msgs — NO P1-10-style final-hour collapse.
- Depth gaps 5/5/5 total (reconnect-driven), all recovered
  (degraded=false, crossed 0 at END). Clock 36/36 syncs ok, 0 failures
  (offset −582ms → −208ms, RTT ~343ms).

Engines (all monotonic, 0 invalid / 0 late everywhere): returns 3886
samples/symbol over 31.5h span (restored + live); flow 566,244 events;
book 587,330 msgs; OI 1029/1029 polls ok (p50 347ms, slow polls
absorbed); discovery 36 scans (924 seen → 467 eligible, HOT 6 with
hysteresis); structure evaluating (symbols_evaluated). Detectors are
telemetry only: 22622 funding crossings (same hypothesis-artifact
class), 11 individual + 1 window liquidations, 181 volume spikes — no
threshold conclusions.

Research recorder (P1-11C validation): RUNNING all 6h → drained STOPPED;
writes 8273, drops 0, errors 0, inflight 0, high-water 6. Rows added:
flow_10s +6191 (vs ~6480 est, 95.5%), flow_1m +1041 (~96%), book_1m
+1041 (~96%) — shortfall is the documented stall episode plus edge
partials, no unexplained loss. Historical DB +1.58MB (16.47 → 18.05MB),
integrity ok; operational DB 206.9 → 238.9MB (retention caps hold:
snapshots at 1000), integrity ok; persistence errors 0, locks 0.

Dashboard: alive throughout and after (PID 30984); feed/health states
independent and truthful (STALE chip after completion is honest — last
snapshot is the 06:48:23Z final). No phantom RUNNING. The known
tasklist/wmic popup defect (P1-10R-FIX-01) stayed cosmetic: 2 spawns
per 4s poll, negligible overhead, no evidence impact; fix deferred to a
separate post-soak change (CREATE_NO_WINDOW), NOT applied here.

Safety: BOT_MODE=observe in startup + final; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, capital 0, no order
paths (static tests green). NO VIOLATION.

P1-10 failure mode eliminated: the old run died externally at 4.91h
with an unhealthy finale; P1-10R survived its full window in a
session-independent process AND its worst transport episode (~9.5min)
self-recovered with 3.5 clean hours after it.

## P1-10R-FIX-01 console-popup fix — APPLIED (2026-10-08, post-PASS)

Root cause (confirmed earlier): every 4s browser poll of
`/api/control/probe/status` ran `dashboard.process_info()` →
`subprocess.run(tasklist)` + `subprocess.run(wmic)` with no
`CREATE_NO_WINDOW`, flashing visible consoles; probe launches via
`control.start_probe` had the same gap. Fix: new
`dashboard.no_window_flags()` helper (CREATE_NO_WINDOW on Windows, 0
elsewhere — POSIX unchanged) applied to both `process_info` calls and
the `start_probe` Popen. Identity semantics untouched (image +
creation-time checks, honest UNKNOWN on failure). Verified: 420/420
tests (12 new, mocked — no real consoles opened); dashboard restarted
(PID 30984 → 28440, no probe active at the time); 75s observe-only
lifecycle via the canonical plane went STARTING → RUNNING (feed
HEALTHY) → COMPLETED naturally; /overview /movers /system 200;
Next.js :3000 unaffected. Popup suppression is proven at code level
(flags asserted in tests); headless agents cannot visually confirm
flash absence — user-side confirmation still welcome. P1-10R PASS and
P1-12 READINESS unchanged.

## P1-12A market state classifier v0 — RESULT: PASS (2026-10-08)

Deterministic explainable classifier (`classifier.py`, rules v0.1.0,
all-HYPOTHESIS): NORMAL / IGNITION / EXPANSION / EXHAUSTION / REVERSAL +
UNKNOWN (missing/stale/discovery-only), directions UP/DOWN/NONE/UNKNOWN.
Every record carries symbol, state, direction, observed_at_ms,
features_used, evidence_for/against, missing_features, validity,
rules_version, and transition {previous, changed, since, duration,
reasons}. No probabilities, no LONG/SHORT wording, no entries — observed
states only. Priority REVERSAL > EXHAUSTION > EXPANSION > IGNITION >
NORMAL with contradictions stored, never hidden; hysteresis holds
energetic states 2 evals (UNKNOWN exits at once); REVERSAL needs 2
consecutive confirmations; no forced sequence; memory restarts cold and
says so. Inputs are the already-built peer-engine rows (returns +
momentum, 1m flow, book imbalance, 1m OI, 15m range/structure/vol) —
no new ingest/endpoint, no lookahead possible by construction.

Persistence schema v7 (additive, tested v1..v6→v7 with rows preserved):
`state_features` REPLACE/symbol + `state_transitions` append ≤500.
Probe evaluates once per ~30s summary (measured 0.16–0.20ms/batch —
negligible) and logs real transitions; summary carries a `states`
census block. Dashboard: token-page "Market state v0" panel
(state/direction/as-of/rules/previous/reasons/features/missing/validity)
with honest discovery-only/warming notes — no new HTTP contract, no
Next.js changes.

Validation: 25 deterministic fixture tests (all states × directions,
UNKNOWN paths, contradictions, transitions, hysteresis, gaps, cold
restart, no-lookahead incl. future-key injection, timestamps,
discovery-only, serialization, determinism). Controlled 120s
observe-only run via canonical plane COMPLETED naturally: 9 evaluations
(3 symbols × 3 summaries), states + 4 transitions persisted (incl.
BTC NORMAL→REVERSAL with flip evidence), token pages render the panel,
0 rejects, 0 reconnects, 0 orders, both frontends 200. No predictive
accuracy claimed (prospective evaluation is P1-14 territory).

## P1-12B dynamic live universe v0 — RESULT: PASS (2026-10-08)

Bounded HOT selection + lifecycle (`universe_manager.py`, v0, pure
deterministic logic): DISCOVERY_ONLY → PROMOTION_PENDING → SUBSCRIBING →
WARMING → LIVE (DEGRADED on silent streams) with DEMOTION_PENDING →
UNSUBSCRIBING → UNKNOWN + cooldowns. Ranked proposals from existing
`select_hot` votes (no classifier input — no circularity); eligibility +
ticker freshness + slot/stream budgets + transport health gate every
promotion; 1800s LIVE dwell, 3600s demotion cooldown, 2-missed-scan rank
decay, ineligibility bypasses dwell (proven breach), CORE never evicted
or shadowed. Budgets (fail-closed, conservative local policy — official
WS docs unfetchable here, all caps UNVERIFIED): 3 HOT slots, 60 total
streams, 50/connection, 6 connections; actual footprint 4 connections /
≤26 streams. HOT rides `hot-public` (bookTicker+depth) + `hot-market`
(aggTrade); global markPrice/forceOrder arrays never duplicated.
`_connection_loop` accepts a URL callable so reconnects restore exactly
the desired set; resync (cancel exactly the 2 managed tasks + respawn)
fires only on desired-set change with a 60s anti-flap guard; canonical
pair never touched. Engines gained allow/forget (flow/book/returns/
structure/classifier/OI tracker) + OI poller HOT list (≤8 polls/round);
recorder finalizes demoted symbols as explicit PARTIAL (idempotent keys);
markPrice returns ingest extends to subscribed HOT (funding detector
stays CORE-configured). Dashboard overview distinguishes proposals
(`HOT dynamic`) from subscriptions (`HOT subscribed (deep)`) + lifecycle
table + hot_* events; Token Detail opens HOT symbols via live sets.
No schema migration (discovery snapshot blob extended in place).

Validation: 31 tests (manager + probe sync + recorder + classifier +
config + safety surface); full suite 478/478. Controlled 300s
observe-only run (temp 60s-scan config, repo config untouched)
COMPLETED naturally: 465 eligible → 6 proposals → 3 promotions
(OGNUSDT/METUSDT/GRIFFAINUSDT), both HOT connections up, all 3 LIVE
(mark+trade+depth), 0 demotions/failures/refusals, 0 reconnects,
0 rejects, 259k msgs, HOT research buckets 24/4/3 per symbol,
6 symbols classified, safety 0/0/0. Dashboard verified live
(subscribed row, lifecycle table, OGN token panel).

## P1-12B.1 dynamic universe integrity audit — RESULT: PASS (2026-10-08)

Independent review of P1-12B raised two concerns; both reproduced, both
fixed minimally with no architecture change:

A. Candidate freshness (CONFIRMED): `ticker_close_ms=None` promoted,
future timestamps passed the one-sided comparison, and malformed values
aborted the whole update. Fix: per-candidate fail-closed
`check_timestamp_fresh()` (missing/malformed/implausible-unit/too-old/
too-future reject with reasons; ≤60s future skew tolerated and
documented). Upstream passes None through, so the manager gate is the
enforcement point; trusted clock is local wall time.

B. Stream accounting (CONFIRMED, conservative direction): `+2`
connections leaked into a stream total, and reports claimed `17
canonical` vs measured **11** (9 per-symbol + 2 global arrays). Fix:
single authoritative `account_streams()` shared by enforcement and
telemetry (connections and streams separate units; globals counted
once). No over-budget promotion ever occurred (errors over-counted).

Provider docs re-fetched 2026-10-08: empty again — all caps stay
UNVERIFIED/LOCAL_POLICY, nothing raised. Validation: 18 new tests;
full suite 496/496; 240s observe run COMPLETED (3 promotions AIOT/MET/
OGNUSDT all LIVE, 0 staleness skips — real closeTime is fresh ms,
400k msgs, 0 reconnects/rejects, 6 symbols classified, safety clean);
dashboard shows subscribed row + lifecycle + token panels; Next.js
unaffected. P1-12B PASS record stands (append-only correction).

## Known gaps (Phase 1 work ahead, in order)

Minimal dashboard: DONE (P1-03 PASS) → terminal DONE (P1-09 PASS,
v0.8.0 live at http://127.0.0.1:8091).
Returns engine: DONE (P1-04 PASS — universe + 7-TF mark-price log returns).
Discovery + velocity/acceleration/ranking: DONE (P1-05 PASS — 449-eligible
scan, 6-HOT proposal, live momentum + ranks, intel UI + APIs).
Movers integrity + raw-feature validation: DONE (P1-11A PASS — per-category
display keys, 5 regression tests, all families measured trustworthy).
Volume + aggressive flow: DONE (P1-06 PASS — 6-horizon flow, baselines,
acceleration, v0.5.0 dashboard + APIs, healthy 363s validation).
Order book + open interest: DONE (P1-07 PASS — snapshot book intel, OI
polls/deltas/contexts, v0.6.0 dashboard + APIs, 363s validation).
VWAP + volatility + structure: DONE (P1-08 PASS — flow-VWAP, raw vol,
range expansion, confirmed pivots, v0.7.0 dashboard + APIs, 372s run).
Transport re-validation: DONE (P1-01R PASS — 45min healthy window, soak
gate unblocked).
Remaining: P1-13A opportunity/setup engine (NEXT candidate — needs explicit
instruction), then P1-13B UX, calibration (P1-14).
Decision/feature traceability for these lives in `docs/FEATURE_BACKLOG.md`
(F-UNI-01, F-OPP-01/UI-01, F-BT-01, F-PAPER-01, F-PORT-01). P1-11 raw-feature validation may use the valid
4.91h P1-10 evidence; the Movers shared-`_v` category-value anomaly is a
recorded P1-11A audit item (not fixed).

## Blockers / issues

- P1-10 FAIL (2026-10-07): soak killed externally at 4.91h/6h (17677.9s),
  no final_summary, exit unknown. P1-10R re-run required before any soak
  gate passes; launch must survive the full window (see DECISIONS) and
  capture merged stdout+stderr as UTF-8 (the P1-10 UTF-16 PowerShell `>`
  capture wrapped every long JSON line and had to be reconstructed).
- Transport was flaky in this environment (P1-01 PARTIAL: 58 reconnects,
  85% rejects), but P1-01R (45min, 0 reconnects, 0% rejects, sub-second
  lags) now PASSES the soak gate. If a future run shows P1-01-grade
  degradation again, re-validate before trusting soak/calibration gates.
- Detached probe processes die with the harness tool session (observed twice):
  use blocking bounded runs for evidence windows.
- Dashboard RUNNING at http://127.0.0.1:8091 (PID 7564, v0.8.0; read-only,
  localhost — safe to keep). Snapshot goes STALE without a running probe
  feed (honest chip); continuous freshness arrives with the P1-10 soak.
- No secrets, keys, or account access exist or are needed.

## P1-14A prospective setup evaluation V0 — RESULT: PASS (2026-10-08)

Forward outcome observation for P1-13A setups. Registers candidates at first DETECTED
and evaluates mark-price returns at versioned horizons (1m/5m/15m/1h/4h).
Research only — no P&L, no lookahead, no probabilities.

- Module: `src/microstructure_probe/prospective.py` (`ProspectiveRecorder`).
  Idempotent, restart-safe, bounded queue (default 1000), drops telemetry.
- Horizons: 1m/5m/15m/1h/4h (ms). Maturity checked strictly after
  `detected_at_ms + horizon_ms` — no lookahead.
- Outcome states: COMPLETE / PENDING / INSUFFICIENT_HISTORY /
  INVALID_GAP / PARTIAL. Missing ≠ zero; incomplete never forced COMPLETE.
- Persistence schema v9 (additive): `prospective_setups` (REPLACE per key)
  + `prospective_outcomes` (append-only, unique (key, horizon, observed_at_ms),
  rolling 500 per setup). Migration chains v1–v9 all upgraded.
- Retention cleanup: `research_retention_cleanup(days)` — hourly max,
  default 90 days for both tables.
- Probe integration: registers in opportunity cycle (DETECTED + evals<=1),
  observes with current mark_price at summary tick. State exposed in
  `snapshot()["prospective"]`.
- Dashboard: `/api/prospective` (schema_version 9, RESEARCH ONLY banner,
  live status + latest 10 outcomes).
- Fabrication guards: no MFE/MAE, no win-rate, no "X% probability"
  patterns; interpretation says "research priority only — NOT expected profit".
- Tests: 35 tests in `tests/test_prospective.py` — all pass.
  Full suite: 554/554 OK (519 baseline + 35 new).

## P1-14B prospective integrity validation (recovery) — RESULT: PASS (2026-10-09)

Recovery of the interrupted P1-14B session on branch
`phase1/market-intelligence-dashboard` at SHA `e727e54`; workspace recovered,
evidence preserved, no data loss. Validation of P1-14A prospective evaluation
integrity against deterministic tests and real persisted evidence:
event-time maturity, no-lookahead, dedup, restart idempotency, v8→v9 migration,
90-day retention + bounded 500-outcome log, quality flags without fabrication,
dashboard `/api/prospective` parity, observe-only safety. Full suite **593/593**
OK (519 + 35 + 39 `tests/test_p14b_validation.py`).

- Two session fixes accepted into the working tree:
  `prospective.py:106` rehydrates `setup.get("setup_json", {})` so restarted
  registries carry `detected_mark_price` (recompute COMPLETE, not
  INSUFFICIENT_HISTORY); `dashboard.py:403` reads the injected shared store
  so `/api/prospective` mirrors the recorder (parity).
- Real evidence in `data/microprobe.db` (schema v9): 7 unique registered setups
  (event time 2026-10-08 23:42:04 → 24:06:30), 1 observed outcome
  (`REVERSAL_WATCH:ETHUSDT:UP` → 1m, COMPLETE, mark_return_pct=-0.037134,
  detected 2477.50 → current 2476.58). Event-time audit PASS on every record;
  zero duplicates; zero PENDING/INVALID/INSUFFICIENT rows (unobserved horizons
  are absent, never fabricated).
- Pilot preserved: `p14b_pilot_monitor.py` (+`logs/p14b_pilot.log`) — 150s
  observe-only run with DB polling and event-time vs wall-clock audit;
  `p14b_dashboard_readtest.py` — dashboard read-path validation;
  `.firecrawl/*.json` market-data dumps preserved.
- API verified locally: `/api/prospective` returns schema_version 9,
  RESEARCH ONLY banner, setup_count=7, outcome_count=1, full denominator in
  latest_outcomes; `state` = UNKNOWN honestly reflects no live probe.
- Limitations (honest): single outcome is descriptive only (-0.037134%);
  6/7 setups lack observed horizons because the pilot window's event time did
  not reach their 5m/15m/1h/4h maturities — absent, not forced. The pilot
  suffered host clock anomalies (ms/s epoch mismatch in the monitor log) which
  limited coverage; the event-time design tolerates host skew by firing only at
  `detected_at_ms + horizon_ms` and never looking ahead.
- No active run; `BOT_MODE=observe` preserved; zero orders, zero capital;
  Dashboard V2 worktree untouched. P1-14C not started.
- Full report: `docs/P1_14B_VALIDATION_REPORT.md`.

## P1-13A research opportunity/setup engine V0 — RESULT: PASS (2026-10-08)

Observe-only engine that identifies market setups worthy of further
research. Consumes existing P1-12A classifier output + P1-12B universe +
all feature rows — never recalculates states, never generates orders.

- Module: `src/microstructure_probe/opportunity.py`
  (`OpportunityEngine`, `evaluate_symbol`, `historical_reference`,
  `rank_candidates`). Rules version `v0.1.0`.
- 5 setup families: MOMENTUM_CONTINUATION, IGNITION_WATCH,
  EXHAUSTION_WATCH, REVERSAL_WATCH, EXTREME_MOVE_RESEARCH.
- Lifecycle: DETECTED → WATCHING → ACTIVE_RESEARCH → INVALIDATED/EXPIRED
  → UNKNOWN. Cooldown 60 min (code 3_600_000 ms), TTL 24h, max 200 candidates / 500 events.
- Persistence schema v8: `opportunity_candidates` (REPLACE per key) +
  `opportunity_events` (append-only, rolling 500). All upgrade chains
  migrated through v8.
- Probe integration: `opportunity()` property, demotion `forget()`,
  promotion `allow()`, summary stats + event logging.
- Dashboard: `/opportunities` page + `/api/opportunities` JSON endpoint
  (v0.1.0 candidate view-model, RESEARCH ONLY banner).
- Fabrication guards: no confidence/win-rate/expected-return/MFE/MAE;
  no "X% probability" patterns; interpretation says
  "research priority only — NOT expected profit".
- Tests: 58 tests in `tests/test_opportunity.py` — all pass.
  Full suite: 554 tests OK (553 baseline + 1 new).
- Validation run (120s, observe): 3 REVERSAL_WATCH candidates stored
  (DETECTED), 4 lifecycle events, 7 state rows, safety clean
  (BOT_MODE=observe, 0 keys, 0 orders, 11/11 streams).

## P1-14B.1 time integrity, data quality & prospective readiness — RESULT: PASS (2026-10-09)

Audit → reproduce → correct → test → validate → document. Starting SHA
`18c639b`; no other agent changes; safety preserved throughout.

- **Anomaly A (monitor-side, confirmed):** pilot `elapsed=-1789712305900s`
  is `time.time()[s] − t0[ms]` in the executed (unpreserved) monitor
  version — magnitude, +10 s/poll tick, and exact constant all reproduced
  (`t0_ms=1791503809710`, poll-1 wall `1791503809.713313`). The bug also
  defeated the monitor's 200 s timeout (hence the killed session). Core
  engine clean (zero `time.time()` in `prospective.py`; all-ms paths in
  `probe.py`/`clock.py`). Preserved `p14b_pilot_monitor.py` (Run B) is
  unit-clean; kept byte-identical as evidence with hygiene notes.
- **Defect B (core, fixed):** restart rehydration dead on the production
  path — `config/probe.json` has no `db_path`, so `_load_from_db`
  early-returned and restarts orphaned all setups (Run B: `registered_setups=0`
  with 6 DB rows). Fix: default-store rehydration + seen-set rebuild from
  stored outcomes + load-failure warning. Post-fix run: `registered_setups=7`
  from summary #1.
- **Defect C (core, fixed):** `store_prospective_outcome`'s 500-row bounding
  DELETE lacked a key filter — every store wiped all other setups' outcome
  rows (scratch-proven: A×2 then B×1 → total=1, A=0). This artifact shaped
  the P1-14B "single outcome" evidence. Fix: scoped per-key bound. Post-fix
  run: 28 coexisting rows (4/key × 7), 0 dupes, all COMPLETE.
- **Change D (core, fixed):** `observe()` ran only inside the matched-
  candidate loop, so quiet ticks never matured setups (run #1: 7 setups,
  4 summaries, 0 calls — against the spec's per-cycle mandate). Fix:
  per-symbol observation over `opp_bundles` each summary (same mark source).
- **Corrected denominators:** 7 setups cumulative across ≥4 runs (5 pre-pilot
  + 1 Run-A-window + 2 Run-B @00:06:30); 28/28 matured cells COMPLETE
  (4h: 0/7 matured — genuinely future); 0 PENDING/INSUFFICIENT rows;
  no-lookahead PASS all rows; Defect-C losses unrecoverable (documented,
  not reconstructed). The original UP-1m outcome predates the pilots.
- **Host clock:** `w32tm` unsynchronized flag + 9 s dispersion, but live
  offsets sub-second (−120 ms → +448 ms); design correctly avoids depending
  on it (exchange E for ordering; host wall only as self-consistent anchor).
- **Tests:** 609/609 OK (593 + 16 new `test_p14b_1_time_integrity.py`;
  1 P1-14B restart test hardened). Three controlled 120 s observe-only runs
  (exit 0) prove each fix live. P1-12A/B, P1-13A untouched.
- **Readiness:** prolonged-run criteria + blockers recorded (needs 30+ min
  healthy window, pre-run clock resync note, log-capture hygiene). NO long
  run started. V2 worktree/ports untouched.
- Full report: `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`.

## P1-14B.2 prospective operational stability gate — RESULT: PARTIAL (2026-10-09)

Preflight PASS (0 processes, port free, registry COMPLETED, SQLite ok, disk
163.6 GB, baseline identical: v9 / 7 setups / 28 COMPLETE). Clock audit PASS
(+517 ms worst case vs 60 s tolerance; 3/3 syncs ok; deliberate no-resync).
35-min observation via canonical plane (`control start --duration 2100`,
PID 32532, UTF-8 log `logs/probe-runs/probe-20261009T015411Z.log`) ABORTED
by controlled stop at 23.4 min (1401.7 s, exit 0, `stopped-by-agent`) when
the cumulative reject rate crossed 5.15 % (episode marginal rate ~100 % since
rt≈983, 3 market reconnects, markPrice stale, throughput collapse ~7×).
Per §6 the <30 min window is INSUFFICIENT — duration objective not met.

- Pristine first 15.8 min (0 rejects/reconnects); HOT promotions (JCT/OGN/RLC)
  grew streams 11→20 honestly; prospective layer error-free throughout
  (rehydration + per-cycle observe live: 17 new setups incl. first
  EXHAUSTION_WATCH/MOMENTUM_CONTINUATION, 40 new outcomes).
- Post-run read-only audit: 24 unique setups, 68/68 COMPLETE, 0 dupes
  (restart idempotency holds live), no-lookahead + math PASS, 68/68 matured
  cells covered (52 unmatured absent honestly), max lateness 6732.6 s
  recorded not backdated. DB file +0.0 MB; disk 163.5 GB. CPU/mem per-process
  not captured (stated, not inferred).
- Tests 609/609 OK (no new tests — no confirmed defect; episode is
  environmental). Gates: CLOCK/PERSISTENCE/PROSPECTIVE/RESOURCE/SAFETY PASS
  (resource with capture note); TRANSPORT PARTIAL (limiting gate).
- No 4–6 h run authorized. V2/main untouched. Full report:
  `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`.

## P1-14B.3 transport freshness & prospective outcome validity — RESULT: PARTIAL (2026-10-09)

P1-14B.2's episode root-caused from per-summary corrected-lag series
(bookTicker p95 0.4 s → 375 s; processing sub-ms frozen; rate collapse without
drain spike; syncs stable; worst stall on zero-reconnect `public`): host-external
delivery stall, then path outage. Local backlog, clock skew, and HOT logic discarded
with evidence; provider-vs-ISP left unseparated (no vantage point).
Open-but-stale never triggers error retries (gap), and `last_seen` updates on receipt,
so flowing-stale traffic looked healthy — receipt ≠ acceptance.

- 68 historical outcomes classified read-only (rows preserved): 19 VALID_FRESH,
  28 VALID_BUT_DELAYED (honest-late), 21 INSUFFICIENT_FRESHNESS_EVIDENCE
  (degraded-window, math/lookahead still verified), 0 STALE_OR_INVALID.
  Detection-time marks were fresh everywhere (1–17 s); only observation-time age
  was unknowable in v9 columns.
- Fixes (minimal, no new motor states): stale-mark gate (age >120 s known →
  PENDING with explicit reason; unknown fail-open) with `sample_age_ms`
  pass-through; freshness watchdog (accepted-traffic accounting per stream,
  pure stream→connection mapping, 90 s / 300 s budgets, 120 s grace + cooldown,
  one-shot consume → existing retry path); additive summary `freshness` block.
- Tests: 629/629 OK (609 + 20 new `test_p14b_3_transport_freshness.py`).
- Controlled validation (single authorized ≤35 min run, PID 34040, UTF-8 log
  `logs/probe-runs/probe-20261009T100545Z.log`): 10-min pre-window committed
  (6 min pristine); watchdog fired market+public → both reconnected in ~12 s →
  5 min zero rejects (recovery PROVEN live); second episode + path outage
  (handshake timeouts, 10 error-reconnects) → controlled stop at 17.1 min
  (exit 0). Window <30 min = INSUFFICIENT. Post-run: 24 setups, 99 outcomes
  (68+31) all COMPLETE, 0 dupes; 21 missing cells fully explained (OGN/RLC
  15m/1h/4h: never simultaneously matured+observed+marked — unsubscribed +
  CORE-only restore, no defect). No PENDING fired live (marks absent-not-stale).
- Gates: CLOCK/PROSPECTIVE/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL.
  No 4–6 h run authorized; P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`.

## P1-14B.4 prospective freshness & PENDING lifecycle integrity — RESULT: PASS (2026-10-09)

UNKNOWN-freshness audit: via the probe, mark present implies age present/finite/>=0
(`returns.feature` atomicity) — UNKNOWN arose only from direct callers; `nan`
slips comparisons and negative age signals clock pathology (both closed).
Precedent: classifier/opportunity engines already gate at 300 s; detections
always had fresh marks (1–17 s). Policy: strict classification
(ok/unknown/nonfinite/future; sub-ms negatives clamped, documented).

- PENDING lifecycle decision (documented vs alternatives): grace-deferred, then
  terminal. Failed evaluations retry silently while `now − first ≤ horizon_ms`
  (recovery window = one horizon past maturity = pre-existing det+2H audit bound,
  now enforced); then terminal PENDING with explicit reason. INSUFFICIENT stays
  immediate+terminal. Upgrade-to-COMPLETE rejected (schema cannot express it without
  backdating or dupe rows). No schema change (v9), no new states, no rewrites;
  restart restarts grace (bounded, documented).
- Outcome Contract v1.1 (`PROSPECTIVE_CONTRACT_VERSION`): decision table + additive
  telemetry (`completed/pending/insufficient/in_grace`, dashboard-compatible).
- Tests: 683/683 OK (648 + 19 new `test_p14b_4_lifecycle.py` + 16 net from converting
  `test_prospective.py`'s 35 pytest-style functions — AUDIT FINDING: unittest discovery
  silently ran 0 of them; now all execute). Legacy suites updated intent-preserving
  to v1.1 (fresh ages; grace patterns; strict-unknown rename). Market/opportunity
  rules untouched.
- Validation: 120 s controlled run COMPLETED naturally (11/11, 0/0, reg=24 from
  summary 1, 0 writes/errors, DB byte-identical 24/99, new telemetry live). No
  stale-mark occasion live (marks fresh-or-absent; Fix A unit-proven). No 35-min,
  4–6-h, or paper runs. All 99 historical rows preserved byte-identical.
- Gates: prospective/persistence/safety PASS (no transport re-rating — no long run).
  Verdict PASS. P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`.

## P1-14B.5 transport resilience & independent network diagnostics — RESULT: PASS (operational, 2026-10-10)

Attribution resolved as far as evidence allows: with identical code/config/host, NO episode
reproduced — persistent host or bot defects DISCARDED; episodes are intermittent path/provider
instability (which of the two still UNKNOWN — stated, not forced).

- Independent probe (`netprobe.py`, stdlib + existing websockets dep): single reference connection
  (host-pinned, private streams refused, params mirrored, read-only), bookTicker + markPrice-array
  streams, per-message E/lag/reorder/gap tracking, DNS/handshake/error classes, UTF-8 JSONL, bounded
  duration. 17 deterministic tests (faked transports/clocks). Limitation (honest): the bare
  `/stream` path served zero markPrice-array messages in 40 min while bookTicker flowed — tool-side
  path limitation, not a health signal; reference coverage is bookTicker-only for now.
- Coincident 35+40 min windows AGREE: bot bookTicker p50 ~175 ms / p95 ~390 ms vs reference p50
  ~340 ms / p95 ~370 ms (same sub-second regime); bot markPrice healthy (p50 ~243 ms); rejects 0;
  reconnects 0/0; E-reorders 0; reference attempts 1, errors {}. DNS 8.3 ms.
- Health classifier (pure, shared): raw socket vs FLOWING_FRESH/FLOWING_STALE/SILENT/RECONNECTING/
  UNAVAILABLE + evidence, missing-is-None; summary `connectionHealth` additive; netprobe reuses it.
  8 tests. Watchdog 10/10 re-verified (code + live log: cooldowns 292 s apart, recoveries, no loops).
- Layered diagnosis: host (w32tm self-syncing, +322 ms, no resync; CPU/NIC per-process still
  uncaptured — stated gap), transport (handshake timeouts = post-TCP path slowness, non-DNS),
  engine (sub-ms, queues empty), data (all feeds fresh).
- Controlled validation: preflight PASS + 10-min diagnostic gate → single ≤35 min run (PID 32940)
  COMPLETED naturally: 2102.5 s, 20/20, 0 reconnects, 0 rejects, exit 0 — **≥30-min healthy window
  DEMONSTRATED** (P1-14B.1 blocker #1 satisfied as far as one window can). Post-run: 49 setups
  (+25), 150 outcomes (+51) all COMPLETE, 0 dupes, 0 anomalies; contract v1.1 + v9 intact.
- Tests 708/708 OK (683 + 17 + 8). Gates: TRANSPORT/FRESHNESS/PERSISTENCE/SAFETY PASS.
  Verdict PASS (operational). Still NO 4–6 h authorization (recurrence risk — repeat advisable);
  P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`.

## P1-14B.6 reproducibility & operational readiness — RESULT: PARTIAL (2026-10-10)

Second window reproduced BOTH regimes: ~22.6 min pristine, then delivery episode (rejects → 8.83%,
error reconnects 1+3, watchdog fired 3 cycles, handshake timeouts). Abort rule breached UNACTED —
live supervision lost to a harness timeout at launch (demerit recorded; no safety rule breached).

- netprobe markPrice placement verified 2×2 live (arrays ONLY on `/market/stream`; per-symbol on
  `/stream`+`/public/stream — mirrors the bot's own routing): `--base-path` allowlist + placement
  warning + two-instance operational reference. Official docs unfetchable (recorded); vendor
  incident reports TODAY corroborate provider-side instability (Sierra Chart feed stops;
  connector ACK-but-no-data issue) — kept as context, not proof.
- Fixes: netprobe heartbeat summaries (total silence now observable) + host telemetry
  (`os.times` CPU%, psapi RSS with real-handle fix, per-stream exact bytes, UNKNOWN-safe) in
  bot summary `host` block + netprobe records; shared health classifier + `connectionHealth`.
- Discriminating evidence: bot CPU flat 3–6% + 30.5 s summary cadence through the episode
  (local compute/loop-blockage DISCARDED); references on the same host stayed healthy
  (bookTicker p95 ≤581 ms bump coinciding with bot collapse = shared wobble, ~100× milder);
  per-connection selective degradation → server-side edge attribution refined (reconnect
  recovery works until handshake-refusal stage). Provider-vs-ISP residual UNKNOWN (stated).
- Tests 726/726 OK (708 + 4 path + 1 warning + 1 flag-off + 12 host + heartbeat). Post-run:
  57 setups (+8), 202 outcomes (+52) all COMPLETE, 0 dupes, 0 anomalies; v1.1 + v9 intact.
- Gates: CLOCK/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL. Verdict PARTIAL
  (duration + abort-supervision failed; fixes validated). Still NO 4–6 h authorization
  (repeat advisable); P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`.

## P1-14B.7 persistent supervision & enforced abort gates — RESULT: PASS (2026-10-10)

P1-14B.6's abort breach happened because evaluation lived in the agent session. Fix by
architecture: `control supervise` — a detached, registry-leased watcher evaluating documented
abort rules every cycle from probe evidence, enforcing one-shot verified-PID stops with persisted
reasons. Never starts/restarts runs, never touches foreign PIDs, never acts on UNKNOWN.

- Rules (exact, LOCAL_POLICY except cumulative 5% rejects): safety immediate; rejects >5%;
  >5 reconnects/10 min sliding; persistence ≥2 events/10 min ×2 checks (or recorder DEGRADED);
  clock >30 s ×3; DB unreadable ×6; watchdog-overwhelm compound (forced≥3 + errors≥3 + rising).
  Freshness-absence reduces to these (documented). Streaks persist in the lease (restart-safe).
- Lease serializes supervisors (live→refuse, stale/corrupt→recorded takeover); failure budget
  (5×) marks FAILED and exits without touching the probe; terminal ABORTED + reason/threshold/
  observed persisted; second cycle no-op; launchers preserved.
- Identity: PID + image + creation-time; wmic absent on this host class (verified) → ctypes
  GetProcessTimes fallback restores full identity (proven live with ISO stamps).
- Validation: 34 supervisor tests (decision matrix, lease/races, stale/reuse no-touch, terminal
  no-ops, V2 contract keys, no-start assertion, store isolation) + REAL-PID integration (breach
  evidence → sleeper killed, foreign sleeper alive, ABORTED persisted, no re-fire). Suite 760/760.
  Brief live run (150 s probe + 12-cycle supervisor): claimed, heartbeated, clean exit, zero false
  aborts; probe 11/11, 0/0, reg=57, DB identical. Found+fixed: self-registration wiped evidence
  paths (same-PID preservation now).
- V2 contract additive (`supervisor` block in control status → API; mapping table; UI renders via
  existing opaque strings). No frontend changes. All 202 rows / 57 setups preserved byte-identical.
- Gates: prospective/persistence/safety PASS (mechanism + validation, no long run). Verdict PASS.
  Still NO 4–6 h authorization; P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`.

## P1-14B.8 supervised maiden voyage & abort enforcement — RESULT: PASS (2026-10-10)

Agent-independence demonstrated in execution, not assertion. Probe PID 33292 ran 2102.147 s
per final_summary (13:12:44 → 13:47:55Z, exit 0) while supervisor PID 25800 ran 70 cycles 13:13:35 → 13:48:24Z
and exited cleanly — zero agent contact after launch. Post-hoc log audit (68 summary + one
final_summary): 0.00% rejects,
0 reconnects, 20/20 streams, reg 57→66 (+9 setups), 35 writes, 0 errors — nothing breached,
correctly nothing aborted. The long window ran supervisor-only: a concurrently launched sentinel died silently in ~30 s (no cycles,
no output); root-cause class: silent early death under buffering (observability gap, not a
proven cause — `-u`/flush improve diagnostics, they do not fix process lifetime) — encoded fixes: flushed
startup prints in both mains, `-u` in detached launches, lease-presence launch verification.

- Sentinel layer completed: claim/takeover/no-op semantics, stale/FAILED-lease abort via
  canonical `enforce_abort`, own failure budget, additive status block + CLI, no-start guarantee.
- Brief three-layer validation (150 s probe + 14-cycle supervisor + 12-cycle sentinel, verified
  leases; brief-run preflight was 66/228): claimed, heartbeated to natural COMPLETED, zero false
  aborts, zero orphans; probe
  11/11, 0/0/0, reg=66, DB byte-identical (66/228/0 dupes, unchanged by the brief run).
- Tests 775/775 OK (760 + 15 sentinel). Post-run: 66 setups (+9), 228 outcomes (+26) all COMPLETE,
  0 dupes, 0 anomalies; v1.1 + v9 intact; 202 prior rows preserved.
- Gates: CLOCK/TRANSPORT/FRESHNESS/SUPERVISION/PERSISTENCE/SAFETY PASS. Verdict PASS.
  Still NO 4–6 h authorization (recurrence risk); P1-14C not started; V2/main untouched.
  Full report: `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md`.

## P1-14B.8 follow-up — enforce fencing (bounded correction, 2026-10-11)

Frontend review `d80fb9b:docs/DASHBOARD_V2_50_CORRECTIONS_REVIEW.md` (backend
`8648366`) left HIGH findings: `enforce_abort` terminated before fencing,
terminal marks ignored run replacement, `aborted_by` hardcoded, heartbeat
regression no-op'd. Fixed deterministically, no market runs launched:

- `enforce_abort`: STOPPING via locked `update_registry`; pre-terminate gate
  re-verifies eligible state, run PID+ctime, canonical liveness, owner lease
  and foreign STOPPING marker (`already-stopping` refusal). Failed/refused
  marker never reaches termination. ABORTED/FAILED marks recheck run
  identity, own marker and lease; `aborted_by` persists the real owner
  (`supervisor`/`sentinel`/`direct`). `sentinel_once` heartbeat is now
  locked+fenced (replaced sentinel no-ops; no clobber of supervisor block).
  Cleanup: single JSON parse in `update_registry`; unreachable abort-field
  block removed.
- Regressions `tests/test_enforce_abort_fencing.py` (13): foreign owner never
  terminates (x2); COMPLETED+takeover between read and STOPPING preserved
  (x2); STOPPING write failure never terminates (x2); PID/ctime + foreign
  marker fenced on ABORT and timeout paths (x4); real owner persisted (x2);
  foreign STOPPING acquisition refused. On `8648366` 8/13 fail (termination
  invoked, COMPLETED overwritten, `sentinel` mis-marked as `supervisor`);
  on corrected code 13/13 pass.
- Heartbeat `test_concurrent_heartbeats_keep_both_fields` now uses owned
  leases (`os.getpid()`): 4 threads x25 locked heartbeats advance both
  `last_check_at`, retain distinctive `11`/`22` + streaks/action, preserve
  the run, exit cleanly with zero hidden errors. Old fixture (PIDs
  424244/424245) left a byte-equivalent record. Added
  `test_racing_sentinel_claims_single_winner`: exactly one winner (supervisor
  race already covered).
- Suite: `python run_tests.py` → 808/808 OK (794 + 13 fencing + 1 sentinel
  race). No probes, P1-14C, long runs or paper trading started. DB/logs
  preserved. V2 transactional supervised start stays PENDING and separate.
  SUCCESS_GATES not advanced.
- Window scope: historical >=30-min healthy windows (P1-14B.5 2102.5 s;
  P1-14B.8 2102.147 s supervisor-only + brief three-layer run) are historical
  evidence only. No new supervised window was run on this corrected SHA (per
  task bounds); corrected-code longevity remains UNDEMONSTRATED.

## P1-14B.8 V2-51 fencing (bounded correction, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `35401f9:docs/DASHBOARD_V2_51_FENCING_REVIEW.md` (backend
`0786617`) left HIGH findings with mocked reproductions
(`scripts/review-p1-14b8-final-fencing.py`,
`design/qa/v2-51/backend-reproductions.json`): post-claim takeover still
reached termination, owned lease need not cover the run, `status()` overwrote
terminals, no `status_readonly()`, thread-only concurrency. Fixed
deterministically, no market runs launched:

- Operation boundary through termination: STOPPING acquisition AND a final
  locked verify-and-kill (same lock held across re-verification and the
  kill, via `update_registry` transform). Post-claim owner/run/marker changes
  refuse with `takeover-after-claim`/`run-replaced`/`replaced-owner` and leave
  the mocked termination uncalled. `_terminate_verified_pid(pid, ctime)` now
  verifies on the real OS handle (Windows: one handle reads GetProcessTimes
  and terminates; POSIX: `pid_is_ours` immediately before `os.kill`) and
  returns False on identity failure. `stop_probe` carries the same
  verify-while-locked discipline with its own `stop:` marker.
- Lease-vs-run: `_owner_lease_valid` (ACTIVE + owned + `watched_pid` == run
  PID + ctime when determinable on both sides) replaces pid-only checks at
  acquisition, pre-kill and terminal marking, for supervisor and sentinel.
  Wrong-run (`wrong-run-lease`), foreign (`replaced-owner`), inactive
  (`owner-lease-invalid`) leases never terminate. Heartbeats keep pid-only
  `_owns_lease` (non-replacement proof) by design.
- `control.status_readonly()`: pure projection shared with `status()` via
  `_status_view` (identical shape/nullability). No writes, no reconciliation,
  no log-handle mutation, no process action. Missing → STOPPED shape without
  creating a file; dead/reused PID, STOPPING and ABORTED preserved
  byte-for-byte. Mutating reconciliation is separated into fenced
  `_reconcile_stale_record` (locked; never touches terminal states nor a
  held enforcement STOPPING) and `dashboard.probe_status()` (browser-polled
  GET path) now reads purely. `try_register`/`start_probe`/`_mark_terminal`
  moved to locked fenced commits (refuse live runs and held STOPPING
  markers; never overwrite terminals).
- Concurrency between processes: `tests/test_process_concurrency.py` (3)
  with spawned owners (distinct PIDs, barrier rendezvous so winners stay
  alive during the race): supervisor+sentinel claim then 10 counted
  heartbeats each (bool returns; every call wrote, both final timestamps
  fall inside the overlapped window, 11/22 + streaks/action survive);
  4-process supervisor and sentinel claim
  races elect exactly one winner; all workers exit 0 with zero hidden
  errors. Without the rendezvous, late starters legitimately take over
  exited winners' leases (documented takeover, not a lock failure).
- Fail-before: 15 new boundary/readonly tests fail on `0786617`
  (termination reached, `status_readonly` missing, ABORTED overwritten with
  FAILED); corrected code passes all. Heartbeat counting fails before the
  bool-return change (returns None). Prior 808 green preserved.
- Suite: `python run_tests.py` → 826/826 OK (808 + 8 boundary + 7 readonly
  + 3 multiprocess). No probes, P1-14C, long runs, paper trading or Start
  enablement. SQLite/logs/evidence preserved. V2/main untouched.
  SUCCESS_GATES not advanced. Transactional supervised start stays PENDING
  and separate.
- Guarantee: with the lock held across final verification and the
  handle-bound kill, a registry takeover cannot interleave at the boundary
  and a reused PID cannot be hit (Windows: same-handle check+kill).
  Residuals (explicit): POSIX has no handle API (microsecond recheck
  window); ctime comparison skipped when indeterminable either side;
  `_owns_lease` stays pid-only for heartbeats; `status()` CLI/`stop_probe`
  stale paths still mutate by design (fenced). No complete-protection claim
  beyond the audited writers.
- Window scope: no new supervised window on this corrected SHA (per bounds);
  historical windows stay historical; corrected-code longevity UNDEMONSTRATED.

## P1-14B.8 V2-52 integration (bounded correction, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `066577e:docs/DASHBOARD_V2_52_INTEGRATION_REVIEW.md` (backend
`55efaa2`) with mocked reproductions (`scripts/review-p1-14b8-v2-52.py`,
`design/qa/v2-52/backend-reproductions.json`). H1+H2 fixed with
failing-first hermetic regressions; `status_readonly()` and contracts kept:

- H1 native Windows termination: `TerminateProcess`/`CloseHandle` now carry
  explicit HANDLE-width (`c_void_p`) argtypes/restype with BOOL checked; a
  `0`/exception returns False with a bounded GetLastError record
  (`_LAST_NATIVE_ERROR`, code + timestamp, single overwritten entry) --
  never reported as success. Handle closed on success, refusal and
  exception paths alike; creation verification and termination stay on the
  same handle inside the registry lock. Missing ctime falls back to
  handle-liveness only (open + queryable times terminate; unqueryable
  refuses) -- PID-reuse NOT excluded there, documented residual.
  Precision: the finding never proved a live process falsely marked
  ABORTED (callers verify disappearance + 10s wait); the demonstrated fault
  was accepting native refusal as success. Tests
  `tests/test_native_terminate.py` (9: matching/mismatched ctime,
  GetProcessTimes refusal, TerminateProcess=0, exception, open failure,
  >32-bit handle intact `0x100000123`, missing-ctime fallback, 2 POSIX).
  Fail-before on `55efaa2`: signatures unconfigured, `0` returned True.
- H2 parent/child start race: `_commit_start` recognizes the own
  just-spawned child by PID + creation-time (captured once) and adopts its
  RUNNING/STARTING record verbatim -- no kill, no STARTING overwrite,
  evidence preserved (byte-preserving: adoption writes nothing). Held
  enforcement markers are never adopted. Genuinely foreign runs and reused
  PIDs (same PID, different ctime) are still refused with exactly one
  orphan-cleanup kill; write failures kill once. Tests
  `tests/test_start_race.py` (5: parent-first, child-first, foreign-winner
  via preflight→commit injection, reused-PID, write failure; response +
  final record + kill count asserted). Fail-before: child-first killed its
  own child and returned started=False. Not extended to the V2 supervised
  transactional launch (separate).
- C1 concurrency precision (corrected V2-54): M1 heartbeat workers
  rendezvous on a shared start barrier with ten effective writes per owner
  and both final timestamps inside the window [t0, t1] (2s tolerance for
  ISO-second truncation). This does NOT prove strict advancement versus the
  claim timestamps, forced per-write interleaving, or longevity.
- Suite: `python run_tests.py` → 840/840 OK (826 + 9 native + 5 start-race;
  M1 strengthened in place). No probes, P1-14C, long runs, paper, trading
  or Start enablement. SQLite/logs/evidence preserved. V2/main and
  SUCCESS_GATES intact. `status_readonly()` kept in all GET paths.
  Transactional supervised start stays separate.
- Residuals (explicit): POSIX pre-kill recheck window (no handle API);
  ctime-None fallback excludes PID-reuse proof; `_owns_lease` pid-only kept
  for heartbeats; `status()` CLI/`stop_probe` stale paths mutate by design
  (fenced). No general PASS, no demonstrated longevity, no authorization
  for new runs.

## P1-14B.8 V2-54 corrections (bounded, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `d4d82c9:docs/DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md`
(backend `b801ab0`) with mocked reproductions
(`scripts/review-p1-14b8-v2-54.py`,
`design/qa/v2-54/backend-reproductions.json`). R1+R2 fixed with
failing-first hermetic regressions; `status_readonly()` and contracts kept:

- R1 exact Win32 BOOL: native signatures now use 32-bit
  `ctypes.wintypes.BOOL` (`c_long`; `c_bool` is 1 byte and misreads native
  returns such as 256 as falsy) for TerminateProcess/CloseHandle/
  GetProcessTimes results, the OpenProcess inherit flag, and HANDLE-width
  (`c_void_p`) arguments -- bound once in `_configure_kernel_signatures`
  (no silent setup), verified on the same handle inside the registry lock.
  Refusal/exception propagation, bounded `_LAST_NATIVE_ERROR` and guaranteed
  close preserved. Tests `tests/test_win32_bool.py` (7: 32-bit width +
  exact type identity, ABI 0/1/256 through real WINFUNCTYPE callbacks --
  256 truthy under BOOL and falsy under `c_bool` -- plus end-to-end helper
  acceptance of a 256 native success). Fail-before on `b801ab0`: width 1,
  no exact-type helper, 256 returned False. No real termination failure or
  false ABORTED is claimed (out of scope by review precision).
- R2 child-first log association: adoption with absent evidence now performs
  a conditional locked handoff binding the parent-created log to the same
  PID+ctime run (revalidating state, no enforcement hold, no valid log
  present). Valid pre-existing evidence is preserved verbatim (no write);
  foreign/terminal/enforcement races refuse without touching; handoff
  OSError keeps the verified live child running with the association
  explicitly unconfirmed (`evidence_associated: False` -- never declared
  confirmed when not established); no log is invented for direct launches
  (handoff only binds the log this start created). Tests rewritten onto the
  REAL `try_register()` child-first flow (evidence None) plus existing
  evidence, interleaved STOPPING, and handoff write failure; parent-first,
  foreign, reused-PID and commit-failure cases kept with response + record +
  kill-count assertions. Fail-before: association stayed None.
- C1 precision corrected in test wording and here: M1 is a shared start
  barrier with ten effective writes per owner and final timestamps inside
  [t0, t1] -- NOT strict advancement versus claim timestamps, NOT forced
  per-write interleaving, NOT longevity. Earlier "advance" phrasing above
  is superseded by this scope.
- Suite: `python run_tests.py` → 850/850 OK (840 + 7 win32-bool + 3
  start-race delta: 8 cases = 4 kept + 4 handoff/real-registration cases
  replacing 1 artificial). No probes, backfills, P1-14C, long windows,
  paper, trading or Start. SQLite/logs/evidence preserved. V2/main/
  SUCCESS_GATES intact. Supervised transactional start stays separate.
- Residuals (explicit): POSIX recheck window; ctime-None fallback;
  pid-only heartbeat ownership; mutating CLI/stop paths by design (fenced);
  pure status certifies no OS liveness. No general PASS, no longevity, no
  authorization for new runs.

## Supervised transactional launch — preparation DISABLED (2026-10-11) — RESULT: DONE (acotado)

Contract first: `docs/SUPERVISED_LAUNCH_CONTRACT.md` (preconditions +
capacity, per-process identity/association, sequence, watcher confirmation
criteria, finite budget, partial failure/cancellation/rollback, confirmed/
rejected/uncertain outcomes, backend/BFF responsibilities + field compat).
R1/R2 accepted as closed; not reopened.

- Implementation: `control.launch_supervised_transaction` (public, refuses
  with `supervised-launch-disabled` and zero side effects) +
  `_launch_supervised_impl` (tested engine reusing `start_probe`, leases,
  identity, verified termination, registry lock; pure-read verification,
  kill-only rollback). No HTTP route, CLI subcommand, Start enablement or
  contract change ships with this preparation.
- Confirmation rule: Popen/ACTIVE lease/heartbeat alone never confirms.
  Both watchers must verify ACTIVE + owned PID/ctime + watched==run +
  alive + parseable fresh non-future heartbeat on ONE fresh read inside the
  budget. Confirmation is point-in-time, never future protection.
- Rollback: reverse order, spawn-captured identity only, verified kills;
  already-dead counts as cleaned; foreign/terminal records never written
  or killed. Unverifiable cleanup → UNCERTAIN with pending evidence (never
  declared completed).
- Failure matrix (`tests/test_supervised_launch.py`, 23): full path;
  foreign pre-seed / probe / supervisor / sentinel spawn-register failures;
  absent / stale / future / malformed / wrong-run leases; dead watcher;
  reused watcher PID; timeout; unreadable verification; takeover/STOPPING
  and terminal interleaves (records preserved); refused/stuck kills
  (uncertain); concurrent launches elect one confirmation (single
  parent-held Popen patch -- per-thread global patches leak process-wide);
  repeated launch rejected; verification+rollback issue zero registry
  writes under strict no-write mocks. Fail-before: 23/23 missing API.
- Suite: `python run_tests.py` → 873/873 OK (850 + 23). No real probes,
  market traffic, P1-14C, long runs, paper, orders or Start. SQLite/logs/
  evidence preserved. V2/main/SUCCESS_GATES intact. `status_readonly()` in
  GETs. No phase advanced.
- Residuals (explicit): default Popen spawners dormant (untested against
  live OS); POSIX/no-handle and ctime-None limits inherited; heartbeat
  ownership pid-only; CLI/stop mutations by design (fenced); pure status
  proves no liveness. No general PASS, no longevity, no operational
  authorization.

## DASH-V2-64 backend reconciliation + read contracts (2026-10-11) — RESULT: DONE (acotado)

Frontend checkpoints read from Git only (`dash-v2-03-token-detail`
`8780da2`: cutover audit, backend handoff, V2-63 data contract). No V2,
main, SQLite, log, or evidence mutation; no collector/formula duplication.

- Preflight/reconciliation: branch `phase1/market-intelligence-dashboard`,
  local `da231b9` vs remote `c635938` (owner fix "fence disabled launch
  ownership and uncertainty", +29 tests). Worktree clean (tracked),
  zero Python processes, COMPLETED terminal registry, unheld sidecar lock,
  stale dashboard pidfile only → fast-forward `da231b9..c635938` executed
  with no reset/clean/kill. No conflict or active-process blocker existed.
- Deployed identity (verified post-FF): V2 `runtime-control.ts` spawns
  Python with cwd+PYTHONPATH = this workspace (`/src`) calling
  `control.status_readonly()` (fallback READ_ONLY_STATUS_REQUIRED), and
  reads canonical `data/microprobe.db` via DatabaseSync readOnly. V2
  imports NOTHING else from backend Python. Deployed source == accepted
  `c635938`; the audit's da231b9-vs-remote split is closed on this
  checkout (V2 re-verifies the exact SHA before consuming).
- Inventory: `docs/DASHBOARD_V1_READ_CONTRACTS.md` — all legacy GET pages
  + 25 JSON APIs (fields, units, nullability, response-time `generated_at`,
  empty→404 semantics), universe/search (persisted-only universe, exact/
  prefix/substring order, limit 25; `normalize_symbol` accepts unicode
  alnum — STRICTER-than-Python V2 parser is a V2-side boundary for
  DASH-V2-65), historical coverage + event studies (separate historical
  DB, fixed columns, limits 20/50), price ranges 5m–24h anchored at
  REQUEST time (vs V2-63 LAST_RETAINED_SAMPLE ≤600 buckets + >60s gap
  segments — never silently substituted) + CSV/JSON export metadata.
- Diagnostics: `status_readonly()` purity re-pinned by new
  `tests/test_dashboard_get_purity.py` (G1–G3: stale RUNNING never
  reconciled, absent never created, process/feed reported separately,
  zero writes/handles/actions; mutation check restoring legacy `status()`
  fails G1/G3). Recency never proves identity/liveness/protection;
  unverified reads UNKNOWN. Future authorized runs must produce the
  evidence list in §5 of the inventory doc — no standing authorization.
- Retirement: reversible old-UI plan PROPOSED, NOT executed. Audit-found
  blocker: `control.py` lazily imports shared helpers FROM `dashboard.py`
  (`repo_root`, `process_info`, `pid_is_ours`, `no_window_flags`), so
  file-level retirement is blocked pending helper extraction (proposed
  prerequisite). Operational stop alone is fully reversible today.
- Code added: only the pinning test file (no source change; V2-63 already
  covers presentation, old APIs already serve history/exports).
- Suite: `python run_tests.py` → 905/905 OK (902 + 3 pinning), exit 0. No
  probes, backfills, P1-14C, long runs, paper, orders, Start, or gate
  advancement. Deterministic results only — no longevity claim.

## Helper extraction: control decoupled from the HTTP module (2026-10-11) — RESULT: DONE (acotado)

Per DASH-V2-67 handoff (`dash-v2-03-token-detail` `8712dfb`, read from Git
only): `repo_root / process_info / pid_is_ours / no_window_flags` (+
`_creation_time_ctypes`) moved VERBATIM to new
`src/microstructure_probe/host_process.py` (stdlib only, verified
byte-identical bodies); `dashboard.py` re-exports the same objects (no
duplication; old helpers, importers, and dashboard-namespace tests keep
working); `control.py` binds them at top level with all 16 lazy
`from .dashboard import` removed (one mis-indented `def _probe_env`
repaired to module level). Controller-behavior patch targets moved
`dashboard.pid_is_ours` → `control.pid_is_ours` (24 sites) and
`dashboard.process_info` → `host_process.process_info` (7 sites) after a
full import/caller/cycle/patch-target audit (only control.py imported the
helpers from dashboard; views only use DASHBOARD_VERSION). New
`tests/test_host_process_boundary.py` (H1 source scan, H2 subprocess
isolation with the dashboard import blocked, H3 object-identity compat, H4
parity) — failing-first (collection ImportError + missing API on base).
V2-64 doc corrections applied alongside: manual (not automatic) SHA
verification, current price schema 3 (5 historical ranges, 10k raw / 1200
display), REQUEST-vs-retained + ASCII-vs-Unicode kept explicit,
prospective (microprobe.db) vs historical.db split explicit, purity-scope
limit (`_ensure` writable paths) explicit. Suite 909/909 OK (905 + 4
boundary), exit 0. No probes, backfills, traffic, P1-14C, long runs,
paper, orders, Start, main merge, SUCCESS_GATES, formula, or accepted-fix
changes. No old-UI/server/file retirement executed (file-level removal
still waits on this extraction's review). SQLite/registry/logs preserved.

## DASH-V2-71B System data contracts (2026-10-11) — RESULT: DONE (acotado)

V2 checkpoints read from Git only (`dash-v2-03-token-detail` `f52b68f`:
acceptance, recorded diagnostics, migration plan). No V2/main/SQLite/log/
evidence mutation; no second collector or database; no probes or traffic.

- Preflight/reconciliation: local == origin == `9f3e084` on entry (already
  synced, clean worktree, foreign files preserved); no reset/clean/force.
- Matrix: `docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md` — per-field
  reader/table/column, meaning+unit, observation-vs-read timestamps,
  nullability/absence, scope/limits, historical-vs-current, and side
  effects for persistence, universe/budget, research, classifier/
  opportunities, runtime/watchers/feed; safe-reader allowlist with purity
  notes; NOT_AVAILABLE host resources (no column on schema v9, verified on
  the live DB read-only; log-only `host` block is not a reader contract)
  and ops audit log (latest `last_exit` + capped lifecycle tables only);
  V1 diffs (price anchor, search limits/parser, prospective vs historical
  DBs); real record examples; frontend MUST-respect decisions; concrete
  retirement blockers.
- Validation: `tests/test_read_purity.py` (full read battery leaves
  operational/historical DBs, registry, and evidence byte-identical, no
  new `.db` files, content queries agree; temp fixtures only). No defect
  found in these read paths on existing stores → no source change (fresh-DB
  `init_db`/`_ensure`/WAL paths documented as NOT safe for V2 instead).
- Suite: `python run_tests.py` → 910/910 OK (902 + 3 GET-purity + 4
  boundary + 1 read-purity), exit 0. No probes, backfills, P1-14C, long
  runs, paper, orders, Start, main merge, SUCCESS_GATES, formula, or
  accepted-fix changes. Deterministic only. (One early full run reported
  905 on the same tree; four subsequent consistent measurements — three
  discovery counts plus per-file sum plus a full OK execution — establish
  910; the single 905 reading is unreproduced and superseded.)


## Auditoría trazabilidad EVAL-CENSUS-V2 — 2026-10-17 (addendum sobre commits b5cd690 + bea541a)

- Identidad 1385927: prefijo de 7 chars del SHA publicado `13859277b7baa8b029d385c41bd3cb60c7cd4b13` (commit EVAL-CENSUS-V2, rama review/o1-funcional-v2-observacion), NO un run_id ni sesión. Verificado: `git rev-parse --verify 1385927` → objeto válido; `git show 1385927` → commit; `git fetch origin` OK; `HEAD == origin/rama` (0 commits de diferencia). Repo canónico: `C:\proyectos\binance-futures-microstructure-bot`, no junction/reparse. DBs canónicas intactas (microprobe.db, historical.db, sin modificación; `hashes_equal=True` en barrera de aislamiento).
- Flujo reconstruido desde manifiestos ejecutados (temp/opencode/eval*_*, fuera de Git) + artefacto publicado (`frontend/src/data/census-eval-v2.json`, sha256 `2b74a8419ea731e7b23f005c2c4e60655fd5efb4116032c1bcd3244dd6d37060`):
  - 9320 detecciones censo (todas las resoluciones/símbolos) → 7541 trio 15m+1h que entra al builder (6121 15m + 1420 1h); 1779 fuera de alcance del builder = MINAUSDT 1h (626) + NMRUSDT 1h + ORCAUSDT 1h (1153), verificado por membresía individual (no por resta).
  - Builder (MAP-CANDIDATE-v2): 7167 admitidas direccionales + 374 excluidas por motivo (gap 225, no_entry 4, h2_no_confirmation 43, h2_reclaim 102) + expansión mapping 1:2 (placebo TIME-PLACEBO-v1 seed 42, mismo count) → 14334 eventos en events.json.
  - Selection purge (cutoff 1790010000000): 30 dev-crossing purgados → 14304 (= 7152 hipótesis + 7152 placebo).
  - Hipótesis 1x: 7152 eventos, 2991 trades, 5 abiertas, 4161 skipped_overlap, 2986 realizadas.
  - Placebo 1x: 7152 eventos, 2264 trades, 2 abiertas, 4888 skipped_overlap, 2262 realizadas.
  - Total: 14304 eventos, 5255 trades, 7 abiertas, 9049 overlaps, 5248 realizadas. `realizadas = trades − abiertas` verificado.
- H1/H3 direccionales 15m @1x: 12 celdas, 12 negativas (no 18; el 18 del commit mezcla 6 celdas baseline/comparator). Corregido por addendum.
- Duplicados 594/616 VERIFICADOS en conjunto completo (9320 detecciones):
  - 15m trio: 6121 det, 371 grupos/383 extra
  - 1h trio: 1420 det, 45 grupos/47 extra
  - MINAUSDT 1h: 626 det, 90 grupos/92 extra
  - NMRUSDT+ORCAUSDT 1h: 1153 det, 88 grupos/94 extra
  - Total: 9320 det, 594 grupos/616 extra ← coincide exactamente con artefacto.
  - Clave de agrupación: (symbol, interval, formation_time) en múltiples familias. Permitido en censo (cada familia es distinta), NO cuenta como operaciones independientes. Builder asigna una familia por detección (no duplica trades). `max_concurrent=1` es intra-celda, NO prueba independencia entre familias/cedas.
- Trazabilidad: manifiestos con event_ids en temp/opencode (fuera de Git); vínculo completo detección→operación NO publicado en Git (UNKNOWN hasta que los manifiestos se incorporen). Cada evento en manifiestos events.json tiene campos de identidad requeridos (symbol, event_time_ms, direction, family, rules_version, group, reference_price); IDs técnicos (event_id con índice) únicos; claves semánticas duplicadas reportadas y clasificadas.
- Causalidad: mecanismo testeado en fixtures (`test_causal_census.py`: entry >= available, available_at = close_time de formación, decision_time NULL). Sobre datos reales del censo completo, entry>=available no está en el artefacto publicado (es propiedad del reconstruct, no del ledger); resultado sobre datos reales = UNKNOWN hasta incorporar manifiestos a Git.
- Funding: 741 settled_events (escala 1x, hipótesis+placebo) = aplicaciones por operación; 270 liquidaciones únicas del calendario (90/símbolo BTC/ETH/SOL, funding_raw.json n=90); 0 unknown-excluded (no cobertura completa); 24/60 celdas uncovered (holdings fuera calendario span). 741 ≠ 270 (métricas distintas). unknown-excluded y uncovered son conceptos distintos.
- MFE/MAE: mfe_mean/mae_mean de backtest_offline.run_backtest = excursión por posición, NO ganancia capturada por la salida. Rango global todas celdas 1x: MFE 0.0-1.04%, MAE 0.0-0.50%. Rango direccional 1x n>=30: MFE 0.19-0.64%, MAE 0.16-0.42% (aprox. al citado 0.18-0.66/0.10-0.42; subpoblación no especificada en el doc original, corregido como excursión no captura).
- Verificador: `tests/test_audit_offline_eval_traceability.py` (30 tests unittest, todos pasan: 0 fallos, 0 errores) + `scripts/audit_offline_eval_checks.py` (runner del suite) + `scripts/audit_offline_eval_ledger.py` (genera reporte JSON con SHA256 de inputs, estatus COMPLETO/INCOMPLETE). Evidencia publicada: `docs/evidence/audit_offline_eval_ledger.json`.
- Tests de mutación incluidos: duplicado semántico con índice distinto, entrada antes de disponibilidad, referencia de detección inexistente, familia/segmento ausente, motivo de descarte ausente, campo funding ausente, manifiesto alterado, input alterado vs hash, población MFE/MAE incorrecta, control positivo válido. Cada defecto produce fallo esperado.
- Reproducción completa: requiere ejecutar `reconstruct_causal_census.py` + `build_census_eval_inputs.py` + `select_eval_events.py` + `run_family_evaluation.py` sobre `historical.db` read-only. Los manifiestos intermedios están en `temp/opencode/` (fuera de Git). No declarada reproducibilidad externa completa sin probarla.
- Sin corridas Binance, forward, paper, órdenes, optimización, cambios de umbrales. Sin modificar DBs canónicas. V2 disponible en 3020; monitor detenido.
- Pendientes: incorporar manifiestos temp/opencode a Git para trazabilidad completa (vínculo detección→operación sigue UNKNOWN).


## Auditoría EVAL-CENSUS-V2 — corrección con evidencia verificable (2026-10-18)

Corrección del addendum anterior (2026-10-17) con evidencia real, no declaraciones:

- Verificador: 45 tests unittest (0 fallos, 0 errores). Meta-prueba de mutación: al alterar el verificador los tests fallan (3 y 1 fallos dirigidos). Los tests ejercitan funciones puras del verificador con fixtures y datos reales, no tautologías.
- Causalidad VERIFICADA sobre datos reales: 9314/9314 detecciones OK (formation ≤ available ≤ entry), 6 UNKNOWN (entry NULL → no_entry), 0 violaciones. Ya no UNKNOWN.
- Vínculo detección→evento H1/H3: 6868 eventos, 0 sin respaldo, 0 excedentes. H2 vinculado reconstruyendo CONFIRM-H2 determinista.
- Duplicados events.json: 0 errores. Clasificados con origen: H1/continuation (2 detecciones distintas), H2 (confirmaciones en misma barra), placebo (colisiones rng internas).
- Referencias artefacto↔manifiesto: consistentes. Campos compartidos coinciden.
- Funding: 741 settled, 0 unknown_excluded, 24/60 uncovered — verificados por función pura por celda.
- MFE/MAE: rango global y n≥30 calculados por función pura (rango_mfe_mae). Excursión, no captura.
- Ledger publicado (docs/evidence/audit_offline_eval_ledger.json): incluye secciones causalidad, duplicados_censo, duplicados_events, referencias con evidencia real.
- Generador: INCOMPLETE + exit≠0 sin inputs (tests de integración). Sin rutas absolutas de usuario. SHA256 de cada input.
- Suite completa: 1247 tests OK. Barrera de aislamiento: hashes_equal=True, file_writes=0.
- Pendiente: incorporar manifiestos temp/opencode a Git (vínculo detección→operación sigue UNKNOWN fuera de temp).

## Auditoría EVAL-CENSUS-V2 — veredicto global, trazabilidad a operación y paquete de evidencia (2026-10-18)

Corrige y extiende el addendum anterior de forma explícita:

- Verificador: 58 tests unittest (0 fallos, 0 errores): 45 funciones puras + 3 PackageMode + 10 CLI fixtures. Meta-prueba de mutación: al alterar el verificador los tests fallan. Los tests ejercitan funciones puras con fixtures y datos reales, no tautologías.
- Veredicto global PASS/FAIL/INCOMPLETE integrado en el ledger. Estado actual: INCOMPLETE (0 discrepancias, 2 incompletos: MINAUSDT/1h y NMRUSDT/1h tail-edge sin build_report). No se declara "auditoría completa" mientras esos 2 vínculos sigan abiertos.
- Trazabilidad hasta la operación real: `scripts/reconstruct_replay_traces.py` re-ejecuta el runner sobre events/candles con configuración inferida de manifiestos; 0 celdas fail (equivalencia demostrada por celda: conteos, exit_reasons, config_hash, mfe/mae, expectancy, total_net, fees, funding, max_drawdown). 5255 trades escala 1.0 reconciliados exactamente (5255=5255; 5248 realizadas + 7 abiertas). Vinculación trade→evento vía admitted_positions.
- Paquete de evidencia: `docs/evidence/eval-census-v2-package/` (33 archivos, package_manifest.json con SHA256). `build_eval_package.py` + `verify_eval_package.py` (PASS). Trades se regeneran con reconstruct_replay_traces.py desde el paquete.
- Pruebas CLI: 10 casos de alteración + control íntegro; cada alteración genera FAIL o INCOMPLETE con exit ≠ 0; control da PASS y exit 0.
- Campos económicos: E_net↔expectancy_net, exit_stop↔exit_reasons.stop, placebo_E_net↔baseline expectancy_net — 60 celdas, 0 discrepancias (rtol=1e-9).
- Tail-edge: 4/6 exclusiones esperadas verificadas (BTC 15m, SOL 15m, ETH 1h, SOL 1h); MINAUSDT/1h y NMRUSDT/1h conservados como INCOMPLETE (afectan solo al censo externo al replay, no a operaciones evaluadas).
- Suite completa: 1260 tests OK (2 skipped). Barrera de aislamiento: hashes_equal=True, file_writes=0, datos sin cambios.
- Parámetros registrados vs inferidos documentados en package_manifest.json.
- Pendiente: incorporar manifiestos temp/opencode a Git para cerrar el vínculo completo detección→operación y verificar los 2 tail-edge pendientes.


## Corrección de defectos restantes de la auditoría — 2026-10-19 (commit 2677b2f, rama review/o1-funcional-v2-observacion)

Corrige los defectos pendientes de la auditoría EVAL-CENSUS-V2 sin corridas Binance, sin forward, sin paper, sin órdenes, sin cambios de estrategia/mapping/costes/umbrales, sin modificar DBs canónicas, dashboard ni servicios. Temporales fuera de OneDrive. Suite completa 1274 tests OK (2 skipped). Barrera de aislamiento: hashes_equal=True, file_writes=0.

### 1. Tiempos obligatorios (vincular_trades_eventos)
- Campos requeridos validados: entrada efectiva finita (entry_ms), disponibilidad efectiva (available_at finita), H2: confirmación y cierre conocido de su vela (close_time_ms finita), salida/estado según contrato realizada o abierta.
- Ausencia o valor inválido → INCOMPLETE, nunca aceptación implícita (antes entry_ms ausente saltaba la comparación causal y close_time_ms ausente la evitaba en H2).
- Entrada anterior a disponibilidad → FAIL.
- No se deriva disponibilidad igualándola a la entrada.
- Respaldo verificado con símbolo, resolución, familia, dirección e identidad compatibles; clave de respaldo ahora incluye source_interval para no cruzar detecciones de resoluciones distintas que compartan símbolo y timestamp.
- Devuelve discrepancias (FAIL) e incompletos (INCOMPLETE) por separado.

### 2. Reconstrucción fail-closed (reconstruct_replay_traces.py)
- Una celda fallida no genera trazas consumibles como "verificada": solo las operaciones de celdas equivalentes van a trades_*.json; las de celdas falladas van a diagnostico_celdas_fallidas.json, etiquetado explícito FALLIDA_NO_CONSUMIBLE, que el ledger rechaza.
- reconstruction_manifest.json registra veredicto (COMPLETO si todas las celdas, else FAIL), cobertura, celdas_fail, trades_sha256 y inputs_sha256.
- Antes de escribir, limpia trazas/manifiestos/diagnóstico de ejecuciones previas en out-dir (no deja archivos antiguos que parezcan de la nueva reconstrucción).
- El ledger valida el manifiesto de trazas (veredicto COMPLETO, cobertura de los 6 combos, hashes de trades, sin faltantes/extra/obsoletos, cada archivo consumible) ANTES de consumirlas; un manifiesto FAIL, hash mismatch, archivo faltante, extra o no consumible → rechazo (FAIL/INCOMPLETE, exit ≠ 0).

### 3. Modo temp
- events_pre definido: n_in_pre_purge documentado (conteo pre-purge en modo --temp-dir).
- --package: inputs ya post-purge, sin segunda purga (segunda_purga=false).
- Exactamente uno de --package / --temp-dir obligatorio; ausencia o ambos → error de uso (exit 2).
- Equivalencia demostrada entre ambos modos sobre inputs correspondientes (orden, identidades, purga, resultados idénticos).

### 4. Pruebas de integración obligatorias (cadena reconstructor → archivos → ledger)
Nuevos tests en tests/test_cli_fixtures.py y tests/test_reconstruct_replay_traces.py. Para cada caso, estado y exit esperados vs observados; los defectos producen FAIL/INCOMPLETE y exit ≠ 0; el control válido pasa dentro de su alcance:
- entry_ms ausente → INCOMPLETE, exit ≠ 0.
- entry_ms no finito → INCOMPLETE, exit ≠ 0.
- H2 con close_time_ms ausente → INCOMPLETE, exit ≠ 0.
- Entrada anterior a disponibilidad → FAIL, exit ≠ 0.
- Respaldo de resolución incompatible → INCOMPLETE, exit ≠ 0.
- Celda con resultado económico alterado → FAIL, exit ≠ 0.
- reconstruction_manifest con FAIL → ledger rechaza trazas → FAIL, exit ≠ 0.
- Archivo de trades alterado después de reconstruir (hash mismatch) → FAIL, exit ≠ 0.
- Archivo de trades obsoleto de ejecución previa (extra) → FAIL, exit ≠ 0.
- Archivo esperado ausente → INCOMPLETE, exit ≠ 0.
- Control íntegro → PASS, exit 0.
- Ambos modos de reconstrucción (package y temp-dir) equivalentes → exit 0.

### 5. Checkout limpio y alcances (desde commit 2677b2f)
a. Hashes del paquete publicado docs/evidence/eval-census-v2-package/: 33/33 archivos OK (PASS), sha256 vs package_manifest.json coinciden.
b. Regeneración de trades (--package): exit 0, veredicto COMPLETO, 168 celdas ok / 0 fail, 6 trades_*.json.
c. Ledger con esas trazas: exit 1 (INCOMPLETE, no PASS), veredicto global INCOMPLETE, 0 discrepancias, trazabilidad_operaciones COMPLETO, n_trades_revisados=5255.
d. Comandos, estados, exits y hashes registrados en C:\proyectos\binance-temp\audit_checkout_20261019\verificacion_checkout.txt (fuera del repo).

### Veredictos separados (no rebajados)
- Replay evaluado BTC/ETH/SOL: PASS dentro de su alcance explícito (6 celdas-combo, 168 celdas, equivalencia por celda, 5255 trades escala 1x reconciliadas, trazabilidad COMPLETO, 0 discrepancias).
- Censo extendido MINA/NMR y otros símbolos: INCOMPLETE (tail-edge de MINAUSDT/1h y NMRUSDT/1h no verificable: falta build_report para esos símbolos; no es un defecto del replay, es un gap de evidencia del censo externo al replay).
- Veredicto global del ledger: INCOMPLETE (0 discrepancias, 2 incompletos declarados), exit 1. No se declara "auditoría completa" mientras esos 2 vínculos sigan abiertos.

### Residual MINA/NMR (preciso)
- Falta exactamente: build_report.json que cubra MINAUSDT/1h y NMRUSDT/1h (interval 1h, counts.excluded_no_entry == 1 para cada uno) en el paquete de census extendido.
- Lo que permitiría verificarlo: el build_report del builder para esos símbolos/resolución, para que clasificar_tail_edge confirme excluded_no_entry == n_tail_edge (1 == 1) y los marque como exclusiones esperadas.
- Las detecciones de MINA/NMR ya están en census_1h_detections.jsonl del paquete; no se trata de "manifestos de temp" genéricos, falta el build_report que las ampare.
- Impacto: veredicto global INCOMPLETE, no PASS; replay BTC/ETH/SOL reportado por separado como PASS.

---

## Reconciliación documental — 2026-10-20 (presupuesto cero)

### Correcciones al informe previo (commit b9c2733 solo publicó 12 líneas en PAPER_LAB_PLAN_ETAPA5.md; no era reconciliación completa)

| Afirmación previa | Corrección | Evidencia de respaldo |
|---|---|---|
| "audit_public_data" / "39 tests" como entrega localizada | **audit_public_data NO LOCALIZADA** (ni en checkout ni en Git: `glob **/*audit_public_data*` → sin resultados). Los 39 tests son `tests/test_p14b_validation.py` (P1-14B.1–.11), real pero ajeno a esa entrega. | `git grep audit_public_data` vacío; conteo `def test_` en test_p14b_validation.py = 39. |
| Esquema operativo descrito como v9 vigente | Operativo = **schema v10** (22 tablas); histórico = **schema v3** (16 tablas). v9 no es el estado operativo vigente. | `docs/DECISIONS.md` (línea ~1354): "operacional v10 (22 tablas), historico v3 (16 tablas)"; `docs/DASHBOARD_V2_27B7AF5_READ_HANDOFF.md`; `docs/ARCHITECTURE.md`. |
| 5255 trades sin desglose | Hipótesis 1x: **2991 trades** (5 abiertas → **2986 realizadas**), 4161 skipped_overlap. Placebo 1x: **2264 trades** (2 abiertas → **2262 realizadas**), 4888 skipped_overlap. Total: **5255 trades** (7 abiertas → **5248 realizadas**). `realizadas = trades − abiertas`. | `docs/ADDENDUM_CENSUS_EVAL_V2_CORRECCION.md` (tabla hipótese/placebo/total y línea 88); `docs/CURRENT_STATE.md` §Veredictos separados (n_trades_revisados=5255). |
| MFE/MAE presentado como ganancia | **MFE/MAE = excursión por posición, NO ganancia capturada por la salida.** Rango global 1x: MFE 0.0–1.04%, MAE 0.0–0.50%. Dirección n≥30: MFE 0.19–0.64%, MAE 0.16–0.42% (excursión, no captura). | `docs/CURRENT_STATE.md` (línea ~2217); `docs/BACKTEST_READ_CONTRACT_V1.md` (mfe_mean/mae_mean = excursión, salida alimenta MAE). |
| V2 vistas declaradas sin inspeccionar | `/movers` es **real** (MoversDashboard + canonicalMarket). `/paper-lab` renderiza **componente real** (PaperLabReplay). `/backtest` es **stub** (`FutureWorkspace kind="backtest"`, no real). | `frontend/src/app/movers/page.tsx`; `frontend/src/app/paper-lab/page.tsx`; `frontend/src/app/backtest/page.tsx`. |
| Paper Lab "no publicado" afirmado implícitamente | Confirmado explícito: **ningún archivo de Paper Lab publicado en Git** (`git ls-files` vacío para paper-lab-replay-v1.json, build_paper_lab_replay.py, paper-lab-replay.ts). Todo está **untracked** (trabajo de otro agente en curso). Artefacto determinista verificado: `build_paper_lab_replay.py --check` → PASS, sha256 `7ba452c308378c7f26a20b12761625dcace6b839ba7576d0221bba0346f41826`. No servido ni revisado visualmente por este agente. | `git ls-files` (vacío); re-ejecución --check estable; `docs/PAPER_LAB_PLAN_ETAPA5.md` sección "Estado actual". |

### Hechos de identidad y concurrencia (verificados 2026-10-20, sin reset/clean/force)
- Rama: `review/o1-funcional-v2-observacion`, al día con `origin/review/o1-funcional-v2-observacion` (`git fetch origin` sin cambios remotos nuevos).
- Remoto: `https://github.com/mariomoreta/binance-futures-microstructure-bot.git` (fetch + push).
- SHA inicial (este ciclo): `b9c27338dee21160da9a839894029c3c70b0e316`.
- Cambios locales preexistentes (NO creados ni staged por este agente): `frontend/src/app/paper-lab/page.tsx`, `TopNav.tsx`, `format.ts` (modificados) + untracked Paper Lab (componentes, tests, build script, artefacto). Se preservan sin tocar.

### Estado de Paper Lab (cuatro estados distinguidos, cierre funcional 2026-10-20, ver docs/PAPER_LAB_PLAN_ETAPA5.md)
1. Trabajo local: `frontend/src/components/paper-lab/`, `frontend/src/lib/paper-lab-replay.ts`, `frontend/src/app/paper-lab/page.tsx`, `scripts/build_paper_lab_replay.py`, `frontend/src/artifacts/paper-lab-replay-v1.json`, tests. No es motor de paper (sin position manager, ledger de caja, funding recurrente ni risk engine).
2. Código publicado en Git: artefacto, generador, parser/player, componentes, ruta y tests publicados con la entrega de 2026-10-20. `/backtest` sigue siendo stub.
3. Probado: `build_paper_lab_replay.py --check` PASS (sha256 `0db0c4d0…`, ver «Correcciones acotadas de Paper Lab (2026-10-20)» más abajo; el valor `96a5fa46…` de esta línea quedó superado); suite frontend 368/368; `tsc --noEmit` limpio; `eslint src` 0 errores. Tests de fronteras temporales t−1/t/t+1, estados, contexto y rechazos. Umbrales siguen siendo HIPÓTESIS.
4. Servido y revisado: build de Next servida en `127.0.0.1:3020/paper-lab` (sin monitor activo), sirve la operación LONG (`PLR-BTCUSDT-LONG-1788903900000`), no la SHORT obsoleta. Capturas desktop+mobile de los tres estados (`antes de entrada` / `abierta` / `cerrada`) generadas; verificación de contenido por árbol de accesibilidad + texto (el modelo es texto y las APIs de visión configuradas están caídas: NVIDIA 401, OpenRouter sin auth). La inspección **visual** de las PNG queda a cargo del revisor humano; no se fabrica un veredicto visual.

### Selector: no sobreestimar el censo
El censo EVAL-CENSUS-V2 evalúa reglas/variables que contiene; **no sustituye** universo histórico, ranking rolling24 ni liquidez ausentes. No se ejecuta evaluación completa del selector por faltar inputs. Se prepara protocolo de adquisición escalonado (universo ligero → candidatos → detalle limitado, fuentes gratuitas, sin colectores iniciados). Matriz detalle en `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md`.

### Próxima acción concreta
Definir y ejecutar (offline, sobre copia, presupuesto cero, sin órdenes ni capital) el protocolo de selección automática sobre EVAL-CENSUS-V2 (info disponible en T, sin lookahead, ventana incompleta → UNKNOWN), emitiendo WATCH / SIN_ENTRADA / DESCARTADO con motivo versionado. Es la dependencia previa al motor paper completo (Etapa 5).

---

### Correcciones 2026-10-21 (identidad del artefacto y estudio retrospectivo W/LUMIA)

- **Identidad del artefacto Paper Lab (verificada en código y en build servida):** **BTCUSDT 15m LONG H1** (no SHORT). `replay_id=PLR-BTCUSDT-LONG-1788903900000`, `event_time_ms=1788903900000` (2026-09-08T21:45:00Z), `entry_ms=1788904800000` (22:00:00Z), `exit_ms=1788907500000` (22:45:00Z, salida por `horizon`), `entry_px=78458.7`, `exit_px=78456.8`, `gross_pnl=-0.0242`, `net_pnl=-1.6242` (pérdida). Artefacto determinista en `frontend/src/artifacts/paper-lab-replay-v1.json` (sha256 `96a5fa46…`; **actualizado a `0db0c4d0…` el 2026-10-20, ver «Correcciones acotadas…»**); 3 velas + 5 pasos de evento (n_steps=8; **ahora 7 pasos: 3 velas + 4 eventos**) más 48 velas de contexto previo real (solo visuales).
- **Frontera de revelación causal (corregida 2026-10-20):** la cinta **separa pasos de vela de pasos de evento**. Una vela cerrada se conoce al cierre de la barra (marcas `.999`). Un **evento** (señal/disponibilidad/entrada/cierre) se revela en **su propio paso, en su ms exacto**: un evento a `04:00:00.000` **no** es conocido con cursor `03:59:59.999` ni se adelanta al cierre de la vela. La propuesta previa (revelar todos los eventos en el paso de cierre) era incorrecta y queda corregida. Invariante `event.at_ms <= step.known_at_ms` verificada por el generador y el parser.
- **Estudio retrospectivo W/LUMIA (auditoría, sin segunda implementación):** paquete `binance_case_study/` (12 archivos, hashes 12/12 OK). 1.499 velas 5m cerradas + 1.499 velas 1m cerradas por símbolo (WUSDT, LUMIAUSDT, BTCUSDT, GTCUSDT), corte `2026-10-12T10:57:19.690Z` (~5,2 días). `fundingIntervalHours=4` real para WUSDT/LUMIAUSDT frente al fallback `FUNDING_INTERVAL_MS = 8h` (**corregido 2026-10-20:** el motor **ya acepta un `FundingCalendar` por contrato** — `src/microstructure_probe/backtest_offline.py`, `class FundingCalendar` — y `8h` es solo el fallback cuando no se inyecta calendario; su `interval_ms` es cadencia nominal informativa y la contabilidad usa las liquidaciones realizadas). Por tanto la fidelidad se logra **inyectando el `FundingCalendar` real** de cada contrato, no cambiando la constante global; datos ausentes → UNKNOWN o exclusión. No cambiar el 8 global por 4 ni duplicar la contabilidad. Casos documentados como `NOT_SIGNAL` (ex-post high/low no es señal); WUSDT subió sobrecomprada antes de corregir (−10,97% máx→último cierre); LUMIAUSDT ganadora de 24h que cayó y rebotó sin recuperación duradera. Sesgo de selección retrospectiva declarado. Sin OOS, sin calibración, sin rentabilidad. `Casos_Binance_W_LUMIA.png` no inspeccionada visualmente (`NOT_ASSESSED`).
- **Qué falta para mostrar esos casos:** calendario de funding real por símbolo y tasa liquidada; spread/profundidad/coste estimado; fills reales; serie OOS; partición cronológica; vinculación `run_id`/`event_id` con `as_of`; snapshot por evento con hash del dataset. Sin calibrar reglas ni seleccionar ejemplos por beneficio.

### Correcciones acotadas de Paper Lab (2026-10-20, sobre `d9359e3`)

- **Artefacto nuevo (determinista):** `frontend/src/artifacts/paper-lab-replay-v1.json`, sha256 **`0db0c4d0cf1767736cbeafbae62e12a10adce512e423520bb5046c58dfbfff99`** (sustituye a `96a5fa46…`). `build_paper_lab_replay.py --check` → **PASS**. `replay_id=PLR-BTCUSDT-LONG-1788903900000` sin cambios.
- **Causalidad de revelación (formación vs disponibilidad):** el paso de `signal` en `event_time_ms` (21:45) queda **eliminado**; revelaba un patrón no conocible hasta su disponibilidad (21:59:59.999). Ahora hay un único paso de evento `detection` en `available_at`, que **muestra `formation_time_ms` como metadata** («Detección conocida (formación conservada como metadata)»). Nuevo `initial_cursor_ms` (= último cierre de contexto) define el instante inicial **anterior** a la detección; la vista inicial muestra el contexto ya conocido a ese instante. Invariantes verificadas por generador y parser: `event.at_ms <= step.known_at_ms`; `formation_time_ms <= detection.at_ms`; ninguna detección con reloj `< available_at`.
- **Cinta de pasos:** pasa de 8 a **7 pasos** (`candle formacion → detection → entry → candle → candle → candle → exit`); 3 velas + 4 eventos. Los valores económicos **no cambian** (`gross=-0.02421656234419101`, `net=-1.6241971890943157`, `fees=0.9999878917188278`, `funding=0.0`); la corrección es de visualización/revelación, no de mecánica.
- **Metadatos visible fija vs revelada:** la cabecera de identidad (símbolo, dirección·familia, intervalo, `replay_id`) se rotula explícitamente como **«escenario seleccionado offline»** (no detección automática); el panel «Revelación de la detección» muestra Estado = «Detección aún no conocida» / «Detección revelada».
- **Estado del reproductor separado del de posición:** nuevos `playerState` `sin_iniciar`/`reproduciendo`/`pausado`/`terminado` (etiquetas SIN INICIAR / REPRODUCIENDO / PAUSADO / TERMINADO). Avanzar manualmente ya **no** muestra «REPOSO» con posición abierta: aparece PAUSADO + posición ABIERTA; el botón principal ofrece «Reanudar» cuando corresponde (nombre accesible coherente con la acción). Reiniciar restablece ambos.
- **Gráfico responsive y etiquetas:** SVG con `viewBox` + `width:100%` + `preserveAspectRatio` (escala a 360/390px sin recorte derecho). Etiquetas de nivel con **anti-solape** (se desplaza solo el texto, no la línea/los precios reales) + leyenda identificable. Frontera contexto/replay marcada en la **primera vela del replay** (no el inicio de toda la serie). Eje de precios con margen para no recortar extremos. Verificación geométrica de DOM (no visual): 360/390/1440px sin overflow de página, 0 elementos fuera del viewport, 0 textos SVG fuera del viewBox, entradas+stop visibles.
- **QA:** suite frontend **368/368** (55 archivos); `tsc --noEmit` limpio; `eslint src` 0 errores (3 warnings preexistentes en `RunStatusBar.tsx`/`BotControl.tsx`); `next build` OK, `BUILD_ID=45NLJvJuWqcMjj2IFxW-E`. Servido en `127.0.0.1:3020/paper-lab` (solo el servidor del proyecto reemplazado; **sin monitor** activo): HTTP 200, `replay_id` LONG presente, BUILD_ID presente. **Inspección visual de las PNG = límite declarado** (modelo texto; NVIDIA 401, OpenRouter sin auth): verificación por DOM/texto, no PASS visual.

### Correcciones de la entrega Backtest → Paper Lab (2026-10-20; bloques A/B/C, sobre `4e61587`)

**Bloque A — Serialización portable del paquete (commit `84e6294`).**

- **Defecto real (auditoría independiente, reproducido):** en checkout limpio Linux, 21/33 archivos del paquete no coincidían con `package_manifest.json`. Causa raíz: sin `.gitattributes` y con `core.autocrlf=true`, git normalizaba a LF en el blob; `build_eval_package.py` había hasheado bytes CRLF. Los 12 restantes son archivos sin salto de línea interno (LF puros), de ahí que solo 21 fallaran.
- **Corrección:** `.gitattributes` raíz marca `docs/evidence/eval-census-v2-package/**` y su `package_manifest.json` como `-text` (binario). Paquete renormalizado para almacenar los bytes exactos que declara el manifiesto. Verificación estricta por sha256 sin normalizaciones silenciosas.
- **Verificado:** 33/33 blobs del commit hashean al manifiesto; `verify_eval_package.py` PASS desde worktree limpio con `core.autocrlf=false`; ejecución desde ese checkout: `trades=15765`, `n_trades_1x=5255`, `reconciliacion=True`, `trades.json` sha256 `815b8a650a6365dfeb24dbc0fac456462c1ea04079f963209711d20d902cfa85` (byte-idéntico); alteración real de un byte → verify FAIL (exit 1) + ejecutor fail-closed (`PACKAGE_VERIFICATION_FAILED`, exit 3, sin `trades.json`).
- **Regresión:** `tests/test_dashboard_backtest.py::PackagePortabilityTest` (5 tests). Falla antes del fix.
- **Límite:** plataforma verificada = Windows + worktree con `core.autocrlf=false` (equivalente Linux por bytes de blob). No se probó una máquina Linux real. Reproducibilidad NUMÉRICA ≠ igualdad de BYTES: el defecto era el segundo.

**Bloque B — ejecución, resultados y ubicación (commit `76763d7`).**

- **Identidad única de ejecución:** `run_id` propio por solicitud (`bt-<experiment>-<ts>-<rnd>`), separado del `experiment_id`; `job_id` = run. Estado en `backtest-results/<experiment>/<run_id>/` + puntero `current.json`.
- **Exclusión entre procesos:** lock por archivo con creación exclusiva (`O_EXCL`). Un lock vivo no se puede duplicar ni por doble clic ni desde otro proceso; un lock abandonado (pid muerto/presupuesto vencido) se cierra como fallido **sin relanzar**.
- **Propiedad verificable:** solo `executor_token`+`executor_pid`+`started_at_ms` juntos prueban identidad. PID vivo ajeno/reutilizado → `PROCESS_IDENTITY_UNKNOWN`, nunca `ejecutando`, nunca se mata.
- **Presupuesto efectivo** (`BACKTEST_BUDGET_MS`): aplicado en el ejecutor (deadline → `TIMEOUT`, fail-closed) y en lectura. Error asíncrono de `spawn` → `SPAWN_FAILED` persistido.
- **Resultados/caché vinculados a la ejecución:** hashes verificados antes de servir (`RESULT_INTEGRITY_FAILED`/`RESULT_INCOMPLETE` explícitos); `?run=<run_id>` para dirigir a una ejecución concreta; artefacto de replay nombrado por `run_id`+hash+identidad y la operación debe pertenecer a esa ejecución (`TARGET_NOT_IN_RUN`).
- **Ubicación canónica única:** `<repo>/backtest-results/` (ignorado por git), coincidiendo código y contrato. Evidencia previa **preservada** en `backtest-results/_legacy/`; ruta heredada `frontend/.backtest-runs/` mantenida e ignorada. Nada borrado. Retención acotada que nunca elimina una ejecución activa.
- **Defecto adicional corregido:** `PaperLabSource` ya no muestra la operación anterior durante carga/fallo de una identidad nueva.
- **Verificado:** `pytest tests/test_dashboard_backtest.py` 16 OK; frontend vitest 418/418; `tsc` limpio; `eslint` 0 errores (3 warnings preexistentes); `next build` OK (`BUILD_ID=wzsmXGqnMRh6hnIP_xAan`). Ejecución real del ejecutor con los nuevos argumentos: `identity=verified`, `run_id` propio, `result_hashes` coincidentes, `trades.json` sha256 `815b8a65…` (sin cambio).


## Cierre del bloque F-CHART-BINANCE-04 (2026-10-24, base `965ab87`, sin nueva ventana)

**Causa demostrada.** El BFF devolvía `upstream.body` en crudo: no declaraba fin ni
error del upstream, no emitía causa y no abortaba el upstream al cancelar el
cliente; con el SSE abierto el navegador no tenía señal de que el feed había
muerto. El hook, ante `onerror`, solo incrementaba `attempts` (sin cambio
visible) y derivaba `LIVE` de un `status` congelado: sin mensajes nuevos podía
parecer vivo o quedarse mudo sin causa hasta agotar 6 reintentos (≈30 s) o
indefinidamente. El `consumers_tras_cerrar = 1` de la ventana era el propio
navegador (consumidor legítimo con la pestaña abierta); la parada forzada del
proceso no se usa como prueba de liberación.

**Corrección.** BFF con `AbortController` + `req.signal`, bombeo de frames,
`event: error` con `STREAM_UPSTREAM_CLOSED`/`STREAM_UPSTREAM_ERROR`, `cancel()`
aborta el upstream. Hook con frescura local (ticker 1 s: `STALE` > 10 s,
`DISCONNECTED` > 60 s, `LIVE` = `live && age <= fresh`) y causa inmediata en
`onerror`/`event: error` con código. Servicio: al cerrar el cliente se despierta
el bucle del consumidor (sin esperar el heartbeat de 5 s). Paginación: se pide el
bloque estrictamente anterior (`to = anchor - step`, `from = to - 299·step`) y se
antepone con `mergeEarlierSeries` (dedupe por `open_time`, gana la fila cargada,
cobertura/huecos recalculados, `added` = únicas); `added === 0` marca
`earlierExhausted`; no se exige `+300`.

**Medido con transporte controlado (WS falso local + servicio real + BFF real,
cero Binance).** Cliente cierra con el servicio vivo: consumidores 1 → 0 en
**14 ms**. Servicio se detiene: EOF en el cliente + `event: error`
`STREAM_UPSTREAM_ERROR` en **6025 ms**. DOM real del panel: `LIVE` con el feed
controlado y **12 ms** tras `POST /shutdown` → `DESCONECTADO`, `no LIVE` y causa
visible. Evidencia: `docs/evidence/market-stream-controlled-disconnect-2026-10-24.json`,
`docs/evidence/market-lab-controlled-disconnect-2026-10-24.json` (+ PNG) y
`docs/evidence/market-lab-disconnect-planes-2026-10-24.md`.

**Paginación `300→303`.** Con copia de la caché y sin red: con el bloque anterior
ausente, la petición antigua devuelve otra vez la ventana reciente (302
solapadas, 0 nuevas) y el contador solo crece por el stream (300 → 303 medido);
la petición nueva devuelve 0 (no hay historia) y no finge crecimiento. Con el
bloque almacenado, la petición nueva devuelve exactamente 300 anteriores (0
solapan) y el merge conserva el extremo reciente. Evidencia:
`docs/evidence/pagination-300-303-2026-10-24.json`. Exigir `+300` era un
criterio equivocado.

**Pruebas.** `tests/test_market_stream.py` 29/29 (incluye liberación inmediata al
cerrar el SSE); `tests/test_market_stream_window.py` 25/25; frontend focalizado
28/28 (BFF 8, hook 10, explorador 10); `market-chart-contract` 13/13;
`tsc --noEmit` 0; `eslint` 0 en los archivos tocados; `next build` OK.

**Estado servido.** `BUILD_ID=XozH8PXJA4yZR59XphpyH`, dashboard PID 33444 en
`127.0.0.1:3020`, `/market-lab` HTTP 200; servicio `8791` **detenido**; DBs
canónicas intactas (solo se copió `market_cache.db` a temp para la traza).

**Diagnóstico de seguridad Next.js (sin actualizar).** Instalado `next 16.4.0`
(lock 16.4.0; rango `^16.4.0`). Tres advisories: `GHSA-2464-fhr4-w9xw`
(critical, Image Optimization + SVG, glibc Linux), `GHSA-673q-mjm6-r5xr`
(critical, `use cache` con typed arrays) y `GHSA-p3m5-59mp-jv5r` (high, Server
Actions DoS); parcheadas en **16.4.1**. La app actual no cumple los prerrequisitos
(0 usos de `next/image`, `sharp` no instalado, win32, 127.0.0.1, 0 `"use cache"`,
0 `"use server"`). El `next build` se detiene una vez con el aviso de seguridad y
completa al reintentar. Evidencia:
`docs/evidence/nextjs-security-diagnosis-2026-10-24.json`. Actualización
**no ejecutada** (prohibida por el operador en este bloque).

**Veredicto.** El `FAIL` medido de la ventana sigue siendo el veredicto de
`F-CHART-BINANCE-04`; la corrección se acredita por separado con transporte
controlado. Repetir la ventana requiere autorización explícita.

**Desviaciones declaradas.** Durante el diagnóstico se arrancó dos veces el
servicio sin `--base-url` (inspección del DOM y sonda SSE): abrió el WS público
de Binance ~9 s y ~30 s, sin claves, sin API privada y sin órdenes; no es una
ventana de aceptación y **no se usa como evidencia**. Además, una página
`/market-lab` con `0GUSDT` 1h seleccionado encadenó 12 peticiones REST públicas
(`01:43:47Z`–`01:44:18Z`) que **añadieron 3.552 velas** a la caché derivada
`data/market-cache/market_cache.db` (`0GUSDT` 1h: 47 → 3.599 filas; 12 filas en
`market_fetch_ledger`), sin perder filas previas. Las DBs canónicas
(`microprobe.db`, `historical.db`) siguen intactas (mtime 2026-10-15); la caché
es derivada y las velas son historia real. Se ejecutó
`wal_checkpoint(TRUNCATE)` para dejarla consistente. El veredicto de la ventana
no cambia. Riesgo residual: una sola interacción puede encadenar varias
descargas de "anteriores" (12 medidas); pendiente de investigar.

**Límites.** Las capturas controladas no acreditan recepción real (eso sigue
acreditado solo por la captura #1 de la ventana); inspección visual
`NOT_REVIEWED` (modelo de texto, sin proveedor de visión); repetición de la
ventana pendiente; los 5 `high` de cadena de desarrollo siguen sin abordar.

## Transporte aislado y paginación acotada — cierre de los dos defectos (2026-10-24, base `5dec9ff`, sin ventana)

**1. Transporte falla cerrado (causa de las conexiones accidentales).** El
servicio construía `BinanceKlineTransport()` (endpoint público) y
`build_recovery(_rest_client())` cuando no había `--base-url`: los dos arranques
"de diagnóstico" del bloque anterior abrieron el WS público sin declararlo. Ahora
`--transport` es obligatorio: `local` exige `ws://127.0.0.1|localhost|::1:<puerto>`,
desactiva la reparación REST y no tiene fallback; `public` es la activación
explícita. Sin transporte válido el proceso sale con código 2
(`TRANSPORT_CONFIG`) antes de abrir nada. El orquestador de ventana pasa el modo
y `/health` publica `transport.mode`/`transport.base_url`. Evidencia:
`docs/evidence/market-stream-transport-failclosed-2026-10-24.json` (6/6 casos
inválidos → exit 2) y `tests/test_market_stream_transport.py` (13/13; el test de
runtime arranca el servicio real sobre un WS falso local y verifica cero
resoluciones de `fstream.binance.com` y liberación del consumidor).

**2. Paginación: disparador identificado y acotado.** La cadena de 12 peticiones
(`market_fetch_ledger` ids 42–53, `1792806227319` → `1792806258691`, 31,4 s) se
disparaba desde el evento de rango: al anteponer un bloque, si el feed había
actualizado la última vela, `isSuffix()` fallaba, no se desplazaba el rango
lógico y la vista caía sobre el bloque recién antepuesto (borde izquierdo), que
volvía a pedir otra página; cada vuelta cambiaba el ancla y saltaba el guard
anterior. Reproducido en `price-chart-market.test.tsx` ("anteponer con el extremo
reciente actualizado"). La primera interacción de la cadena sigue `UNKNOWN`: la
evidencia de la ventana no registra acciones de UI. Corrección: (a) la descarga
se decide al terminar un gesto (rueda con debounce 250 ms, `pointerup`, `keyup`)
con `frontend/src/lib/earlier-gate.ts` (gesto nuevo, cooldown 600 ms, borde,
ancla distinta o intento fallido); (b) el encuadre se conserva por índice exacto
de la primera vela previa, aunque el extremo reciente cambie; (c) el explorador
usa guard síncrono de petición en vuelo y clave de rango, distingue cancelación /
agotamiento / fallo y conserva el gráfico con reintento manual.

**Segunda observación del mismo defecto (previa a la corrección).** `ACTUSDT` 1h
encadenó 6 peticiones REST públicas el 2026-10-24 entre `12:07:10.299Z` y
`12:07:27.733Z` (17,4 s, ids 54–59 del `market_fetch_ledger`) y añadió 1.799
velas a la caché derivada (el símbolo no tenía filas). Cliente `UNKNOWN`; no
consta ninguna ejecución de navegador en este bloque. Evidencia:
`docs/evidence/market-lab-pagination-cascade-2026-10-24.json`, que también fija
la cadena de 12 de `0GUSDT` (ids 42–53, 31,4 s).

**Pruebas.** Backend: `tests/test_market_stream.py` 29/29,
`test_market_stream_window.py` 25/25, `test_market_stream_transport.py` 13/13.
Frontend focalizado: gate 5/5, `price-chart-market` 9/9 (incluye la regresión de
múltiples eventos de rango tras anteponer → una sola petición), explorador 12/12
(dos clics en el mismo tick → una petición; fallo → gráfico conservado +
reintento), contrato 13/13. `tsc --noEmit` 0, `eslint` 0 en los archivos tocados,
`next build` OK (un aborto esperado por el aviso de seguridad y reintento).

**Estado servido.** Dashboard reiniciado sobre el build nuevo: PID 32712,
`BUILD_ID=y_fx2dQ35CUiQeOHtUhfl` presente en el HTML de `/market-lab` (HTTP 200);
servicio 8791 **detenido**; sin ventana Binance. DBs canónicas intactas
(`microprobe.db`/`historical.db` mtime 2026-10-15); no se borró evidencia previa.

**Seguridad Next.js (verificada, sin actualizar).** Tres advisories consultadas
en la API oficial de GitHub (`api.github.com/advisories`):
`GHSA-2464-fhr4-w9xw` (critical; `next >=16.0.0 <=16.4.0`, parche `16.4.1`;
requiere Image Optimization con SVG + `sharp < 0.35.5` + Linux glibc),
`GHSA-673q-mjm6-r5xr` (critical; `>=16.0.0 <=16.4.0`, parche `16.4.1`; requiere
`use cache` con typed arrays) y `GHSA-p3m5-59mp-jv5r` (CVE-2026-94482, high;
`>=16.0.0 <=16.4.0`, parche `16.4.1`; requiere al menos una Server Action).
Contraste con `package-lock.json`: `next 16.4.0` (afectado), `sharp 0.35.5`
instalado (versión del workaround), `server-reference-manifest` sin acciones
registradas, `next.config.ts` sin `cacheComponents`; sondas en el servidor real:
`/_next/image` con SVG local y remoto → 400, POST de Server Action → 400. No se
deduce solo por búsqueda de texto. Actualización a 16.4.1 **no ejecutada**.
Evidencia: `docs/evidence/nextjs-security-diagnosis-2026-10-24.json`.

## Aceptación local automatizada: dos recorridos consecutivos PASS (2026-10-24, base `6be44b9`, sin ventana Binance)

**Hecho.** El procedimiento completo `WS público -> servicio SSE -> BFF ->
/market-lab` se ejecutó dos veces consecutivas con transporte loopback y
aislamiento de red real, sin abrir ninguna ventana Binance. Ambos recorridos
terminaron `PASS` procedural y el finalizer dio `PASS` con `failed=[]` y
`missing=[]`. Evidencia: `docs/evidence/local-acceptance-2026-10-24/`
(`summary.json`, `run-1/`, `run-2/`), con
`summary.git_sha=6be44b96b11a9362f2ec128947034f782726e971`,
`build_id=FE1Eg1exjGrbZJpHz5vRO`, `transport=loopback_test` y
`binance_accredited=false`.

**Arnés.** `scripts/market_stream_local_acceptance.py`: cache temporal
(`MICROPROBE_MARKET_CACHE_DB`) con 2 contratos (1m 7 días, 1h 30 días) y
catálogo de 2 entradas; raíz sombra `MARKET_EXPLORER_ROOT` con
`sitecustomize.py` que bloquea/registra conexiones no loopback y wrapper del
explorador con `--no-fetch` (`fetch.allowed=false`,
`catalog.refresh.reason=DISABLED`); proxy 8793 que registra/rechaza intentos
públicos; allowlist del navegador solo `127.0.0.1:3020`; WS falso 8794 en reloj
real; servicio real 8792 con `--transport local`; dashboard en 3020. Fases con
máximo propio y límite global 180 s; sin esperas manuales de 20 s.

**Resultado.** Recorrido 1: 83.0 s; recorrido 2: 115.5 s. Cero intentos
públicos (`proxy=0`, `guard=0`, `browser=0`), cero consumidores residuales,
parada limpia, paginación `298 -> 599` con 1 petición y 300 aperturas nuevas
únicas, amplitud de ventana preservada, actualizaciones ≤10 s con el servicio
vivo, reconexión `consumers=0 -> 1` con `updated` posterior (2 intentos, ~3.8 s
observados) y aviso `explorer-stream-down` con causa real (`TypeError:
ECONNREFUSED`), 599 velas conservadas y `nav=1`/`reload=0`. El
`orchestrator_exit=2` es el `UNKNOWN` previo al `--finalize`; no es el veredicto.

**Correcciones de soporte (sin cambios económicos).**

1. `scripts/market_stream_window.py`: `--post-reconnect-signal` mantiene el
   servicio vivo tras `consumers=1` hasta la captura DOM de reconexión;
   `--dashboard-url` usa host/puerto reales; `_service_env` conserva el
   `PYTHONPATH` del arnés.
2. `frontend/src/lib/use-market-stream.ts`: al error del `EventSource` con el
   stream abierto consulta el endpoint de estado; si `available=false`, cierra
   y declara el aviso con la causa real. El 503 JSON del BFF es fatal para
   `EventSource` (no reintenta), por lo que sin esta consulta el aviso no
   aparecía. La causa de frescura no sobrescribe el aviso terminal.
3. `ContractExplorer` incluye el detalle real en el aviso.

**Pruebas.** Backend: 71/71 (`test_market_stream_window` 29,
`test_market_stream_transport` 13, `test_market_stream` 29). Frontend
focalizado: 23/23 (`use-market-stream` + `contract-explorer`), `tsc --noEmit`
0, `eslint` 0 errores (5 avisos preexistentes). La integración son los dos
recorridos del arnés.

**Estado servido (canónico).** Dashboard reiniciado sin el entorno de prueba:
PID 30216 en `127.0.0.1:3020`, `BUILD_ID=FE1Eg1exjGrbZJpHz5vRO` en
`/market-lab` (HTTP 200), `/api/v1/market-contracts` devuelve 931 entradas
(catálogo canónico, no las 2 de prueba), `/api/v1/market-stream/status` HTTP 200
`available=false` y servicio 8791/8792 detenido. DBs canónicas intactas; sin
monitor, paper, órdenes, pagos ni móvil.

**Límite.** El WS es falso y loopback: este PASS **no acredita recepción de
Binance**. El check `transport_origin` es `required=false` y queda `ok=false`;
la acreditación real sigue exigiendo `--transport public` y autorización humana
explícita. La actualización de Next.js 16.4.1 sigue **no ejecutada**.

## Integración del parche de seguridad Next.js 16.4.1 (2026-10-24, SHA integrado `9991552`)

**Rama integrada.** `review/o1-nextjs-16.4.1-security` hasta `9991552` se integró en
`review/o1-funcional-v2-observacion` por **fast-forward** (destino `2703891` era ancestro
del origen; no hubo divergencia, ni merge, ni reset, ni force). Push normal a
`origin/review/o1-funcional-v2-observacion`.

**Alcance publicado.** Solo dos archivos de dependencias más la evidencia del
recorrido aislado:
- `frontend/package.json`: `next` `^16.4.0` → `^16.4.1`.
- `frontend/package-lock.json`: `next`, `@next/env` y los ocho `@next/swc-*` de
  plataforma a `16.4.1` (82 líneas cambiadas; sin `npm audit fix`, sin `--force`,
  sin upgrade general).
- `docs/evidence/local-acceptance-2026-10-24-nextjs-16.4.1/`: un recorrido
  automatizado PASS con transporte loopback, cero peticiones públicas.
- No hay archivos ajenos ni cambios de producto en el commit de seguridad.

**Verificación.** `npm ci` desde el lockfile (exit 0); `next build` completó al
primer intento con Next.js 16.4.1 y sin `SecurityFatalError`;
`npm audit --omit=dev` → 0 vulnerabilidades (2 altas restantes solo en la
cadena de desarrollo: undici vía jsdom, zod vía plugins de ESLint). Pruebas de
mercado/SSE/Paper Lab/Backtest ya acreditadas en el worktree (247 passed, 1
skipped) y no repetidas por no haber cambios de producto.

**Despliegue.** Instancia previa del dashboard en `127.0.0.1:3020` (PID 31312)
detenida y reemplazada únicamente por esa instancia del proyecto (ahora PID
21512), sin afectar monitor, backtest ni sesiones. Variables de ensayo y proxies
eliminadas del entorno antes de arrancar.

**Estado servido (canónico).** `BUILD_ID=r1bBrZkP65q5w79uMhJsF` (lítera, coincide
en `/market-lab`); Next.js 16.4.1. Endpoints comprobados: `/market-lab` 200,
`/paper-lab-live` 200, `/paper-lab` 200, `/backtest` 200.
`/api/v1/market-contracts` devuelve 931 entradas desde caché; 
`/api/v1/market-stream/status` HTTP 200 `available=false` (servicio de stream
detenido, no se arrancó). Solo el puerto 3020 ocupado; 8791/8792/8793/8794
libres, sin procesos residuales de ensayo.

**Límites.** Sin conexiones públicas Binance, sin nueva ventana, sin monitor,
sin paper prospectivo, sin órdenes, sin pagos, sin móvil, sin cambios
económicos. Los DBs canónicos y los archivos ajenos se preservaron.

**Estado del parche de seguridad (2026-10-24).** Parche de seguridad integrado
y servido; aceptación real automatizada del gráfico pendiente.

**Acreditación de Binance en modo `--transport public`.** Activar
`--transport public` por sí solo **no acredita** recepción de Binance. El
arnés solo acredita (`binance_accredited = true`) cuando el servicio recibe e
identifica eventos reales de Binance: identidad exacta
(`venue=binance`, `market_type=usd_m_futures`, símbolos `BTCUSDT`/`MINAUSDT`,
intervalo `1m`) y al menos un mensaje de vela del símbolo primario. En modo
`local` (loopback) `binance_accredited` es siempre `false` y el PASS no
acredita recepción de Binance. La ventana pública sigue sin ejecutarse; queda
pendiente de autorización humana explícita.

**Preflight cerrados antes de la ventana pública.**

1. **Presupuesto REST efectivo (máximo 2 solicitudes de velas, 300 cada una,
   incluyendo carga inicial, paginación y recuperación).**
   - `scripts/market_stream_window.py` arranca el servicio en modo public con
     `--no-recovery`: la reparación REST queda desactivada, por lo que el
     servicio no realiza solicitudes públicas de velas de recuperación.
   - `src/microstructure_probe/market_stream_service.py` acepta
     `--no-recovery` y fuerza `recovery=False` incluso en modo public.
   - `scripts/market_stream_local_acceptance.py` rastrea
     `rest_market_requests` (peticiones a `/api/v1/market-series`) y exige
     `rest_market_budget <= 2`. Cualquier hueco de cobertura impide PASS
     (check `coverage_intact` del evaluador).
   - Verificado con transporte local: regresión PASS, `rest_market_budget:
     true`, `global_deadline_respected: true`, `zero_public_attempts: true`.

2. **Entorno del dashboard.** `MICROPROBE_STREAM_URL` debe heredarlo el
   proceso Next.js al arrancar; establecerlo solo en la terminal del arnés no
   modifica el servidor existente. Para la ventana pública se sustituye
   únicamente la instancia del dashboard en `127.0.0.1:3020` (PID identificada
   por puerto), tras comprobar ausencia de trabajos activos de monitor,
   backtest o sesiones. Se conserva el valor anterior y se restaura el servidor
   con su configuración original tras la ventana; no basta con `Remove-Item` en
   la terminal.

**Procedimiento de la próxima ventana Binance (preparado, no conectado).**
Comando (PowerShell, ruta absoluta bajo `$env:TEMP`):

```powershell
$env:MICROPROBE_STREAM_URL = "http://127.0.0.1:8792"
python -X utf8 scripts/market_stream_local_acceptance.py --transport public `
    --runs 1 --out-dir docs/evidence/local-acceptance-2026-10-24-public `
    --workdir "$env:TEMP\opencode\market-acceptance" `
    --dashboard-url http://127.0.0.1:3020 --service-port 8792 `
    --duration 75.0 --hold-seconds 20.0 --await-timeout 45.0 `
    --release-timeout 15.0 --reconnect-timeout 15.0
# Restaurar entorno: quitar MICROPROBE_STREAM_URL tras la ejecución
Remove-Item Env:MICROPROBE_STREAM_URL -ErrorAction SilentlyContinue
```

Sustituye únicamente la instancia del dashboard en `127.0.0.1:3020`
(PID identificada por puerto; comando `npm start` en `frontend/`). No hay
trabajos activos de monitor, backtest ni sesiones que se vean afectados.

**Diagnóstico y corrección del fallo de la ventana pública (SHA `5fd7a29`).**

**Causa demostrada:** El navegador no encontraba
`[data-testid="explorer-open-BTCUSDT"]` porque el catálogo canónico tiene 931
entradas y el explorador las devuelve paginadas (20 por página, orden
alfabético). BTCUSDT comienza por "B" y no aparece en la primera página (hay
contratos comenzando por "0" y "1" antes). El botón `explorer-open-BTCUSDT`
simplemente no existía en el DOM de la primera página.

**Corrección mínima aplicada** en `scripts/market_stream_local_acceptance.py`:

1. **Flujo de usuario real:** en lugar de esperar directamente el botón, el
   arnés ahora busca "BTCUSDT" en el input de catálogo, pulsa búsqueda y
   entonces espera y hace clic en `explorer-open-BTCUSDT`. Esto funciona
   con cualquier tamaño de catálogo.
2. **Preflight obligatorio:** antes de iniciar el servicio público, el
   navegador debe estar ya en BTCUSDT/1m con el gráfico cargado
   (`explorer-selected` contiene "BTCUSDT" y el interval selector vale "1m").
   Si el preflight falla, se aborta sin arrancar el servicio ni consumir la
   ventana.
3. **Verificación local:** dos recorridos consecutivos PASS con transporte
   loopback (83s y 115s), `preflight_ok: true`, `zero_public_attempts: true`,
   `rest_market_budget: true`, `global_deadline_respected: true`.

**Resultado del preflight:** PASS en ambos recorridos locales. El navegador
llega a BTCUSDT/1m con gráfico cargado antes de iniciar el servicio.

**Preflight contra el dashboard canónico (2026-10-25, SHA `d9e651a`).**
Evidencia: `docs/evidence/preflight-verify-2026-10-25/`.

Dos recorridos consecutivos PASS contra el dashboard canónico con catálogo real
de 932 contratos y solicitudes públicas bloqueadas:

| Run | Total (s) | page_open (ms) | catalog_state (ms) | search_and_select (ms) | interval_select (ms) | identity_and_graph (ms) | public_requests |
|-----|-----------|----------------|--------------------|------------------------|----------------------|-------------------------|-----------------|
| 1   | 2.465     | 183            | 67                 | 1320                   | 25                   | 9                       | 0               |
| 2   | 3.326     | 1092           | 62                 | 1232                   | 23                   | 9                       | 0               |

**Resultado de cada paso:**
- `/market-lab`: HTTP 200, `BUILD_ID=r1bBrZkP65q5w79uMhJsF` (Next.js 16.4.1)
- Catálogo: 932 entradas, estado "catálogo: consultando" (desde caché, sin refresco)
- Búsqueda "BTCUSDT": botón `explorer-open-BTCUSDT` encontrado y clickeado
- Identidad exacta: `BTCUSDT · BTC/USDT · PERPETUAL · TRADING · elegible`, fuente `binance · fapi · /fapi/v1/klines · origen de las velas: klines`
- Intervalo: `1m`
- Gráfico: vela provisional desde caché (candles_count=0, servicio no arrancado)
- Peticiones públicas: 0 (cero)
- Errores de consola: 0, errores de página: 0
- Procesos residuales: 0, puertos 8791-8794 libres

**Aclaración sobre los 0,007/0,006 s reportados previamente:** Ese tiempo medía únicamente la comprobación final de `wait_for_function` en `wait_preflight()` (la condición ya se cumplía tras los pasos de búsqueda y selección), no el recorrido completo. El preflight completo abarca: apertura de página, carga del catálogo, búsqueda, selección de resultado, elección de intervalo y verificación de identidad — aproximadamente 2.5-3.3 s en total.

**Veredicto del preflight:** PASS en ambos recorridos. El navegador llega a BTCUSDT/1m con gráfico cargado desde caché antes de iniciar cualquier servicio. Si este preflight fallara en la ventana pública, se abortaría sin arrancar el servicio ni consumir la ventana.

**Ventana pÃºblica Binance autorizada (2026-10-25, SHA `f1f189d`).**
Evidencia: `docs/evidence/window-public-2026-10-25/`.

Una Ãºnica ventana pÃºblica ejecutada con `--transport public`,
runs=1, deadline global 180 s, BTCUSDT+MINAUSDT 1m, `--no-recovery`
(reparaciÃ³n REST desactivada), mÃ¡ximo 3 consumidores, 1200 mensajes,
6000 eventos SSE, 3 reconexiones, hasta 2 REST de velas (300 cada una).

**Resultado: veredicto PASS (finalizer), pero procedural_pass FALSE**
por exceder el presupuesto REST (3 solicitudes vs lÃ­mite 2). Todos los
criterios funcionales pasaron:

| Criterio | Resultado |
|---|---|
| Identidad exacta Binance (venue=binance, BTCUSDT, 1m) | PASS |
| binance_accredited | true |
| RecepciÃ³n y cierre de ambos sÃ­mbolos | PASS |
| LIVE en navegador | PASS |
| PaginaciÃ³n Ãºnica (1 peticiÃ³n), 300 velas nuevas, encuadre preservado | PASS |
| consumers=0 con servicio vivo (liberaciÃ³n) | PASS |
| ReconexiÃ³n con consumidores=1 y actualizaciÃ³n posterior | PASS |
| Parada con causa visible, sin LIVE, histÃ³rico conservado | PASS |
| Sin recarga (nav=1, reload=0) | PASS |
| DBs canÃ³nicas intactas | PASS |
| Cero peticiones pÃºblicas del navegador | PASS |
| Deadline global 180 s respetado (total 119,67 s) | PASS |
| Presupuesto REST (mÃ¡x 2 solicitudes de velas) | FAIL (3 solicitudes) |

**Por quÃ© 3 solicitudes REST:** El preflight del navegador hace una
solicitud a `/api/v1/market-series` para BTCUSDT/1m (servida desde
cachÃ© por el BFF, no de Binance). Tras iniciar el servicio pÃºblico, el
navegador reconecta y hace una segunda solicitud inicial. La paginaciÃ³n
hace una tercera. El contador `rest_market_requests` del arnÃ©s cuenta
todas las peticiones a `/api/v1/market-series`, incluidas las servidas
desde cachÃ© durante el preflight. El presupuesto de 2 REST se excede
por 1.

**Tiempos:** fase de minuto 44,6s, preflight 0,007s, page_ready 6,4s,
acceptance 49,1s, pagination 2,9s, release 0,02s, reconnect 3,4s,
down_notice 2,5s. Total 119,67s (< 180s).

**Limpieza:** process_exited=True, port_closed=True,
pidfile_removed=True, health_refused=True. Sin puertos residuales,
sin procesos de servicio, DBs canÃ³nicas intactas.

Dashboard restaurado al entorno canÃ³nico (sin MICROPROBE_STREAM_URL),
BUILD_ID=r1bBrZkP65q5w79uMhJsF, `/market-lab` HTTP 200, catÃ¡logo 932
entradas, servicio de stream detenido.

La ventana pÃºblica no se repetirÃ¡ ante fallo. Queda pendiente ajuste
del contador REST para excluir peticiones servidas desde cachÃ© durante
el preflight antes de una futura autorizaciÃ³n.

**Addendum: reconciliaciÃ³n de presupuesto REST (SHA `d49216f`).**

Se separaron tres mÃ©tricas de red en el arnés
(`scripts/market_stream_local_acceptance.py`):

| MÃ©trica | DefiniciÃ³n | Valor en ventana pÃºblica |
|---|---|---|
| `bff_market_requests` | Llamadas del navegador al BFF (`/api/v1/market-series`) | 3 |
| `cache_reads` | Lecturas con `fetch_performed=True` en respuesta del BFF | 2 |
| `upstream_binance_requests` | Solicitudes HTTP realmente enviadas a Binance | UNKNOWN |

**Detalle de las 3 llamadas al BFF:**

| # | Timestamp (ms) | Símbolo | Intervalo | Rango (from_ms → to_ms) | Fuente | fetch_performed | Solicitudes upstream acreditadas |
|---|---|---|---|---|---|---|---|
| 1 | 1792935062704 | BTCUSDT | 1h | 1791858662696 → 1792935062696 | Navegador → BFF | True | No acreditadas (sin registro del servicio Python) |
| 2 | 1792935062731 | BTCUSDT | 1m | 1792917122727 → 1792935062727 | Navegador → BFF | True | No acreditadas (sin registro del servicio Python) |
| 3 | 1792935121013 | BTCUSDT | 1m | 1792899180000 → 1792917120000 | Navegador → BFF | True | No acreditadas (sin registro del servicio Python) |

**Rutas de solicitud REST:**

1. **RecuperaciÃ³n REST del stream de market-stream**: desactivada con
   `--no-recovery`. El servicio de market-stream no hace peticiones REST a
   Binance para recuperar velas perdidas.

2. **Descargas REST del explorador histÃ³rico**: el BFF (`market_explorer.py`)
   puede hacer peticiones REST a Binance a travÃ©s del `HistoryClient` cuando
   `fetch_block` es invocado desde `series_payload`. El campo
   `fetch_performed=True` en la respuesta del BFF indica que `fetch_block`
   se ejecutÃ³, lo que intenta llamar a `client.paginate_klines()` ->
   `urllib.request.urlopen()` a `https://fapi.binance.com`. Sin embargo, el
   `network.json` del navegador sÃ³lo registra peticiones del navegador al
   BFF (puerto 3020), no las peticiones del proceso Python del BFF a Binance.
   No hay registros de solicitudes HTTP upstream a Binance en la evidencia
   conservada.

**Fundamento de upstream_binance_requests:**

Ausencia de registro NO equivale a cero. No hay registros de solicitudes
HTTP a `fapi.binance.com` en el `network.json` del navegador, en el
`orchestrator.log`, ni en el `run.json`. El `fetch_performed=True` sÃ³lo
indica que `fetch_block` fue llamado (se intentÃ³ una peticiÃ³n), no que la
peticiones HTTP se enviaron exitosamente a Binance.

Por lo tanto, `upstream_binance_requests = None` (UNKNOWN), no 0.

**Resultado reconciliado del presupuesto REST:**

| MÃ©trica | Valor |
|---|---|
| Solicitudes upstream a Binance | UNKNOWN (sin registros) |
| Presupuesto autorizado | Máx. 2 solicitudes pÃºblicas de velas (≤300 cada una) |
| Cumple presupuesto | UNKNOWN (no se puede determinar) |

**CorrecciÃ³n del evaluador:**
- `rest_market_budget` ahora mide `upstream_binance_requests <= 2`, no
  llamadas al BFF. Si `upstream_binance_requests` es `None` (desconocido),
  el presupuesto es `None` (UNKNOWN), no se asume cumplido.
- `bff_market_requests` se mantiene como mÃ©trica distinta (informativa).
- `cache_reads` se mantiene como mÃ©trica distinta (informativa).
- El veredicto global integra aceptaciÃ³n funcional y cumplimiento de
  lÃ­mites, evitando `procedural_pass=True` junto a presupuesto
  desconocido.

**Resultado global reconciliado: UNKNOWN**

El `procedural_pass=FALSE` del `local.json` original se mantiene tal cual
(FAIL del presupuesto REST por contar llamadas al BFF en lugar de
upstream real). Con la correcciÃ³n del evaluador, el presupuesto REST
serÃ­a UNKNOWN (no se puede determinar si se cumpliÃ³ o no), no PASS.

**Regresiones locales** (`tests/test_market_stream_budget.py`, 7 tests):
- `test_cache_complete_zero_upstream`: cachÃ© completa → 0 upstream → OK
- `test_download_consultation_counts_real`: consulta con descarga → contabilizaciÃ³n real
- `test_retries_and_multiple_pages_all_count`: reintentos y varias pÃ¡ginas → todos cuentan
- `test_unverifiable_origin_unknown`: origen no verificable → UNKNOWN
- `test_budget_exceeded_fail_global`: presupuesto excedido → FAIL global
- `test_local_transport_always_ok`: transporte local → siempre OK
- `test_three_distinct_metrics`: las tres mÃ©tricas son independientes
## Sesión de ingeniería — transporte local (2026-10-26, HEAD 365f7eb)

**Control de sesión en el dashboard existente** (/market-lab). Botón visible
"Iniciar / Detener sesión" (data-testid tn-iniciar-sesion /
tn-detener-sesion). Abrir el dashboard NO inicia nada; cada acción es un
POST acotado al BFF y el backend es la fuente de verdad. Reutiliza el
controlador canónico (scripts/paper_lab_session.py +
src/microstructure_probe/paper_lab_engine.py con mecánica de
acktest_offline.run_backtest) y los servicios existentes (BFF
pi/v1/paper-lab/sessions*, pi/v1/market-series sobre caché local
client=None, 0 upstream). Fuente LOCAL SIMULADA: UN token candidato
(MINAUSDT 1m) + BTC como contexto (BTCUSDT 1m), ambos de caché local;
0 llamadas a Binance, ventana no abierta ni solicitada.

**Seis paneles separados:** estado de la sesión; fuente LOCAL SIMULADA;
recepción/frescura de datos (reloj T, cursor, velas conocidas); evaluador
(regla ENGINEERING-MINA-1M-v1, decisión en T, motivo/evidencia); posición
paper (entrada/stop/marca/P&L no realizado); último error o motivo de
abstención.

**Vista de operación:** velas incrementales + reloj de sesión; candidato y
motivo de decisión; entrada pendiente vs fill ejecutado; entrada/stop/salida
en el gráfico (PaperChart); posición abierta/cerrada y motivo; P&L no
realizado/realizado, costes y funding UNKNOWN; historial de eventos y
exportación JSON/CSV. Todos los paneles comparten session_id, símbolo,
tiempos y config_hash.

**Regla de ingeniería:** ENGINEERING-MINA-1M-v1, explícita, versionada y
separada de cualquier estrategia aprobada; caso de ingeniería, no selección
por rentabilidad; el backend decide con evidencia en T; el navegador no
envía decisiones ni estado económico como autoridad.

**Política de parada:** detener NO inventa cierre de posición; congela la
sesión (detenida) y deja la posición tal cual (sin salida inventada, sin
comisión de salida, sin realizado); se recupera por get tras recarga sin
duplicar entrada ni cierre.

**Recarga:** el estado autoritativo vive en paper-lab-sessions/ (atómico,
control de revisión); el navegador solo guarda el puntero session_id
(never estado económico) y recupera vía GET
/api/v1/paper-lab/sessions/[id].

**Recursos:** arranque/parada propios del BFF (spawnSync por acción),
sin procesos huérfanos, sin afectar procesos ajenos; servicio de datos local
(market-stream) permanece detenido por defecto.

**Aceptación (A–E) demostrada frente al backend real:**
A) iniciar → recibir datos → evaluar (ENTRADA_SIMULADA) → entrada automática
(fill por 
un_backtest) → gestión (pasos de marca) → cierre por regla
(horizonte) → exportación JSON/CSV;
B) evidencia insuficiente → SIN_ENTRADA/DESCARTADO, sin posición;
C) fin de datos → sin nuevas entradas, estado visible, posición no cerrada
inventada (open_at_end);
D) recarga → recuperación del mismo estado (session_id/config_hash
idénticos) sin duplicar entrada ni cierre;
E) detener → sesión detenida, recursos propios liberados, sin afectar
procesos ajenos. Transporte local aislado, 0 peticiones Binance, cadena
dashboard → BFF → Python → dashboard.

**Pruebas:** 
px tsc --noEmit 0; 
px eslint 0 en archivos nuevos;

px vitest run src/test/paper-lab-live-api.test.ts 9/9;
python run_tests.py -q 1290 OK / 2 skipped; 
ext build OK.
E2E de navegador real (Chromium headless) sobre
http://127.0.0.1:3020/market-lab: flujo A completo verificado
(iniciar → ENTRADA_SIMULADA → Entrar → abierta → pasos de gestión →
cerrada por horizonte → exportación JSON), recarga recupera estado idéntico
sin duplicar entrada ni cierre, detener congela sin cerrar, B (abstención
SIN_ENTRADA/DESCARTADO, sin posición) y C (fin de datos sin cierre
inventado) verificadas vía HTTP; D y E con caveat de timing del navegador
(ver notas). Nota: los clics de "Paso a paso" en el navegador son
intermitentes (timing React/Playwright); el camino backend → BFF → Python
está verificado por HTTP (crear → evaluar → step ×31 → cerrada por horizonte:
CERRADA en paso 31: status=cerrada, reason=horizon,
exit_px=0.06251, realized_net=-10.00).

**Última actualización:** 2026-10-26.

## Sesión de ingeniería — transporte local (refinamiento, 2026-10-27, HEAD 933606b)

**Alcance aclarado:** "Sesión de ingeniería / replay sobre caché", no
"sistema completo autónomo". El recorrido con datos nuevos continuos (feed
vivo de Binance recorriendo el gráfico) sigue pendiente de autorización
explícita; no se abrió conexión pública a Binance en esta sesión.

**Alcance de --no-fetch:** el BFF de market-series expone la opción de solo
lectura controlada por backend `read_only=1`. La sesión de ingeniería la usa
y el BFF pasa `--no-fetch` al CLI: cero upstream, solo caché local, ausencia
en caché devuelve motivo (NO_COVERAGE) con cero intentos upstream. El
explorador normal llama al mismo BFF sin `read_only`, por lo que conserva la
adquisición bajo demanda con sus presupuestos existentes (ledger compartido
de reservas antes del envío, pages ≤ 2, 30 req/min compartido). Se verificó
con transporte simulado: sesión de ingeniería sin caché → cero upstream;
explorador normal con bloque faltante → adquisición acotada permitida.

**Recuperación por identidad autoritativa:** al recuperar una sesión (recarga
con sesión abierta), el contexto de mercado se carga con el `symbol` y el
`intervalo` del `config` de la sesión recuperada, nunca con las propiedades
predeterminadas del componente (defaults MINAUSDT/1m). Se muestra la
referencia de entrada y la configuración recuperadas: session_id, símbolo,
intervalo, config_hash, regla, reloj T, revisión y entry_px fijo. Probado
con una sesión cuyo símbolo/intervalo difieren de los predeterminados.

**Reloj y evidencia compartida:** indicadores (market-indicators/v1) y
contexto BTC (market-btc-context/v1) se recalculan en el backend con el
reloj T de la sesión (solo velas conocidas en T, sin futuros). Open conocido
al abrir; OHLC completo solo al cierre (close_time_ms <= T). Flujo sin
eventos registrados → UNKNOWN.

**Sincronización de reloj:** la actualización de vista se centraliza tras
cada respuesta autoritativa (`applyAuthoritative`). Si `clock_ms` cambia —
incluido `Entrar` (avanza T) — indicadores y contexto se corresponden con
ese T: se descarta el contexto anterior y se recarga para el nuevo T con la
identidad autoritativa de la sesión. Mientras se actualizan, no se muestran
valores previos como actuales (contexto suspendido hasta que se recarga).
Probado: entrada, paso, salida, reinicio y recuperación.

**Regla de ingeniería:** ENGINEERING-MINA-1M-v1, explícita, versionada,
separada de estrategia aprobada. entry_px se fija antes de evaluar (cierre
de última vela de contexto, no el cierre de la vela de entrada), por lo que
la regla no garantiza entrada por igualdad automática. Dos prefijos de datos
(A=20 contexto, B=35 contexto) bajo la misma configuración demuestran que A
admite entrada y B se abstiene.

**Vista de operación:** velas incrementales + reloj de sesión; candidato y
motivo de decisión; entrada pendiente vs fill ejecutado; entrada/stop/salida
en el gráfico (Lightweight Charts); posición abierta/cerrada y motivo; P&L
no realizado/realizado, costes y funding UNKNOWN; historial de eventos y
exportación JSON/CSV. Todos los paneles comparten session_id, símbolo, tiempos
y config_hash.

**Política de parada:** detener congela la sesión (detenida) sin inventar
cierre; se recupera por GET tras recarga sin duplicar entrada ni cierre.

**Aceptación (A–E) demostrada:**
A) HTTP: crear → evaluar (ENTRADA_SIMULADA) → step (entrar) → pasos de
   gestión → cerrada por horizonte (exit_px=0.06302, realized_net=3.98,
   funding=None); E2E navegador: iniciar → ENTRADA_SIMULADA → Entrar →
   abierta → pasos de gestión.
B) HTTP: entry_px por encima de todos los cierres → SIN_ENTRADA/DESCARTADO,
   position.open=false, sin posición.
C) HTTP: fin de datos → sin nuevas entradas, posición no cerrada inventada
   (open_at_end).
D) HTTP y navegador: recarga recupera session_id/config_hash idénticos sin
   duplicar entrada ni cierre; verificado con sesión ABIERTA.
E) HTTP y navegador: detener → sesión detenida, recursos propios
   liberados, sin afectar procesos ajenos.

Transporte local aislado, 0 peticiones Binance, cadena
dashboard → BFF → Python → dashboard.

**Pruebas:** npx tsc --noEmit 0; npx eslint 0 (archivos nuevos);
npx vitest run src/test/paper-lab-live-api.test.ts 9/9;
npx vitest run src/test/session-lab.test.ts 4/4;
npx vitest run src/test/engineering-session.test.tsx 5/5;
python run_tests.py -q 1290 OK / 2 skipped; next build OK.
BUILD_ID servido: yeIE931T35_a8l_k-WiqW (SHA fuente del árbol
933606b841afc3c705acd1a3a04593b2e8c02fb5, frontend del commit 933606b
más los cambios de esta sesión).

**Límites pendientes:** conexión a Binance público (ventana aparte,
autorización explícita); selector automático de varios símbolos; monitor en
vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; indicadores
provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos
continuos.

## Sesión de ingeniería — modo autónomo (2026-10-27, base `9a24308`, rama `feat/ingenieria-autonoma`)

**Qué cambió:** la sesión de ingeniería (`/market-lab`) avanza sola con un
solo "Iniciar sesion": datos → cálculos → regla → entrada pendiente → fill
simulado → gestión → cierre, sin pulsar "Entrar" ni "Paso a paso" para cada
transición. El bucle autónomo vive en el componente
(`frontend/src/components/session-lab/EngineeringSession.tsx`) y reutiliza
exactamente el endpoint `POST /api/v1/paper-lab/sessions/[id]/step` de
"Paso a paso" (un proceso Python por acción vía `spawnSync`; sin proceso
persistente por tick). Retardo observable 1500 ms entre pasos
(`AUTONOMOUS_STEP_DELAY_MS`), tope de seguridad `MAX_AUTONOMOUS_STEPS=200`.

**El navegador solo observa:** no conduce el reloj ni decide trades; cada
transición la decide el motor Python. Cerrar o recargar la pestaña no
interrumpe la sesión del backend (estado autoritativo en
`paper-lab-sessions/`). Tras la evaluación, la autonomía arranca sola si el
estado es `en_espera` o `abierta`; las abstenciones
(`SIN_ENTRADA`/`DESCARTADO`/`sin_iniciar`) nunca abren el bucle.

**Fin del transporte local:** si un paso no avanza `clock_ms` en
`en_espera`/`sin_iniciar`, la autonomía se detiene con causa visible
(`session-transport-cause`): sin entrada nueva, sin cierre inventado
(`open_at_end`). Lo mismo al terminar en `cerrada` con posición abierta y
`open_at_end=true`. Chip visible durante la autonomía
("Autónomo: backend avanza el reloj"); "Entrar"/"Paso a paso" deshabilitados
mientras dura; una acción manual detiene la autonomía y retoma el control.

**Corrección de selección de prefijo antes de iniciar:** `changePrefix`
ignoraba la elección sin sesión activa (preexistente en `9a24308`), lo que
impedía el escenario B en el navegador. Ahora la elección sin sesión fija el
prefijo para el próximo "Iniciar"; con sesión viva se conserva la
reconstrucción con el mismo `entry_px` fijo. Verificado: sesión creada con
35 velas de contexto (prefijo B). Nota factual: con la caché actual
MINAUSDT 1m, el prefijo B NO garantiza abstención (la señal y el fill
ocurrieron también con B); la abstención real se demuestra vía HTTP con
stop ya vulnerado en T (DESCARTADO, sin posición, terminal).

**Aceptación (A–E) con modo autónomo:**
A) navegador: un "Iniciar sesion" → autonomía sola → ABIERTA (fill
   ejecutado) → CERRADA por horizonte (exit_px=0.06302, realized_net=3.98,
   exit_executed=true, open_at_end=false), 2 pasos automáticos, sin botones
   de avance; evidencia `docs/evidence/INGENIERIA_AUTONOMA_A_ABIERTA.png`.
B) navegador + HTTP: sesión con stop ya vulnerado en T → DESCARTADO, sin
   posición; al recuperarla en el navegador NO hay chip autónomo ni pasos
   (revisión sin cambios); evidencia
   `docs/evidence/INGENIERIA_AUTONOMA_B_ABSTENCION.png`; además unidad de
   `sin_iniciar` sin autonomía en `engineering-session.test.tsx`.
C) HTTP: sesión con señal pendiente de fill y sin más velas → los pasos dejan
   de avanzar el reloj (cursor/clock invariantes), sin entrada nueva; la
   causa visible y la detención del bucle están cubiertas por unidad
   (test C). Sesión detenida al cierre para no dejar sesiones pendientes.
D) navegador: recarga con posición ABIERTA → mismo session_id/config_hash,
   un único evento de entrada, sin duplicar efectos; la autonomía NO se
   re-engancha sola tras recarga (el navegador observa); "Paso a paso"
   vuelve a estar habilitado y completó el cierre por horizonte.
E) navegador: "Detener sesion" con posición abierta → `detenida`, posición
   congelada (pos_open=true, result=null, sin evento de salida), paso
   posterior no-op (revisión/cursor invariantes); evidencia
   `docs/evidence/INGENIERIA_AUTONOMA_E_DETENIDA.png`.

**Pruebas:** `npx tsc --noEmit` 0; `npx eslint` 0 (componente + test);
`npx vitest run src/test/engineering-session.test.tsx` 8/8 (5 previas + 3
autónomas A/B/C); suite frontend completa 596 passed / 1 skipped (78
archivos). Python: suite completa 1476 tests → 2 fallos PREEXISTENTES en
HEAD (no causados por esta sesión; motor y rutas sin tocar):
`tests/test_paper_lab_engine.py::test_public_dict_vela_solo_open_sin_ohlc`
y `tests/test_market_stream_window.py` (scenario FAIL≠UNKNOWN); 2 skipped.
`next build` OK. Exportación JSON/CSV intacta.

**Límites pendientes:** conexión a Binance público (ventana aparte,
autorización explícita); selector automático de varios símbolos; monitor en
vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; indicadores
provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos
continuos; los dos fallos preexistentes de la suite Python.

**Servidor canónico tras el bloque (2026-10-27):** `next start` en
`127.0.0.1:3020`, node PID **32856**, BUILD_ID **`GC5lmJU9kuk4F0d3Z7WxI`**,
SHA fuente del árbol servido **bc2589a** (rama `feat/ingenieria-autonoma`,
empujada a `origin`). URL de la sesión de ingeniería:
`http://127.0.0.1:3020/market-lab`. Estado de entrega: `/market-lab` y `/`
HTTP 200; sin puntero de sesión en el navegador ("Sesión no iniciada"); las
cuatro sesiones de evidencia del bloque terminales (cerrada/detenida); sin
proceso Python persistente de la sesión (spawnSync por acción). NOTA: existe
un listener PREEXISTENTE en 8792 (node no; `python scripts/market_stream_service.py`,
PID 33104, arrancado 2026-10-26) que no fue arrancado ni detenido en esta
sesión; no es un servicio de ensayo de este bloque. `main` remota sigue en
`d6801a5` (práctica previa: se empuja la rama activa, sin merge a main).


## Addendum 2026-10-31 â€” Prueba de integraciÃ³n real de sesiÃ³n nueva con contexto reciente (sin Binance)

Se reescribiÃ³ `tests/test_session_new_public_market_local.py` como prueba de
integraciÃ³n real (antes: usaba mÃ©todos internos `_consume_*`/`_load_state`,
escribÃ­a en la ruta canÃ³nica `data/engineering-session/sessions`, no levantaba
HTTP/WS, generaba una vela futura rotulada cerrada y `fetchMarketSeries`
pedÃ­a `0â†’9999999999999`).

Cambios:
- Aislamiento: `TemporaryDirectory` para sesiones y SQLite de prueba; se
  audita la ruta canÃ³nica y se eliminan Ãºnicamente artefactos propios de este
  test (hypothesis_id `ENG-MINA-01`; sesiones desconocidas intocadas). Se
  corrigiÃ³ la afirmaciÃ³n de "directorio temporal".
- Rango reciente: `fetchMarketSeries` calcula una ventana explÃ­cita de velas
  cerradas (sin `0â†’9999999999999`); `series_payload` clampa `end` al reloj
  actual; adquisiciÃ³n pÃºblica bloqueada salvo `readOnly=false` (expresa).
- IntegraciÃ³n real: servidor HTTP de klines y servidor WS locales en puertos
  efÃ­meros; `scripts/market_explorer.py` (HistoryClient + puerta de presupuesto
  LedgerAttemptGate) como camino BFF/CLI; `market_stream_service` (SSE,
  transporte local); sesiÃ³n vÃ­a `EngineeringHTTPServer` (mismo objeto que el
  BFF `/api/v1/engineering-sessions`) por HTTP real (POST/GET), sin mÃ©todos
  internos del motor. SQLite de prueba con datos de 4 dÃ­as atrÃ¡s; el HTTP
  devuelve contexto reciente de MINAUSDT y BTCUSDT (rango reciente, no
  backfill de 4 dÃ­as). Se acredita con log de solicitudes: rangos recientes,
  presupuesto aplicado (ledger compartido), snapshot unido al primer cierre
  nuevo sin huecos ni duplicados, sesiÃ³n preparada; todas las velas cerradas
  con cierre conocido en el reloj de la prueba.
- Resultado: `docs/evidence/test_session_new_public_market_local/result.json`
  (verdict PASS) y `request-log.jsonl`. Regresiones: `test_market_explorer.py`
  42/42, suite frontend 622/623, `tsc`/`eslint` 0, `next build` OK.
- Sin Binance, Ã³rdenes, pagos, mÃ³vil ni cambios econÃ³micos.



## Ventana pública de integración — 2026-10-31 (base e2243c9, autorizada 1x)

Ejecutada una única ventana pública autorizada sobre `--transport public`, símbolos `BTCUSDT`+`MINAUSDT` 1m, reutilizando el recorrido corregido (`scripts/market_stream_window.py` + `scripts/market_stream_service.py` + arnés `scripts/market_stream_local_acceptance.py`), sin editar código durante la ventana ni relanzamiento automático.

**Preflight (antes del primer acceso público):**
- SHA fuente: `git rev-parse HEAD = e2243c9` (coincide con el solicitado).
- BUILD_ID servido: dashboard 3020 reconstruido desde `e2243c9` (`next build` + `next start -p 3020`, PID 21152), sirve `t4z0bfKQ_kIP9qv1WHCKR` (coincide con `frontend/.next/BUILD_ID`; `_preflight` `served=true`).
- Procesos: 8791 libre; 8792 ocupado por servicio LOCAL preexistente (PID 31124, `--transport local`, no tocado); 3020 dashboard propio. Sin sesiones activas (`service.json` obsoleto sin listener; `paper-lab-sessions` vacío).
- Control de arranque / rango reciente: verificado en código (`series_payload`: `end = min(end, now)`, ventana explícita de `bars` velas cerradas; sin `0→9999999999999`).
- Límites efectivos en código: 1 socket WS combinado (`BinanceKlineTransport.build_url`), `socket_reconnects` con tope script 3; consumidores SSE efectivos 3 (hub total 4 con 1 suscripción interna BTC de contexto); `--no-recovery` + `client=None` → 0 REST de recuperación; `bars=300` ≤ 300; `DEFAULT_DURATION_S=180`; hub `persistence=MEMORY_ONLY`; DBs canónicas solo lectura.

**Ejecución (127,47 s de 180 s global):**
- `transport_origin=binance`, servicio PID 32552 en 8791 (`--transport public --no-recovery --max-seconds`), parado limpio (exit 0, puerto cerrado, pidfile eliminado, health rechazado).
- Recepción: 69 eventos vela BTCUSDT + 5 MINAUSDT; cierre confirmado 1793455800000 (close_time 1793455859999), siguiente vela 1793455860000; 64 actualizaciones provisionales misma apertura; 0 huecos; `identity_exact` (BTCUSDT/MINAUSDT, venue=binance, market_type=usd_m_futures, 1m).
- Navegador: LIVE (RECIBIENDO), DOM identidad exacta, paginación 299→600 (1 petición, 300 nuevas, misma identidad, sin recarga), liberación consumers=0 con servicio vivo, reconnexión consumers=1, aviso `explorer-stream-down` con causa al parar.
- Consumo REST: servicio 0 upstream; navegador/BFF 2 peticiones market-series (carga inicial 299 velas + paginación 300 velas, ≤300 cada una); total ≤ 3 ≤ 4; `external: []`, `browser_external: []`, cero peticiones públicas del navegador.
- DBs canónicas: `microprobe.db` y `historical.db` sin cambios (mtime/size idénticos); caché derivada `market_cache.db` creció (esperado, aislada).
- Escritura: solo JSON de evidencia en `docs/evidence/window-public-2026-10-31/`; cero DB canónica, cero sesiones paper.

**Veredicto (finalizer, run.json): `PASS`**, `failed=[]`, `missing=[]`, `acquisition_finished=true`, `stop_reason=ACCEPTANCE_REACHED`, `visual_review=NOT_REVIEWED`. Todas las 21 checks requeridas OK (incluidas las 7 de DOM). Nota: el arnés falló al construir el resumen final por `NameError` (`rest_market_requests` no definida, variable ajena a la cadena) por lo que `local.json` reporta `verdict=ERROR`/`procedural_pass=false`, pero el veredicto autoritativo del finalizer en `run.json` es `PASS`.

**Estado final:** servicio 8791 detenido y puerto libre; 8792 sin tocar; dashboard 3020 disponible sirviendo `e2243c9` (BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR`), sin sesión de ensayo activa; sin posiciones paper abiertas; sin órdenes, claves, pagos, móvil ni optimización. Sin posición abierta que conservar (no hubo entrada).


## Cierre y correccion de la ventana pública de integración — 2026-10-31 (base e2243c9)

Se corrigió el cierre de la ventana pública autorizada ejecutada sobre `--transport public`,
símbolos `BTCUSDT`+`MINAUSDT` 1m, usando el recorrido corregido (`scripts/market_stream_window.py`
+ `scripts/market_stream_service.py` + arnés `scripts/market_stream_local_acceptance.py`),
sin editar código durante la ventana ni relanzamiento automático. Los originales de evidencia
(`run.json`, `network.json`, `local.json`) se conservan intactos; la corrección se publica como
addendum reproducible: `docs/evidence/window-public-2026-10-31/addendum-reconciliacion-2026-10-31.md`.

**Resultado global reconciliado:**
- Cadena Binance → servicio SSE → BFF → DOM: **PASS funcional** (21/21 checks OK, 7/7 DOM,
  `acquisition_finished=true`, `stop_reason=ACCEPTANCE_REACHED`, paginación 299→600, parada limpia).
- Consumidores SSE simultáneos: **INCUMPLIMIENTO**. Máximo autorizado: 3. Pico medido en
  `health_before_close`: 4 (`service=1, bff=1, browser=1, internal_benchmark=1`). El
  `internal_benchmark` (suscripción interna compartida BTC, refcount) se contabilizaba como
  consumidor adicional, llevando el pico a 4.
- **Veredicto GLOBAL: NO PASS** (el incumplimiento de consumidores, 4 > 3, impide que el global
  sea PASS aunque la cadena de datos del gráfico/transporte sea funcional).
- Presupuesto REST (recalculado offline desde el ledger `market_fetch_ledger`, id 140–143):
  4 intentos totales a Binance (1 exchangeInfo + 3 klines), 3 solicitudes de velas cada una ≤300
  velas. Dentro del presupuesto autorizado (máx. 4 intentos totales; máx. 300 velas c/u).
  No se equiparan llamadas al BFF con solicitudes a Binance. `upstream_binance_requests` nunca se
  asume cero sin ledger (UNKNOWN si no hay registros).

**Correcciones al arnés (demostradas con transporte local):**
1. `scripts/market_stream_window.py::_consumer_allocation`: elimina el doble conteo del
   consumidor benchmark del total declarado (pico 4 → 3; máximo autorizado 3).
   `internal_benchmark` queda solo como campo informativo.
2. `scripts/market_stream_local_acceptance.py`: corrige `NameError`
   (`rest_market_requests` indefinida); `rest_market_budget` se evalúa contra el presupuesto
   autorizado (≤ 4 intentos REST a Binance), no contra llamadas al BFF.
3. `tests/test_engineering_session_local_backend.py` (nueva): prueba focalizada de sesión backend
   de ingeniería que recibe eventos y registra decisiones con transporte local (sin red, sin
   Binance): `session_id`, `config_hash`, runner (engine), decisión causal (`RULE-CAUSAL-V1`)
   registrada con motivo y evidencia, `revision` incrementada, recepción de eventos
   (`step_forward` avanza `clock_ms`/`cursor`), cero entradas válido si queda acreditada la
   evaluación. 1/1 pasa.

**Alcance realmente probado — sesión de ingeniería: NO EVALUADA.**
Los checks del arnés de ventana no acreditan la sesión de ingeniería (no hay `session_id`,
`config_hash`, runner, eventos recibidos, revisiones ni decisiones bajo mercado real en esta
ventana). No existe evidencia de sesión de ingeniería bajo mercado real en 2026-10-31
(`paper-lab-sessions/` sin archivos de fecha 179345...; evidencia de ingeniería previa es del
2026-10-28 con transporte local, sin Binance real). La ausencia de posiciones abiertas **no**
se presenta como abstención demostrada.

**Estado final:** servicio 8791 detenido y puerto libre; 8792 sin tocar (servicio local
preexistente PID 31124); dashboard 3020 disponible en `e2243c9` (BUILD_ID
`t4z0bfKQ_kIP9qv1WHCKR`), sin sesión de ensayo activa; sin posiciones paper abiertas
(no hubo entrada bajo mercado real); sin órdenes, claves privadas, pagos, móvil ni
optimización; DBs canónicas intactas. Pruebas focales: 41/41 pasan
(`test_engineering_session_local_backend.py` + `test_market_stream.py`).

**Qué falta:** sesión de ingeniería bajo mercado real (NO EVALUADA, pendiente de ventana
autorizada con transporte public); repetición de la ventana pública con consumidores ≤ 3 para
pasar el veredicto global (requiere autorización explícita).



## Cierre y bloqueo de la ventana pública de sesión de ingeniería — 2026-10-31 (base e2243c9 / commit 22987a4)

Se ejecutó **una sola** ventana pública autorizada sobre ``--transport public``,
símbolos `BTCUSDT`+`MINAUSDT` 1m, usando el arnés nuevo
`scripts/engineering_live_window.py` que orquesta el servicio de mercado
`market-stream/v1` (puerto 8791) y el servicio de sesiones de ingeniería
`engineering-session-service/v1` (puerto 8797, ruta de sesiones aislada).
**La ventana se cerró con veredicto BLOQUEO (no PASS).**

**Causa del bloqueo:** no se pudo obtener un contexto reciente de velas
cerradas para fijar el reloj T inicial de la sesión de ingeniería. La caché
derivada local no tenía velas recientes para el rango, y las 2 peticiones REST
klines a Binance (dentro del presupuesto de 4 totales; ≤300 velas c/u)
devolvieron HTTP 200 pero 0 velas válidas (cuerpo no parseable como lista de
klines). Sin contexto reciente, `create_session` con transporte
`market_stream` rechazó con:

    VALIDATION_ERROR: LIVE_CONTEXT_REQUIRED: la sesión live necesita contexto
    (ventana de velas cerradas conocidas) para fijar el reloj T inicial

Por lo tanto **no se creó la sesión de ingeniería**, no hubo eventos de
mercado recibidos por la sesión, ni revisiones ni decisiones, y no hay
evidencia de ejecución que verificar. Cero entradas (válido solo si se acredita
evaluación real — aquí no se acreditó).

**Preflight verificado (antes del bloqueo):**
- SHA fuente: `git rev-parse HEAD = 22987a4` (árbol `e2243c9`, el solicitado).
- BUILD_ID servido: dashboard 3020 sirve `t4z0bfKQ_kIP9qv1WHCKR` (coincide con
  `frontend/.next/BUILD_ID` y el árbol); `/market-lab` HTTP 200.
- Procesos: 8791 libre antes de arrancar; 8792 ocupado (servicio LOCAL
  preexistente PID 31124, **no tocado**); 3020 dashboard propio. Sin procesos
  de ingeniería activos antes de la ventana.
- Rango reciente: `series_payload` clampa `end` al reloj actual (ventana
  explícita de `bars` velas cerradas; sin `0→9999999999999`).
- Límites efectivos impuestos por el orquestador: 1 WS combinada (hub de
  market-stream), ≤3 consumidores SSE (monitoreados en /health), ≤3
  reconexiones, ≤4 REST totales, ≤300 velas/consulta, deadline 180 s,
  cero escrituras en DBs canónicas, hub usa una WS combinada.

**Presupuesto REST (recalculado offline desde el ledger y la respuesta):**
- Intentos REST totales a Binance: 2 (klines BTCUSDT + klines MINAUSDT),
  cada una ≤300 velas. Límite autorizado: 4 totales. **Cumple.**
- Peticiones del navegador al BFF: n/a (no hay navegador en esta ventana;
  no se repite el ensayo del gráfico).
- Escrituras en DBs canónicas: ninguna (`db_unchanged=true`).

**Recursos y limpieza:**
- Servicios propios (market-stream 8791, engineering-session 8797) detenidos
  tras la ejecución; puertos en TIME_WAIT, sin proceso activo.
- 8792 (servicio local preexistente) **no tocado**.
- Dashboard 3020 disponible, sirviendo `e2243c9`, sin sesión de ensayo activa.
- DBs canónicas (`microprobe.db`, `historical.db`): **intactas**.
- Sesión de ingeniería: **no creada** (no hay `session_id` ni `config_hash`).
- Evidencia: `docs/evidence/window-public-2026-10-31/run.json` +
  `addendum-bloqueo-contexto.md`.

**Veredicto global: BLOQUEO.** No se integra como PASS porque no se creó la
sesión de ingeniería ni se recibió/evaluó evento de mercado real. No se repite
la ventana (instrucción del operador). Una futura ventana requeriría resolver
primero la disponibilidad de contexto reciente de velas cerradas antes de
conectar a Binance.

Sin órdenes reales, claves privadas, pagos, móvil ni optimización. Sin cambios
durante la ventana.


## 2026-11-03 - NO PASS en la aceptación pública A–J: deadline terminal corregido (base `263039b`)

- Se rectifica el "10/10 PASS" de
  `ADDENDUM_PUENTE_PUBLICO_DEFECTOS_20261103.md`: medía estado JSON del backend,
  no el camino productivo (E sin UI, G sin proceso/puerto, H sin ejecutar la
  parada, I afirmaba `position.open=false`, contra el requisito).
- Corregido el defecto terminal del deadline en
  `engineering_session_service.py`: `deadline_passed()` (hecho temporal),
  `is_terminal()` (estado persistido) e `is_deadline_exceeded()` (terminal o
  plazo vencido). El watcher cierra el listener propio y el reinicio de una
  corrida vencida no reactiva ni concede tiempo (`PUBLIC_RUN_DEADLINE_EXCEEDED`).
- Nueva aceptación ejecutada con el BFF productivo (build
  `afm2q3kpfKZ0sigxBFsB5`, Host 3020, puerto alterno), el servicio real, proveedor
  loopback `/time`+klines, directorios temporales exclusivos y bloqueo
  registrado de red pública.
- Resultado: **7 criterios PASS (A, B, C, D, G, I, J) y 3 NO ACREDITADO
  (E, F, H)**. Comando `python -m pytest tests/test_public_run_integration.py
  tests/test_public_run_deadline.py -v --no-header --color=no` → 11 passed,
  3 failed, exit 1. Evidencia en
  `docs/evidence/public-acceptance-20261103/pytest-public-acceptance.txt`.
- Hallazgos no corregidos (fuera de alcance): el gestor BFF lee
  `data/engineering-session/public-run.json` y el backend escribe en
  `.../sessions/public-run.json` (la parada propia nunca detiene); el fetch de
  `/time` usa el número de muestras (5) como límite de ventana (30/min),
  bloqueando la sincronización si hubo actividad reciente; el estado persistido
  nunca sale de `preparing`; el primer arranque público desde la UI falla por
  `PUBLIC_RUN_ID_REQUIRED`.
- Sin Binance, sin ventana pública, sin cambios económicos, sin rebuild del
  frontend. 3020 (pid 20088) y 8792 (pid 31124) preservados; 8797 libre.
- Regresiones: 94 passed (`engineering_*`, `paper_lab_*`).

## 2026-11-03 - Cierre de la aceptación pública E/F/H y rectificación del deadline (base 374e92a -> 374e92a + cambios de este bloque)

- Cierre de E (consumo real en interfaz), F (recuperación sin devolver cupos) y H (parada propia efectiva).
  * E: EngineeringSession.tsx renderiza httpAttempts/deadlineExceeded (UNKNOWN si no hay valor, nunca cero ficticio); public/route.ts emite httpAttempts (camelCase) y lee el registro persistente desde disco cuando el servicio no arranca (etchPublicRun fallback a 
eadPublicRunRecord). publicOriginAllowed centralizado en engineering-service-manager.ts con ENGINEERING_PUBLIC_ALLOWED_HOST (default 127.0.0.1:3020; producción sin abrir). Prueba E2E con Playwright: navegador real renderiza Intentos HTTP: 5 y 7 coincidiendo con SUM(requests) del ledger. Evidencia: docs/evidence/public-acceptance-20261103/e-consumption-ui.png.
  * F: tras 7/7 consumido, el BFF consulta la corrida desde disco (run_id/started_at_ms/deadline_ms/http_attempts>0; no inexistente ni consumo cero); reinicio con el mismo run_id se rechaza explícito (503 ENGINEERING_SERVICE_EXITED), cero /time nuevos, registro conservado; corrida terminal no se reactiva (egin() rechaza).
  * H: corregido el desajuste de rutas — el gestor BFF lee el registro en sessions/public-run.json (mismo lugar autoritativo que el backend), no en data/engineering-session/public-run.json. run_id ajeno → rechazo, proceso/puerto intactos; identidad incierta → rechazo, sin shutdown; run_id propio → parada efectiva (proceso termina, puerto libre, pid-file retirado), registro conserva causa/consumption/historial.
- Backend: PublicRunRecord._save() reconstruye http_attempts desde el ledger (coherente con 	o_dict()); main() persiste http_attempts tras la sincronización exitosa.
- Pruebas: 14/14 aceptación pública pasan (A–D, F–J en 	est_public_run_integration.py; E en 	est_public_run_e_ui.py; G en 	est_public_run_deadline.py), salida 0. Regresiones engineering_*/paper_lab_*/deadline: 99 passed.
- Sin Binance, sin ventana pública, sin cambios económicos ni ampliación de presupuesto. 3020 (pid 20088) y 8792 (pid 31124) preservados; 8797 libre. opencode.json y archivos ajenos no se commitean.
- Build: 
ext build OK (BUILD_ID afm2q3kpfKZ0sigxBFsB5); 	sc --noEmit 0 errores; eslint 0 errores (1 advertencia preexistente).


## 2026-11-03 - Cambio de prioridad: investigación universo y liquidez (rama research/universe-liquidity-v1, base 78371aa)

- PRIORIDAD CAMBIADA: se pausa expansión del dashboard, Paper Lab, gestores de procesos y aceptación pública. El objetivo inmediato es investigar la hipótesis económica (liquidez vs flujo agresor → continuación/reversión) y la selección automática de candidatos sobre el universo elegible.
- Documento: docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md (protocolo breve, tabla de cobertura, resultado descriptivo nivel A, plan mínimo de adquisición NO ejecutado).
- Evidencia computada (solo lectura SQLite): docs/evidence/research/universe_liquidity_v1/coverage.json y descriptive.json; script scripts/research_universe_liquidity_inventory.py.
- Resultado: hipótesis NO testeable hoy sobre outcomes resueltos (0 filas de profundidad/libro en el instante T para la ventana resuelta; universo resuelto = 6 símbolos = 1.15% de 522 elegibles; retorno forward medio ≈ 0 en BTC/ETH/SOL). Diagnóstico computado de insuficiencia, no otro simulador. Plan mínimo de adquisición propuesto (no ejecutado).
- Sin Binance, sin ventana pública, sin órdenes, sin cambios de reglas operativas ni económicas. 3020 (pid 20088) y 8792 (pid 31124) preservados; 8797 libre. opencode.json y archivos ajenos no se commitean.


## 2026-11-03 - Autoselección de candidatos para investigación (rama research/universe-liquidity-v1, base 2f5fc70)

- Inventario corregido: scripts/research_universe_liquidity_inventory.py (COUNT(*) filas no grupos; elegibilidad desde datos y filtros explícitos; sin 522/942 hardcodeados; procedencia REAL/FIXTURE/UNKNOWN por evidencia; n_events_with_1h_outcome cuenta específicamente horizonte 1h; descartes y denominadores publicados; fórmula y unidades de retornos declaradas).
- Matriz de aprovechamiento de datos existentes: docs/evidence/research/universe_liquidity_v1/joint_coverage.json. Cobertura útil liquidez+flujo+resultado posterior = 1 de 14 símbolos research (BTCUSDT, solo horizonte 1h); los otros 13 no tienen precio posterior.
- Autoselección de investigación: scripts/research_selector.py (política versionada research-selector-v1, bounded set, ambos lados, criterios en T, límites de candidatos, comparador con semilla fijada, trazabilidad por ciclo). Pruebas: tests/test_research_selector.py (11 pruebas de mecanismo, sin ventaja económica).
- Pruebas de inventario: tests/test_research_inventory.py (10 pruebas, conteos conocidos, mezcla de horizontes, procedencia desconocida, elegibilidad).
- Resultado: cobertura insuficiente para probar la hipótesis liquidez-vs-flujo sobre universo representativo. Diagnóstico de insuficiencia, no otro simulador. Plan mínimo de adquisición propuesto (no ejecutado).
- Sin Binance, sin ventana pública, sin órdenes, sin cambios de reglas operativas ni económicas. 3020 (pid 20088) y 8792 (pid 31124) preservados; 8797 libre. opencode.json y archivos ajenos no se commitean.
