## F-EXTREME-OPERATING-ALIGNMENT-20261106 — Dirección y prioridad operativas

**1. Title:** Alinear autoselección/investigación de perpetuos extremos con
entrada, dirección, stop-loss, gestión, salida y comprobación económica.

**2. Approval status:** AUTORIZADO por el usuario para alinear documentación.
El diseño ya fue entregado en `6a10c307`; su revisión/cierre no aprueba reglas,
capturas nuevas, cambios de presupuesto ni ejecución real por este registro.

**3. Implementation status:** DOCUMENTADO en PRODUCT_GOAL, AGENTS, MASTER_PLAN,
ROADMAP, estado/cola y documento de investigación. Capacidades operativas
existentes se reutilizan; no se declara implementado el objetivo completo.

**4. Evaluation status:** análisis v4 de `public-pilot-1h-20261106a` cerrado
como exploratorio con límites. Diferencias brutas y asociación de flujo no
acreditan estrategia rentable, generalización ni promoción de fase.

**5. Evidence:** solicitud explícita del usuario del 2026-11-06;
`docs/PRODUCT_GOAL.md`;
`docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/informe_analisis_universo_liquidez_v4.md`.

**6. Verdict:** alineación documental, sin cambio de código, parámetros, gates,
datos ni autorizaciones de operación. Historia conservada.

**7. Next step:** revisar/cerrar `EXPERIMENTO_OPERATIVO_V1.md` ya entregado: una regla,
datos y ejecución posibles, comparadores/cobertura, períodos, métrica y criterios
de decisión, presupuesto. No otra captura automática ni expansión de sistemas.

---

## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `bf974f2`)

**1. Title:** Corregir semántica de costes en PnLPanel y verificar aceptación
  local A-J del recorrido visible del dashboard.

**2. Approval status:** EJECUTADO (corrección de costes, regresiones, aceptación
  local integrada; sin conexión Binance, sin órdenes reales, sin cambios de
  estrategia, sin nuevos motores, sin pagos, sin móvil).

**3. Implementation status:** IMPLEMENTADO en rama `dash-v2-04-recorrido-visible`.

**4. Evaluation status:** PASS - typecheck, lint, build y pruebas de costes pasan.
  Aceptación local A-J verificada desde navegador real: 11/11 PASS.

**5. Evidence:** `docs/evidence/dashboard-EFHI-20261103/`
  (capturas DOM, respuestas backend, aceptación-summary.json).

**6. Verdict:** PASS - costes corregidos con semántica correcta, aceptación
  local verificada.

**7. Next step:** dejar 3020 disponible con build verificado y sin demo activa;
  servicio 8797 detenido (residual).

## Corrección semántica de costes y aceptación A-J del dashboard (base `bf974f2`)

## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `ead35d2`)

**1. Title:** Corregir semántica de costes en PnLPanel y verificar aceptación
  local A-J del recorrido visible del dashboard.

**2. Approval status:** EJECUTADO (corrección de costes, regresiones, aceptación
  local integrada; sin conexión Binance, sin órdenes reales, sin cambios de
  estrategia, sin nuevos motores, sin pagos, sin móvil).

**3. Implementation status:** IMPLEMENTADO en rama `dash-v2-04-recorrido-visible`.

**4. Evaluation status:** PASS - typecheck, lint, build y pruebas de costes pasan.
  Aceptación local A-J verificada desde navegador real: 11/11 PASS.

**5. Evidence:** `docs/evidence/dashboard-recorrido-visible-20261103/`
  (capturas DOM, respuestas backend, aceptación-summary.json).

**6. Verdict:** PASS - costes corregidos con semántica correcta, aceptación
  local verificada.

**7. Next step:** dejar 3020 disponible con build verificado y sin demo activa;
  servicio 8797 detenido (residual).

## Corrección semántica de costes y aceptación A-J del dashboard (base `ead35d2`)

## Recorrido visible en dashboard V2 - /market-lab (2026-11-03, base `2e3830a`)

**1. Title:** Llevar al dashboard existente el recorrido backend ya acreditado:
  sesión → datos nuevos → evaluación con decisión y motivo → señal pendiente → posición paper.

**2. Approval status:** AUTORIZADO por este prompt (implementación de interfaz, cableado a
  servicios existentes, aceptación local integrada; sin conexiones públicas nuevas, sin órdenes
  reales, sin cambios de estrategia, sin nuevos motores, sin pagos, sin móvil).

**3. Implementation status:** IMPLEMENTADO en rama `dash-v2-04-recorrido-visible`.

**4. Evaluation status:** PASS - typecheck, lint, build y 628 pruebas frontend pasan. Aceptación
  local A-J verificada desde navegador real (Playwright, DOM/red): 11/11 PASS.

**5. Evidence:** Cambios en `frontend/src/lib/format.ts`,
  `frontend/src/components/paper-lab-live/PnLPanel.tsx`,
  `frontend/src/components/session-lab/SessionStatusPanels.tsx`,
  `frontend/src/components/session-lab/EngineeringSession.tsx`,
  `frontend/src/test/format.test.ts` (regresiones de semántica de costes).

**6. Verdict:** PASS - recorrido visible integrado en el dashboard existente.

**7. Next step:** dejar 3020 disponible con build verificado y sin demo activa; no integrar a
  main.

## Recorrido visible en dashboard V2 - implementación (base `2e3830a`)

## Recorrido visible en el dashboard V2 - /market-lab (2026-11-03, base `4b35d2c`)

**1. Title:** Llevar al dashboard existente el recorrido backend ya acreditado:
  sesión → datos nuevos → evaluación con decisión y motivo → señal pendiente →
  posición paper cuando corresponda.

**2. Approval status:** AUTORIZADO por este prompt (implementación de interfaz,
  cableado a servicios existentes, aceptación local integrada; sin conexiones públicas
  nuevas, sin órdenes reales, sin cambios de estrategia, sin nuevos motores, sin pagos,
  sin móvil).

**3. Implementation status:** IMPLEMENTADO en rama `dash-v2-04-recorrido-visible`.

**4. Evaluation status:** PASS - typecheck, lint, build y 622 pruebas frontend pasan.
  Aceptación local desde el navegador (A-J) documentada y verificable.

**5. Evidence:** Cambios en `frontend/src/components/session-lab/SessionStatusPanels.tsx`,
  `frontend/src/components/session-lab/EngineeringSession.tsx`,
  `frontend/src/components/paper-lab-live/PnLPanel.tsx`, `frontend/src/lib/format.ts`.

**6. Verdict:** PASS - recorrido visible integrado en el dashboard existente.

**7. Next step:** dejar dashboard disponible en 3020 con entorno canónico limpio y sin
  demo activa; no integrar a main.

## Reconciliación de la ventana pública `eng-run-public-20261102d` (2026-11-03, base `88c5d2c`)

## Reconciliación de la ventana pública `eng-run-public-20261102d` (2026-11-03, base `88c5d2c`)

**1. Title:** Reconciliar precisiones de conexiones/reconexiones y señal frente a fill de la ventana pública.

**2. Approval status:** EJECUTADO (aclaración documental, base `88c5d2c`, sin cambios de código, sin repetir ventana).

**3. Implementation status:** IMPLEMENTADO. Addendum en
`docs/evidence/engineering-live-public-20261102d/ADDENDUM_RECONCILIACION.md` con rutas y campos exactos de evidencia.

**4. Evaluation status:** PASS. Se confirma que el límite autorizado de reconexiones WS (0 <= 3, contador
`socket.reconnects`) se cumplió; que `ws_connects=4` son aperturas acumuladas no equivalentes a reconexiones;
que el fill ejecutado tiene evento `entry` explícito (`kind=entry`, at_ms=1793674620000, precio 0.05564); y que el
veredicto global PASS se mantiene sin rebajar criterios.

**5. Evidence:** `docs/evidence/engineering-live-public-20261102d/ADDENDUM_RECONCILIACION.md` y evidencia original
intacta (`evidence.json`, sesión, logs, command.txt, preflight.json, RESULTADO.md).

**6. Verdict:** PASS global mantenido. Sesión abierta y congelada.
**7. Next step:** siguiente bloque de producto: control visible del recorrido acreditado en el dashboard.

## Ventana pública `eng-run-public-20261102d` - acreditación del recorrido completo (2026-11-03, base `d307fc7`)

## Ventana pública `eng-run-public-20261102d` - acreditación del recorrido completo (2026-11-03, base `d307fc7`)

**1. Title:** Ejecutar una ventana pública única con run_id nuevo y acreditar:
cierre nuevo admitido → avance de T → evaluación vinculada (decisión+motivo) → parada limpia.

**2. Approval status:** AUTORIZADA por este prompt (una sola ejecución, run_id `eng-run-public-20261102d`, nunca reutilizar `eng-run-public-20261102c`; 180 s deadline; 7/7 HTTP upstream; 1 WS combinada; 3 consumidores SSE; 3 reconexiones; cero escrituras DB; sin órdenes reales).

**3. Implementation status:** EJECUTADA (una sola vez, sin relance, sin cambios de código durante la ventana).

**4. Evaluation status:** PASS - veredicto global PASS con todos los criterios obligatorios: identidad y referencia válidas; 3 cierres nuevos admitidos; 2 evaluaciones ejecutadas y vinculadas (evento/T/config_hash/decisión/motivo); decisión no-null con motivo explícito; todos los límites cumplidos (ledger 7/7, consumidores 2, reconexiones 0, DBs intactas); limpieza efectiva. SIN_ENTRADA con motivo válida.

**5. Evidence:** `docs/evidence/engineering-live-public-20261102d/` (`RESULTADO.md` punto de entrada; `evidence.json` traza completa; `command.txt`; `preflight.json`; `service_logs/`; `sessions/`).

**6. Verdict:** PASS global. Sesión queda abierta y congelada (posición paper-lab simulada, sin orden real; sin salida inventada). No valida rentabilidad ni edge.

**7. Next step:** sesión congelada, sin acción inmediata. No bloqueantes: literal `build_served` y fixture de `tests/test_engineering_live_window_local.py`.

## Corrección tramo SSE/adaptador + veredicto arnés (2026-11-02, base `4e141a7`)

## Corrección tramo SSE/adaptador + veredicto arnés (2026-11-02, base `4e141a7`)

**1. Title:** Reproducir y corregir localmente el tramo
HUB → SSE → adaptador de ingeniería → cierre admitido → avance de T →
evaluación, y eliminar el falso PASS del arnés.

**2. Approval status:** AUTORIZADO por el operador de forma acotada:
base `4e141a7`, SIN Binance, SIN nueva ventana pública; reutilizar
servicios/motor/arnés existentes; diagnóstico con evidencia; reproducción
loopback; corrección mínima; regresiones; sin cambios de estrategia,
presupuestos ni ventana.

**3. Implementation status:** IMPLEMENTADO. Relojes separados en el
diagnóstico (conexión/lectura/silencio/deadline) y confirmado defecto de
medición (`events_processed` nunca incrementado en `_run_drive_market`);
clasificación de desconexiones del adaptador (`READ_TIMEOUT`/`EOF`/…);
contadores por alcance (`events_processed`, `cierres_admitidos`,
`counters`, `gates_rechazadas` acotadas, identidad en evaluaciones);
drain acotado en el HUB (30 s); veredicto del arnés con exigencias de
admisión + evaluación vinculada (SIN_ENTRADA con motivo válida); motor sin
cambios; ningún límite aumentado.

**4. Evaluation status:** PASS. Reproducción local con el adaptador
PRODUCTIVO: (a) lectura estable con heartbeats −> 0 desconexiones;
(b) silencio real −> `READ_TIMEOUT` clasificado + reconexión acotada +
cancelación efectiva; (c) corte y reconexión −> cierre pendiente admitido
UNA vez (watermark) con evaluación vinculada (evento/T/config_hash/
decisión/motivo) y duplicados/provisionales sin efectos económicos; (d)
forma 20261102c exacta → FAIL del arnés; 98 pruebas PASS.

**5. Evidence:** `docs/evidence/engineering-sse-local-20261102b/`
(`RESULTADO.md` con tabla de relojes y hallazgos, `cmd-pruebas.txt`)
+ histórica intacta `docs/evidence/engineering-live-public-20261102c/`.

**6. Verdict:** PASS en local (loopback); el estado del sistema no se
declara completo - la acreditación pública sigue pendiente de ventana
autorizada con run_id nuevo.

**7. Next step:** nueva ventana pública autorizada (run_id nuevo) para
acreditar el recorrido completo con el veredicto corregido.

## Ventana pública única `eng-run-public-20261102c` (2026-11-02, base `a11c02e`)

## Ventana pública única `eng-run-public-20261102c` (2026-11-02, base `a11c02e`)

**1. Title:** Ejecutar UNA ventana pública autorizada con el arnés corregido
(a11c02e) y acreditar: sesión creada → cierre nuevo admitido por la sesión →
avance de T → evaluación con decisión y motivo.

**2. Approval status:** AUTORIZADO por el operador de forma acotada: una sola
ejecución pública (`run_id` NUEVO `eng-run-public-20261102c`), deadline 180 s,
máx. 7 intentos HTTP upstream, 300 velas/consulta, 1 WS combinada
(MINAUSDT+BTCUSDT, 1m), 3 reconexiones, 3 consumidores SSE, 0 escrituras en
DBs canónicas, sin órdenes reales ni claves, sin relanzamientos ni
diagnósticos públicos auxiliares.

**3. Implementation status:** EJECUTADA una sola vez (sin relanzar).
`session_id=PL-MINAUSDT-LONG-1793669229096-9d935300`,
`config_hash=4a339c046cc3ad63`, regla `RULE-CAUSAL-V1`; la ventana usó el
arnés existente en base `a11c02e` (SHA-256 completo en `preflight.json`;
BUILD_ID servido
`t4z0bfKQ_kIP9qv1WHCKR`, árbol frontend `1f6f0500cb9115fa5c9d44e07be2c5524bdee690`).

**4. Evaluation status:** **FAIL de aceptación**
(`EVALUACION_NO_ALCANZADA`) pese al PASS interno del arnés. Acreditado:
contexto cerrado no-futuro (camino corregido en a11c02e funcionó en producción:
600 velas contiguas, último cierre 1793669219999 ≤ referencia 1793669228291,
vela en curso excluida fila a fila), referencia de reloj público válida,
presupuesto exacto 7/7 ledger compartido, WS pública 237 mensajes sin
reconexiones con 3 cierres nuevos admitidos POR EL HUB, limpieza completa y
DBs canónicas intactas. NO acreditado: eventos procesados por la sesión
(`eventos_procesados=0`, `events=[]`), avance de T por evento (rev 2 con
`clock_ms=1793669280000` sin evento: UNKNOWN), evento disparador y
evaluación con decisión y motivo. Causa clasificada: adaptador SSE del
servicio de ingeniería (60/237 frames, 5 desconexiones
`TimeoutError`, conexión efectiva ~147 s tarde). No es fallo de Binance ni
del contexto corregido. `SIN_ENTRADA` no aplica (no hubo eventos
procesados).

**5. Evidence:** `docs/evidence/engineering-live-public-20261102c/` —
`evidence.json` (arnés, PASS interno), `summary.json` (veredicto global
FAIL + motivo), `RESULTADO.md`, `preflight.json`, `post_state.json`,
`ledger-run-id.json` (7 filas), `command.txt`, `sessions/`
(sesión persistida, `events=[]`), `service_logs/` (stderr vacío),
`harness-stdout.log` (UTF-16LE) + `harness-stdout-utf8.txt`.

**6. Verdict:** FAIL (contrato de aceptación del recorrido completo).

**7. Next step:** corrección local del adaptador SSE de ingeniería
(causa de desconexiones/TimeoutError y de `eventos_procesados` plano, y del
cambio de `clock_ms` sin evento); luego solicitar nueva autorización para
UNA ventana pública con `run_id` NUEVO.

## Contexto cerrado del arnés + pid-files aislados (2026-11-02, base `f033c06`)

## Contexto cerrado del arnés + pid-files aislados (2026-11-02, base `f033c06`)

**1. Title:** Corrección en código (sin Binance, sin ventana pública) del
defecto que causó el FAIL de `eng-run-public-20261102b`: el contexto enviado
incluía la vela del minuto en curso.

**2. Approval status:** AUTORIZADO por el operador de forma acotada:
trabajar sobre HEAD `f033c06` de `diag/recorrido-local-4f4273c`, corregir
solo preparación de contexto y aislamiento del pid-file en el arnés
existente, con pruebas locales del camino productivo vía proveedores
loopback, cero Binance y cero ventana pública. No autorizaba nueva ventana
pública, cambios de presupuesto, integración de rama ni relejar la
validación del backend.

**3. Implementation status:** IMPLEMENTADO. En
`scripts/engineering_live_window.py` (SHA-256
`97bec590…`): referencia temporal del reloj público sincronizado del
servicio de ingeniería con validez comprobada (`_reference_now_ms`;
`_verify_clock` ahora cableado; nunca reloj del navegador), ventana que
termina en la última vela cuyo cierre ya ocurrió (`_context_window`; cierre
exactamente igual a la referencia admitido, sin tolerancia positiva),
validación fila a fila de lo recibido (REST y caché: cierre ausente,
posterior a la referencia u OHLC de cache pre-cierre → excluido con
diagnóstico), aborto explícito ANTES de crear sesión si tras filtrar falta
contexto (`_prepare_context` + `_validar_contexto_cerrado`, taxonomía
`CONTEXTO_*` replicada, no relajada; sin descargas automáticas extra), y
`--pid-file` exclusivo por servicio y corrida con limpieza solo de lo
propio (`market_stream_service.py` ahora acepta `--pid-file`;
`sessions_dir/market-service.json` y `sessions_dir/engineering-service.json`;
`data/market-stream/service.json` de 8792 intacto). Proveedores locales de
pruebas (`local_kline_provider.py`, `local_ws_kline_provider.py`) respetan
exactamente el rango pedido.

**4. Evaluation status:** **PASS en las pruebas locales requeridas** (sin
Binance): nueva suite `tests/test_engineering_context_closed.py` 7/7 — vela
en curso excluida aunque la respuesta REST la incluya; cierre exactamente
igual a la referencia admitido; contexto insuficiente tras filtrar provoca
aborto con motivo `CONTEXTO_INSUFICIENTE` sin crear sesión y sin descargas
extra; proveedor local respeta el rango pedido y demuestra contexto
reciente, cerrado y contiguo por símbolo; pid-file ajeno preexistente
idéntico antes/después incluso ante fallo de arranque; servicio real escribe
su pid-file exclusivo y no reconstruye el por defecto. Regresión completa
local: `tests/test_engineering_live_window_local_recorrido.py` 2/2
(WS → servicio → SSE → evaluación, recorrido end to end con el arnés
corregido). Regresiones de clock/presupuesto: 32/32
(`test_engineering_clock_readiness.py`, `test_engineering_clock_budget.py`)
y servicio de mercado 40/40 (`test_market_stream.py`). Verificación de
integridad: 8792 y 3020 vivos e intactos; sin escrituras en DBs canónicas.

**5. Limitations:** el comportamiento contra Binance real queda SIN
verificar (así está autorizado): la ventana pública corregida exige
autorización nueva y run_id NUEVO. `tests/test_engineering_live_window_local.py`
sigue sin recomponerse (fixture `Args` desfasada; fallaba igual antes del
cambio). El literal histórico del detalle `build_served` («árbol e2243c9»)
sigue pendiente y no bloquea.

**6. Evidence:** `tests/test_engineering_context_closed.py`;
`tests/test_engineering_live_window_local_recorrido.py`;
`scripts/engineering_live_window.py`, `scripts/local_kline_provider.py`,
`scripts/local_ws_kline_provider.py`,
`src/microstructure_probe/market_stream_service.py`;
`docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/DECISIONS.md`
(entrada 2026-11-02 del mismo día).

**7. Last update:** 2026-11-02 (corrección implementada y verificada en
local; ventana pública nueva aún no autorizada).

## Ventana pública única — veredicto FAIL por contexto con vela en curso (2026-11-02, base `d2ca1cb`)

**1. Title:** Ejecución de UNA ventana pública autorizada con el arnés
existente (`scripts/engineering_live_window.py`) para acreditar contexto
reciente → sesión creada → cierre nuevo → avance de T → evaluación con
decisión y motivo, con presupuestos, identidad, logs persistentes y limpieza
verificados.

**2. Approval status:** AUTORIZADO por el operador de forma acotada para una
sola ejecución: deadline 180 s, hasta 7 intentos HTTP upstream totales por
run_id, 1 conexión WS combinada MINAUSDT+BTCUSDT 1m, hasta 3 reconexiones,
hasta 3 consumidores SSE, ≤300 velas por petición, cero escrituras en DBs
canónicas, sin órdenes ni claves. La autorización NO cubre una segunda
ejecución ni reutilizar el run_id.

**3. Implementation status:** WINDOW_EXECUTED — sin cambios de código. Se
ejecutó una vez (run_id `eng-run-public-20261102b`) con transporte y reloj
públicos. El preflight verificó HEAD `d2ca1cb`, rama
`diag/recorrido-local-4f4273c`, arnés SHA-256 `32429af0…`, dashboard 3020
(BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR`, árbol frontend `1f6f050…`), puertos
8791/8797 libres y 8792 intacto. El reloj público quedó válido
(`public_sincronizado`, 5/5 muestras, offset −60.40 ms). La creación de
sesión fue rechazada con `VALIDATION_ERROR: CONTEXTO_FUTURO`: el arnés
envió la vela del minuto en curso.

**4. Evaluation status:** **FAIL** (el arnés registra `ERROR` por excepción
antes de `_verdict()`). Criterios acreditados 2/8: referencia temporal
válida y presupuestos/limpieza. No acreditados: sesión/identidad, contexto
cerrado no futuro, cierre nuevo admitido, T anterior/nuevo + evento +
contador, decisión con motivo. Consumo exacto 7/7 en el ledger compartido
(5 `/time` + 2 `klines`, 0 bloqueos pre-envío). Limpieza y DBs canónicas
correctas. Sin relanzamiento.

**5. Limitaciones:** el estado de conexión de la WS combinada y el contador
de reconexiones quedan UNKNOWN (no se muestreó `/health` del servicio de
mercado tras el fallo); cero consumidores SSE se deduce del flujo de control
(la conducción nunca se inició), no de un contador. El presupuesto del
run_id quedó agotado, por lo que no cabe reintento dentro de la misma
autorización.

**6. Evidence:** `docs/evidence/engineering-live-public-20261102b/`
(`RESULTADO.md`, `summary.json`, `preflight.json`, `evidence.json`,
`post_state.json`, `ledger-run-id.json`, `harness-stdout.log`,
`harness-stderr.log`, `service_logs/`); `docs/DECISIONS.md` (2026-11-02);
`docs/CURRENT_STATE.md`; `docs/TASK_QUEUE.md`.

**7. Last update:** 2026-11-02 (ventana ejecutada; veredicto FAIL; sin
relanzamiento; corrección del arnés pendiente de autorización y prueba).

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, `DESKTOP_FIRST_SCOPE_20261020`,
  WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS (incluida la entrada
  2026-11-02 de readiness), SAFETY_RULES y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-11-02: el contexto de la
  ventana pública solo puede contener velas cerradas respecto de la
  referencia; la vela en curso nunca se envía; no se relaja la validación
  del servicio; no se relanza ni se reutiliza el run_id cuando el
  presupuesto está agotado; toda nueva conexión exige autorización nueva.
- `FEATURES_IMPLEMENTED` — ninguna función nueva. Solo evidencia, veredicto
  y documentación de una ventana fallida.
- `FEATURES_VERIFIED` — preflight sin conexión (dashboard/BUILD_ID, puertos,
  DBs), sincronización pública real del reloj (5/5), presupuesto compartido
  exacto 7/7 sin bloqueos, limpieza efectiva y DBs canónicas intactas.
- `DEFERRED_FEATURES` — corrección de `_load_recent_context` (excluir velas
  no cerradas) + prueba local; repetición de la ventana pública con run_id
  nuevo y autorización explícita; recorrido SSE→adaptador→evaluación.
- `BACKLOG_UPDATED` — yes: este bloque, CURRENT_STATE, TASK_QUEUE,
  DECISIONS y evidencia en `docs/evidence/engineering-live-public-20261102b/`.
- `DOCUMENTATION_CONFLICTS` — el check `build_served` imprime un literal
  histórico ("árbol e2243c9") que no es el árbol servido; el check
  `contexto_cargado` afirma "velas cerradas" aunque incluía una abierta. Se
  dejan registradas ambas discrepancias; ningún resultado histórico se
  reescribe.

## Indicadores compartidos V1 — primera integración vertical (2026-10-25, base `09632f4`, sin Binance)

**1. Title:** Primera integración vertical de indicadores compartidos en
`/market-lab`: inventario de motores P1 y sus fuentes, subconjunto mínimo
derivable de velas cerradas, backend única autoridad con salida versionada
(`market-indicators/v1`) para gráfico y futuro evaluador, y visualización con
valores al cursor.

**2. Approval status:** DECIDIDO por el operador para este bloque (desktop,
presupuesto cero, sin conexiones públicas, sin monitor/paper/órdenes). Sin
estrategia nueva, sin señales de entrada, sin optimización; no re-alimenta
motores P1 ni duplica sus cálculos.

**3. Implementation status:** IMPLEMENTED — módulo nuevo
`src/microstructure_probe/kline_indicators.py` (contrato
`market-indicators/v1`: solo velas cerradas, `declined[]` para lo no
derivable de OHLC, UNKNOWN con motivo, sin lookahead); gancho en
`series_payload` (bloque opcional `indicators`); nota del payload
actualizada; frontend: tipos y guard en `market-chart-contract.ts`
(`parseMarketIndicators`, `marketIndicatorAtCursor`,
`marketIndicatorsBadgeText`, fusión de bloques en `mergeEarlierSeries`),
badge `market-chart-indicators` en `MarketMeta` con valores al cursor,
nota y resumen a11y actualizados. Demo local `scripts/indicators_v1_demo.py`.
Continuación (base `2ffdede`): hilo incremental backend
(`market_stream_service.py`: snapshot pasa el bloque; en cada `closed`
fusiona la vela por `open_time`, recalcula y emite `event: indicators`) +
frontend (`applyStreamIndicators` con guard de identidad, nuevo gana, sin
recarga); badge con UNIDADES visibles; demo de navegador
`scripts/indicators_v1_public_demo.py` con transporte local + guardia de 0
solicitudes externas y verificación de identidad del dashboard en 3020.
Docs: §11/§11b del contrato del explorador, `SHARED_INDICATORS_V1.md` (§4bis),
CURRENT_STATE, TASK_QUEUE, DECISIONS (cuatro entradas), este backlog.

**4. Evaluation status:** VERIFIED con datos locales (0 peticiones upstream,
0 llamadas Binance). Backend: `tests/test_kline_indicators.py` 19/19
(velocidad 5 velas = 4 saltos validada por TIEMPO, sin lookahead,
provisional excluido y frontera de cierre, huecos/warmup con motivo sin
ceros, volumen ausente, contract, integración de `series_payload`);
regresión completa de la sesión 171 PASS (kline/explorer/history_client/
budget/market_stream), `test_market_stream.py` 34/34 con el hilo
incremental. Frontend 592 passed/1 skipped (incluye
`market-stream-contract.test.ts`, badge con unidades en
`price-chart-market.test.tsx`), `tsc` 0, `eslint` 0. Demo de navegador:
PASS 15/15 verificaciones DOM (evidencia
`docs/evidence/indicators-v1-public-2026-10-25/`, 0 externas,
BUILD_ID `e_lib1MO18w7gv6PJG2rm`).
NO evaluado: rentabilidad, señales, estrategia (fuera de alcance por diseño).

**5. Limitaciones:** warmup por payload (las primeras velas del rango
declaran `INSUFICIENT_CANDLES` aunque el caché tenga más historia fuera de
la ventana); `vwap_typical_10` es aproximación por precio típico y NO el
VWAP de negociación; sin indicadores provisionales en V1 (la vela en
formación se excluye, no se estima); flow/spread/profundidad/OI/contexto
BTC siguen sin fuente en este canal; el badge es de lectura bajo cursor,
no un panel independiente; el recalculo incremental aplica SOLO al
intervalo conectado por el stream (ventana de sesión), no a otros.
Demo: requiere ser la ÚNICA servida en 3020 (aborta si el puerto está
ocupado por un servidor ajeno; un servidor ajeno con su propio cache
env produce comparaciones de otra corrida — aprendizaje 2026-10-25).

**6. Evidence:** `docs/evidence/indicators-v1-2026-10-25.json`;
`docs/evidence/indicators-v1-public-2026-10-25/` (evidence.json PASS 15/15,
0 externas, 3 capturas, logs de build/serve/service);
`tests/test_kline_indicators.py`; `tests/test_market_stream.py`;
`frontend/src/test/market-indicators.test.ts`;
`frontend/src/test/market-stream-contract.test.ts`;
`frontend/src/test/price-chart-market.test.tsx`;
`frontend/src/lib/market-chart-contract.ts`; `frontend/src/lib/market-stream.ts`;
`frontend/src/lib/use-market-stream.ts`;
`src/microstructure_probe/market_stream_service.py`;
`scripts/indicators_v1_public_demo.py`;
`docs/SHARED_INDICATORS_V1.md`; §11 y §11b
`docs/MARKET_EXPLORER_CONTRACT_V1.md`; `scripts/indicators_v1_demo.py`;
`docs/DECISIONS.md` (2026-10-25, cuatro entradas); `docs/CURRENT_STATE.md`;
`docs/TASK_QUEUE.md`.

**7. Last update:** 2026-10-25 (demo de entrega PASS; caso canónico
restaurado en 3020 con 0 huellas públicas).

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE,
  DECISIONS (2026-10-25 ×4: presupuesto, precisiones, indicadores,
  incremental + causa raíz del servidor ajeno),
  `MARKET_EXPLORER_CONTRACT_V1` §3/§8/§11/§11b, `SHARED_INDICATORS_V1`,
  `SAFETY_RULES`, `DESKTOP_FIRST_SCOPE_20261020` y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-25: que solo se calcula lo
  derivable de velas cerradas auditadas y todo lo demás viaja `declined[]`
  con motivo; backend única autoridad + guard de identidad en el navegador;
  fusión de bloques por unión de filas validadas sin recálculo;
  `execution_id` = atribución por petición (no corrida, no ámbito del
  presupuesto, que es la ventana del ledger filtrada solo por tiempo);
  velocidad = 5 velas cerradas (4 saltos) validada por tiempo, no posición;
  recalculo incremental en el servicio por cierre con frame SSE
  `indicators` (vela provisional nunca entra en la ventana);
  identidad del dashboard del demo verificada (aborta si 3020 es de otro
  servidor; un huérfano con cache de otra corrida falsea comparaciones).
- `FEATURES_IMPLEMENTED` — subconjunto `log_return_bps`, `velocity_bps_5`,
  `rel_volume_10`, `vwap_typical_10`, `vwap_dev_bps_10`; bloque versionado;
  integración payload→modelo→badge con UNKNOWN con motivo y valores al
  cursor; hilo incremental backend+frontend sin recarga; badge con
  unidades; demo de entrega local con 0 solicitudes externas; demo y
  evidencia local.
- `FEATURES_VERIFIED` — backend 19 `test_kline_indicators` + 34
  `test_market_stream` + 171 regresión de la sesión PASS; frontend 592
  PASS/1 skip, `tsc`/`eslint` 0; demo PASS 15/15 verificaciones DOM
  (badge=backend al cursor, GAP→`UNKNOWN(GAP_IN_WINDOW)`, cierre actualiza
  sin reload, provisional excluido, símbolo sin arrastre), 0 externas,
  3 capturas.
- `DEFERRED_FEATURES` — fuentes reales de aggTrades/libro/OI/contexto BTC en
  el canal de velas (requieren nueva autorización y presupuesto explícito);
  volatilidad realizada y estructura de velas cerradas (decisión de
  ventana/semántica); indicadores provisionales (`F-…` posterior);
  `build_recovery` al ledger (vecino opcional del presupuesto); evaluador
  (no existe aún; el bloque ya le sirve de contrato); revisión visual de
  las capturas por el operador (la demo distingue DOM vs visual).
- `BACKLOG_UPDATED` — yes: este bloque, `SHARED_INDICATORS_V1.md` (§4bis),
  `MARKET_EXPLORER_CONTRACT_V1.md` §11/§11b, CURRENT_STATE, TASK_QUEUE,
  DECISIONS.
- `DOCUMENTATION_CONFLICTS` — el estado previo decía "no se dibujan
  indicadores ni se fabrican" y decía "automatizar el lado navegador" como
  tarea pendiente: la nota del gráfico y la tarea fueron actualizadas a la
  realidad (indicadores versionados del backend; automatización
  implementada en `market_stream_local_acceptance.py`, PASS×2). El FAIL del
  2026-10-24 sigue vigente; ningún resultado histórico reescrito. Los
  primeros fallos de la demo de entrega (`TIMEOUT_WAITING_series_1m`,
  gap FAIL) NO implicaban defecto de código: huérfano de servidor ajeno en
  3020 documentado en DECISIONS; la demo endurecida ahora lo detecta.

## Presupuesto REST upstream — reconciliación de alcance corregido (2026-10-25, base `309aee1`, commit `2edb56c`)

Cierre de la verificación pedida por el operador sobre el alcance real del
control de presupuesto del bloque `1b36647`/`309aee1`, con corrección aplicada
reutilizando mecanismos existentes y demostración con transporte local
(127.0.0.1; **0 llamadas Binance, ventana no abierta ni solicitada**).

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE,
  DECISIONS 2026-10-25, SAFETY_RULES, DESKTOP_FIRST_SCOPE_20261020 y este
  backlog (F-CHART-BINANCE-04 y su presupuesto REST).
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-25: reserva transaccional por
  intento (`BEGIN IMMEDIATE`) en el ledger compartido `market_fetch_ledger`;
  `LedgerAttemptGate` en `HistoryClient` con `UpstreamBudgetExceeded` antes de
  abrir socket; columnas `execution_id`/`detail` (históricas NULL = UNKNOWN);
  BFF propaga `--execution-id bff-<uuid>`; defecto latente `_window_weight`
  corregido; `build_recovery` y el régimen de peso Binance quedan fuera del
  presupuesto compartido, documentado.
- `FEATURES_IMPLEMENTED` — `MarketCache.reserve_fetch_attempt`/
  `complete_fetch_row`/`window_usage`/`fetch_rows_by_execution` (+ migración
  idempotente); gancho `attempt_gate` en `HistoryClient.get()`;
  `LedgerAttemptGate` + `build_client` en `market_explorer` con presupuesto por
  intento (páginas y reintentos, sin doble conteo); CLI
  `--execution-id`/`--max-upstream`/`--api-base` (solo loopback);
  `scripts/rest_budget_scope_demo.py`.
- `FEATURES_VERIFIED` — `tests/test_budget_scope_shared.py` (10): dos procesos
  reales del CLI concurrentes comparten límite=2 (2 upstream), tercer intento
  bloqueado antes del transporte (0 hits nuevos), reintentos (500→reintento)
  consumen 2 cupos y el 4.º intento de otro proceso se bloquea, filas
  sobreviven y reconstruyen el consumo por `execution_id`, carrera de 3 con
  2 concedidas/1 denegada. Baseline focalizado: **147 passed**
  (`pytest -k "explorer or history_client or budget or market_stream"`);
  `tsc`/`eslint` 0; vitest explorador 48/48; migración aplicada y verificada
  en `data/market-cache/market_cache.db` real con `--no-fetch` (0 upstream).
- `DEFERRED_FEATURES` — conectar `build_recovery` al ledger compartido
  (requiere autorización del operador); ejecutar en una ventana Binance real
  el arnés de navegador YA implementado
  (`scripts/market_stream_local_acceptance.py --transport public`,
  verificado PASS×2 en loopback el 2026-10-24; solo con autorización
  explícita) — la automatización del lado navegador no queda por construir;
  repetir ventana sin autorización sigue prohibido; móvil/Flutter (deferido
  por alcance de escritorio).
- `BACKLOG_UPDATED` — yes: este bloque, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS`, evidencia `docs/evidence/rest-budget-scope-2026-10-25.json`.
- `DOCUMENTATION_CONFLICTS` — el estado previo (`309aee1`) describía el
  presupuesto como medido por upstream real, pero la medición por intento era
  en memoria y la compartición era postenvío con carrera; el "2 upstream" del
  arnés de ventana era un techo del navegador, no un límite del backend. El
  veredicto `FAIL` de la ventana 2026-10-24 se mantiene intacto; ningún
  resultado histórico se reescribe.

## F-CHART-BINANCE-04 — Ventana viva ejecutada una vez por el camino real (2026-10-24, base `4956dee`)

**1. Title:** Demostrar con una sola ventana acotada que un mensaje real de Binance recorre `Binance → hub → servicio SSE → BFF → gráfico` de `/market-lab`, con adquisición separada del veredicto, evidencia DOM explícita y parada limpia.
**2. Approval status:** DECIDED y **ejecutado una vez** el 2026-10-24 con autorización explícita del operador: una conexión WS combinada, `BTCUSDT` + `MINAUSDT` 1m, ≤180 s, 1200 mensajes, 6000 eventos, ≤3 reconexiones, 3 consumidores SSE incluido el navegador, sin repetición automática. Sigue sin autorizar la conexión Binance continua, el monitor, el paper prospectivo, las órdenes, el móvil ni la ampliación de límites.
**3. Implementation status:** IMPLEMENTED — `scripts/market_stream_window.py` (orquestador del servicio existente, espera del navegador con consumidor primario, SSE directo y vía BFF, `evaluate_acceptance` puro, `--finalize`); `scripts/market_stream_service.py` reutilizado; selector del explorador con `1m` (`ContractExplorer.tsx`), histórico y suscripción con `symbol=BTCUSDT&interval=1m`; plan, contrato §15 y pruebas. No implementados: repetición automática de la ventana, indicadores compartidos, paper prospectivo, móvil.
**4. Evaluation status:** **EJECUTADO UNA VEZ CON BINANCE REAL — veredicto `FAIL` (exit 1), `acquired=true`.** Ventana `00:47:04Z`–`00:48:27Z` (83,46 s de 180 s): 1 intento de socket, 0 reconexiones, 96 eventos `BTCUSDT` + 14 `MINAUSDT`, 50 actualizaciones provisionales de la misma apertura, cierre `1792802820000` y siguiente vela `1792802880000`, BFF con 96 eventos e identidad `BTCUSDT/1m`, 0 huecos, pico de consumidores 3 y residual 1, parada limpia (exit 0, puerto cerrado, PID file eliminado, `/health` rechazado), DBs canónicas intactas (mtime 2026-10-15 11:46:27) y `market_cache.db` actualizada solo por la paginación REST del explorador. Fallan solo `dom_state_live` (la captura #2 se tomó 7 s después de la parada: la espera de 20 s expiró durante la paginación) y `dom_after_stop` (el aviso `explorer-stream-down` no apareció: el SSE del BFF siguió abierto y no se agotaron los reintentos). Cadencia medida: mediana 418 ms, mínimo 250 ms, máximo 12041 ms. Evidencia: `docs/evidence/market-stream-window-2026-10-23.json` + `…-dom-1.json`, `…-dom-2.json`, `…-dom-stop.json`. Pruebas: backend 53/53 (`test_market_stream_window` 25 + `test_market_stream` 28), explorador 12/12, `tsc --noEmit` 0, `eslint` 0. NO evaluado: repetición de la ventana, revisión visual por modelo (`NOT_REVIEWED`), rentabilidad, indicadores, ejecución.
**5. Limitaciones:** la evidencia DOM la captura el operador con un snippet documentado; el `hold` de 20 s no cubre una paginación que termine después del cierre; el aviso de servicio detenido depende de que el BFF cierre el SSE o de que el hook reconsulte `/status`; la paginación subió el contador 300→303 con ~45 KB nuevos en caché (posible defecto de anteposición, sin corregir); una ventana de minutos no generaliza al universo ni a otros intervalos; la cadencia se mide, no se asume.
**6. Evidence:** `docs/evidence/market-stream-window-2026-10-23.json`; `docs/evidence/market-stream-window-2026-10-23-dom-1.json`; `…-dom-2.json`; `…-dom-stop.json`; `docs/evidence/market-lab-1m-identity-2026-10-23.json`; `scripts/market_stream_window.py`; `tests/test_market_stream_window.py`; `frontend/src/test/contract-explorer-intervals.test.tsx`; `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md`; `docs/MARKET_EXPLORER_CONTRACT_V1.md`; `docs/CURRENT_STATE.md`; `docs/TASK_QUEUE.md`; `docs/DECISIONS.md` (2026-10-22 y 2026-10-23).
**7. Last update:** 2026-10-24.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS (2026-10-22 presupuesto de consumidores; 2026-10-23 selector `1m`), `MARKET_STREAM_CONTRACT_V1` §15, `MARKET_STREAM_LIVE_WINDOW_PLAN`, `MARKET_EXPLORER_CONTRACT_V1`, `SAFETY_RULES`, `DESKTOP_FIRST_SCOPE_20261020` y este backlog (F-04 anterior).
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-22: el presupuesto de consumidores incluye al navegador (3 totales) y la ventana espera al consumidor primario antes de abrir los suyos. DECISIONS 2026-10-23: el selector del explorador ofrece `1m` sin tocar backend, contrato ni presupuesto REST. Resultado 2026-10-24: veredicto `FAIL` medido, sin segunda ventana ni sustitución de prueba.
- `FEATURES_IMPLEMENTED` — ventana real orquestada sobre el servicio existente (preflight, espera del navegador, 2 consumidores propios, muestras, cierre, `--finalize` con exit codes 0/1/2); selector `1m` con histórico y suscripción alineados; espera del consumidor primario; documentación y evidencia.
- `FEATURES_VERIFIED` — cadena real Binance → hub → SSE → BFF → DOM con `LIVE` e identidad exacta (captura #1), cierre y siguiente vela, 96 eventos en el BFF, 3 consumidores sin exceder, parada limpia y DBs canónicas intactas; pruebas 53/53 backend, 12/12 explorador, `tsc`/`eslint` limpios, build `eiXlHvN4lJBLWcuOopsh_` servido y verificado en navegador real.
- `DEFERRED_FEATURES` — repetición de la ventana (requiere nueva autorización); corrección del `hold`/captura #2; aviso de servicio detenido con SSE del BFF abierto; análisis de la paginación 300→303; revisión visual por modelo; retención del caché; indicadores compartidos; paper con datos vivos; móvil/Flutter; REA; `/antislop` end-to-end.
- `BACKLOG_UPDATED` — yes: este bloque, `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`, `MARKET_STREAM_LIVE_WINDOW_PLAN` (resultado), `MARKET_EXPLORER_CONTRACT_V1` (selector de la UI).
- `DOCUMENTATION_CONFLICTS` — el plan asumía que la captura #2 cabría en los 20 s de espera y que el aviso de servicio detenido aparecería siempre al parar; la ejecución real mostró lo contrario y queda registrado como limitación, no como `PASS`. `CURRENT_STATE`/`TASK_QUEUE` de F-03 citan 60 s/400 mensajes: histórico válido, sustituido por 180 s/1200 mensajes. La recepción real se acredita con la evidencia de esta ventana; el veredicto global es `FAIL` por los dos checks DOM, nunca `PASS`.

### Corrección del cierre de F-CHART-BINANCE-04 (2026-10-24, base `965ab87`)

**1. Title:** Cerrar el expediente de la ventana `FAIL` sin repetirla: propagar
cierre/error/cancelación entre servicio, BFF y navegador, retirar `LIVE` por
frescura con causa inmediata y corregir la paginación `300→303`.

**2. Approval status:** DECIDED dentro del alcance autorizado (escritorio,
presupuesto cero, observación; sin nueva conexión Binance, sin actualización
automática/mayor, sin cambios económicos ni de estrategia).

**3. Implementation status:** IMPLEMENTED — BFF con `AbortController` +
`req.signal` + bombeo de frames + `event: error`
(`STREAM_UPSTREAM_CLOSED`/`STREAM_UPSTREAM_ERROR`) + `cancel()` aborta el
upstream; hook con frescura local (ticker 1 s) y causa inmediata en
`onerror`/`event: error` con código; servicio despierta el consumidor al cerrar
el cliente; `mergeEarlierSeries` + petición del bloque estrictamente anterior en
`ContractExplorer.tsx`. No implementados: repetición de la ventana, indicadores,
paper prospectivo, móvil.

**4. Evaluation status:** VERIFIED con transporte controlado (WS falso local +
servicio real + BFF real; cero Binance): consumidores 1 → 0 en 14 ms con el
servicio vivo; EOF + `event: error` `STREAM_UPSTREAM_ERROR` en 6025 ms al parar;
DOM real `DESCONECTADO` + causa en 12 ms. Paginación: con el bloque almacenado la
petición nueva devuelve 300 anteriores (0 solapan) y el merge conserva el extremo
reciente; con el bloque ausente no finge crecimiento. Pruebas: backend 29/29 +
25/25, frontend focalizado 28/28, contrato 13/13, `tsc`/`eslint` 0, `next build`
OK (`BUILD_ID=XozH8PXJA4yZR59XphpyH`, `/market-lab` 200). **NO re-verificado con
Binance**: la ventana real no se repite sin autorización y su veredicto sigue
`FAIL`. Inspección visual `NOT_REVIEWED`.

**5. Limitaciones:** las capturas controladas no acreditan recepción real; el
detalle de causa del upstream es técnico (`TypeError: UND_ERR_SOCKET`); el
`hold` de 20 s sigue sin cubrir una paginación que termine después del cierre
(hay que paginar antes); los 5 `high` de cadena de desarrollo siguen; el primer
`next build` se detiene con el aviso de seguridad y completa al reintentar.
Desviación del diagnóstico: 12 peticiones REST reales encadenadas por una página
`/market-lab` con `0GUSDT` 1h seleccionado añadieron 3.552 velas a la caché
derivada (sin perder filas previas; DBs canónicas intactas) y revelaron que una
sola interacción puede encadenar varias descargas de "anteriores".

**6. Evidence:** `docs/evidence/market-stream-controlled-disconnect-2026-10-24.json`;
`docs/evidence/market-lab-controlled-disconnect-2026-10-24.json` (+ PNG
`market-lab-controlled-live-2026-10-24.png` y `...-down-2026-10-24.png`);
`docs/evidence/market-lab-disconnect-planes-2026-10-24.md`;
`docs/evidence/pagination-300-303-2026-10-24.json`;
`docs/evidence/nextjs-security-diagnosis-2026-10-24.json`;
`frontend/src/app/api/v1/market-stream/route.ts` (+ test);
`frontend/src/lib/use-market-stream.ts`;
`frontend/src/lib/market-chart-contract.ts`;
`frontend/src/components/market-lab/ContractExplorer.tsx`;
`src/microstructure_probe/market_stream_service.py`;
`tests/test_market_stream.py`; `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` §12.

**7. Last update:** 2026-10-24.

#### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS` (2026-10-22 presupuesto de consumidores; 2026-10-23 selector
  `1m`; 2026-10-24 veredicto `FAIL`), `MARKET_STREAM_CONTRACT_V1` §15,
  `MARKET_STREAM_LIVE_WINDOW_PLAN` §11, `MARKET_EXPLORER_CONTRACT_V1`,
  `SAFETY_RULES`, `DESKTOP_FIRST_SCOPE_20261020` y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-24: el cierre/error del upstream
  se declara explícitamente en el BFF (nunca se reenvía el cuerpo en crudo); el
  hook calcula la frescura localmente y muestra la causa sin esperar reintentos;
  el consumidor se libera al cerrar el cliente sin esperar al heartbeat; la
  paginación pide el bloque estrictamente anterior y cuenta velas únicas (no
  exige `+300`).
- `FEATURES_IMPLEMENTED` — BFF pump/abort/causa; hook de frescura y causa
  inmediata; liberación inmediata del consumidor; `mergeEarlierSeries` y
  petición anterior; pruebas nuevas (BFF, hook, contrato, explorador, servicio);
  documentación y evidencia.
- `FEATURES_VERIFIED` — liberación 14 ms; EOF + causa 6025 ms; DOM 12 ms;
  paginación 300 únicas/0 solape con extremo reciente preservado; 300→303
  unitario; `tsc`/`eslint` 0; build y `/market-lab` 200.
- `DEFERRED_FEATURES` — repetición de la ventana real (requiere autorización);
  actualización de Next.js a 16.4.1 (decisión pendiente); revisión visual por
  modelo; retención del caché; indicadores compartidos; paper con datos vivos;
  móvil/Flutter; REA; `/antislop` end-to-end.
- `BACKLOG_UPDATED` — yes: esta sección, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS` y `MARKET_STREAM_LIVE_WINDOW_PLAN` §12.
- `DOCUMENTATION_CONFLICTS` — el plan de la ventana asumía que el aviso de
  servicio detenido aparecería siempre al parar; la ejecución real mostró lo
  contrario y ahora la causa está demostrada y corregida, pero el veredicto
  medido sigue `FAIL` hasta repetir la ventana. `TASK_QUEUE`/`CURRENT_STATE`
  anteriores citan BUILD_ID `eiXlHvN4lJBLWcuOopsh_`: histórico válido, sustituido
  por `XozH8PXJA4yZR59XphpyH`.

## Transporte aislado y paginación acotada (2026-10-24, base `5dec9ff`, sin ventana)

**1. Title:** Eliminar las conexiones accidentales al endpoint público y las
descargas encadenadas de "anteriores" sin abrir una nueva ventana Binance ni
actualizar Next.js.

**2. Approval status:** DECIDED dentro del alcance autorizado (escritorio,
presupuesto cero, observación; sin nueva conexión Binance, sin actualización de
Next.js, sin cambios económicos/estrategia).

**3. Implementation status:** IMPLEMENTED —
`market_stream_service.py` exige `--transport local|public`: `local` valida
`ws://127.0.0.1|localhost|::1:<puerto>`, desactiva `build_recovery` y no tiene
fallback; `public` es la activación explícita; sin transporte válido, exit 2
(`TRANSPORT_CONFIG`) antes de abrir sockets. `/health` declara
`transport.mode/base_url`; el orquestador de ventana pasa el modo. Paginación:
`frontend/src/lib/earlier-gate.ts` decide al terminar un gesto (rueda con
debounce 250 ms, `pointerup`, `keyup`); `PriceChart.tsx` conserva el encuadre por
índice exacto de la primera vela previa aunque el feed actualice la última;
`ContractExplorer.tsx` añade guard síncrono de petición en vuelo, clave de rango
y distinción cancelación/agotamiento/fallo con reintento manual.

**4. Evaluation status:** VERIFIED sin red pública. Backend: 29/29 + 25/25 +
13/13 (incluye servicio real con WS falso local, cero resoluciones de
`fstream.binance.com`, liberación del consumidor). Frontend: gate 5/5, PriceChart
9/9 (regresión: múltiples eventos de rango tras anteponer → una sola petición;
anteponer con extremo reciente actualizado conserva encuadre), explorador 12/12
(dos clics en el mismo tick → una petición; fallo → gráfico conservado y
reintento), contrato 13/13. `tsc --noEmit` 0, `eslint` 0 en los archivos tocados,
`next build` OK. CLI: 6/6 configuraciones inválidas → exit 2 sin sockets.
Evidencia: `docs/evidence/market-stream-transport-failclosed-2026-10-24.json`.
**NO verificado con Binance**: el veredicto medido de la ventana sigue `FAIL` y
no se repite sin autorización.

**5. Limitaciones:** la primera interacción de la cadena de 12 sigue `UNKNOWN`
(la evidencia de la ventana no registra acciones de UI); una segunda cadena
observada antes de la corrección (`ACTUSDT`, 6 peticiones en 17,4 s, ids 54–59)
confirma el mismo patrón; la corrección se acredita por reproducción del
mecanismo, no por una nueva ventana; el servicio
sigue manual y detenido por defecto; los 5 `high` de cadena de desarrollo siguen;
`next build` se detiene una vez con el aviso de seguridad y completa al
reintentar.

**6. Evidence:** `docs/evidence/market-stream-transport-failclosed-2026-10-24.json`;
`docs/evidence/market-lab-pagination-cascade-2026-10-24.json` (cadenas
observadas `0GUSDT` 12 y `ACTUSDT` 6, leídas en modo solo-lectura);
`docs/evidence/nextjs-security-diagnosis-2026-10-24.json` (advisories desde
`api.github.com/advisories` + lock + manifiestos + sondas locales);
`tests/test_market_stream_transport.py`; `tests/test_market_stream.py`;
`tests/test_market_stream_window.py`; `frontend/src/lib/earlier-gate.ts` (+ test);
`frontend/src/components/chart/PriceChart.tsx` (+ test);
`frontend/src/components/market-lab/ContractExplorer.tsx` (+ test);
`scripts/market_stream_window.py`; `docs/MARKET_STREAM_CONTRACT_V1.md` §9;
`docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` §12.6.

**7. Last update:** 2026-10-24.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS` (2026-10-24 cierre/error del BFF, frescura local, liberación
  inmediata, bloque anterior), `MARKET_STREAM_CONTRACT_V1`, `MARKET_STREAM_LIVE_WINDOW_PLAN`
  §12, `SAFETY_RULES`, `DESKTOP_FIRST_SCOPE_20261020` y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-24: el servicio no arranca sin
  transporte explícito (falla cerrado, sin fallback público); `local` exige
  loopback y desactiva la reparación REST; la paginación automática se decide
  solo al terminar un gesto y nunca por el cambio de rango que provoca anteponer.
- `FEATURES_IMPLEMENTED` — resolución/validación de transporte en el servicio
  (+ `/health`), puerta `earlier-gate`, evaluación al final del gesto, anclaje
  exacto del encuadre al anteponer, guard de petición en vuelo y estados
  cancelación/agotamiento/fallo en el explorador, pruebas y evidencia.
- `FEATURES_VERIFIED` — 6/6 configuraciones inválidas sin sockets; servicio real
  con WS local sin resoluciones públicas y liberación del consumidor; una página
  por gesto; dos clics → una petición; fallo → gráfico conservado + reintento;
  `tsc`/`eslint` 0; build OK; `/market-lab` 200.
- `DEFERRED_FEATURES` — nueva ventana real (requiere autorización); actualización
  de Next.js a 16.4.1 (decisión pendiente); revisión visual por modelo;
  retención del caché; indicadores compartidos; paper con datos vivos;
  móvil/Flutter; REA; `/antislop` end-to-end.
- `BACKLOG_UPDATED` — yes: esta sección, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS`, `MARKET_STREAM_CONTRACT_V1` §9, `MARKET_STREAM_LIVE_WINDOW_PLAN`
  §12.5–§12.6.
- `DOCUMENTATION_CONFLICTS` — el diagnóstico previo decía "`sharp` no instalado";
  el lock y `node_modules` muestran `sharp 0.35.5` (opcional de Next), que es la
  versión del workaround. La sección histórica de la ventana se conserva tal
  cual; el `FAIL` medido no se reinterpreta.

## F-CHART-BINANCE-03 — Actualización continua de velas en el explorador (2026-10-21, base `469e282`)

**1. Title:** Vela en formación actualizándose sin recargar la página para el contrato seleccionado, con conexión compartida backend, snapshot+stream reconciliados, reconexión con backoff, reparación acotada de huecos, estados honestos (CONECTANDO/RECIBIENDO/OBSOLETO/DESCONECTADO/RECUPERANDO) y `LIVE` condicionado a frescura real.
**2. Approval status:** DECIDED dentro del alcance autorizado (escritorio, presupuesto cero, observación; reutilizar adquisición/normalización/reconexión/límites/supervisión existentes; sin indicadores nuevos, sin seleccionador, sin paper con datos vivos, sin riesgo/estrategias/optimización, sin órdenes/capital/pagos, sin móvil, sin REA, sin Antislop). **Autoriza implementación, pruebas controladas, REST acotado ya contemplado y despliegue local del dashboard; NO autoriza abrir la conexión Binance continua** (ventana viva aparte).
**3. Implementation status:** IMPLEMENTED — backend `src/microstructure_probe/{market_stream,market_stream_service}.py` + `scripts/{market_stream_service,market_stream_window}.py`; contrato `docs/MARKET_STREAM_CONTRACT_V1.md`; plan `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md`; BFF `frontend/src/app/api/v1/market-stream/{route,status/route}.ts`; `frontend/src/lib/{market-stream,use-market-stream,stream-bridge}.ts`; `PriceChart.tsx` con serie provisional propia y actualización incremental; `ContractExplorer.tsx` con panel de estado del feed; `market-chart-contract.ts` con bloque `stream` opcional. No implementados: indicadores compartidos, selección automática, paper prospectivo, ventana viva ejecutada.
**4. Evaluation status:** VERIFICADO con transporte controlado y servido; **NO verificado con Binance** — backend focalizado `tests/test_market_stream.py` 28/28 (casos A–I + URL/backoff/frames de control + HTTP/SSE en puerto efímero); suite backend 1405 passed + 2 skipped; frontend 538 passed + 1 skipped (539), `tsc --noEmit` 0, `eslint src` 0 errores/5 warnings preexistentes, `next build` OK; build `n6FZutTsk5m8FFilTlxIo`, PID 18112, `/market-lab` HTTP 200; navegador (DOM/red): `MINAUSDT` 299 velas + 1 provisional `COVERED`, panel `DESCONECTADO · servicio detenido` / `no LIVE` / `sin mensajes`, 1 petición `market-series`, 1 `status`, **0** intentos de `EventSource`, proxy `/api/v1/market-stream` 503 `STREAM_SERVICE_DOWN`; smoke del servicio en 8799 con `socket.connected=false`, `attempts=0`, `streams=[]` y parada limpia (PID file borrado, 0 procesos). Ledger del caché acumulado 25 peticiones/0 reintentos/0 fallos; `historical.db` y `microprobe.db` con mtime 2026-10-15 11:46:27. NO evaluado: recepción real, cadencia real, cierre real, inspección visual por modelo, rentabilidad, indicadores, ventana viva.
**5. Limitaciones:** el feed solo se abre con el servicio local arrancado a mano (por defecto está **detenido**); sin persistencia de actualizaciones (anillo en memoria de 300 velas y liberación a los 30 s); la reparación REST puede quedar `partial`/`failed` y se muestra tal cual; `1M` sigue excluido del explorador; sin poda automática del caché; 5 vulnerabilidades `npm audit` `high` de cadena de desarrollo sin abordar por decisión razonada; fallo intermitente preexistente de `backtest-guard-regressions` (C1) bajo carga de suite completa; sin inspección visual por modelo; sin móvil/Flutter. La cadencia de actualización documentada por Binance es contradictoria (1000–2000 ms vs 250 ms): se medirá en la ventana viva y no se afirma.
**6. Evidence:** `docs/MARKET_STREAM_CONTRACT_V1.md`; `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md`; `docs/CURRENT_STATE.md` § actualización continua; `docs/DECISIONS.md` §2026-10-21; `tests/test_market_stream.py`; `frontend/src/test/{market-stream-contract.test.ts,use-market-stream.test.tsx,price-chart-market.test.tsx,contract-explorer.test.tsx}`; `data/market-cache/market_cache.db` ledger (25/0/0); captura `.playwright-mcp/market-stream-service-down.png` y red del navegador (sin `EventSource`).
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, skill dashboard-v2, CURRENT_STATE, TASK_QUEUE, DECISIONS, `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`, `docs/MARKET_EXPLORER_CONTRACT_V1.md`, `docs/SAFETY_RULES.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md` y este backlog (F-CHART-BINANCE-02, F-PAPER-03).
- `NEW_DECISIONS_RECORDED` — DECISIONS §2026-10-21 «Actualización continua de velas (`market-stream/v1`)»: contrato antes de código; servicio dedicado y planos separados; una sola conexión combinada en `/market`; sin dependencias nuevas; snapshot desde el almacén sin duplicar REST; reconciliación por buffer con desbordamiento declarado; sin persistencia del feed; reparación acotada y declarada; `LIVE` como conclusión; reconexión con presupuesto; límites duros; cambio de identidad sin contaminación; vela provisional en serie propia; estados de verificación separados.
- `FEATURES_IMPLEMENTED` — hub con refcount y anillo; transporte con backoff/jitter, `serverShutdown`, frames de control; detección y reparación de huecos; servicio SSE local con `/health`/`/stream`/`/shutdown` y PID file; BFF SSE + estado; hook con una `EventSource` por gráfico y tope de reintentos; fusión de snapshot+stream por `open_time` con la cerrada ganando; serie provisional ámbar; actualización incremental de la cola; panel de estado con fuente, identidad, estado, LIVE, última actualización, velas y huecos; aviso explícito de servicio detenido.
- `FEATURES_VERIFIED` — A–I con transporte y REST simulados (28/28); fusión/`LIVE`/etiquetas/huecos en pruebas unitarias; hook con `EventSource` falso (conexión, ticks, cierre, cambio de símbolo, desmontaje, servicio detenido); serie provisional y no reescritura de cerradas en `price-chart-market`; navegador real sobre el build servido (histórico visible + servicio detenido + `no LIVE` + 0 intentos de stream); smoke del servicio con parada limpia; presupuesto REST y mtimes canónicos sin cambios.
- `DEFERRED_FEATURES` — ventana viva (requiere autorización explícita); indicadores compartidos; paper con datos vivos; selección automática; política de retención/poda del caché; stops/objetivos arrastrables; F-PAPER-01; móvil/Flutter; REA; `/antislop` end-to-end; fallo intermitente de `backtest-guard-regressions`.
- `BACKLOG_UPDATED` — yes: este bloque, `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`, `MARKET_STREAM_CONTRACT_V1`, `MARKET_STREAM_LIVE_WINDOW_PLAN` y punteros en `ACUERDOS_GRAFICO_BINANCE_V1` / `MARKET_EXPLORER_CONTRACT_V1`.
- `DOCUMENTATION_CONFLICTS` — F-CHART-BINANCE-02 y el aviso de `/market-lab` decían «sin websocket, sin feed continuo»: siguen siendo ciertos para el **estado por defecto** (servicio detenido) y se corrige el texto de la página para no negar la capacidad ya implementada; la vista ya no afirma LIVE por defecto. `F-CHART-BINANCE-01/02` declaraban feed vivo NO implementado: ahora está implementado y probado con transporte controlado, **no** verificado con Binance. Se mantiene que un socket abierto no equivale a LIVE y que no hay PASS visual.

## F-NAV-V2-ACCESS-01 — Acceso directo a mercado y simulación

Approval: DECIDED por petición del usuario. Implementation: IMPLEMENTED (navegación + orden del explorador). Verified: pruebas de navegación 4/4, typecheck/lint/build y HTML servido; VISUAL NOT VERIFIED. No cambia mercados, estrategia ni motor económico. Fuente base 25a0f01.

- DECISIONS_REVIEWED: AGENTS, WORKFLOW, skill dashboard-v2, CURRENT_STATE, TASK_QUEUE, FEATURE_BACKLOG, diseño/progreso/decisiones V2.
- NEW_DECISIONS_RECORDED: nombres y rutas distintos para mercado, simulación y replay; feed continuo se mantiene pendiente explícito.
- FEATURES_IMPLEMENTED: tres accesos visibles y explorador primero en /market-lab.
- FEATURES_VERIFIED: 4/4 navegación; tsc/eslint/build exit 0; cuatro páginas HTTP 200 con enlaces y BUILD_ID 3ThnqxocDEmcursE2ZYpu. Sin inspección visual ni clics de navegador en esta sesión.
- DEFERRED_FEATURES: feed continuo, indicadores compartidos y paper prospectivo; móvil/Flutter e IA diferidos.
- BACKLOG_UPDATED: este ID, CURRENT_STATE y TASK_QUEUE.
- DOCUMENTATION_CONFLICTS: se aclara que el enlace Paper Lab anterior abría solo replay; gráfico existente y catálogo NO significan LIVE. Historia preservada.

## F-CHART-BINANCE-02 — Búsqueda de contratos USD-M e histórico paginado bajo demanda (2026-10-21, base `9689f3e`)

**1. Title:** Explorador de contratos Binance USD-M Futures con catálogo cacheado, histórico leído de lo almacenado y adquirido solo el bloque faltante, paginación hacia atrás que conserva el encuadre y gráfico reutilizado, sin feed continuo ni indicadores.
**2. Approval status:** DECIDED dentro del alcance autorizado (escritorio, REST público acotado, presupuesto cero, sin websocket/monitor/paper prospectivo/órdenes/capital/optimización; sin cambios de estrategia, umbrales, costes, funding ni motor canónico; móvil diferido).
**3. Implementation status:** IMPLEMENTED (paso 4 parcial de `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`) — backend `src/microstructure_probe/{market_cache,market_explorer}.py` + `scripts/market_explorer.py`; BFF `frontend/src/app/api/v1/{market-contracts,market-series}/route.ts`; `frontend/src/lib/{market-explorer,market-chart-contract,explorer-bridge}.ts`; gráfico generalizado `frontend/src/components/chart/PriceChart.tsx` (con `paper-lab-live/PaperChart.tsx` como fachada); UI `frontend/src/components/market-lab/ContractExplorer.tsx` en `/market-lab`; correcciones (a) recuperación de sesión desde la pantalla inicial y (b) encuadre inicial en `PaperLabLive.tsx`/`PriceChart.tsx`. NO implementados: feed vivo/continuo, reconexión, indicadores compartidos, vela en formación refrescándose sola.
**4. Evaluation status:** VERIFICADO — backend `pytest tests -q` 1375 passed + 2 skipped; focalizado `tests/test_market_explorer.py` 41/41; frontend 520 passed + 1 skipped (521); `tsc --noEmit` 0; `eslint src` 0 errores/5 warnings preexistentes; `next build` OK; build `9xXiQvrFIA0YaC3Vc_61F`, PID 16164, `http://127.0.0.1:3020/market-lab` HTTP 200; REST público 16 peticiones (0 reintentos, 0 fallos), catálogo 931 contratos, BTCUSDT y MINAUSDT 1h con 299 → 556 velas al paginar y 43 huecos reales del canónico declarados; navegador real con `MINA` → `MINAUSDT` → histórico → «Cargar anteriores» y con recuperación de sesión paper por `GET` (0 mutaciones). NO evaluado: inspección visual por modelo (sin proveedor de visión), rentabilidad, feed vivo, indicadores, reconexión.
**5. Limitaciones:** sin conexión continua, así que la última vela no se refresca sola y la vista nunca se rotula LIVE; `1M` excluido (mes calendario sin ms fijos); los huecos del canónico se muestran como huecos y no se rellenan; caché sin poda automática; sin indicadores ni objetivos (no existe productor para este flujo); 5 vulnerabilidades `npm audit` `high` de cadena de desarrollo sin abordar por decisión razonada; fallo intermitente preexistente de `backtest-guard-regressions` (C1) bajo carga de suite completa; sin inspección visual por modelo; sin móvil/Flutter.
**6. Evidence:** `docs/MARKET_EXPLORER_CONTRACT_V1.md`; `docs/CURRENT_STATE.md` § explorador de contratos; `docs/DECISIONS.md` §2026-10-21 explorador; `docs/ACUERDOS_GRAFICO_BINANCE_V1.md` §actualización paso 4; `tests/test_market_explorer.py`; `frontend/src/test/{market-explorer,market-chart-contract,price-chart-market,contract-explorer,paper-lab-initial-recovery}.test.*`; ledger `data/market-fetch-ledger` del caché aislado (16 peticiones); capturas `.playwright-mcp/market-lab-explorer-{selected,paginated}.png` y `paper-lab-live-recovered.png`.
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS, `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`, `docs/PAPER_CHART_CONTRACT_V1.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md`, `docs/MASTER_PLAN.md` y este backlog (F-CHART-BINANCE-01, F-PAPER-03).
- `NEW_DECISIONS_RECORDED` — DECISIONS §"2026-10-21 — Explorador de contratos USD-M e histórico paginado bajo demanda": auditoría previa y reutilización, autoridad única Python, caché aislada no canónica, presupuesto explícito, leer antes de pedir, vela provisional honesta, intervalos con aritmética exacta, paginación que conserva el encuadre, encuadre inicial una sola vez, no contaminación entre contextos, componente único de gráfico, recuperar sin crear, triage de dependencias y verificación declarada por estados.
- `FEATURES_IMPLEMENTED` — catálogo USD-M cacheado con búsqueda y motivos de exclusión; histórico canónico+caché con cobertura explícita; adquisición del bloque faltante con presupuesto; paginación hacia atrás con rango visible preservado; descarte de respuestas tardías; estados de carga/vacío/sin cobertura/error/rate limit; volumen con unidad; `market-chart/v1` con `operation=null` y guarda anti-marcas de Paper Lab; recuperación de sesión paper desde la pantalla inicial; encuadre inicial diferido y único.
- `FEATURES_VERIFIED` — A–H por pruebas focalizadas (A, B, C, D, E, F, G, H) y, además, A, C, E, F y G con navegador real sobre el build servido; backend focalizado y suite completa; `tsc`, `eslint`, `next build`; verificación REST acotada con ledger (16 peticiones, 0 reintentos, 0 fallos) y cobertura declarada; BFF con 400/403 comprobados.
- `DEFERRED_FEATURES` — feed vivo/continuo y reconexión (paso 4b, requiere autorización separada); indicadores compartidos; vela en formación refrescándose sola (paso 5); política de retención/poda del caché; stops/objetivos arrastrables; F-PAPER-01; móvil/Flutter; ejecución end-to-end de `/antislop`; fallo intermitente de `backtest-guard-regressions` bajo carga.
- `BACKLOG_UPDATED` — yes: este bloque, y las actualizaciones de `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`, `ACUERDOS_GRAFICO_BINANCE_V1` y el nuevo `MARKET_EXPLORER_CONTRACT_V1`.
- `DOCUMENTATION_CONFLICTS` — F-CHART-BINANCE-01 declaraba "contrato vivo/búsqueda/indicadores/volumen NO implementados": sigue vigente para contrato vivo e indicadores, pero búsqueda, histórico paginado y volumen de mercado quedan implementados aquí y se anotan como tales. El residual previo «el selector de persistencia solo aparece con sesión activa» queda corregido y se documenta como cerrado. La falta de inspección visual por modelo se declara; DOM/geometría/HTTP, análisis de píxeles y capturas no se convierten en PASS visual. El caché del explorador se documentó como aislado y no canónico; no se escribió en `microprobe.db` ni en `historical.db`.

## F-CHART-BINANCE-01 — Contrato `paper-chart/v1` y gráfico Lightweight Charts sobre fixtures (2026-10-21, base `ac716d3`)

**1. Title:** Contrato versionado de datos, tiempos e IDs para el gráfico de `/paper-lab-live` y gráfico financiero interactivo alimentado solo por el backend existente, primero sobre fixtures.
**2. Approval status:** DECIDED dentro del alcance autorizado (escritorio, fixtures, sin Binance/monitor/adquisición/paper prospectivo/órdenes/pagos/optimización; sin cambios de estrategia, umbrales, costes, funding ni motor canónico; móvil diferido).
**3. Implementation status:** IMPLEMENTED (rebanada sobre fixtures) — `frontend/src/lib/paper-chart-contract.ts`, `frontend/src/components/paper-lab-live/PaperChart.tsx`, integración en `PaperLabLive.tsx`, `paper-lab-live.ts` (velas nullable, `event_id`), `src/microstructure_probe/paper_lab_engine.py` (`event_id` público y tiempo de simulación en eventos de decisión), `docs/PAPER_CHART_CONTRACT_V1.md`, `frontend/THIRD_PARTY_NOTICES.md` y `frontend/THIRD_PARTY_LICENSES/`. Se eliminó el `LiveChart` previo. Contrato vivo/búsqueda/indicadores/volumen siguen NO implementados.
**4. Evaluation status:** VERIFICADO en fixtures — backend focalizado 38/38, suite completa 1290 OK (2 skipped), frontend 484 passed + 1 skipped, `tsc --noEmit` 0, `eslint` 0 errores (5 warnings preexistentes); build `PPE-Io-M4ivYg3dvJRqwh`, PID 27612, HTTP 200; aceptación A–H con controles reales (incluida la regresión 101 → 95.95 → -51.56 sin salida 80 y `open_at_end` sin cierre inventado). NO evaluado: inspección visual por modelo (proveedor sin autenticación), búsqueda de contratos, histórico paginado, feed vivo, desconexión/reconexión, volumen/indicadores, rentabilidad.
**5. Limitaciones:** solo fixtures (sin venue Binance real); `volume`/`indicators`/`target` ausentes porque el backend no los produce; el selector de persistencia solo aparece con sesión activa (corregido en F-CHART-BINANCE-02), así que recuperar tras refresco exigía seleccionar una fixture primero; el ajuste inicial tras pasos incrementales puede omitir la primera vela de contexto hasta `Ajustar` (corregido en F-CHART-BINANCE-02); 5 vulnerabilidades `npm audit` no abordadas; sin móvil/Flutter.
**6. Evidence:** `docs/PAPER_CHART_CONTRACT_V1.md`; `docs/CURRENT_STATE.md` § gráfico Paper Lab; `docs/DECISIONS.md` §2026-10-21 gráfico Paper Lab; `frontend/src/test/paper-chart-contract.test.ts`; `frontend/src/test/paper-chart.test.tsx`; `tests/test_paper_lab_engine.py` (`event_id`, solo-open, tiempo de simulación); capturas `.playwright-mcp/paper-chart-{A..H}*.png`.
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS, `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`, `docs/DASHBOARD_V2_API_CONTRACTS.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md` y este backlog (F-PAPER-02, F-PAPER-03, F-CHART-BINANCE-01).
- `NEW_DECISIONS_RECORDED` — DECISIONS §"2026-10-21 — Gráfico Paper Lab: contrato `paper-chart/v1` y Lightweight Charts 5.2.1": auditoría previa, identidad/UNKNOWN, ms→s, solo-open, stop/salida/realizado, `event_id` y tiempo de simulación, biblioteca fijada y licencias, montaje cliente y limpieza, verificación honesta y residuales.
- `FEATURES_IMPLEMENTED` — contrato `paper-chart/v1`; adaptador y componente; marcadores/líneas; estados de cobertura; `event_id` público; tiempos de simulación en eventos de decisión; avisos de licencia.
- `FEATURES_VERIFIED` — A–H en navegador real sobre el build servido; pruebas de contrato/wiring/backend; typecheck, lint y builds; cierre automático y `open_at_end` reconciliados con la API.
- `DEFERRED_FEATURES` — búsqueda de contratos, histórico paginado, feed vivo y reconexión; volumen/indicadores (sin productor); objetivo (no existe); stops/objetivos arrastrables; F-PAPER-01; móvil/Flutter; ejecución end-to-end de `/antislop`.
- `BACKLOG_UPDATED` — yes: este bloque, la sección histórica de F-CHART-BINANCE-01 y las actualizaciones de `CURRENT_STATE`, `TASK_QUEUE` y `DECISIONS`.
- `DOCUMENTATION_CONFLICTS` — el registro previo de F-CHART-BINANCE-01 declaraba "NOT IMPLEMENTED" y ausencia de `lightweight-charts`; se actualiza a implementación parcial sobre fixtures preservando que el contrato vivo, la búsqueda y los indicadores siguen NO implementados. La falta de inspección visual por modelo se declara; DOM/geometría/HTTP y capturas no se convierten en PASS visual. El residual del selector de persistencia se documenta, no se corrige aquí.

## F-PAPER-03 — Orden temporal del stop, stop efectivo y paridad canónica en Paper Lab (2026-10-21)

**1. Title:** Corrección de la salida por stop de Paper Lab para que respete el orden temporal (stop de la vela de entrada antes que un gap posterior), publique el stop efectivo que gobierna la operación y coincida con `run_backtest` en precio, tiempo y costes.
**2. Approval status:** DECIDED dentro del alcance autorizado (desktop-only, fixtures, sin Binance/monitor/paper prospectivo/órdenes/pagos/optimización; sin cambios de estrategia, umbrales ni motor canónico).
**3. Implementation status:** IMPLEMENTED en `src/microstructure_probe/paper_lab_engine.py` (revelado open/close, autoridad única, stop efectivo, `open_at_end`, `can_step`), `frontend/src/components/paper-lab-live/{PaperLabLive,LiveChart}.tsx`, `frontend/src/lib/paper-fixtures.ts` (fixture `btc_long_stop_order`), `tests/test_paper_lab_engine.py` y `frontend/src/test/live-chart.test.tsx`.
**4. Evaluation status:** VERIFICADO — paridad exacta con `run_backtest` en LONG (95.95 @ 1800000, neto -51.56), SHORT (103.95, -51.64), gap legítimo (90) y fin de datos (`open_at_end`, `realized` null); motor 30/30, integración 5/5, suite completa 1290 OK (2 skipped), frontend 471 passed + 1 skipped, `tsc --noEmit` 0; navegador real con cierre automático por `Paso a paso` (sesión `PL-BTCUSDT-LONG-1792627398136-5241b33a`): entrada 101.00, stop 95.95, salida 95.95, neto -51.56, funding UNKNOWN; HTTP 200 con los mismos valores. NO evaluado: inspección visual por modelo (sin proveedor de visión), rentabilidad, motor paper completo.
**5. Limitaciones:** La verificación visual se limita a DOM/geometría y capturas locales; no hubo modelo de visión disponible. `open_at_end` mantiene el neto no realizado sin costes hipotéticos de salida (coherente con el contrato existente; no se cambia aquí). Funding ausente sigue UNKNOWN. Sin Lightweight Charts, móvil ni paper prospectivo.
**6. Evidence:** `docs/CURRENT_STATE.md` § F-PAPER-03; `docs/DECISIONS.md` 2026-10-21 orden temporal/stop efectivo; `tests/test_paper_lab_engine.py` (LONG/SHORT/continuación/fin de datos); `frontend/src/test/live-chart.test.tsx`; capturas `.playwright-mcp/paper-lab-stop-order-*.png`; build `MzvbhIwIOPI7PNIKJlAve`, PID 24060.
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS (mecánica canónica `backtest_offline` y entradas previas de Paper Lab), FEATURE_BACKLOG (F-PAPER-02, F-CHART-BINANCE-01), `docs/ACUERDOS_GRAFICO_BINANCE_V1.md` y `docs/DESKTOP_FIRST_SCOPE_20261020.md`.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"2026-10-21 — Paper Lab: orden temporal del stop, stop efectivo y paridad canónica": revelado open/close, autoridad única, stop efectivo publicado, `open_at_end` y alcance.
- `FEATURES_IMPLEMENTED` — F-PAPER-03 (orden temporal, stop efectivo, paridad, fixture de cierre automático, gráfico sin velas `null`).
- `FEATURES_VERIFIED` — paridad canónica LONG/SHORT/gap/continuación; 35 pruebas focalizadas; 1290 backend OK; 471 frontend; typecheck 0; navegador real y HTTP 200 con cierre automático.
- `DEFERRED_FEATURES` — inspección visual por modelo; F-PAPER-01 (motor paper completo); F-CHART-BINANCE-01 (contrato/gráfico Lightweight Charts); selector/riesgo/caja/funding recurrente; ejecución end-to-end de `/antislop`; móvil/Flutter.
- `BACKLOG_UPDATED` — yes: este bloque + `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`; F-TOOL-ANTISLOP-01 y F-CHART-BINANCE-01 reconciliados.
- `DOCUMENTATION_CONFLICTS` — F-PAPER-02 declaraba la validación de navegador pendiente; F-PAPER-03 la cubre para el cierre automático por stop, pero no la convierte en validación visual por modelo ni en aceptación de rentabilidad. Se preserva el historial.

## F-TOOL-ANTISLOP-01 — Anti Slop opcional para presentación y comentarios (2026-10-21)

**1. Title:** Integración local y opcional de Anti Slop en OpenCode como revisión de presentación y comentarios, sin puerta funcional ni dependencia del runtime.
**2. Approval status:** DECIDED por instrucción explícita del usuario en modo piloto acotado (solo este repositorio, solo núcleo + `antislop-code`, sin configuración global, sin otro modelo, sin subagentes, sin tocar lo funcional pendiente).
**3. Implementation status:** IMPLEMENTED — `.opencode/skills/antislop/{SKILL.md,VERSION,LICENSE,LOCAL_CONDITIONS.md}`, `.opencode/skills/antislop-code/{SKILL.md,LICENSE}`, `.opencode/commands/antislop.md`, `docs/ANTISLOP_PILOT.md` y una línea de uso opcional en `AGENTS.md`. Upstream fijado a `439a2ef5b9dd0ebe74e8113ff43f5928d0fe2a6a` (v3.2.21, MIT) con SHA-256 registrados.
**4. Evaluation status:** VERIFICADO PARCIALMENTE — OpenCode `v2.0.32` descubre ambas skills sin reiniciar y `/api/command` del proyecto registra `antislop`; revisión piloto manual sobre `dashboard.py` con 2 hallazgos y 5 comentarios técnicos preservados; dos ejecuciones headless cargaron el núcleo sin editar archivos y no entregaron informe (timeout de 300 s y error de proveedor `503`). NO evaluado: ejecución end-to-end completa del comando, ahorro de tokens, calidad de salida con modelos distintos. En el bloque F-PAPER-03 (2026-10-21) no se reintentó: sigue PENDIENTE.
**5. Limitaciones:** No es puerta de aceptación ni prueba de causalidad, seguridad, economía o rentabilidad. El núcleo upstream contiene instrucciones de instalación/modo que aquí solo se neutralizan por documento local y por el propio comando; el aviso automático de skills puede ofrecerlas en tareas no relacionadas. Sin CI ni hooks. Sin medición de tokens (solo bytes).
**6. Evidence:** `docs/ANTISLOP_PILOT.md` (origen, commit, licencia, hashes, uso y retirada); `docs/CURRENT_STATE.md` § piloto; `docs/DECISIONS.md` 2026-10-21 Anti Slop; `.opencode/skills/antislop/LOCAL_CONDITIONS.md`; `.opencode/commands/antislop.md`.
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS, FEATURE_BACKLOG (F-PAPER-02, F-CHART-BINANCE-01) y `docs/DESKTOP_FIRST_SCOPE_20261020.md` (alcance vigente escritorio).
- `NEW_DECISIONS_RECORDED` — DECISIONS §2026-10-21 Anti Slop opcional local: alcance mínimo, upstream intacto con licencia, condiciones locales separadas, comando bajo demanda, precedencia del proyecto, PASS sin valor funcional y verificación parcial declarada.
- `FEATURES_IMPLEMENTED` — F-TOOL-ANTISLOP-01 (piloto de revisión estilística opcional).
- `FEATURES_VERIFIED` — descubrimiento de skills y registro del comando en OpenCode `v2.0.32`; revisión piloto sobre archivo publicado sin editarlo; ninguna edición de archivos durante la ejecución headless.
- `DEFERRED_FEATURES` — ejecución end-to-end completa del comando; skills `antislop-ui`, `antislop-copywriting`, `antislop-human`, `antislop-layoutmobile`; integración en CI/hooks; medición de tokens; cualquier trabajo móvil/Flutter.
- `BACKLOG_UPDATED` — yes: este bloque + `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`, `docs/ANTISLOP_PILOT.md` y la línea opcional de `AGENTS.md`.
- `DOCUMENTATION_CONFLICTS` — el núcleo upstream declara "load always" y ofrece un asistente de instalación que escribe en `AGENTS.md` y lee preferencias globales; este piloto lo contradice a propósito y lo deja registrado en las condiciones locales. No se declara validación end-to-end que no se completó.

## F-PAPER-02 — Causa del fill, controles reales y stop único en Paper Lab (2026-10-21)

**1. Title:** Corrección de los tres bloqueos revisados de Paper Lab sobre `2a17088`: información futura en el fill, controles `canStep`/`onDecide` desconectados y salida por stop como economía paralela sin política de hueco.
**2. Approval status:** DECIDED dentro del alcance autorizado (desktop-only, fixtures, sin Binance/monitor/paper prospectivo/órdenes/pagos/optimización, sin cambios de estrategia, umbrales, costes ni motor económico).
**3. Implementation status:** IMPLEMENTED en `src/microstructure_probe/paper_lab_engine.py`, `frontend/src/lib/paper-lab-live.ts`, `frontend/src/components/paper-lab-live/PaperLabLive.tsx`, con pruebas en `tests/test_paper_lab_engine.py`, `tests/test_paper_lab_integration.py`, `frontend/src/test/paper-lab-live-api.test.ts`.
**4. Evaluation status:** VERIFICADO por pruebas focalizadas — motor 26/26, integración A–E 5/5 (CLI real con almacenamiento temporal aislado), API frontend 9/9, `tsc --noEmit` exit 0. Regresión obligatoria: `T=899999` con aperturas futuras 110 vs 50 produce estado público idéntico hasta T (excluyendo `session_id`/`created`/`updated`/`revision`/`input_hash`) y rellena después al precio revelado. NO evaluado: navegador real sobre los controles, suite completa re-ejecutada, rentabilidad.
**5. Limitaciones:** pasada de navegador de `/paper-lab-live` pendiente (no ejecutada, no se declara); dos errores `react-hooks` por `useMemo` condicional (~324/330) preexistentes y no corregidos; la suite completa no se re-ejecutó por el alcance acotado; el MVP sigue sin motor paper completo (position manager, ledger, funding recurrente, risk engine); funding ausente permanece `UNKNOWN`.
**6. Evidence:** `docs/CURRENT_STATE.md` §"Correcciones Paper Lab: fill causal, controles reales y stop compartido"; `docs/DECISIONS.md` §2026-10-21 causalidad/controles/stop; `tests/test_paper_lab_engine.py` (regresión de futuro en T, gap LONG/SHORT, salida manual de 4 velas); `tests/test_paper_lab_integration.py` (`--at-ms`, escenarios A–E); `frontend/src/test/paper-lab-live-api.test.ts`.
**7. Last update:** 2026-10-21.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE, DECISIONS (entrada F-CHART-BINANCE-01 que exige cerrar estos tres bloqueos antes del gráfico), FEATURE_BACKLOG (F-CHART-BINANCE-01, F-PAPER-01) y `docs/backtest_offline` como mecánica canónica.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"2026-10-21 — Causalidad del fill, controles reales y mecánica de stop única en Paper Lab" (append-only): prefijo causal, entrada pendiente sin fill, `can_step` del backend, `_finalize_exit` compartido y política gap.
- `FEATURES_IMPLEMENTED` — F-PAPER-02 (fill causal, entrada pendiente con reloj monótono, `can_step` publicado, `onDecide` conectado, stop/gap con mecánica económica única).
- `FEATURES_VERIFIED` — F-PAPER-02 en pruebas focalizadas (26 motor, 5 integración, 9 API frontend, `tsc` limpio) y regresión de futuro en T.
- `DEFERRED_FEATURES` — verificación en navegador real de los controles; motor paper completo (F-PAPER-01); contrato/gráfico Lightweight Charts (F-CHART-BINANCE-01); selector, riesgo/caja/funding recurrente y evaluación prospectiva.
- `BACKLOG_UPDATED` — yes: este bloque + `CURRENT_STATE`, `TASK_QUEUE` y `DECISIONS`.
- `DOCUMENTATION_CONFLICTS` — el cierre de `2a17088` declaraba el recorrido HTTP completo sin acreditar los tres bloqueos; aquí se registra la corrección real y se conserva que la validación por navegador **no** se ejecutó, para no convertir pruebas de componente en aceptación visual.

### Ampliación 2026-10-21 — verificación real en navegador (sobre `3acf511`)

**1. Title:** Corrección de cuatro defectos de control descubiertos al operar `/paper-lab-live` en Chromium real: orden de hooks, cierre prematuro por gate de evidencia, cursor sobre la serie fusionada y controles duplicados.
**2. Approval status:** DECIDED dentro del alcance autorizado (desktop-only, fixtures, sin Binance/monitor/órdenes; sin cambios de reglas, costes, umbrales ni motor económico; fixtures sin modificar).
**3. Implementation status:** IMPLEMENTED en `frontend/src/components/paper-lab-live/PaperLabLive.tsx`, `frontend/src/components/paper-lab-live/SessionControls.tsx`, `src/microstructure_probe/paper_lab_engine.py` y `tests/test_paper_lab_engine.py`.
**4. Evaluation status:** VERIFICADO — motor 27/27 (5 corridas consecutivas sin flake), integración A–E 5/5, frontend Paper Lab 67/67, `tsc --noEmit` limpio, `eslint` del panel 0 errores, y recorrido real en navegador (crear → abstención sin evidencia → señal pendiente → entrada → gestión → cierre manual) con `decision_at=1788920099999`, `available_at=1788920100000`, entrada @143.355, salida manual @145.08042078, `realized_net=10.4263712`, `funding=UNKNOWN`. NO evaluado: stop/gap por navegador (cubierto por pruebas), horizonte por navegador (fixture termina en fin de datos).
**5. Limitaciones:** BTC LONG termina en `open_at_end` (caso D) y ETH SHORT se abstiene en el primer cierre bajo la regla causal; sus salidas etiquetadas no son alcanzables desde la UI sin cambiar fixtures, y no se cambiaron. Motor paper completo (F-PAPER-01) sigue fuera de alcance. Suite completa no re-ejecutada.
**6. Evidence:** `docs/CURRENT_STATE.md` §"Correcciones Paper Lab tras verificación real en navegador"; `docs/DECISIONS.md` §2026-10-21 verificación en navegador; `tests/test_paper_lab_engine.py` (nuevo `test_evaluate_con_contexto_sin_vela_de_operacion_no_cierra`, cursor `==2` + `can_step` tras el fill, `_now_ms` congelado en la regresión); build servido `cqYJQQU1Vh-vQGU-6bioV`, PID 23688.
**7. Last update:** 2026-10-21.

## F-CHART-BINANCE-01 — Búsqueda, gráfico vivo e indicadores compartidos (2026-10-21)

- Approval status: objetivo y documentación ACORDADOS por el usuario; esta entrega no autoriza corrida Binance.
- Implementation status: PARCIAL (2026-10-21) — contrato `paper-chart/v1` y gráfico Lightweight Charts implementados sobre fixtures (ver entrada superior de este backlog); el contrato vivo, la búsqueda de contratos, el histórico paginado y los indicadores siguen NO implementados.
- Evaluation status: VERIFICADO en fixtures (aceptación A–H, pruebas focalizadas, build servido); NO EVALUATED para feed vivo ni rentabilidad.
- Contrato y aceptación: [Acuerdos de gráfico Binance V1](ACUERDOS_GRAFICO_BINANCE_V1.md).
- Dependencias: tres bloqueos revisados de Paper Lab 2a17088 *(cerrados 2026-10-21 con F-PAPER-02; el recorrido de navegador de los controles se ejecutó en `d48a224` y el cierre automático por stop se verificó con F-PAPER-03; la rebanada de contrato/gráfico sobre fixtures se implementó en la entrada superior de 2026-10-21; el contrato vivo/búsqueda/indicadores siguen pendientes)*; contrato causal, catálogo/cobertura, suscripciones por consumidor, retención y recuperación. Selector/riesgo/caja/funding tienen pendientes separados.
- Primera versión: escritorio, velas/volumen/zoom/histórico y eventos backend. Arrastre de stops, móvil y REA productivo fuera de esta versión.

### Cierre documental (siete campos)
- DECISIONS_REVIEWED: AGENTS, WORKFLOW, MASTER_PLAN, SUCCESS_GATES, DESKTOP_FIRST_SCOPE, CURRENT_STATE, TASK_QUEUE, DECISIONS y FEATURE_BACKLOG.
- NEW_DECISIONS_RECORDED: objetivo de búsqueda/gráfico vivo bajo demanda, fuente compartida, contrato y secuencia en DECISIONS y documento enlazado.
- FEATURES_IMPLEMENTED: documentación y enlaces; ninguna funcionalidad gráfica nueva.
- FEATURES_VERIFIED: identidad/rama/remoto, revisión de código referida, preservación y enlaces locales de estos documentos; sin suite ni QA visual ejecutados en esta tarea documental.
- DEFERRED_FEATURES: implementación del contrato, ventana Binance, selector/gestión paper completos, stops arrastrables, móvil/Flutter e IA.
- BACKLOG_UPDATED: este ID y prioridad enlazada en CURRENT_STATE/TASK_QUEUE.
- DOCUMENTATION_CONFLICTS: se explicita que el cierre reportado 2a17088 no acredita resolver los tres bloqueos revisados; registros anteriores preservados, sin DONE global ni gates.


## Cinco defectos de Backtest V2 corregidos — 2026-10-20 (base `37bde91`)

**1. Title:** Cierre de cinco defectos probados de la entrega Backtest →
Paper Lab: ciclo de vida del bloqueo, identidad del ejecutor, hashes
declarados, retención segura e hipótesis/placebo en la UI.
ID: F-BT-01 (habilitante acotado); engancha con F-PAPER-01.
**2. Approval status:** DECIDED dentro del alcance autorizado (sin Binance,
monitor, paper prospectivo, órdenes, credenciales, optimización, ni cambios
de estrategia, mapping, costes, umbrales o motor económico).
**3. Implementation status:** IMPLEMENTED. `frontend/src/lib/backtest-control.ts`
(bloqueo con guard por experimento, CAS en reconciliación, identidad por
evidencia del SO, resultados estrictos, retención conservadora, caché de
replay acotada), `frontend/src/lib/process-evidence.ts` (nuevo), `frontend/src/lib/backtest-results.ts`
(agregados nulos + `ledger_sum` + `openMarksOf`), `BacktestWorkspace.tsx`
(hipótesis/placebo separados), `scripts/run_dashboard_backtest.py`
(artefactos con `run_id`/`experiment_id`), `scripts/build_paper_lab_replay.py`
(`--run-id`, `backtest_run_id`, hash de `backtest_trades`).
**4. Evaluation status:** A) Ejecución offline reproducible: EJECUTADA en
navegador real (dos corridas consecutivas, 15765 trades, reconciliación OK).
B) Estrategia completa de extremos: **NO EVALUADA**. C) Enlace a Paper Lab:
DEMOSTRADO (artefacto enlazado al run correcto; identidad ajena → 422 con
motivo). D) Reproducción fall-antes/pasa-después de los cinco defectos:
EJECUTADA (7/7 fallan en `37bde91`, 7/7 pasan con el arreglo).
**5. Limitaciones:** la inspección visual se hizo sobre capturas del build
servido (DOM + lectura de imagen); no se auditó contraste WCAG. No se probó
una máquina Linux real (argumento por bytes en `process-evidence.ts`).
**6. Evidence:** `docs/evidence/BACKTEST_V2_DEFECT_REGRESSIONS_FAIL_BEFORE.txt`
(base `37bde91`, 7 fallos), `..._PASS_AFTER.txt` (7 pasan),
`docs/evidence/BACKTEST_V2_E2E_BROWSER_EVIDENCE.md` + 3 capturas de escritorio
`docs/evidence/BACKTEST_V2_FIX_DESKTOP_*.png` (alcance escritorio vigente,
`docs/DESKTOP_FIRST_SCOPE_20261020.md`: QA/capturas móviles aplazadas); contrato
`docs/BACKTEST_READ_CONTRACT_V1.md` (amend. v4.5/v4.6);
`frontend/src/test/backtest-defect-regressions.test.ts`,
`backtest-control.test.ts` (41), `backtest-results.test.ts` (11),
`backtest-workspace.test.tsx` (5), `backtest-integration.test.ts` (gate);
`tests/test_dashboard_backtest.py`.
Verificado: frontend 452 passed / 1 skipped (61 archivos + 1 omitido);
`tsc --noEmit` limpio; `eslint` 0 errores (3 warnings preexistentes);
`next build` OK (`BUILD_ID=7IfLc2UBHcbIAl2WG0t91`); `python run_tests.py -q`
1290 OK (2 skips); barrera de aislamiento
`tests=1290 ok=True prohibited={} blocked=0 ro=1 file_writes=0 hashes_equal=True
data_diff/logs_diff vacíos`.
**7. Last update:** 2026-10-20.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — `docs/BACKTEST_READ_CONTRACT_V1.md` (amend. B y
  portabilidad), `docs/DECISIONS.md` §identidad/ejecución, entrega funcional
  previa, auditoría independiente de los cinco defectos.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"Cinco defectos de Backtest V2:
  bloqueo de ciclo de vida, identidad del ejecutor, hashes declarados,
  retención e hipótesis/placebo" (append-only).
- `FEATURES_IMPLEMENTED` — F-BT-01 (control de ejecución con identidad
  verificable, resultados íntegros y presentación separada hipótesis/placebo).
- `FEATURES_VERIFIED` — F-BT-01 (reproducción fall-antes/pasa-después 7/7;
  452/1 frontend; e2e real de dos corridas + replay; 1290 OK backend; barrera
  de aislamiento limpia).
- `DEFERRED_FEATURES` — motor paper completo (F-PAPER-01), F-PORT-01,
  protocolo de auto-selección offline, evaluación completa de extremos,
  residual MINA/NMR, estudio W/LUMIA; próxima fase (solo registrada, no
  implementada): paper lab con datos vivos, selector causal → decisión
  versionada → simulación → gestión → cierre → exportación.
- `BACKLOG_UPDATED` — yes: esta sección + cierre.
- `DOCUMENTATION_CONFLICTS` — la UI sumaba hipótesis+placebo como beneficio y
  presentaba ceros como si fueran datos; el contrato no declaraba la regla de
  retención ni la exigencia de hashes completos/identidad de artefacto.
  Corregido por amend. v4.5/v4.6 y por esta sección, sin reescribir historia.

## Correcciones de la entrega Backtest → Paper Lab — 2026-10-20 (bloques A/B/C, base `4e61587`)

**1. Title:** Cierre de defectos de la entrega funcional Backtest → Paper Lab.
ID: F-BT-01 (habilitante acotado); engancha con F-PAPER-01.
**2. Approval status:** DECIDED dentro del alcance autorizado (sin Binance,
monitor, paper prospectivo, ordenes, credenciales, optimizacion, ni cambios
de estrategia/mapping/costes/umbrales/motor economico).
**3. Implementation status:** IMPLEMENTED (acotado), por bloques.
- **Bloque A (commit `84e6294`):** serialización portable del paquete
  (`-text` en `.gitattributes` + renormalize); manifiesto hashea bytes
  exactos; verificación estricta intacta.
- **Bloque B (commit `76763d7`):** identidad de ejecución única, exclusión
  entre procesos (`O_EXCL`), propiedad verificable, reconciliación sin
  auto-relanzar, UNKNOWN explícito, presupuesto efectivo, error async de
  spawn, resultados/caché vinculados y verificados por hash, ubicación
  canónica `<repo>/backtest-results/` (evidencia previa preservada), retención
  acotada segura, y `PaperLabSource` sin mostrar la operación previa en
  carga/fallo.
- **Bloque C:** pendiente (métricas, hipótesis vs placebo, escenarios de
  coste, conteos, revisión visual + capturas, entrega).**4. Evaluation status:** A) Ejecución offline reproducible desde checkout
limpio: EJECUTADA (`trades=15765`, `n_trades_1x=5255`, reconciliación OK).
B) Estrategia completa de extremos: **NO EVALUADA**. C) Enlace a Paper Lab:
DEMOSTRADO.
**5. Limitaciones:** locales por bloque (ver DECISIONS/CURRENT_STATE).
Bloque A: plataforma verificada = Windows + `core.autocrlf=false` (equiv.
Linux por bytes); no se probó una máquina Linux real.
**6. Evidence:** `.gitattributes`; `tests/test_dashboard_backtest.py::PackagePortabilityTest`;
`docs/BACKTEST_READ_CONTRACT_V1.md` (amend. portabilidad); `docs/DECISIONS.md`
§Bloque A; `docs/CURRENT_STATE.md` §Bloque A.
**7. Last update:** 2026-10-20.

### Cierre (siete campos, obligatorios) — Bloque A

- `DECISIONS_REVIEWED` — contrato de lectura de backtest; entrega funcional
  previa (`4e61587`); auditoría independiente del paquete.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"Serialización portable del paquete
  EVAL-CENSUS-V2 (Bloque A)" (append-only).
- `FEATURES_IMPLEMENTED` — F-BT-01 (paquete byte-portable).
- `FEATURES_VERIFIED` — F-BT-01 (33/33 blobs == manifiesto; verify PASS desde
  checkout limpio; alteración real rechazada; `PackagePortabilityTest`).
- `DEFERRED_FEATURES` — mismas que la entrega base (motor paper completo,
  F-PORT-01, auto-selección offline, evaluación completa de extremos,
  residual MINA/NMR, W/LUMIA).
- `BACKLOG_UPDATED` — yes: nueva sección de correcciones.
- `DOCUMENTATION_CONFLICTS` — la entrega base describía el paquete como
  "33 archivos, hashes OK" sin declarar el defecto de serialización en
  checkout limpio; corregido por sección nueva, no por reescritura de historia.

### Cierre (siete campos, obligatorios) — Bloque B

- `DECISIONS_REVIEWED` — contrato de lectura de backtest (amend. portabilidad
  y ejecución); entrega funcional previa; auditoría independiente.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"Identidad de ejecución,
  resultados/caché vinculados y ubicación canónica (Bloque B)".
- `FEATURES_IMPLEMENTED` — F-BT-01 (ejecución controlada: identidad única,
  exclusión entre procesos, resultados/caché vinculados, ubicación canónica).
- `FEATURES_VERIFIED` — F-BT-01 (`pytest tests/test_dashboard_backtest.py`
  16 OK; frontend vitest 418/418; 25 tests de control + 4 de cambio de
  operación; ejecución real con identidad verificada y hashes coincidentes).
- `DEFERRED_FEATURES` — motor paper completo, F-PORT-01, auto-selección
  offline, evaluación completa de extremos, residual MINA/NMR, W/LUMIA.
- `BACKLOG_UPDATED` — yes: Bloques A/B/C y cierre B.
- `DOCUMENTATION_CONFLICTS` — contrato y código divergían en la ubicación de
  resultados (`frontend/.backtest-runs/` vs `<repo>/backtest-results/`);
  reconciliado a la ubicación canónica del contrato, sin borrar evidencia.

## Backtest offline funcional en V2 + enlace a Paper Lab — 2026-10-20 (sin push aun)

**1. Title:** Primera evaluacion offline versionada ejecutable desde V2
(`eval-census-v2-trio`) + enlace operacion -> Paper Lab. ID: F-BT-01
(habilitante acotado), engancha con F-PAPER-01 (replay, no motor paper).
**2. Approval status:** DECIDED dentro del alcance autorizado (sin ejecucion
real, sin Binance, sin optimizacion automatica, sin cambios de umbrales ni
del motor economico). Protocolo de auto-seleccion offline: NO iniciado
(fuera de alcance).
**3. Implementation status:** IMPLEMENTED (acotado). Ejecutor
`scripts/run_dashboard_backtest.py`; BFF `frontend/src/lib/backtest-control.ts`
+ rutas `api/v1/backtest/{run,status,results,replay}`; UI
`frontend/src/components/backtest/BacktestWorkspace.tsx`; contrato de lectura
`frontend/src/lib/backtest-results.ts`; enlace en
`frontend/src/components/paper-lab/PaperLabSource.tsx`; generador extendido
`scripts/build_paper_lab_replay.py --trades-json`; docs
`docs/EXTREMES_EVALUABILITY_MATRIX.md`. F-BT-01 sigue siendo **no** un
backtester completo de la estrategia de extremos.
**4. Evaluation status:** A) Evaluacion offline sobre censo historico:
EJECUTADA y revisable en V2 (15765 trades, reconciliacion por celda OK). B)
Estrategia completa de extremos sobre universo/liquidez: **NO EVALUADA**
(matriz deja el hueco explicito; sin ranking/liquidez/universe causal).
C) Enlace a Paper Lab: DEMOSTRADO por test (ganadora/perdedora/abierta) y
por enlace real; no es seleccion automatica.
**5. Limitaciones:** in-sample/no-pristine (held-out por tiempo de evento,
no pristino); costes por escenarios 1x/2x/3x (no apalancamiento, spread/
slippage UNKNOWN); funding UNKNOWN fuera del calendario; no cartera conjunta
(no se suman simbolos como portfolio); `summary.json` con metadatos de reloj
no deterministas (aceptado); no valida edge ni rentabilidad.
**6. Evidence:** `docs/BACKTEST_READ_CONTRACT_V1.md` (UNWIRED->WIRED),
`docs/PAPER_LAB_PLAN_ETAPA5.md` (enlace), `docs/EXTREMES_EVALUABILITY_MATRIX.md`,
`scripts/run_dashboard_backtest.py`, `frontend/.backtest-runs/` (ignorado),
tests `tests/test_dashboard_backtest.py` + `frontend/src/test/backtest-*.test.ts`.
Verificado: backend 1291 OK + frontend 400/400 + `tsc --noEmit` limpio +
`eslint` 0 errores + `next build` OK (`BUILD_ID=eBIlrCEoIFTWay0VAx6VA`);
checkout limpio reproduce trades=15765/reconciliacion=True con solo lo
publicado.
**7. Last update:** 2026-10-20.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — objetivo movers extremos; contratos backtest/
  runtime/BFF; cierre Paper Lab 2026-10-20; correcciones acotadas de
  causalidad/estados; DECISIONS §backtest de esta fecha.
- `NEW_DECISIONS_RECORDED` — DECISIONS §"Backtest offline funcional en V2 +
  enlace operacion -> Paper Lab" (append-only).
- `FEATURES_IMPLEMENTED` — F-BT-01 (habilitante: ejecucion offline +
  resultados + enlace a replay).
- `FEATURES_VERIFIED` — F-BT-01 (tests + determinismo + checkout limpio);
  enlace operacion->replay (winner/loser/open).
- `DEFERRED_FEATURES` — F-PAPER-01 (motor paper completo), F-PORT-01,
  protocolo de auto-seleccion offline, evaluacion completa de extremos,
  residual MINA/NMR `build_report`, estudio W/LUMIA (separado).
- `BACKLOG_UPDATED` — yes: nueva seccion + nota de supersesion de artefacto
  en el item Paper Lab.
- `DOCUMENTATION_CONFLICTS` — la entrada Paper Lab citaba sha256
  `0db0c4d0...` y `/backtest` como stub (`FutureWorkspace`); ambos quedan
  superados (artefacto `72af8007...`; `/backtest` funcional), corregidos por
  nota de supersesion, no por reescritura de historia.

## Bot + Dashboard V2 para corridas de observacion — 2026-10-13 (review/bot-dashboard-v2-observacion, sin push aun)
V2 (checkpoint 27b7af5, rama dash-v2-03-token-detail) como interfaz principal
para observacion/evaluacion; dashboard Python pasa a LEGADO (funcional, no
primario; sin semanticas contradictorias). Agentes IA + Kronos: ver
F-KRONOS-01 (PROPOSED, diferido, fuera de alcance; sin dependencias ni
integraciones; no es requisito de arranque). Pendientes tecnicos previos se
mantienen. Gates sin avance.

## Entrega nueve archivos 6fd6091-base — 2026-10-13 (push review/entrega-nueve-archivos-6fd6091 completado)
Cierres tecnicos (habilitante, sin IDs nuevos): cap holding, calendario
monocontrato, mark stale, fees exit-value (1 assert legacy corregido),
symbol en manifiesto, handoff 27b7af5 real (gates 2/9 vs v10/v3).
R1-R7 + dirigidas + comparador verdes; barrera con 9 preexistentes
contrastados. Distincion: implementacion DONE; validacion financiera NOT
IMPLEMENTED. Gates sin avance.

## Bot + V2 observacion — 2026-10-13 (review/bot-dashboard-v2-observacion, sin push aun)
V2 principal (27b7af5 a continuar) + legado Python (sin contradicciones) +
matriz/ciclo/aceptacion/preflight + F-KRONOS-01 diferido. Sin IDs nuevos de
producto salvo F-KRONOS-01 (PROPOSED). Gates sin avance.

## Correccion tecnica de14ac1-base — 2026-10-13 (review/correccion-tecnica-de14ac1; push 6fd6091 completado)
Motor/contratos (habilitante, sin IDs nuevos): split realizado/abierto
(n_realized/n_open/open_positions; curva realizada; costes hipoteticos),
funding qty x mark + identidad/dedup/gaps (contrato v4.1), runner por
familia H1/H2/H3 + identidad por indice. Comparador M6a/M6b/M7/M8/SELF.
Handoff 27b7af5 (v10/v3 explicito; frontend/ intacto). Incidente v2->v3
reconciliado. Distincion: reproduccion DONE; integracion dashboard
parcial-no-verificada; validacion financiera NOT IMPLEMENTED. Pendientes:
despliegue/operacion de lo corregido, OOS/calibracion/rentabilidad.
Gates sin avance.

## Cierre W/LUMIA documental — 2026-10-13 (push phase1 bc327f1 completado)
Reproduccion de caso (sin ID de producto; habilitante/documental):
addendum v2 en CASE_STUDY + 5 evidencias (hashes, comparacion,
logs, env, script). Distincion: reproduccion DONE; integracion dashboard
(F-STATE-*/F-OPP-UI-01/campos+funding-calendario) NOT IMPLEMENTED;
validacion financiera (F-BT-01/F-PAPER-01, OOS/calibracion/rentabilidad)
NOT IMPLEMENTED. V2 `27b7af59cb1e313169f49655161d66e043b5412d` =
frontend estatico dash-v2-03-token-detail, no SSR backend. Pendientes
correctivos NO resueltos: funding, posiciones abiertas, runner, incidente
de aislamiento, schemas V2. Gates sin avance.

## Correccion V2 + comparador — 2026-10-13 (review/w-lumia-correccion-bc327f1; push de14ac1 completado)
Addendum (historia preservada): V2 `27b7af59cb1e313169f49655161d66e043b5412d`
= rama `dash-v2-03-token-detail` CON rutas BFF (`api/v1/...`) + adapters
SQLite (`canonical-market.ts`, `historicalRead`); integracion parcial,
feed live/operacion NO verificados (UNVERIFIED + warnings en la propia
ruta). Comparador fortalecido con 5 regresiones (temp, originales
intactos). Distincion vigente: reproduccion DONE; integracion dashboard
parcial-no-verificada; validacion financiera NOT IMPLEMENTED. Pendientes:
funding, realizados/marcas, runner, aislamiento, schemas V2. Gates sin avance.

## Mejoras funding/trazabilidad/dashboard/evaluacion — 2026-10-13 (sin push aun)
Ingenieria + docs + evaluacion offline. Sin ordenes/paper/servicios.
Sin rentabilidad ni SUCCESS_GATES. Kronos diferido (fuera de alcance).

## Cierre correctivo R1-R7 — 2026-10-13 (sin push aun)
Motor v3 + migraciones v10 en una init + resolver R7 + 22 regresiones.
Habilitante/correctivo; sin IDs de producto; gates sin avance.

## Cierre correctivo P1-P4 — 2026-10-12 (sin push)
Motor offline v2 + regresiones; inyeccion B/C; linkage run_id v10;
reconciliacion documental. Sin IDs nuevos verificados como feature de
producto; trabajo habilitante + correctivo. Gates sin avance.

## ETAPA-5 Paper Lab plan — 2026-10-12
Design only (no backlog ID): six build items + entry gates. No
implementation, no paper session, no authorization.

## ETAPA-4 offline backtest prep — 2026-10-12
Prep implementation (no backlog ID): isolated engine + 16 tests + unwired
read contract. Mechanics smoke only; strategy validation NOT claimed.

## ETAPA-3 research/backtest contract — 2026-10-12
Contract only (no backlog ID): H1/H2/H3 + cost model + replay limits.
Engine deferred to Etapa 4 prep. No gate advancement.

## ETAPA-2 dataset readiness — 2026-10-12
Enabling research forensics (no backlog ID): pure-read provenance script
(scripts/audit_dataset_provenance.py) + DATASET_READINESS report with
per-population blockers. No data mutation. No gate advancement.

## ETAPA-1 test isolation — 2026-10-12
Enabling test-hygiene (no backlog ID): full-suite write barrier
(scripts/audit_test_isolation.py, PREFIX/POSTFIX evidence), temp-intercepted
repro (scripts/repro_default_store_writes.py), 6 test-file fixture fixes +
tests/test_persistence_isolation.py (5 regressions). 916/916 canonical OK,
zero prohibited writes, stable microprobe hash; Routes B/C residual with
production-side blocker. Report: docs/TEST_ISOLATION_ETAPA1_REPORT.md.
No production change; no gate advancement.
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


# FEATURE BACKLOG — canonical decision traceability & deferred features

## Cierre EVAL-CENSUS-V2 + selector + QA visual — 2026-10-17 (sin corridas)

**1. Title:** Evaluación offline sobre censo causal exhaustivo
(EVAL-CENSUS-V2) + selector extremo (fixtures) + QA visual V2.
**2. Approval status:** DECIDED (criterio pre-fijado del protocolo
prospectivo V1; sin reajustes). H2 fade: HIPTESIS NUEVA (NO aprobada).
**3. Implementation status:** IMPLEMENTED (censo reconstruct_causal_census.py,
selector extreme_selector.py, artefacto census-eval-v2.json force-added,
scripts build_census_eval_inputs.py, tests test_causal_census.py +
test_eval_horizon_grid.py + test_extreme_selector.py + census-eval.test.ts).
**4. Evaluation status:** A) Reglas sobre censo historico: EVALUADO
(0 celdas elegibles, H1/H3 RECHAZADAS, H2 fade RECHAZADO). Desglose 1x:
Hipótesis 2991 trades (5 abiertas → 2986 realizadas, 4161 skipped_overlap);
Placebo 2264 trades (2 abiertas → 2262 realizadas, 4888 skipped_overlap);
Total 5255 trades (7 abiertas → 5248 realizadas). `realizadas = trades − abiertas`.
B) Selector: MECANISMO probado con fixtures, NO evaluado sobre censo. C) Estrategia
completa extremos sobre universo/liquidez: NO EVALUADA (faltan ranking/liquidez/market_cap).
**5. Limitaciones:** in-sample/non-pristine, costes supuestos COST-ASSUME-v1,
mapping candidato MAP-CANDIDATE-v2, sin prueba live, **MFE/MAE = excursión por
posición, NO ganancia capturada por la salida** (rango global 1x MFE 0.0–1.04% /
MAE 0.0–0.50%; direccional n≥30 MFE 0.19–0.64% / MAE 0.16–0.42%), placebo una
realización no distribución, cross-celda no modelada, 6 detecciones tail-edge
sin entry (honesto), residual MINA/NMR sin build_report (INCOMPLETE separado).
**6. Evidence:** docs/OFFLINE_EVAL_CENSUS_V2.md (seccion 7 matriz A/B/C),
frontend/src/data/census-eval-v2.json (sha256 2b74a841...d37060),
docs/evidence/VISUAL_QA_CENSUS_EVAL_V2.png, suites backend 1202 OK +
frontend 314/314 + typecheck 0 + build OK.
**7. Last update:** 2026-10-17.

## Paper Lab — replay histórico de ingeniería (reconciliación 2026-10-20)

**1. Title:** Primer replay histórico de Paper Lab sobre EVAL-CENSUS-V2 (PAPER-LAB-REPLAY-V1).
**2. Approval status:** DECIDED (diseño Etapa 5, sin autorización de motor paper ni sesión live).
**3. Implementation status:** PARCIAL (solo replay de ingeniería; motor paper completo NO implementado).
**4. Evaluation status:** Artefacto determinista verificado (`scripts/build_paper_lab_replay.py --check` → PASS, sha256 `96a5fa46499000a8aa223093a145bda49744157468ae80c56b4b126234e80882`; **actualizado 2026-10-20 a `0db0c4d0cf1767736cbeafbae62e12a10adce512e423520bb5046c58dfbfff99`** tras las correcciones acotadas de causalidad/gráfico/estados). Operación BTCUSDT 15m H1 reproducida antes de ver P&L; salida honesta en pérdida (`gross_pnl=-0.0242`, `net_pnl=-1.6242`, salida por `horizon`). La detección se revela en su instante de disponibilidad (`available_at`), mostrando `formation_time` como metadata. No es selección automática, ni paper en vivo, ni simulación prospectiva. Suite frontend 368/368, `tsc --noEmit` limpio, `eslint` 0 errores.
**5. Limitaciones:** no lee DB canónica, no consulta Binance, no ejecuta órdenes, no gestiona posiciones, no hay ledger de caja/funding recurrente/risk engine, no valida selector real sobre universo. BTC/ETH/SOL = controles de mecánica.
**6. Evidence:** `docs/PAPER_LAB_PLAN_ETAPA5.md` (sección Estado actual), `frontend/src/artifacts/paper-lab-replay-v1.json`, `scripts/build_paper_lab_replay.py`, `frontend/src/lib/paper-lab-replay.ts`, `frontend/src/test/paper-lab-replay.test.ts`, `frontend/src/test/paper-lab-components.test.tsx` (publicados en la entrega de 2026-10-20). Servido en `127.0.0.1:3020/paper-lab`; servida la operación LONG (no la SHORT obsoleta). Capturas desktop+mobile de tres estados generadas; inspección visual pendiente del revisor humano.
**7. Last update:** 2026-10-20.
**8. Estado de entrega (cerrado 2026-10-20):** artefacto determinista, parser/player/componentes y ruta V2, tests y evidencias, selección independiente del P&L, reconciliación P&L/costes al cierre, capturas antes de entrada/abierta/cerrada, SHA/build servido y URL local verificada. Pendiente **fuera de este ítem:** motor paper completo (Etapa 5), no autorizado.

### Corrección acotada: camino real dashboard → BFF → Python (2026-10-21, sobre ec0416a) — cierre funcional

**1. Title:** Corrección de defectos en el recorrido real cliente/BFF/backend de Paper Lab + flujo integrado extremo a extremo verificado por HTTP real.
**2. Approval status:** DECIDED (dentro del alcance autorizado, sin Binance ni motor paper).
**3. Implementation status:** IMPLEMENTED. Commit `1892c23` publicado en `review/o1-funcional-v2-observacion` (push `7a3db9c → 1892c23`).
**4. Evaluation status:**
   - Motor Python: 23/23 (`test_paper_lab_engine.py`) — todas pasan.
   - Suite completa: `python run_tests.py -q` → 1290 OK / 2 skipped / exit 0.
   - Frontend: `tsc --noEmit` limpio; `npm test` → 470 passed / 1 skipped; `next build` OK (`BUILD_ID=jhFu3mEN9yZAntBo_sWsC`).
   - Servidor: PID 31072, `http://127.0.0.1:3020`; `/api/v1/runtime` y `/paper-lab-live` sirven HTTP 200.
   - **Flujo integrado HTTP real (crear → evaluar sin señal → avanzar → confirmar señal → entrar → gestionar → cerrar → recuperar/exportar):** todos los pasos 200. Tiempos: decision_at=899999, entry_ms=900000 (>= decision_at), exit_px=95.95, exit_reason=stop, exit_executed=true, realized_net=-51.56, total ~952ms.
   - **Conflictos HTTP reales:** dos steps concurrentes misma revisión → uno 200, otro 409 REVISION_CONFLICT; sin entrada duplicada. Misma request_id con contenido distinto → 409 REQUEST_CONTENT_CONFLICT. Revisión obsoleta → 409. Sesión inexistente → 404.
   - **Caso D (fin de datos, posición abierta):** exit_executed=false, realized_net=null, open_at_end=true, exit_fees_executed=0, posición sigue abierta, GET idéntico.
   - Reloj causal: `create_session` fija clock_ms al close_time de la última vela de contexto; `evaluate_session` rechaza sin `at_ms`/`clock_ms`; nunca usa hora actual.
   - Sin información futura: `session_to_public_dict` filtra a solo lo conocido en T en todas las respuestas públicas (incluido GET).
   - Request_id e idempotencia en BFF; conflictos HTTP 409; BFF interpreta respuesta del CLI incluso con salida != 0 (parsea stdout Y stderr).
   - Fin de datos no es cierre ejecutado: mark_px no sustituye exit_px; realized_net null si open_at_end.
   - `known_close_cutoff` en `run_backtest` (default `horizon_end`, compatible hacia atrás).
**5. Limitaciones:** sin Binance, monitor, paper prospectivo, órdenes, pagos, móvil ni optimización. Recorrido vía navegador interactivo no grabado como evidencia visual (verificado por HTTP/DOM y texto). Motor paper completo (Etapa 5) sigue NO implementado.
**6. Evidence:** docs/DECISIONS.md (entrada 2026-10-21), docs/CURRENT_STATE.md (sección MVP Paper Lab), tests/test_paper_lab_engine.py, tests/test_paper_lab_integration.py, frontend/src/test/paper-lab-live-api.test.ts.
**7. Last update:** 2026-10-21.

### Correcciones acotadas de Paper Lab (2026-10-20, sobre `d9359e3`)

- **Causalidad de revelación:** eliminado el paso `signal` anticipado en `event_time_ms`; la detección se revela en `available_at` con `formation_time_ms` como metadata. `initial_cursor_ms` (anterior a la detección) define la vista inicial con el contexto ya conocido. Invariantes de generador/parser + tests t−1/t/t+1, formación, fronteras de entrada/salida y «datos posteriores no alteran la vista anterior al cursor».
- **Estados:** estado del REPRODUCTOR (`sin_iniciar`/`reproduciendo`/`pausado`/`terminado`) separado del de POSICIÓN; reiniciar restablece ambos; avanzar manual con posición abierta muestra PAUSADO (no «REPOSO»).
- **Gráfico/etiquetas:** SVG responsive (sin recorte a 360/390px), anti-solape de etiquetas (línea conserva su precio real) + leyenda, frontera contexto/replay en la primera vela del replay, eje con margen. Verificación geométrica de DOM (no visual): sin overflow de página, 0 elementos fuera de viewport, 0 textos SVG fuera de viewBox.
- **Artefacto/build:** sha256 `0db0c4d0cf1767736cbeafbae62e12a10adce512e423520bb5046c58dfbfff99`; 7 pasos (3 velas + 4 eventos); `BUILD_ID=45NLJvJuWqcMjj2IFxW-E` servida en `127.0.0.1:3020/paper-lab`; mecánica económica sin cambios.
- **Supersesión 2026-10-20 (nota, sin reescribir):** el artefacto fijo y el build anteriores quedan **superados** por las correcciones de enlace Backtest→Paper Lab: `replay_id` incorpora group+scale (enlaces únicos); sha256 `72af8007d5956244ec7b902c0b12f960cdc6993b6912b4749fff9fcfcb62f172` (`--check` PASS; ventana/pasos idénticos). `/backtest` deja de ser stub (`FutureWorkspace`) y es funcional. Detalle en la sección de esta fecha más arriba.

## Estudio retrospectivo de extremos — paquete W/LUMIA (auditoría 2026-10-21)

**1. Title:** Auditoría del paquete existente `binance_case_study/` como estudio retrospectivo de extremos (WUSDT/LUMIAUSDT, controles BTCUSDT/GTCUSDT).
**2. Approval status:** DECIDED (auditoría documental y de compatibilidad con el motor; no segunda implementación, no detección automática, no calibración).
**3. Implementation status:** NOT IMPLEMENTED como funcionalidad de producto; EXISTENTE como paquete de datos (untracked, `binance_case_study/`, 12 archivos, hashes 12/12 OK vs `SHA256SUMS.txt`).
**4. Evaluation status:** DESCRIPTIVE / IN-SAMPLE. 1.499 velas 5m cerradas + 1.499 velas 1m cerradas por símbolo, corte `2026-10-12T10:57:19.690Z` (~5,2 días), sin duplicados ni huecos. `fundingIntervalHours=4` real (W/LUMIA) frente al fallback `FUNDING_INTERVAL_MS = 8h` (**corregido 2026-10-20:** el motor ya acepta `FundingCalendar` por contrato — `src/microstructure_probe/backtest_offline.py` — y `8h` es solo el fallback cuando no se inyecta calendario; la fidelidad se logra inyectando el calendario real, no cambiando la constante global). Casos documentados como `NOT_SIGNAL` (ex-post high/low no es señal). Sesgo de selección retrospectiva declarado. Sin OOS, sin calibración, sin rentabilidad.
**5. Limitaciones:** no es detector automático; no se seleccionan ejemplos por beneficio; no se calibran reglas sobre estos casos; no hay spreads/profundidad/fills medidos; no hay serie OOS; `Casos_Binance_W_LUMIA.png` no inspeccionada visualmente (`NOT_ASSESSED`).
**6. Evidence:** `binance_case_study/analysis_summary.json` (casos W/LUMIA con puntos forward 15m/30m/60m), `binance_case_study/supplemental_analysis.json` (funding 4h, calidad de series), `binance_case_study/Investigacion_Binance_W_LUMIA.md` (informe descriptivo), `docs/evidence/CASE_STUDY_WUSDT_LUMIA_*` (hashes, comparación, regresiones, entorno).
**7. Qué falta para mostrar esos casos:** calendario de funding real por símbolo y tasa liquidada; spread/profundidad/coste estimado; fills reales; serie OOS; partición cronológica; vinculación `run_id`/`event_id` con `as_of`; snapshot por evento con hash del dataset.
**8. Last update:** 2026-10-21.
**9. Dependencia:** motor de backtest (backtest-offline/v4) para contabilizar funding real cruzado; no bloquea el replay de ingeniería del trío.

## DASH-V2-71B reviewer correction — 2026-10-11
89232f7 independently reviewed: discovery/canonical 910, exit0. Strengthened
existing purity test (missing historical-byte assertion, no new logs, env
restoration); historical-tempfile mutation passed old proof and fails new.
No application source change. Final bytes do not certify readonly mode;
four HistoryStore init calls observed. See DASH_V2_71B_REVIEW_CORRECTIONS.md.
Full cutover/Start/gates unchanged; universe detail=test provenance pending.


## DASH-V2-69 — 2026-10-11 — extraction proof review
Exact c59c5ec extraction reviewed independently. Five helper bodies match; original Python 3.14 find_module blocker was ineffective despite four green tests. Existing H2 strengthened with find_spec plus deliberate negative control; four focused tests pass. No application source edits. V1 contract retirement section now closes extraction prerequisite while retaining parity/review/authorization requirements; no retirement performed. See DASH_V2_69_EXTRACTION_PROOF_REVIEW.md; canonical verification recorded there. Full cutover and operational readiness remain PARTIAL; Start/gates/main/DB/registry preserved.


## Sesión de ingeniería — transporte local (2026-10-26, HEAD `365f7eb`)

**1. Title:** Sesión de ingeniería observable en el dashboard existente (`/market-lab`): iniciar/detener "Sesión de ingeniería — transporte local" con seis paneles separados (estado, fuente LOCAL SIMULADA, recepción/frescura, evaluador, posición paper, último error/motivo de abstención) y vista de operación completa (datos → gráfico → indicadores/contexto BTC/flujo → candidato → decisión → posición paper → gestión → cierre → exportación).

**2. Approval status:** DECIDED dentro del alcance autorizado (desktop, presupuesto cero, sin conexión pública Binance, sin monitor, sin paper prospectivo, sin órdenes, sin pagos, sin móvil/Flutter, sin estrategia nueva; fuente LOCAL SIMULADA = caché local `client=None`, 0 upstream; ventana con mercado real y conexión Binance pública diferida, requiere autorización explícita).

**3. Implementation status:** IMPLEMENTED. Control de sesión en `frontend/src/components/session-lab/EngineeringSession.tsx` + `SessionStatusPanels.tsx` + `EngineeringSession.module.css` + `frontend/src/lib/session-lab.ts`; cableado en `frontend/src/app/market-lab/page.tsx`; reutiliza controlador canónico (`scripts/paper_lab_session.py` + `src/microstructure_probe/paper_lab_engine.py` con mecánica de `backtest_offline.run_backtest`) y servicios existentes (BFF `api/v1/paper-lab/sessions*`, `api/v1/market-series`). Regla de ingeniería `ENGINEERING-MINA-1M-v1` (explícita, versionada, separada de estrategia aprobada); candidato UN token (MINAUSDT 1m) + BTC como contexto (BTCUSDT 1m), ambos de caché local.

**4. Evaluation status:** `npx tsc --noEmit` 0; `npx eslint` 0 en archivos nuevos; `npx vitest run src/test/paper-lab-live-api.test.ts` 9/9; `python run_tests.py -q` 1290 OK / 2 skipped; `next build` OK. E2E de navegador real (Chromium headless) sobre `http://127.0.0.1:3020/market-lab`: A) iniciar → recibir datos (caché local, 0 upstream) → evaluar (ENTRADA_SIMULADA) → entrada automática (fill por run_backtest) → gestión (pasos de marca) → cierre por regla (horizonte) → exportación JSON/CSV; B) evidencia insuficiente → SIN_ENTRADA/DESCARTADO, sin posición; C) fin de datos → sin nuevas entradas, estado visible, posición no cerrada inventada (`open_at_end`); D) recarga → recuperación del mismo estado (session_id/config_hash idénticos) sin duplicar entrada ni cierre; E) detener → sesión detenida, recursos propios liberados, sin afectar procesos ajenos. Nota: los clics de "Paso a paso" en el navegador son intermitentes (timing React/Playwright); el camino backend → BFF → Python está verificado por HTTP (crear → evaluar → step ×31 → cerrada por horizonte en `debug_flow3.py`).

**5. Limitaciones:** no conecta a Binance público (ventana aparte, autorización explícita); un solo token candidato (caso de ingeniería, no rentabilidad); no es escáner de universo ni estrategia aprobada; no inventa spread/profundidad/funding/fills de mercado real (funding UNKNOWN, costes ejecutados separados); no es paper prospectivo ni motor completo (Etapa 5 fuera de alcance); móvil/Flutter/IA diferidos; indicadores provisionales fuera de alcance.

**6. Evidence:** `frontend/src/components/session-lab/EngineeringSession.tsx`; `frontend/src/components/session-lab/SessionStatusPanels.tsx`; `frontend/src/components/session-lab/EngineeringSession.module.css`; `frontend/src/lib/session-lab.ts`; `frontend/src/app/market-lab/page.tsx`; `src/microstructure_probe/paper_lab_engine.py` (sesión, regla causal, paso, stop, salida, persistencia); `scripts/paper_lab_session.py`; BFF `frontend/src/app/api/v1/paper-lab/sessions/*`; `api/v1/market-series` (caché local, 0 upstream). Evidencia de ejecución: `docs/evidence/sesion-ingenieria-transporte-local-*.json` (E2E A–E); capturas del navegador (`docs/evidence/sesion-ingenieria-*.png`); BUILD_ID servido en `127.0.0.1:3020`.

**7. Last update:** 2026-10-26.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — `docs/DECISIONS.md` (sesión de ingeniería — transporte local, 2026-10-26), `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md` (alcance escritorio vigente), `docs/ACUERDOS_GRAFICO_BINANCE_V1.md` (origen/autoridad del backend, sin navegador como fuente de decisión), `docs/PAPER_CHART_CONTRACT_V1.md` (gráfico sobre velas conocidas en T).
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-26: sesión de ingeniería como control observable en el dashboard existente sin gestor paralelo; fuente LOCAL SIMULADA = caché local (0 upstream); regla `ENGINEERING-MINA-1M-v1` explícita y versionada; regla de parada (detener congela, no cierra ni inventa salida); persistencia autoritativa en `paper-lab-sessions/` con el puntero de sesión (no estado económico) en el navegador.
- `FEATURES_IMPLEMENTED` — control iniciar/detener sesión; seis paneles (estado, fuente, recepción/frescura, evaluador, posición paper, último error/abstención); vista de operación (velas incrementales + reloj, candidato/motivo, entrada pendiente vs fill, entrada/stop/salida en gráfico, posición abierta/cerrada, P&L realizado/no realizado, costes, funding UNKNOWN, historial eventos, exportación JSON/CSV); compartición de session_id/símbolo/tiempos/config_hash entre paneles.
- `FEATURES_VERIFIED` — backend: `create`→`evaluate`→`step`→`step`…→`cerrada` por horizonte (paso 31, `realized_net` calculado, `funding=None`) vía HTTP; frontend: `tsc` 0, `eslint` 0, vitest paper-lab-live-api 9/9; E2E de navegador: iniciar → evaluar (ENTRADA_SIMULADA) → Entrar → abierta → pasos de gestión → cerrada por regla → exportación JSON; recarga recupera sesión idéntica sin duplicar; detener congela sesión sin cerrar; B (abstención SIN_ENTRADA/DESCARTADO, sin posición) verificada vía HTTP.
- `DEFERRED_FEATURES` — conexión a Binance público (ventana aparte, autorización explícita); selector automático de varios símbolos; monitor en vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; IA; indicadores provisionales; stops/objetivos arrastrables; motor paper completo (Etapa 5).
- `BACKLOG_UPDATED` — yes: esta sección + `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`.
- `DOCUMENTATION_CONFLICTS` — ninguna contradictoria; se aclara que "fuente LOCAL SIMULADA" ≠ Binance LIVE y que el backend (no el navegador) es la autoridad de decisión y estado económico.

## F-PAPER-04 — Sesión de ingeniería observable en el dashboard (2026-10-26)

Véase la entrada anterior; este ítem es un índice ligero del mismo trabajo para el backlog de producto (control de sesión + vista de operación + aceptación A–E).


**Rules:**

- Statuses: `DECIDED` (approved, binding) / `PROPOSED` (discussed, not
  approved) for approval; `NOT IMPLEMENTED` / `PARTIAL` / `IMPLEMENTED` /
  `VERIFIED` for implementation. A discussed feature is never auto-marked
  IMPLEMENTED or VERIFIED.
- VERIFIED requires linked evidence (tests, logs, screenshots, commits).
- New material decisions needing user approval are recorded as PROPOSED
  first — never treated as binding before approval.
- IDs are stable and unique (`F-<AREA>-<NN>`). Never reuse an ID.

## Status legend (2026-10-08 snapshot)

| ID | Title | Approval | Implementation | Phase |
|---|---|---|---|---|
| F-STATE-PY-01 | Market State Intelligence — Python presentation | DECIDED | VERIFIED (token panel) | P1-12A DONE |
| F-STATE-V2-OV-01 | V2 Overview: state distribution + transitions | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-MV-01 | V2 Movers: state/direction columns + filters | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-TK-01 | V2 Token Detail: state explanation panel | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-STATE-V2-TL-01 | State timeline visualization | PROPOSED | NOT IMPLEMENTED | Later |
| F-UNI-01 | Dynamic LIVE-universe expansion (P1-12B) | DECIDED | VERIFIED | P1-12B DONE |
| F-OPP-01 | Research-based opportunity engine (P1-13A) | DECIDED | IMPLEMENTED (pending VERIFIED) | P1-13A DONE |
| F-P14A-01 | Prospective setup outcome evaluation (P1-14A→P1-14B.8) | DECIDED | VERIFIED (contract v1.1; supervised) | P1-14A/P1-14B/P1-14B.1/P1-14B.4/P1-14B.5/P1-14B.7/P1-14B.8 DONE, P1-14B.2/P1-14B.3/P1-14B.6 PARTIAL |
| F-OPP-UI-01 | Opportunities dashboard (P1-13B) | DECIDED | NOT IMPLEMENTED | P1-13B |
| F-BT-01 | Historical backtesting (P1-14) | DECIDED | NOT IMPLEMENTED | P1-14 |
| F-PAPER-01 | Forward paper validation (P1-15) | DECIDED | NOT IMPLEMENTED | P1-15 |
| F-PORT-01 | Paper portfolio (P1-16) | DECIDED | NOT IMPLEMENTED | P1-16 |
| F-V2-BFF-01 | Next.js API integration (BFF) | DECIDED | NOT IMPLEMENTED | DASH-V2 future |
| F-LAUNCH-SUP-01 | Supervised transactional launch | PROPOSED (enablement needs explicit authorization) | PARTIAL (V2-62 corrected disabled preparation; 902 tests; no wiring) | Future (V2 review of exact SHA first) |
| F-CMC-01 | CoinMarketCap supplementary metadata | DECIDED (staged) | NOT IMPLEMENTED | CMC-00/01/02 |
| F-CORE-01 | Completed Phase 1 foundations (index) | DECIDED | VERIFIED | P1-00…P1-11C, P1-10R |

---

## F-KRONOS-01 — Agentes IA + Kronos (investigacion futura)

- **Product objective:** explorar, solo como investigacion futura, si
  agentes IA y la fuente de datos Kronos pueden aportar contexto de
  mercado (metadata agregada, nunca fills, PnL ni backtest de Binance).
- **Origin / decision date:** objetivo Bot+V2 2026-10-13 (propuesta
  registrada, NO aprobada para implementacion).
- **Approval status:** PROPOSED (deferral explicito). **Implementation
  status:** NOT IMPLEMENTED. Cero dependencias instaladas, cero
  integraciones, cero codigo. No es requisito de arranque de ninguna
  corrida de observacion/evaluacion ni del ciclo de uso V2.
- **Target phase:** futura e indefinida (fuera del alcance actual:
  observacion + V2 como interfaz principal).
- **Dependencies:** ninguna (diseno pendiente de aprobacion previa).
- **Acceptance criteria (si algun dia se aprueba):** proveedor etiquetado
  obligatorio; jamas fuente de mark-price, liquidez, fills, PnL o
  backtest; revision legal previa si aplica.
- **Evidence needed:** ninguna aun (nada que probar).
- **Docs:** este backlog (unico registro hasta aprobacion).
- **Open questions:** valor real, estabilidad de acceso, credenciales.
- **Last update:** 2026-10-13 (diferido).

## F-STATE-PY-01 — Market State Intelligence, Python dashboard

- **Product objective:** expose validated classifier output (state,
  direction, timestamp, coverage, evidence) with truthful UNKNOWN/STALE
  behavior; never as LONG/SHORT recommendations, probabilities, or
  profitability claims.
- **Origin / decision date:** `docs/MARKET_STATES.md` (vocabulary + gating);
  phase order decision 2026-10-06 (`docs/DECISIONS.md`); authorized by
  P1-11A/B/C + P1-10R PASS chain; implemented P1-12A 2026-10-08.
- **Approval status:** DECIDED. **Implementation status:** VERIFIED
  (token-page panel; movers/system exposure not built — see F-STATE-V2-MV-01
  for V2-side tracking; no Python movers state column exists).
- **Target phase:** P1-12A DONE.
- **Dependencies:** P1-04…P1-08 engines, P1-09 token page, P1-11A/B/C +
  P1-10R gates (all satisfied).
- **Affected subsystems:** `classifier.py`, `persistence.py` (schema v7),
  `probe.py` (per-summary evaluation), `dashboard.py` + `dashboard_views.py`
  (token panel).
- **Required UI locations:** `/symbol/:symbol` state panel (done).
- **Data/API requirements:** persisted `state_features` rows; no new HTTP
  contract needed (server-rendered from existing store reads).
- **Acceptance criteria:** deterministic versioned rules; evidence
  for/against + missing + validity on every record; hysteresis; no
  probabilities; discovery-only honesty. All met.
- **Evidence:** `tests/test_classifier.py` (25 tests), 447/447 suite,
  120s observe COMPLETED run (9 evals, transitions persisted),
  token-page screenshots in P1-12A report.
- **Docs:** `docs/CLASSIFIER_SPEC.md`, `docs/FEATURE_MODEL.md`,
  `docs/ARCHITECTURE.md`, `docs/MARKET_STATES.md`.
- **Open questions:** none blocking; calibration is P1-14 territory.
- **Last update:** 2026-10-08.

## F-STATE-V2-OV-01 — V2 Overview: state distribution + transitions

- **Product objective:** Overview shows market-state distribution across
  the observed universe (with observed-universe denominator) plus recent
  transitions, all from authoritative Python classifications.
- **Origin / decision date:** `docs/DASHBOARD_V2_DESIGN_SPEC.md` +
  V2 architecture review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2 future slice (after BFF).
- **Dependencies:** F-V2-BFF-01 (versioned state view-model),
  F-STATE-PY-01 (authoritative values). React must never compute
  authoritative classifications.
- **Affected subsystems:** `frontend/src/app/overview/`, BFF routes.
- **Required UI locations:** `/overview` state distribution + transitions.
- **Data/API requirements:** versioned `/api/v1` state view-model with
  denominator, provenance, freshness.
- **Acceptance criteria:** denominator shown; stale/unknown distinguished;
  zero fabricated states; visual QA vs references.
- **Evidence needed:** BFF contract tests, component tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`,
  `docs/DASHBOARD_V2_API_CONTRACTS.md`.
- **Open questions:** exact view-model schema (pending BFF design).
- **Last update:** 2026-10-08.

## F-STATE-V2-MV-01 — V2 Movers: state/direction columns + filters

- **Product objective:** Movers table gains state and direction columns
  with matching filters, sourced from Python classifications.
- **Origin / decision date:** V2 design review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2 future slice (after BFF).
- **Dependencies:** F-V2-BFF-01, F-STATE-PY-01.
- **Affected subsystems:** `frontend/src/app/movers/`, BFF routes.
- **Required UI locations:** `/movers` columns + filter controls.
- **Data/API requirements:** per-symbol state + direction + freshness in
  the movers view-model.
- **Acceptance criteria:** filters combine with existing ones; nulls stay
  last/empty; no LONG/SHORT language.
- **Evidence needed:** contract + component + interaction tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-STATE-V2-TK-01 — V2 Token Detail: state explanation panel

- **Product objective:** Token Detail explains the current state with
  supporting evidence, counterevidence, missing inputs, previous
  transitions, and rule version — mirroring F-STATE-PY-01 content.
- **Origin / decision date:** V2 design review 2026-10-07.
- **Approval status:** DECIDED (design). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** DASH-V2-03 or later BFF-backed slice.
- **Dependencies:** F-V2-BFF-01, F-STATE-PY-01.
- **Affected subsystems:** `frontend/src/app/symbol/[symbol]/`, BFF routes.
- **Required UI locations:** `/symbol/[symbol]` state panel.
- **Data/API requirements:** full classification record view-model.
- **Acceptance criteria:** evidence/counterevidence/missing/version all
  visible; discovery-only honesty preserved.
- **Evidence needed:** contract + component tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-STATE-V2-TL-01 — State timeline visualization

- **Product objective:** visual timeline of state transitions per symbol
  (later enhancement, not existing functionality).
- **Origin / decision date:** governance capture 2026-10-08 from the
  standing "timeline is later" agreement.
- **Approval status:** PROPOSED. **Implementation status:** NOT IMPLEMENTED.
- **Target phase:** Later (after F-STATE-V2-TK-01).
- **Dependencies:** persisted `state_transitions` history, BFF exposure.
- **Affected subsystems:** frontend token/detail views.
- **Required UI locations:** TBD.
- **Data/API requirements:** transition history view-model.
- **Acceptance criteria:** TBD at approval; must never imply prediction.
- **Evidence needed:** design approval + tests + screenshots.
- **Docs:** this backlog (sole record until approved).
- **Open questions:** chart form, time windows, performance budget.
- **Last update:** 2026-10-08.

## F-UNI-01 — Dynamic LIVE-universe expansion (P1-12B)

- **Product objective:** subscribe/unsubscribe WS streams as HOT set
  evolves, with hysteresis and transport headroom.
- **Origin / decision date:** P1-05 left HOT as proposal-only;
  `docs/ROADMAP.md` phase sequence; next candidate per
  `docs/TASK_QUEUE.md` 2026-10-08.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  VERIFIED (P1-12B PASS 2026-10-08).
- **Target phase:** P1-12B DONE.
- **Dependencies:** P1-12A PASS (satisfied), P1-01R transport headroom.
- **Affected subsystems:** `universe_manager.py`, `probe.py` (managed
  connections + discovery hook), engines (allow/forget), OI poller HOT
  list, recorder `finalize_symbol`, dashboard overview tiers table.
- **Required UI locations:** overview universe tiers + lifecycle (done);
  Token Detail via live sets (done).
- **Data/API requirements:** discovery candidates + select_hot proposals;
  no new HTTP contract (discovery blob extended in place).
- **Acceptance criteria:** no silent resubscription; hysteresis honored;
  live/deep vs discovery-only labeling preserved; transport monitored.
  All met (31 tests + 300s live run: 3 promotions all LIVE).
- **Evidence:** `tests/test_universe.py` + `tests/test_universe_probe.py`
  (31 tests), 478/478 suite, `logs/probe-runs/p12b-300s.log`
  (git-ignored, preserved), `docs/UNIVERSE_SPEC.md`. P1-12B.1 audit
  (2026-10-08): timestamp gate + accounting corrected, 496/496 suite,
  240s observe re-validation (`logs/probe-runs/p12b1-240s.log`).
- **Docs:** `docs/ROADMAP.md`, `docs/TASK_QUEUE.md`, P1-05 decision record,
  `docs/UNIVERSE_SPEC.md`.
- **Open questions:** transport caps stay UNVERIFIED (re-check against
  official docs before raising budgets); resubscribe cadence beyond
  scan-driven sync unevaluated.
- **Last update:** 2026-10-08 (P1-12B.1 corrections applied).

## F-OPP-01 — Research-based opportunity engine (P1-13A)

- **Product objective:** setup candidates from validated states +
  historical analogs with lifecycle, evidence, counterevidence, risks —
  research only, no execution.
- **Origin / decision date:** `docs/ROADMAP.md` phase sequence;
  `docs/SIGNAL_RESEARCH_PLAN.md` (design only).
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  IMPLEMENTED (VERIFIED pending evidence link).
- **Target phase:** P1-13A DONE.
- **Dependencies:** F-UNI-01, classifier history, P1-11C event outcomes.
- **Affected subsystems:** `opportunity.py` (new engine module), persistence (schema v8),
  probe evaluation hook, dashboard `/opportunities` + `/api/opportunities`.
- **Required UI locations:** none yet (engine first; UI is F-OPP-UI-01).
- **Data/API requirements:** candidate lifecycle view-model; no numerical probability claims.
- **Acceptance criteria:** candidates explainable; direction/entry/stop/
  targets nullable until validated; no fabricated confidence;
  cooldown 60 min / max 200 / TTL 24h enforced. All met.
- **Evidence:** `tests/test_opportunity.py` (58 tests), 554/554 suite,
  120s observe COMPLETED run (3 REVERSAL_WATCH candidates stored),
  dashboard live at http://127.0.0.1:8091.
- **Docs:** `docs/OPPORTUNITY_ENGINE_SPEC.md`, `docs/ARCHITECTURE.md`,
  `docs/CURRENT_STATE.md`.
- **Open questions:** candidate scoring methodology (research output).
- **Last update:** 2026-10-08 (P1-13A.1 closeout).

## F-OPP-UI-01 — Opportunities dashboard (P1-13B)

- **Product objective:** present F-OPP-01 candidates (Python `/signals`,
  `/extreme-moves` per ROADMAP; V2 Opportunities per design spec) with
  empty/blocked shells until candidates exist.
- **Origin / decision date:** `docs/ROADMAP.md`; V2 Opportunities section
  `docs/DASHBOARD_V2_DESIGN_SPEC.md` (empty-shell-first rule).
- **Approval status:** DECIDED (sequenced/designed).
- **Implementation status:** NOT IMPLEMENTED (V2 has nav/blocked explanation only).
- **Target phase:** P1-13B.
- **Dependencies:** F-OPP-01.
- **Affected subsystems:** Python dashboard routes; `frontend/src/app/
  opportunities/`.
- **Required UI locations:** `/signals`, `/extreme-moves` (Python);
  `/opportunities` (V2).
- **Data/API requirements:** candidate lifecycle view-model.
- **Acceptance criteria:** honest empty states; no fabricated setups.
- **Evidence needed:** route tests + screenshots.
- **Docs:** `docs/DASHBOARD_V2_DESIGN_SPEC.md`, `docs/ROADMAP.md`.
- **Open questions:** none.
- **Last update:** 2026-10-08.

## F-P14A-01 — Prospective setup outcome evaluation (P1-14A → P1-14B.8)

- **Product objective:** register P1-13A opportunity setups at first DETECTED
  and observe forward mark-price outcomes at versioned horizons (1m/5m/15m/1h
  /4h); research-only: no P&L, no probabilities, no lookahead.
- **Origin / decision date:** `docs/MASTER_PLAN.md` P1-14; `docs/EVENT_LABELING.md`
  forward-outcome concept. Implemented P1-14A 2026-10-08; recovered and re-validated
  P1-14B 2026-10-09 (see P1-14B section in `docs/CURRENT_STATE.md`); time-integrity
  audited and three core defects fixed P1-14B.1 2026-10-09 (see P1-14B.1 section
  in `docs/CURRENT_STATE.md`).
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  IMPLEMENTED + VERIFIED (35 `test_prospective.py` + 39 `test_p14b_validation.py`
  + 16 `test_p14b_1_time_integrity.py` + 20 `test_p14b_3_transport_freshness.py`
  + 19 `test_p14b_4_lifecycle.py`, 683/683 canonical suite green — see P1-14A
  through P1-14B.4 result sections in `docs/CURRENT_STATE.md`; full evidence in
  `docs/P1_14B_VALIDATION_REPORT.md` + `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`
  + `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md` +
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`).
- **Target phase:** P1-14A DONE / P1-14B DONE (recovery) / P1-14B.1 DONE (integrity) /
  P1-14B.2 PARTIAL (stability gate: duration insufficient, prospective layer green) /
  P1-14B.3 PARTIAL (freshness: watchdog + stale-mark gate validated, duration insufficient) /
  P1-14B.4 PASS (contract v1.1: strict unknown-age, grace-deferred terminal PENDING) /
  P1-14B.5 PASS (operational: independent reference + ≥30-min healthy window demonstrated) /
  P1-14B.6 PARTIAL (reproducibility: second window both regimes, attribution refined, fixes validated) /
  P1-14B.7 PASS (persistent supervision: registry-leased abort enforcement, identity restored) /
  P1-14B.8 PASS (supervised maiden voyage: 35-min supervisor window post-audited + sentinel
  layer validated in brief run; V2 launch stays blocked — documented pending).
- **Dependencies:** P1-13A opportunity engine (setups, DETECTED lifecycle,
  candidate_key + setup_family + direction + market_state + rule_version +
  capability_tier fields).
- **Affected subsystems:** `microstructure_probe` (prospective.py, persistence.py
  schema v9), `probe.py` integration, `dashboard.py` (prospective endpoint +
  RESEARCH ONLY banner).
- **Required UI locations:** dashboard prospective tab + `/api/prospective`.
- **Data/API requirements:** schema v9 `prospective_setups` (REPLACE per key) +
  `prospective_outcomes` (append-only, bounded 500/setup); retention max
  hourly, default 90 days on detected_at_ms / observed_at_ms.
- **Acceptance criteria:** idempotent registration (one key = one episode);
  outcome states COMPLETE/PENDING/INSUFFICIENT_HISTORY only (never fabricated);
  UNKNOWN age never FRESH (strict classification); PENDING grace-deferred (recovery
  window = 1 horizon past maturity) then terminal, INSUFFICIENT immediate;
  restart-safe rehydrate from `prospective_setups` (+ seen rebuilt incl. PENDING rows);
  bounded queue + telemetry (writes/drops/errors/inflight/high_water +
  completed/pending/insufficient/in_grace); 4h horizon usable with genuinely
  later data; no orders, keys, P&L, or probabilities.
- **Evidence:** 35 `test_prospective.py` + 39 `test_p14b_validation.py` + 16
  `test_p14b_1_time_integrity.py` (609/609 canonical suite green);
  `/api/prospective` (schema_version 9, RESEARCH ONLY banner); migration chain
  v1–v9; real persisted DB evidence (`data/microprobe.db`, schema v9:
  7 setups, 28 COMPLETE outcomes post-P1-14B.1 fix runs, 0 duplicates,
  event-time/no-lookahead audit PASS — full details in
  `docs/P1_14B_VALIDATION_REPORT.md` + `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`).
  Correction: the P1-14B "single outcome" shape was partly an artifact of the
  outcome-store bounding bug (fixed P1-14B.1); rows already deleted are
  unrecoverable and documented, not reconstructed. P1-14B.2 stability run
  (23.4 min, aborted on the >5 % reject rule): 24 setups, 68/68 COMPLETE,
  0 dupes, 100 % matured-cell coverage — full details in
  `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`. P1-14B.3 freshness work
  (stale-mark gate + watchdog, 20 new tests, 629/629): 24 setups, 99/99 COMPLETE,
  0 dupes; 68-row historical classification (19/28/21/0); 21 missing cells explained
  (unsubscribed OGN/RLC, no defect) — full details in
  `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`. P1-14B.4 contract v1.1 (strict
  unknown-age, grace-deferred terminal PENDING, upgrade rejected with schema
  rationale; 19 new tests; 35 pytest-style tests converted to executing TestCase;
  683/683): 24 setups, 99/99 COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`. P1-14B.5 operational PASS
  (independent reference + coincident 35/40-min agreement; 708/708): 49 setups,
  150/150 COMPLETE, 0 dupes, ≥30-min healthy window demonstrated — full details in
  `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`. P1-14B.6 PARTIAL (second window
  both regimes; attribution refined to server-side per-connection; abort breached
  unacted — supervision lost; 726/726): 57 setups, 202/202 COMPLETE, 0 dupes —
  full details in `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`. P1-14B.7 PASS
  (supervisor engine + 34 tests incl. real-PID abort; 760/760): 57 setups, 202/202
  COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`. P1-14B.8 PASS (35-min supervised
  window post-audited + sentinel layer + brief three-layer validation; 775/775):
  66 setups, 228/228 COMPLETE, 0 dupes, all rows preserved — full details in
  `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md`.
- **Docs:** `docs/PROSPECTIVE_EVALUATION_SPEC.md`, `docs/DECISIONS.md`,
  `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`.
- **Open questions:** MFE/MAE and cohort aggregation deferred to a later
  revision; final horizon list to be frozen once enough 4h data accumulates;
  P1-14B: host-clock skew during the 150s observe window limited outcome
  coverage (documented, not a code defect); P1-14B.1: prolonged-run readiness
  blockers recorded (30+ min healthy window, clock resync note) — no long run
  started; P1-14B.2: 35-min attempt aborted at 23.4 min on transport episode
  (reject rate rule) — duration insufficient, transport limiting, no 4–6 h
  authorization; P1-14B.3: ≤35-min attempt aborted at 17.1 min (second episode
  + path outage after proven watchdog recovery) — duration insufficient,
  transport/freshness limiting, still no 4–6 h authorization; P1-14B.4: contract
  v1.1 enforced (strict unknown-age, grace-deferred terminal PENDING), 120 s
  regression run clean, no long runs; P1-14B.5: ≥30-min healthy window demonstrated
  with reference agreement (repeat advisable);   P1-14B.6: second window both regimes
  (22.6 min healthy), abort breached unacted (supervision lost), attribution refined
  to server-side per-connection — still no 4–6 h authorization; P1-14B.7: abort
  enforcement moved into `control supervise` (registry lease, verified-PID one-shot,
  UNKNOWN-safe) — next supervised window needs explicit instruction, still no 4–6 h;
  P1-14B.8: 35-min supervised window post-audited + sentinel layer validated (brief
  three-layer run) — still no 4–6 h authorization; P1-14B.8-followup (2026-10-11):
  enforce fencing corrected per frontend review `d80fb9b` (locked STOPPING,
  fenced ABORTED/FAILED, real `aborted_by`, owned-lease heartbeat proof, 808/808)
  with no new supervised window on the corrected SHA (historical windows stay
  historical); P1-14B.8-V2-51 (2026-10-11): operation boundary through
  handle-bound termination, run-bound leases, pure `status_readonly()` +
  fenced reconciliation, locked remaining writers, multiprocess proof
  (826/826), no new window; P1-14B.8-V2-52 (2026-10-11): native refusal
  propagation, own-child adoption, C1 barrier+window proof (840/840), no new
  window; P1-14B.8-V2-54 (2026-10-11): exact 32-bit BOOL + ABI proof,
  child-first log handoff on the real-try_register flow, C1 scope qualified
  (850/850), no new window; V2 supervised start still PENDING/separate.
- **Last update:** 2026-10-11 (P1-14B.8 V2-54 BOOL+handoff, DONE acotado).

## F-BT-01 — Historical backtesting (P1-14)

- **Product objective:** replay-based backtester without future leakage;
  24h calibration review of thresholds vs real crossings.
- **Origin / decision date:** `docs/ROADMAP.md` P1-14; SUCCESS_GATES G9.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  PARTIAL (2026-10-20): bounded offline evaluation (`eval-census-v2-trio`)
  executable from V2 with versioned, hash-verified inputs, deterministic
  results and operation→Paper Lab link. NOT a full backtester of the
  extremes strategy (no causal universe/liquidity/ranking yet); no
  calibration of thresholds; no profitability claim.
- **Target phase:** P1-14.
- **Dependencies:** P1-11C outcomes, classifier history, cost model.
- **Affected subsystems:** `scripts/run_dashboard_backtest.py` (allowlisted
  executor) over `docs/evidence/eval-census-v2-package/`; V2 BFF
  `frontend/src/lib/backtest-control.ts` + `api/v1/backtest/*`; UI
  `frontend/src/components/backtest/`.
- **Required UI locations:** V2 `/backtest` (functional since 2026-10-20;
  no longer a stub); results + trade list + linked replay.
- **Data/API requirements:** historical bars + outcome tables + fee model
  (present for EVAL-CENSUS-V2); causal universe/liquidity/ranking (absent).
- **Acceptance criteria:** no-lookahead replay proven; sensitivity noted.
- **Evidence needed:** replay tests + calibration report.
- **Docs:** `docs/ROADMAP.md`, `docs/BACKTEST_READ_CONTRACT_V1.md`,
  `docs/EXTREMES_EVALUABILITY_MATRIX.md`.
- **Open questions:** cost/slippage assumptions; causal universe acquisition.
- **Last update:** 2026-10-20.

## F-PAPER-01 — Forward paper validation (P1-15)

- **Product objective:** live paper engine with state-driven exits and
  risk limits; performance vs backtest.
- **Origin / decision date:** `docs/ROADMAP.md`, MASTER_PLAN Phase 4.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** P1-15.
- **Dependencies:** F-BT-01, risk engine (unbypassable).
- **Affected subsystems:** new paper engine + position manager.
- **Required UI locations:** V2 Paper Lab (blocked explanation exists).
- **Data/API requirements:** live features + state stream + fills sim.
- **Acceptance criteria:** risk limits enforced; halts exercised/reasoned.
- **Evidence needed:** paper-vs-backtest divergence report.
- **Docs:** `docs/PAPER_TRADING.md`, `docs/ROADMAP.md`.
- **Open questions:** none (far horizon).
- **Last update:** 2026-10-08.

## F-PORT-01 — Paper portfolio (P1-16)

- **Product objective:** paper portfolio / dynamic exit management.
- **Origin / decision date:** `docs/ROADMAP.md`, `docs/TASK_QUEUE.md`
  sequence.
- **Approval status:** DECIDED (sequenced). **Implementation status:**
  NOT IMPLEMENTED.
- **Target phase:** P1-16.
- **Dependencies:** F-PAPER-01.
- **Affected subsystems:** TBD.
- **Required UI locations:** TBD.
- **Data/API requirements:** TBD.
- **Acceptance criteria:** TBD at phase entry.
- **Evidence needed:** TBD.
- **Docs:** `docs/ROADMAP.md`.
- **Open questions:** scope deferred until P1-15 evidence exists.
- **Last update:** 2026-10-08.

## F-V2-BFF-01 — Next.js API integration (BFF)

- **Product objective:** same-origin BFF proxying allowlisted Python
  endpoints with versioned view-models; browser never touches Python
  directly, SQLite, keys, or the control nonce.
- **Origin / decision date:** `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`
  + migration plan (DASH-V2-0x slices), 2026-10-07.
- **Approval status:** DECIDED (architecture). **Implementation status:**
  NOT IMPLEMENTED (frontend is static fixtures only).
- **Target phase:** DASH-V2 future slice (explicit authorization).
- **Dependencies:** Python `/api/v1` view-model facade (proposed, not built).
- **Affected subsystems:** `frontend/src/app/api/v1/`, Python API additions.
- **Required UI locations:** all V2 routes (data layer only).
- **Data/API requirements:** envelope (schema_version, provenance,
  freshness, quality flags) per V2 API contracts doc.
- **Acceptance criteria:** BFF security tests (Host/Origin/CSRF/nonce
  non-disclosure/allowlists); no open proxy; Python suite stays green.
- **Evidence needed:** security + contract tests, screenshots.
- **Docs:** `docs/DASHBOARD_V2_FRONTEND_ARCHITECTURE.md`,
  `docs/DASHBOARD_V2_API_CONTRACTS.md`,
  `docs/DASHBOARD_V2_MIGRATION_PLAN.md`.
- **Open questions:** exact `/api/v1` schema validator language.
- **Last update:** 2026-10-11 (DASH-V2-64 backend handoff: reconciled to
  `c635938`; deployed V2 imports this worktree `/src` + `status_readonly()`
  and canonical DB readOnly; legacy read contracts inventoried in
  `docs/DASHBOARD_V1_READ_CONTRACTS.md`; old-UI retirement proposed with
  helper-extraction blocker; GET purity pinned by 3 tests; PARTIAL unchanged,
  no gate advancement. DASH-V2-67 backend: helpers extracted VERBATIM to
  `host_process.py` (stdlib only), `control.py` decoupled from the HTTP
  module, `dashboard.py` re-exports identical objects, boundary tests H1–H4;
  file-level old-UI retirement still NOT executed, pending review.
  DASH-V2-71B backend: System data contracts matrix
  (`docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md`) + read-purity proof
  (1 test, temp fixtures); host resources + ops audit log NOT_AVAILABLE
  (honest absence, future work noted); V2 reads stay on allowlisted
  readers + own readOnly adapter; PARTIAL unchanged, no gate advancement).

## F-LAUNCH-SUP-01 — Supervised transactional launch

- **Product objective:** one atomic operation that starts probe + supervisor
  + sentinel, verifies every component against the run inside a finite
  budget, and rolls back everything launched on any failure. Research and
  operator use only; no trading semantics.
- **Origin / decision date:** V2-55 acceptance checkpoint 2026-10-11
  (enablement NOT authorized); contract `docs/SUPERVISED_LAUNCH_CONTRACT.md`.
- **Approval status:** PROPOSED (pilot brief-120s run needs explicit
  authorization; enablement chain implemented, no run launched).
- **Implementation status:** PARTIAL (contract + enabled backend chain +
  BFF fixed path: readiness-green + START_OBSERVE_2100 + preset allowlist
  + separate status/start/stop budgets + timeout reconcile + capability +
  storage gate + own-keys presets; 2026-10-14, evidence below).
- **Target phase:** O1 pilot (authorized brief run first).
- **Dependencies:** P1-11B.1 run control, P1-14B.7/8 supervision + sentinel,
  registry mutual exclusion, verified termination, pure observation.
- **Affected subsystems:** `control.py` launch section only; dashboard,
  probe, persistence untouched.
- **Required UI locations:** none (BFF renders the outcome envelope only
  after a future enablement review).
- **Data/API requirements:** outcome envelope (outcome/reason/scope/run/
  watchers/verification/rollback/evidence) reusing registry field names,
  nullable-safe; `status_readonly()` stays the GET path.
- **Acceptance criteria:** confirmation only on simultaneous full
  verification (never Popen/lease/heartbeat alone); kill-only rollback of
  transaction PIDs with verified identity; foreign/terminal never touched;
  unverifiable cleanup reported UNCERTAIN with pending evidence.
- **Evidence:** `tests/test_supervised_launch.py` (23 tests + V2PathTest),
  backend directed 143 OK (launch/stop/supervision/abort/identity);
  BFF + UI vitest 255/255 (incl. BotControl 202 x3);
  `docs/evidence/BARRIER_FIX_RESUMEN.json` (barrier 1077 exit 0);
  `docs/evidence/VISUAL_QA_PREPILOTO.txt`.
- **Docs:** `docs/SUPERVISED_LAUNCH_CONTRACT.md`, `docs/ARCHITECTURE.md`,
  `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`,
  `docs/OBSERVATION_RUN_MATRIX.md`.
- **Open questions:** pilot brief-120s authorization (pending user).
- **Last update:** 2026-10-14.

## F-CMC-01 — CoinMarketCap supplementary metadata

- **Product objective:** optional aggregate context (metadata, rankings,
  indices) with mandatory provider labeling; never a Binance mark-price,
  liquidity, fill, PnL, or backtest source.
- **Origin / decision date:** `docs/COINMARKETCAP_FEASIBILITY.md` +
  `docs/EXTERNAL_MARKET_DATA_EVALUATION.md` + `docs/TOKEN_IDENTITY_MAPPING.md`,
  2026-10-07 (staged CMC-00/01/02; legal review still required).
- **Approval status:** DECIDED (staged feasibility; integration NOT
  authorized). **Implementation status:** NOT IMPLEMENTED.
- **Target phase:** CMC-00 (fixtures/mapping) → CMC-01 (bounded keyless
  adapter, needs approval) → CMC-02 (optional).
- **Dependencies:** stable-ID mapping design; legal review; measured
  keyless stability.
- **Affected subsystems:** future backend-only adapter (outside WS path),
  V2 `ProviderAttribution`.
- **Required UI locations:** V2 market context / profiles (when built).
- **Data/API requirements:** ID map + metadata caches with budget TTLs.
- **Acceptance criteria:** verified stable-ID mapping; fixtures for
  ambiguity/429/outage/stale; Binance-only execution math.
- **Evidence needed:** mapping fixtures + adapter tests (none exist).
- **Docs:** as listed under Origin.
- **Open questions:** keyless rate stability, category value, credentials.
- **Last update:** 2026-10-08.

## F-CORE-01 — Completed Phase 1 foundations (evidence index)

- **Product objective:** N/A (index entry — prevents re-planning or
  duplicating finished work).
- **Origin:** phase completion records in `docs/TASK_QUEUE.md`.
- **Approval status:** DECIDED. **Implementation status:** VERIFIED.
- **Target phase:** P1-00…P1-11C, P1-10R (all DONE).
- **Dependencies:** none remaining.
- **Affected subsystems:** N/A (index).
- **Required UI locations:** N/A.
- **Data/API requirements:** N/A.
- **Acceptance criteria:** phase PASS records linked below.
- **Evidence:** COMPLETED section of `docs/TASK_QUEUE.md`; 447/447 suite;
  `logs/p1-10r/` soak evidence (git-ignored, preserved).
- **Docs:** `docs/CURRENT_STATE.md`, `docs/PHASE_1_REPORT.md` (untouchable).
- **Open questions:** none.
- **Last update:** 2026-10-08.

Completed, evidence-linked work:

- P1-00 tooling (`python run_tests.py`) — VERIFIED, 447/447.
- P1-01/P1-01R transport validation — VERIFIED (45min healthy window).
- P1-02 persistence (SQLite, retention-bounded) — VERIFIED.
- P1-03/P1-09 dashboards (Python SSR + terminal) — VERIFIED, live.
- P1-04…P1-08 engines (returns → structure) — VERIFIED (P1-11A scales).
- P1-10R ≥6h soak — PASS (21603.9s, evidence `logs/p1-10r/`).
- P1-10R-FIX-01 console suppression — FIXED.
- P1-11A/B/C research chain — PASS.
- P1-12A classifier v0 — PASS.
- DASH-V2-00/01/02 slices — DONE (static foundation, no integration).

## Mandatory closeout policy

Every future implementation or documentation phase must report these
seven fields in its final report (verbatim names):

- `DECISIONS_REVIEWED` — which decision records were read.
- `NEW_DECISIONS_RECORDED` — what was appended, where.
- `FEATURES_IMPLEMENTED` — backlog IDs completed with evidence.
- `FEATURES_VERIFIED` — backlog IDs verified with evidence links.
- `DEFERRED_FEATURES` — IDs intentionally left not-implemented.
- `BACKLOG_UPDATED` — whether this file changed and why.
- `DOCUMENTATION_CONFLICTS` — contradictions found (fixed or flagged).

If a new material decision needs user approval, record it as PROPOSED
here and request approval before treating it as binding. Never mark
features VERIFIED without evidence.


## F-R3CAP-04 — R3 vivo brief 120s (2026-10-16, autorizada 1x)

- `DECISIONS_REVIEWED` — F-R3CAP-03 (atribucion exacta),
  captura v2, contratos runtime/BFF/detections, readiness.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 vivo brief
  (lanzamiento unico reconciliado por GET sin duplicar;
  PASS vivo con triple RUNNING exact-uuid).
- `FEATURES_IMPLEMENTED` — (sin codigo) corrida supervisada
  brief 120s observe-only + captura automatica con ambas
  identidades fijadas.
- `FEATURES_VERIFIED` — capturador: outcome terminal-captured,
  R3 PASS (t0/+30/+60 RUNNING verificados, exact-uuid,
  snapshot coincidente, current, detections atribuidas;
  0 eventos iniciales validos, 18/3 desde +60s); cierre
  COMPLETED exit 0, 133s congelado, 0 python, sin journals,
  filas UUID 4/6/39/9, JSON + resumen + 2 capturas V2.
- `DEFERRED_FEATURES` — trabajo offline de entradas/salidas
  (recomendado, no ejecutado): engine + runner + mapping +
  funding realizado + costes + purga; paper/ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-R3CAP-04).
- `DOCUMENTATION_CONFLICTS` — none new (respuesta 200 del
  start sin run_id en nivel superior: reconciliacion
  documentada, sin duplicar).

## F-R3CAP-03 — atribucion exacta R3 (2026-10-16, sobre a2aebc5, sin corridas)

- `DECISIONS_REVIEWED` — R3 v2 (veredicto separado, UUID
  tardio, detections verificado), atribucion del feed
  (sin gracia, run_id primero, regresion 20s), identidad
  UNKNOWN + feed estricto, contratos runtime/BFF/detections.
- `NEW_DECISIONS_RECORDED` — DECISIONS §Atribucion exacta R3
  (method/snapshot_run_id/timestamp; PASS solo exact-uuid con
  UUID registro=snapshot; temporal nunca prueba exacto).
- `FEATURES_IMPLEMENTED` — BFF: `feed_attribution_method` +
  `feed_snapshot_run_id` + `feed_snapshot_timestamp` aditivos
  (salud/umbrales/Start-Stop intactos); capturador: conserva
  los tres campos y exige exact-uuid + coincidencia doble +
  resto de identidad para PASS.
- `FEATURES_VERIFIED` — BFF 4 nuevos + capturador 3 nuevos
  (temporal HEALTHY/current sin UUID -> UNKNOWN;
  coincidente+exact -> puede calificar; incompatible ->
  nunca PASS); suites locales frontend 304/304 + capturador
  19/19 + export 6/6 + typecheck; sin Binance.
- `DEFERRED_FEATURES` — R3 vivo, redeploy V2 3020 (build
  anterior intacto), mapping, funding, costes, purga,
  entradas/salidas, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-R3CAP-03).
- `DOCUMENTATION_CONFLICTS` — none new (temporal util pero
  no probatorio; PROPOSED + mecanica intactos).

## F-R3CAP-02 + F-ENTRY-PREP-02 — veredicto R3 y causalidad (2026-10-16, sobre 69d55ba, sin corridas)

- `DECISIONS_REVIEWED` — captura v1, contrato de velas real,
  conversion del runner, `input_hash`, reglas de conocimiento v4.2.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 v2 + causalidad;
  contrato close_time/as_of en inventario.
- `FEATURES_IMPLEMENTED` — captura: veredicto separado + UUID
  tardio/ausencias + detections verificado + identidades fijadas;
  export/runner: close_time aditivo + as_of + cadena; motor
  intacto (campo solo procedencia).
- `FEATURES_VERIFIED` — 6 R3 (terminal-directo, tardio, incompatible,
  foreign, UNKNOWN-completo, PASS con fijadas) + 4 export/causal
  (close_time, as_of vs cutoff, preservacion, intra-vela con
  control negativo); locales, sin Binance.
- `DEFERRED_FEATURES` — R3 vivo, mapping, funding, costes, purga,
  entradas/salidas, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-R3CAP-02,
  F-ENTRY-PREP-02).
- `DOCUMENTATION_CONFLICTS` — none new (PROPOSED + mecanica
  intactos; prep economico no repetido).

## F-R3CAP-01 + F-ENTRY-PREP-01 — captura R3 + prep offline (2026-10-16, sobre 48445f2, sin corridas)

- `DECISIONS_REVIEWED` — cierre brief R1-R11, contratos runtime/
  detecciones/BFF, motor v4.2 + runner, P1-11C, klines retenidos.
- `NEW_DECISIONS_RECORDED` — DECISIONS §R3 capture + prep;
  `docs/ENGINE_ENTRY_EVAL_INVENTORY.md`; reconciliacion 10+1 y
  UNKNOWN/STALE por capas.
- `FEATURES_IMPLEMENTED` — F-R3CAP-01: `scripts/capture_run_window.py`
  (GET-only, pin, +30/60/90, terminal acotado, salida protegida);
  F-ENTRY-PREP-01: `scripts/export_engine_inputs.py` (PROPOSED map
  no aprobado) + inventario + prep mecanico en temp.
- `FEATURES_VERIFIED` — captura 10 + export 2 (locales, sin Binance);
  prep: 8637 velas/1558 eventos/hash/discartes/versiones; economia
  RETENIDA (no leida, no presentada).
- `DEFERRED_FEATURES` — R3 PASS vivo (proxima ventana autorizada);
  mapping H, funding realizado, costes medidos, purga; entradas/
  salidas, backtests validantes, paper, ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-R3CAP-01,
  F-ENTRY-PREP-01).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: "9 PASS" (10+1) y
  backtests jamas inexistentes (reutilizados v4.2 + runner).

## F-LINK-01 + F-EPISODE-V1-01 — piloto brief 20261016T005550Z (2026-10-16, 1x120s autorizada)

- `DECISIONS_REVIEWED` — trazabilidad stem<->UUID, episodios v1,
  contratos runtime/BFF/detections, reconciliacion OBS10M.
- `NEW_DECISIONS_RECORDED` — DECISIONS §piloto brief; evidencia
  `docs/evidence/RUN_BRIEF120_20261016_CLOSEOUT.json` (+2 capturas V2).
- `FEATURES_IMPLEMENTED` — (sin codigo) prueba viva del enlace
  automatico + agrupacion v1 sobre 10 eventos nuevos.
- `FEATURES_VERIFIED` — matriz R1-R11 en el JSON: 10 PASS
  (R1,R2,R4-R11), R3 UNKNOWN (feed mid-run en vivo no capturado;
  enlace exacto disponible + path probado offline), 0 FAIL
  (correccion: el "9 PASS" anterior era error de conteo); 54 filas
  UUID = research.writes; V2 10/2 con enlace exacto y sin mezcla.
- `DEFERRED_FEATURES` — R3 mid-run (residual), evaluacion de
  entradas/salidas, backtests, paper, ejecucion; resto excluido.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-LINK-01,
  F-EPISODE-V1-01, prueba viva, sin VERIFIED economico).
- `DOCUMENTATION_CONFLICTS` — none new (98/4 parcial vs 245/13
  completo ya distinguidos; filas del run vs delta neto por
  retencion distinguidos aqui).

## F-LINK-01 + F-EPISODE-V1-01 — trazabilidad y episodios (2026-10-16, sobre d7dcc70, sin nuevas corridas)

- `DECISIONS_REVIEWED` — control/registro/leases/identidad,
  detector funding, contratos runtime/BFF, V2 (sin consumo crudo),
  reconciliacion OBS10M.
- `NEW_DECISIONS_RECORDED` — DECISIONS §trazabilidad+episodios;
  `docs/EVENT_EPISODES.md` (contrato v1); contratos runtime/BFF.
- `FEATURES_IMPLEMENTED` — F-LINK-01: link_probe_run_id fenced +
  probe_run_id en status + lector exacto con rechazo incompatible;
  F-EPISODE-V1-01: agrupacion v1 + BFF /detections + panel System.
- `FEATURES_VERIFIED` — linkage 7 + episodios 5 (245 retenidos) +
  detecciones 5 + persistencia-linkage 4 restaurados (P3 v10/propaga-
  cion/rehidratacion, `test_persistence_run_linkage.py` verbatim HEAD)
  + feed/BFF/panel nuevos; Start/Stop/propiedad en
  barrera; suites abajo.
- `DEFERRED_FEATURES` — episodios en otras vistas sin fuente
  reconstruible (limitacion informada, no inventada); resto excluido.
- `BACKLOG_UPDATED` — yes: this entry (IDs F-LINK-01,
  F-EPISODE-V1-01).
- `DOCUMENTATION_CONFLICTS` — corregidos: "episodios independientes"
  (agrupados por regla), "byte-identico" sin hashes (tamano estable
  + contenido modificado).

## O2 reconciliation UUID/persistence/funding - 2026-10-16 (sobre 67472e0, sin nuevas corridas)

- `DECISIONS_REVIEWED` — informe OBS10M, codigo recorder/resolve,
  esquema y contenidos DB, log de la corrida.
- `NEW_DECISIONS_RECORDED` — addendum + JSON de reconciliacion (esta
  entrada los indexa).
- `FEATURES_IMPLEMENTED` — correccion UUID/persistencia/funding en el
  informe + addendum + evidencia estructurada (no codigo).
- `FEATURES_VERIFIED` — UUID exacto (20/20 + final_summary + vecinas),
  246 writes a historical.db con UUID (183+33+30), 245 = 13 episodios;
  Starting/Stop/umbrales/identidad no tocados (sin codigo).
- `DEFERRED_FEATURES` — baseline por tabla pre-run (proxima ventana),
  resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: UUID quimera del
  informe, "historical.db sin cambios" (contenido nuevo con 0B),
  245 como cruces independientes (son 13 episodios).

## O2 observation-10m run completed - 2026-10-15 (autorizada, sobre 10cad5c, push 67472e0)

- `DECISIONS_REVIEWED` — preset observation-10m, readiness verde 6/6,
  registro terminal previo, DB legible, cadena supervisada.
- `NEW_DECISIONS_RECORDED` — informe RUN_OBS10M_20261015_COMPLETED
  (ventana, metricas, comparacion con piloto, veredicto acotado).
- `FEATURES_IMPLEMENTED` — primera ventana 600s supervisada via V2
  (no codigo).
- `FEATURES_VERIFIED` — arranque confirmado, 0 rechazos, watchers
  22+22, cierre natural, PIDs muertos, COMPLETED 610s, SQLite+V2, sin
  journal, barra fiel inicio/mitad/final; evidencia + 2 capturas.
- `DEFERRED_FEATURES` — validacion economica (dos ventanas no bastan),
  proximas ventanas, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## V2 feed attribution fix - 2026-10-16 (sobre 3f2fcea, sin nuevas corridas)

- `DECISIONS_REVIEWED` — hardening 3f2fcea, id-spaces registry/DB,
  propiedad, umbrales 0.05/0.5.
- `NEW_DECISIONS_RECORDED` — DECISIONS §correccion + contrato feed
  (sin gracia, run_id priorizado, cruce runtime, regresion 20s).
- `FEATURES_IMPLEMENTED` — atribucion estricta (exacta > temporal),
  previous-run nunca HEALTHY, UNKNOWN sin certeza.
- `FEATURES_VERIFIED` — regresion 20s A/B + run_id exacto +
  runtime-inconsistente; Start/Stop/propiedad/umbrales/identidad
  intactos (suites abajo).
- `DEFERRED_FEATURES` — nuevas corridas, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## V2 identity/feed hardening - 2026-10-16 (sobre 3544ad6, sin nuevas corridas)

- `DECISIONS_REVIEWED` — visibilidad 3544ad6, aborto 0.05, display 0.5,
  staleness cadence vs event-driven, propiedad PID+imagen+ctime.
- `NEW_DECISIONS_RECORDED` — DECISIONS §endurecimiento + contratos feed
  (HEALTHY estricto, atribucion, 0.05 vs 0.5, missing/silent/parse).
- `FEATURES_IMPLEMENTED` — display unknown/gone/replaced, terminal
  explicito, expiracion 30s, feed estricto con atribucion previous-run.
- `FEATURES_VERIFIED` — feed 12 nuevos (invalido/cero/faltante/0.06/
  limpio/previous-run/missing/silent/parse + piloto), supervision 3,
  barra 5, BotControl 4; Start/Stop/propiedad intactos (67 backend).
- `DEFERRED_FEATURES` — nuevas corridas, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new (0.05 enforced vs 0.5 display
  reconciliados por escrito; umbrales intactos).

## V2 run visibility - 2026-10-16 (sobre 5d4fef6, sin nuevas corridas)

- `DECISIONS_REVIEWED` — control canonico (start/stop/supervise/sentinel/
  launch), readiness por capability + storage, BotControl 202 + reconcile,
  identidad host PID+imagen+ctime, contratos runtime V2, piloto COMPLETED
  + aborto previo + journal forense.
- `NEW_DECISIONS_RECORDED` — DECISIONS §visibilidad global + §reconciliacion
  piloto; contratos runtime V2 actualizados; reconciliacion en
  `docs/PILOT_BRIEF_20261015_RECONCILIATION.md`.
- `FEATURES_IMPLEMENTED` — barra global RunStatusBar (todas las pantallas),
  stop proyecto verificado (dashboard/agent/direct), campos run_id/
  process_state/verified/last_exit_at + feed enriquecido, BotControl
  registrado-vs-verificado + terminal congelado.
- `FEATURES_VERIFIED` — backend `tests/test_run_visibility.py` 10 OK
  (origenes, stop, identidad incompleta, reemplazo, timeout, desconexion,
  cierre natural, aborto; procesos sleep aislados); frontend 63 OK
  (bot-control/run-status-bar/stop/start/contract); typecheck limpio;
  barrera completa y QA visual pendientes en el cierre.
- `DEFERRED_FEATURES` — nuevas corridas/pilotos, validacion economica,
  resto O2-O5/IA/Kronos (excluidos).
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — corrected: "V2 will not stop agent runs"
  (ahora stop proyecto verificado); "aborto previo = transporte
  concluyente" (ahora origen UNKNOWN con retraso observado);
  feed UNKNOWN permanente en BFF (ahora enriquecido desde telemetry).

## O1 pilot completed - 2026-10-15 (autorizado, sobre 1c566b1)

- `DECISIONS_REVIEWED` — plan brief, readiness verde, plan de captura.
- `NEW_DECISIONS_RECORDED` — DECISIONS §piloto completado (ventana,
  metricas, veredicto acotado).
- `FEATURES_IMPLEMENTED` — primera ventana sana supervisada (no codigo).
- `FEATURES_VERIFIED` — arranque confirmado, 0 rechazos, watchers 6+6,
  cierre natural, PIDs muertos, COMPLETED, SQLite+V2, sin journal;
  evidencia PILOT_BRIEF_20261015_COMPLETED + copia maintenance JSON.
- `DEFERRED_FEATURES` — validacion economica (una ventana no basta),
  proximas ventanas, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 maintenance applied - 2026-10-15 (autorizado, sobre e773e51)

- `DECISIONS_REVIEWED` — procedimiento DB_MAINTENANCE_RECOVERY.md.
- `NEW_DECISIONS_RECORDED` — DECISIONS §mantenimiento aplicado.
- `FEATURES_IMPLEMENTED` — recovery aplicado (no codigo nuevo).
- `FEATURES_VERIFIED` — apply PASS, journal consumido, hash
  byte-identico, readiness 6/6, 5 rutas 200, monitor no arrancado.
- `DEFERRED_FEATURES` — proximo piloto (nueva autorizacion), resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 window reconciliation - 2026-10-16 (sobre e0b0141)

- `DECISIONS_REVIEWED` — lock-probe forense, registry states, hot
  fixture recipe, spy design.
- `NEW_DECISIONS_RECORDED` — DECISIONS §ventana por registry (forense
  + ventana + hot real + spy).
- `FEATURES_IMPLEMENTED` — ventana registry, fixture hot, spy test.
- `FEATURES_VERIFIED` — journal 22/22, spy fail-before/passa-after,
  barrera pendiente.
- `DEFERRED_FEATURES` — apply (sin solicitar aun), piloto, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 maintenance reconciliation - 2026-10-16 (sobre 3a55052)

- `DECISIONS_REVIEWED` — backup/rollback, hash binding, writer locks,
  pre/post comparison.
- `NEW_DECISIONS_RECORDED` — DECISIONS §mantenimiento aplicable;
  DB_MAINTENANCE_RECOVERY con backup real + comando definitivo.
- `FEATURES_IMPLEMENTED` — --apply con backup/writer/drift/compare.
- `FEATURES_VERIFIED` — journal 22/22, barrera 1108 exit 0, destino
  verificado fuera/inexistente.
- `DEFERRED_FEATURES` — apply canonico (autorizacion), piloto, resto.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 correction reconciliation - 2026-10-16 (sobre 6264ccc)

- `DECISIONS_REVIEWED` — receive-path stamping order, fixture journal
  forensics (magia cero vs hot real), backup/protecciones.
- `NEW_DECISIONS_RECORDED` — DECISIONS §correccion revision (nombres
  honestos, test ruta real, --apply/backup, informe publicado).
- `FEATURES_IMPLEMENTED` — renombres + RealReceivePathTest + --apply
  completo + 14 tests recover/backup.
- `FEATURES_VERIFIED` — attribution 6/6 (3x ruta real), journal 14/14,
  barrera 1100 exit 0, rehearsal publicado re-ejecutable.
- `DEFERRED_FEATURES` — apply canonico (autorizacion), proximo piloto,
  resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new (queue/transit renombrado en
  codigo+tests+docs a dispatch/yield).

## O1 journal/attribution reconciliation - 2026-10-15 (sobre 9b78058)

- `DECISIONS_REVIEWED` — journal/WAL readOnly, `_connection_loop`
  buffering, skew-guard path, telemetry summary shape.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §journal+atribucion;
  `docs/DB_MAINTENANCE_RECOVERY.md` (PROPUESTO, sin aplicar).
- `FEATURES_IMPLEMENTED` — recovery rehearsal script + queue/transit
  instrumentation (threshold untouched).
- `FEATURES_VERIFIED` — rehearsal report (integrity ok, diff 0),
  5 attribution tests, barrier pending (probe.py touched).
- `DEFERRED_FEATURES` — canonical recovery apply (authorization
  pending), next pilot, resto excluido.
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 pilot post-mortem reconciliation - 2026-10-15 (sobre 51d6095)

- `DECISIONS_REVIEWED` — abort rule timestamp-reject-rate, `_status_view`
  counters, `_is_active_state`, BFF concurrency check, journal/WAL
  readOnly semantics.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Post-mortem piloto
  brief" (cronologia, diagnostico sin tocar umbral, error SQLite exacto,
  congelado de contador, ABORTED terminal).
- `FEATURES_IMPLEMENTED` — congelado de contador terminal + ABORTED
  terminal en readiness (sin otro alcance).
- `FEATURES_VERIFIED` — TerminalCounterTest (fail-before), readiness
  ABORTED test, barrera completa pendiente (control.py tocado),
  evidencia `PILOT_BRIEF_20261015_ABORT.txt`.
- `DEFERRED_FEATURES` — proximo piloto (autorizacion), journal recovery
  (proxima corrida autorizada), resto O2-O5/IA/Kronos (excluidos).
- `BACKLOG_UPDATED` — yes: this entry.
- `DOCUMENTATION_CONFLICTS` — none new.

## O1 defect-fix reconciliation - 2026-10-14 (review/o1-funcional-v2-observacion, sobre 972a19e)

- `DECISIONS_REVIEWED` — 202-chain (BFF 202 + reconcile-before-retry),
  host identity call sites (`pid_is_ours` gates), migration pins v9/v2.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Cierre defectos
  pre-piloto" (202-pending + two-read reconcile; `_run_text` UNKNOWN +
  expected-without-real False; versioned temp fixtures).
- `FEATURES_IMPLEMENTED` — F-LAUNCH-SUP-01 UI safety (no new scope).
- `FEATURES_VERIFIED` — BotControl 8/8, robustness 15/15, directed 143
  OK, barrier 1077 exit 0 (`BARRIER_FIX_*`), frontend 255/255.
- `DEFERRED_FEATURES` — pilot brief-120s (authorization pending); test
  redesign beyond fixtures; any O2-O5/IA/Kronos/redesign (excluded).
- `BACKLOG_UPDATED` — yes: this entry + F-LAUNCH-SUP-01 evidence line.
- `DOCUMENTATION_CONFLICTS` — none new; prior MATRIX/handoff fixes stand.

## O1 pre-pilot reconciliation - 2026-10-14 (review/o1-funcional-v2-observacion, sobre e887287)

- `DECISIONS_REVIEWED` — DASH-V2-62/55/51 supervision chain, R8/R9 funding
  causality, 4f1d92e Start-flag record, 207186d operational inventory,
  27b7af5 read handoff, storage preflight docstring + thresholds.
- `NEW_DECISIONS_RECORDED` — `docs/DECISIONS.md` §"Revision independiente
  pre-piloto" (budgets 4200/8000/65000 + START_TIMEOUT_UNCERTAIN/202 +
  ALREADY_RUNNING pre-check; capability-not-callable; storage
  block-256MB/warn-1GB; own-keys presets; compat 9/10+2/3 correction).
- `FEATURES_IMPLEMENTED` — F-LAUNCH-SUP-01 chain (PARTIAL→pilot-ready,
  no run), F-V2-BFF-01 control/data paths (start/stop/readiness +
  supervision/diagnostics/storage-preflight + 9/10 + 2/3 readers).
- `FEATURES_VERIFIED` — vitest 252/252 (232 base + 20 new), typecheck,
  lint 0 errors (1 pre-existing warning), build 31 routes, backend
  directed 49 OK, barrier 1062 (control green; 11 pre-existing contrasted),
  preview QA 10/10 HTTP 200 + 7 captures + 0 overflow + hashes unchanged.
- `DEFERRED_FEATURES` — pilot brief-120s run (needs explicit authorization);
  any other O2-O5 work; migration-pin test redesign (data-state-dependent,
  out of scope, documented).
- `BACKLOG_UPDATED` — yes: F-LAUNCH-SUP-01 status/evidence (this file).
- `DOCUMENTATION_CONFLICTS` — fixed: MATRIX/handoff "v10/v3 incompatible"
  (was 27b7af5-only), prospective hardcoded schema 9, SCHEMA-9 eyebrow,
  `data/historical.db` path, MATRIX dangling STORAGE_PREFLIGHT_CONTRACT ref.

## DASH-V2-62 reconciliation - 2026-10-11

F-LAUNCH-SUP-01 remains PROPOSED for enablement / PARTIAL overall. The five new implementation findings and two contract notes are corrected in disabled preparation; 29 new tests, 902/902 canonical and 52/52 targeted OK. Report: DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md. Operational readiness, real watcher startup binding, enabled access and longevity remain unverified/deferred. F-P14A-01 historical windows unchanged; no new run or gate advancement. User-authorized direct backend correction replaces the V2-61 handoff for these findings; no need for the other agent to repeat them.

## F-OFFLINE-EVAL-01 — cierre evaluacion offline entradas/salidas V1 (2026-10-16, sin ventana forward, sin simulacion prospectiva)

- `DECISIONS_REVIEWED` — diseno OFFLINE_EVAL_DESIGN_V1 (corte+purga,
  solape, baseline, costes, non-pristine), mapping MAP-CANDIDATE-v1
  (auditoria retrospectiva, H1/H2/H3), contrato de lectura
  OFFLINE_EVAL_READ_CONTRACT_V1, motor v4.2 + runner reutilizados,
  adquisicion FUNDING-CAL-v1, R3 vivo b1f2aaf como alcance previo.
- `NEW_DECISIONS_RECORDED` — DECISIONS (Offline entry/exit closeout V1:
  causalidad por operacion, reconciliacion 1558→1557→1412, funding
  1+1403+8 con "4 ventanas" anulado, exposicion intra-celda, unidades
  USDT/1000 USD con friccion ~1.60, costes supuestos, non-pristine,
  pooled no comparable).
- `FEATURES_IMPLEMENTED` — auditoria reproducible offline (export +
  seleccion + runner re-ejecutados en temp, hashes iguales al artefacto)
  + docs/evidence/OFFLINE_EVAL_AUDIT_V1.json (1412 tripletas
  formation/available/entry) + informe V1 corregido (fuente/admitidas,
  funding, exposicion, unidades) + diseno (alcance intra-celda, pooled no
  comparable) + mapping (puntero a prueba por operacion) + nota de alcance
  en OfflineEvalSection + captura visual 3020.
- `FEATURES_VERIFIED` — backend 1168/1168 OK + barrera exit 0
  (0 prohibidos/bloqueados/efectivos, 1 RO esperado, hashes iguales, sin
  diffs) + frontend 310/310 + typecheck limpio + replays 452+457+503=1412
  con input_hash identicos + causalidad 1412/1412 sin violaciones +
  sensibilidad 12/12 celdas negativas a 2x + QA visual 3020
  (overview + historical-research con seccion, 0 errores consola).
- `DEFERRED_FEATURES` — ventana forward pristina (no adquirida),
  simulacion prospectiva (no iniciada), mapping aprobado, costes medidos,
  modelo de posicion/exposicion, baselines alternativos
  (buy-and-hold/placebo/aleatorio), paper/ejecucion.
- `BACKLOG_UPDATED` — yes: this entry (ID F-OFFLINE-EVAL-01).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: ETH 497 (admitidas) vs 498
  (fuente), SOL H2 7→6, friccion ~1.0→~1.60/op, "4 ventanas"→1 sostenida,
  pooled-como-cartera (nunca fue cartera), build servido 3020 identificado
  en CURRENT_STATE (sin redeploy en este cierre).

## F-OFFLINE-EVAL-02 — artefacto publicado + generacion determinista (2026-10-16, sin corridas)

- `DECISIONS_REVIEWED` — F-OFFLINE-EVAL-01, contrato de lectura
  OFFLINE_EVAL_READ_CONTRACT_V1, informe §10, adquisicion FUNDING-CAL-v1.
- `NEW_DECISIONS_RECORDED` — DECISIONS (Fix artefacto offline-eval:
  force-add + agregador byte-identico + hashes funding reconciliados +
  limitacion dataset declarada).
- `FEATURES_IMPLEMENTED` — `scripts/aggregate_offline_eval.py`
  (bundling fail-closed) + `tests/test_offline_eval_aggregation.py`
  (6 tests) + artefacto publicado por force-add (pin c051e888… intacto)
  + informe §10 y contrato actualizados + hashes funding reconciliados.
- `FEATURES_VERIFIED` — regeneracion byte-identica del artefacto desde
  replays en temp (mismo sha) + celdas↔manifiestos identicas + nuevo test
  6/6 + checkout limpio (frontend tests + typecheck + build, sin
  data/logs/canonicos; logs abajo).
- `DEFERRED_FEATURES` — mismos que F-OFFLINE-EVAL-01; publicacion del
  historico canonico (no publicado; limitacion declarada).
- `BACKLOG_UPDATED` — yes: this entry (ID F-OFFLINE-EVAL-02).
- `DOCUMENTATION_CONFLICTS` — corregidos aqui: artefacto ausente en Git
  (404 en limpio), ruta de test en contrato (`src/`→`frontend/src/`),
  hashes funding del draft (transitorios → provenance verificables).

## F-OFFLINE-EVAL-03 - paquete reproducible + causalidad + costes + protocolo (2026-10-17, sin corridas, sin push aun)

- DECISIONS_REVIEWED - paquete/artefacto V1, mapping MAP-CANDIDATE-v1, motor v4.2 + runner, contratos offline-eval, funding/calendarios, P1-11C Carteras, backlog F-OFFLINE-EVAL-02.
- NEW_DECISIONS_RECORDED - DECISIONS parrafo 2026-10-17 (paquete/causalidad/costes/protocolo/V2); docs OFFLINE_EVAL_PACKAGE_V1 (manifiesto), OFFLINE_EVAL_CAUSAL_AUDIT_V2 (matriz), OFFLINE_EVAL_COST_BREAKEVEN_V1 (breakeven+exposicion), PROSPECTIVE_PROTOCOL_V1 (preparacion, no ejecutado).
- FEATURES_IMPLEMENTED - paquete temp + zip + event_ids 1:1 + scripts/reproduce_offline_eval.py; 4 docs; V2 OfflineEvalSection (3 bloques lectura); tests breakeven 7 + causalidad 3.
- FEATURES_VERIFIED - replay byte-identico (c051e888) + input_hash x3 + invariancia 18/18 + s*/fragilidad 2x + frontend offline-eval + typecheck; build + QA visual 3020 pendientes al cierre.
- DEFERRED_FEATURES - publicacion DB canonica/zip (fuera de Git; reproduccion externa PENDIENTE); MAP-APPROVED-v1; disponibilidad live; ventana pristina; costes medidos; TIME-PLACEBO-v1; paper/ejecucion; gates.
- BACKLOG_UPDATED - yes: this entry (ID F-OFFLINE-EVAL-03).
- DOCUMENTATION_CONFLICTS - none new (agregacion != replay distinguido; pooled no cartera reiterado; H3 nunca recuperacion).

## F-EXTREME-OBJECTIVE-01 — Objetivo de movimientos extremos preservado (2026-10-16)
Objetivo de producto: REAFIRMADO POR USUARIO. Plan tecnico: DOCUMENTADO,
PENDIENTE DE AUDITORIA/IMPLEMENTACION por componentes. No feature completa.
Fuente: PRODUCT_GOAL + MASTER_PLAN + EXTREME_MOVERS_OBJECTIVE.md.
Aceptacion: selector causal bilateral, denominadores y cobertura fuera del
trio, enlace evidencia-decision-posicion, costes/exposicion y V2 trazable.
No aprobar mapping ni umbrales por registrar este ID. Reutilizar discovery,
classifier, opportunity, motor/runner y contratos existentes.
DECISIONS_REVIEWED: AGENTS, estado/cola/master/decisions/gates/workflow/backlog,
PRODUCT_GOAL y SIGNAL_RESEARCH_PLAN en base b748d22.
NEW_DECISIONS_RECORDED: alcance de producto preservado; no metodologia nueva.
FEATURES_IMPLEMENTED: documentacion y enlaces, ningun codigo de producto.
FEATURES_VERIFIED: contraste documental; sin pruebas de estrategia nuevas.
DEFERRED_FEATURES: delta selector, cobertura, V2 Backtest/Paper, validacion,
ejecucion segun fases/autorizaciones. IA/Kronos siguen diferidos.
BACKLOG_UPDATED: este ID, sin promover implementacion ni gates.
DOCUMENTATION_CONFLICTS: estados historicos desactualizados preservados;
map H2 mecanico no es fade/rebote validado; funding 8h del plan Paper antiguo
debe reconciliarse al implementar, usando calendario por simbolo.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872; implementacion parcial, secuencia conservada.)

## F-STRUCTURE-EXIT-01 — Estructura historica y gestion dinamica (2026-10-16)
Objetivo documentado por solicitud del usuario; implementacion NO declarada.
Spec: HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md. Depende de auditoria causal/costes,
datos multihorizonte y gestion/riesgo segun fases. No parametros aprobados.
DECISIONS_REVIEWED: instrucciones/planes/gates/workflow y documentos de mercado,
posicion y objetivo previamente auditados en esta rama documental.
NEW_DECISIONS_RECORDED: contexto por zonas y retencion compacta; sin regla trading.
FEATURES_IMPLEMENTED: plan y enlaces documentales solamente.
FEATURES_VERIFIED: contraste con MARKET_DATA y POSITION_MANAGEMENT; sin codigo.
DEFERRED_FEATURES: ingestion/cache/pivotes/ajustes/UI/paper segun auditoria y gates.
BACKLOG_UPDATED: este ID; no cambia fase activa ni autorizaciones.
DOCUMENTATION_CONFLICTS: fuentes historicas y paper funding 8h requieren
reconciliacion al implementar; no extrapolar cobertura local a vida del token.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872; diseno, no garantia.)

## F-EVAL-CENSUS-TRACE-01 — Auditoría trazabilidad EVAL-CENSUS-V2 (2026-10-17)
Addendum sobre commit b5cd690 (1385927 = prefijo SHA del commit EVAL-CENSUS-V2, no run_id).
FEATURES_IMPLEMENTED: ledger de flujo reconstruido desde manifiestos ejecutados + artefacto publicado;
verificador reproducible (20 regresiones, todas pasan); corrección 12/12 vs 18/18; funding separado
(741 aplicaciones vs 270 liquidaciones únicas; 0 unknown-excluded ≠ cobertura completa; 24/60 uncovered);
MF/MAE documentadas como excursión no captura; duplicados 594/616 mecanismo verificado (subset BTC15m: 129/135).
FEATURES_VERIFIED: totales y conteos separados (hipótesis 7152/2991/5/4161; placebo 7152/2264/2/4888; total 14304/5255/7/9049) contra manifiestos y artefacto.
DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git para trazabilidad completa (vínculo detección→operación UNKNOWN); verificación exacta de 594/616 sobre censo completo (reconstruct lento, timeout).
DOCUMENTATION_CONFLICTS: "18/18" del mensaje de commit corregido a "12/12 direccionales"; "0 unknown-excluded" no presentado como cobertura completa.
BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.

## F-EVAL-CENSUS-TRACE-01-CORR — Corrección de F-EVAL-CENSUS-TRACE-01 (2026-10-17)
Corrige el entry anterior de esta misma fecha (líneas 1219-1228) de forma explícita:

FEATURES_IMPLEMENTED: verificador con 30 tests unittest (no "20 regresiones"), todos pasan (0 fallos, 0 errores); ledger portable con SHA256 de cada input y rutas repo-relative (sin rutas absolutas de usuario); tests de mutación que detectan duplicado semántico, entrada antes de disponibilidad, referencia inexistente, familia/segmento ausente, motivo ausente, funding ausente, manifiesto alterado, input alterado vs hash, población MFE incorrecta, control positivo.
FEATURES_VERIFIED: 594 grupos/616 filas verificados EN CONJUNTO COMPLETO (9320 detecciones): 15m trio 371/383, 1h trio 45/47, MINAUSDT 1h 90/92, NMR+ORCA 1h 88/94. Total 594/616 ← coincide exactamente con artefacto. 1779 fuera de alcance del builder verificados por membresía (MINAUSDT 626 + NMR/ORCA 1153 = 1779). Conteos separados hipotésis/placebo verificados contra manifiestos y artefacto.
DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git (vínculo detección→operación sigue UNKNOWN). Ninguna verificación pendiente de 594/616 (ya completada).
DOCUMENTATION_CONFLICTS: "20 regresiones" corregido a "30 tests, todos pasan"; "594/616 solo en BTC15m" corregido a "verificado en conjunto completo"; "1779 por resta" corregido a "1779 por membresía (MINAUSDT 626 + NMR/ORCA 1153)".
BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.




## F-EVAL-CENSUS-TRACE-01-CORR2 — Corrección con evidencia verificable (2026-10-18)
Corrige F-EVAL-CENSUS-TRACE-01-CORR (2026-10-17) de forma explícita:

FEATURES_IMPLEMENTED: verificador con funciones puras (verificar_causalidad_*, verificar_censo_duplicados, clasificar_duplicados_semanticos, origenes_de_evento, vincular_eventos_h1h3, verificar_referencias, verificar_motivos_descarte, verificar_funding_celda, rango_mfe_mae) ejercitadas por 45 tests unittest con fixtures y datos reales; meta-prueba de mutación verificada (los tests fallan cuando el verificador es alterado); generador con estatus INCOMPLETE + exit!=0 cuando faltan inputs; tests de integración del ledger.
FEATURES_VERIFIED: causalidad real 9314 OK / 6 UNKNOWN / 0 violaciones (detections.jsonl del reconstruct); vínculo H1/H3 0 sin respaldo / 0 excedentes; duplicados events.json 0 errores (clasificados: H1 2 detecciones, H2 confirmación misma barra, placebo colisión rng); 594/616 con desglose exacto; 1779 por membresía; referencias consistentes (60 vs 56 celdas, rebound sin eventos esperado); funding 741/0/24-60 por celda; MFE/MAE rangos global y n>=30 calculados.
DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git (vínculo detección→operación completo sigue UNKNOWN fuera de temp).
DOCUMENTATION_CONFLICTS: "30 tests" corregido a "45 tests"; "causalidad UNKNOWN" corregido a "verificada 9314/6/0"; "duplicados reportados" corregido a "clasificados con origen, 0 errores".
BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.

## F-EVAL-CENSUS-TRACE-01-CORR3 — Veredicto global, trazabilidad a operación y paquete de evidencia (2026-10-18)
Corrige F-EVAL-CENSUS-TRACE-01-CORR2 (2026-10-18) de forma explícita:

FEATURES_IMPLEMENTED: veredicto global PASS/FAIL/INCOMPLETE integrado en el ledger; trazabilidad hasta la operación real mediante replay determinista (scripts/reconstruct_replay_traces.py) con equivalencia por celda (conteos, exit_reasons, config_hash, mfe/mae, expectativas, total_net, fees, funding, max_drawdown); 5255 trades escala 1.0 reconciliados exactamente (5248 realizadas + 7 abiertas); paquete de evidencia publicado (docs/evidence/eval-census-v2-package/, 33 archivos, package_manifest.json con SHA256); pruebas CLI de integración (10 casos de alteración + control íntegro); campos económicos comparados con tolerancia explícita (rtol=1e-9, 60 celdas, 0 discrepancias); tail-edge: 4/6 exclusiones esperadas verificadas, MINAUSDT/1h y NMRUSDT/1h conservados como INCOMPLETE.
FEATURES_VERIFIED: 58 tests unittest (0 fallos): 45 funciones puras + 3 PackageMode + 10 CLI fixtures; meta-prueba de mutación verificada; causalidad 9314 OK / 6 UNKNOWN / 0 violaciones; duplicados events.json 0 errores clasificados con origen; 594/616 con desglose exacto; referencias consistentes; veredicto global actual: INCOMPLETE (0 discrepancias, 2 incompletos MINA/NMR).
DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git para cerrar el vínculo completo detección→operación y verificar los 2 tail-edge pendientes (MINAUSDT/1h, NMRUSDT/1h).
DOCUMENTATION_CONFLICTS: "45 tests" corregido a "58 tests"; "causalidad UNKNOWN" corregido a "verificada 9314/6/0"; "auditoría completa" corregido a "INCOMPLETE con 2 incompletos declarados".
BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.


## F-EVAL-CENSUS-TRACE-01-CORR4 — Corrección de defectos restantes de la auditoría (2026-10-19, sobre 2677b2f)
Corrige F-EVAL-CENSUS-TRACE-01-CORR3 de forma explícita: defectos restantes de la auditoría sin corridas Binance, sin forward/paper/órdenes, sin cambios de estrategia/mapping/costes/umbrales y sin tocar DBs canónicas, dashboard ni servicios.

FEATURES_IMPLEMENTED:
- vincular_trades_eventos: campos temporales obligatorios (entry_ms finita, available_at finita, H2 close_time_ms finita, estado realizada/abierta); ausencia o valor inválido → INCOMPLETE (nunca aceptación implícita); entrada antes de disponibilidad → FAIL; respaldo por símbolo/resolución/familia/dirección/identidad sin cruzar resoluciones.
- reconstruct_replay_traces.py fail-closed: celda fallida no publica trazas como "verificada"; trazas fallidas van a diagnostico_celdas_fallidas.json (FALLIDA_NO_CONSUMIBLE, rechazado por el ledger); manifiesto con veredicto/cobertura/hashes validado por el ledger antes de consumir; no quedan archivos antiguos de ejecuciones previas; exactamente uno de --package/--temp-dir obligatorio; --package sin segunda purga; events_pre (n_in_pre_purge) documentado en modo temp.
- Ledger valida manifiesto de trazas (veredicto COMPLETO, cobertura 6 combos, trades_sha256, sin faltantes/extra/obsoletos, consumible) antes de consumir; rechaza manifiesto FAIL, hash mismatch, faltante, extra o no consumible.
- Pruebas de integración obligatorias (reconstructor → archivos → ledger): 17 casos + control; cada defecto FAIL/INCOMPLETE exit ≠ 0; control PASS exit 0 (tests/test_cli_fixtures.py y tests/test_reconstruct_replay_traces.py).
- Checkout limpio verificado: hashes paquete 33/33 OK; trades regeneradas (exit 0, COMPLETO, 168 celdas, 5255 trades); ledger (exit 1, INCOMPLETE, 0 discrepancias, trazabilidad COMPLETO, n_trades_revisados=5255). Evidencia: C:\proyectos\binance-temp\audit_checkout_20261019\verificacion_checkout.txt.

FEATURES_VERIFIED: suite completa 1274 tests OK (2 skipped); barrera de aislamiento hashes_equal=True, file_writes=0, datos sin cambios.

DEFERRED_FEATURES: incorporar manifiestos temp/opencode a Git y/o publicar build_report de MINAUSDT/1h y NMRUSDT/1h para cerrar los 2 tail-edge pendientes y pasar el veredicto global a PASS.

DOCUMENTATION_CONFLICTS: "ninguna traza fallida se publica" corregido: el código anterior SÍ escribía "equivalencia": "verificada" con trades de celdas falladas; el contrato fail-closed ahora lo impide y el ledger rechaza las trazas fallidas. Se distingue publicación (paquete), reproducción (regenerar trades desde paquete) y aceptación (veredicto PASS del ledger).

VEREDICTOS SEPARADOS (no rebajados):
- Replay BTC/ETH/SOL: PASS dentro de alcance explícito (6 celdas-combo, 168 celdas, equivalencia por celda, 5255 trades escala 1x reconciliadas, trazabilidad COMPLETO, 0 discrepancias).
- Censo extendido MINA/NMR: INCOMPLETE (tail-edge MINAUSDT/1h y NMRUSDT/1h no verificable: falta build_report).
- Global del ledger: INCOMPLETE (0 discrepancias, 2 incompletos declarados), exit 1.

RESIDUAL MINA/NMR (preciso): falta build_report.json que cubra MINAUSDT/1h y NMRUSDT/1h (interval 1h, counts.excluded_no_entry == 1 cada uno). Las detecciones ya están en census_1h_detections.jsonl del paquete; lo que falta es el build_report que las ampare para clasificar_tail_edge (excluded_no_entry == n_tail_edge = 1). Impacto: global INCOMPLETE, no PASS; replay BTC/ETH/SOL reportado por separado como PASS.

BACKLOG_UPDATED: este ID; sin cambio de fase activa ni autorizaciones. Gates sin avance.


## F-CHART-BINANCE-04 — Segunda ventana real (2026-10-24 14:04Z, base `2f2f9ea`): FAIL de aceptación

**1. Title:** Ejecutar una sola ventana acotada por el camino real
(`Binance → hub → servicio SSE → BFF → /market-lab`) con el parche de medición
de liberación/reconexión y evidencia DOM explícita.

**2. Approval status:** DECIDED y ejecutado una vez el 2026-10-24 con
autorización explícita del operador; sin repetición, sin ampliación de límites,
sin monitor/paper/órdenes/móvil.

**3. Implementation status:** IMPLEMENTED — orquestador
`scripts/market_stream_window.py` con `--release-browser`,
`--release-timeout` y `--reconnect-timeout` (medición; sin cambios de producto),
`--finalize` con evidencia DOM y checks puros; `scripts/market_stream_service.py`
y el explorador existentes. No implementado: automatización del lado navegador
(capturas/desconexión/reconexión), repetición automática, indicadores, paper
prospectivo.

**4. Evaluation status:** **EJECUTADO UNA VEZ CON BINANCE REAL — veredicto
`FAIL` (exit 1), `acquired=true`.** Ventana `14:04:37.065Z`–`14:05:43.957Z`
(66,89 s de 180 s): 1 intento de socket, 0 reconexiones, 58 mensajes / 58
aplicados / 2 cierres, 46 eventos `BTCUSDT` + 12 `MINAUSDT`, 38 actualizaciones
provisionales de la misma apertura, cierre `1792850640000` y siguiente vela
`1792850700000`, BFF con 46 eventos e identidad `BTCUSDT/1m`, 0 huecos, pico de
consumidores 3, parada limpia (exit 0, puerto cerrado, PID file eliminado,
`/health` rechazado), DBs canónicas intactas y 2 peticiones REST públicas de
velas (inicial de 299 + paginación de 300; catálogo desde caché, sin
`exchangeInfo`). Fallan `consumers_released` (la desconexión del navegador no se
ejecutó en los 20 s), `browser_reconnected` (sin liberación previa),
`dom_state_live` y `dom_update_fresh` (captura #2 `OBSOLETO`/`no LIVE`, 35 s
después de la parada), `dom_pagination_preserved` (error de frescura) y
`dom_after_stop` (sin aviso); falta `dom_candles_grew` (la captura #1 llegó ~2 s
después del cierre). `visual_review=NOT_REVIEWED`. Evidencia:
`docs/evidence/market-stream-window-2026-10-24.json` + `.-dom-1.json`,
`.-dom-2.json`, `.-dom-stop.json`.

**5. Limitaciones:** la ventana no ejecutó la secuencia de liberación/reconexión
(el operador quedó bloqueado en la paginación); la paginación superó el `hold`
de 20 s; la captura #1 no precede al cierre por adjuntar la página cerca del
borde de minuto; el aviso de servicio detenido no apareció con el SSE del BFF
abierto; una ventana de minutos no generaliza al universo ni a otros intervalos.

**6. Evidence:** `docs/evidence/market-stream-window-2026-10-24.json`;
`docs/evidence/market-stream-window-2026-10-24-dom-1.json`;
`docs/evidence/market-stream-window-2026-10-24-dom-2.json`;
`docs/evidence/market-stream-window-2026-10-24-dom-stop.json`;
`scripts/market_stream_window.py`; `tests/test_market_stream_window.py`;
`docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` (§13); `docs/CURRENT_STATE.md`;
`docs/TASK_QUEUE.md`; `docs/DECISIONS.md` (2026-10-24).

**7. Last update:** 2026-10-24.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE,
  DECISIONS (2026-10-22/23/24), `MARKET_STREAM_LIVE_WINDOW_PLAN` §13,
  `SAFETY_RULES`, `DESKTOP_FIRST_SCOPE_20261020` y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-24: parche de medición
  autorizado (release/reconnect) y `browser_reconnected` exige liberación
  previa; la ventana se ejecutó una vez y su veredicto `FAIL` no se rebaja.
- `FEATURES_IMPLEMENTED` — orquestador con liberación/reconexión y finalize;
  evidencia DOM; sin cambios de producto.
- `FEATURES_VERIFIED` — cadena real Binance → hub → SSE → BFF → DOM con
  `LIVE` e identidad exacta, cierre y siguiente vela, 46 eventos en el BFF,
  3 consumidores, parada limpia y DBs intactas; pruebas 25/25 del orquestador.
- `DEFERRED_FEATURES` — automatización del lado navegador; aviso de servicio
  detenido; repetición de la ventana (solo con autorización); revisión visual;
  retención del caché; indicadores; paper con datos vivos; móvil/Flutter; REA;
  `/antislop` end-to-end.
- `BACKLOG_UPDATED` — yes: este bloque, `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS`, `MARKET_STREAM_LIVE_WINDOW_PLAN` §13.
- `DOCUMENTATION_CONFLICTS` — el plan asumía que la paginación cabría en el
  `hold` de 20 s y que el aviso de servicio detenido aparecería al parar; la
  ejecución real mostró lo contrario. El `browser_reconnected=True` inicial se
  corrigió a `False` porque no hubo liberación previa; el veredicto sigue `FAIL`.
  La cadena real se acredita; la aceptación end-to-end no.

## Aceptación local automatizada (2026-10-24, base `6be44b9`, sin ventana Binance)

**1. Feature / decision ID:** F-STREAM-LOCAL-ACCEPTANCE-01 (arnés local
automatizado) y F-STREAM-DOWN-NOTICE-02 (aviso de servicio detenido con causa).

**2. Approval status:** aprobado por el alcance vigente (sin ventana real; sin
cambios económicos). La ventana real sigue requiriendo autorización explícita.

**3. Implementation status:** implementado. `scripts/market_stream_local_acceptance.py`;
`--post-reconnect-signal` y `--dashboard-url` en `scripts/market_stream_window.py`;
consulta de estado en `frontend/src/lib/use-market-stream.ts`; detalle real en
`ContractExplorer`; regresión del hook.

**4. Verification status:** verificado con dos recorridos consecutivos `PASS`
(`docs/evidence/local-acceptance-2026-10-24/`), cero intentos públicos, cero
consumidores residuales, parada limpia, finalizer `PASS`, aviso con causa real,
histórico conservado y sin recarga. Pruebas: backend 71/71, frontend focalizado
23/23, `tsc` 0, `eslint` 0 errores.

**5. Deferred:** ventana Binance real (solo con autorización); actualización
Next.js 16.4.1 (worktree separado); revisión visual humana; retención de caché;
indicadores; paper con datos vivos; móvil/Flutter; REA; `/antislop` end-to-end.

**6. Evidence / references:** `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` §14;
`docs/CURRENT_STATE.md` (2026-10-24); `docs/TASK_QUEUE.md` (2026-10-24);
`docs/DECISIONS.md` (2026-10-24); `docs/evidence/local-acceptance-2026-10-24/`.

**7. Last update:** 2026-10-24.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — AGENTS, WORKFLOW, CURRENT_STATE, TASK_QUEUE,
  DECISIONS (2026-10-24), `MARKET_STREAM_LIVE_WINDOW_PLAN` §14, `SAFETY_RULES`,
  `DESKTOP_FIRST_SCOPE_20261020` y este backlog.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-24: aceptación local
  automatizada con transporte loopback y aislamiento real; el aviso de servicio
  detenido se declara al consultar el estado (el 503 del BFF es fatal para
  `EventSource`); `--post-reconnect-signal` coordina la captura DOM con la
  parada; el PASS local **no** acredita Binance.
- `FEATURES_IMPLEMENTED` — arnés local; señal post-reconexión; consulta de
  estado del hook; detalle de causa en el aviso; regresión del hook.
- `FEATURES_VERIFIED` — dos recorridos consecutivos `PASS` procedural;
  `298 -> 599` con 1 petición; `consumers=0 -> 1` con actualización posterior;
  aviso `TypeError: ECONNREFUSED`; 599 velas conservadas; `nav=1`, `reload=0`;
  cero peticiones públicas; DBs canónicas intactas.
- `DEFERRED_FEATURES` — ventana real (autorización); Next.js 16.4.1; revisión
  visual; retención de caché; indicadores; paper con datos vivos; móvil;
  REA; `/antislop`.
- `BACKLOG_UPDATED` — yes: este bloque, `MARKET_STREAM_LIVE_WINDOW_PLAN` §14,
  `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`.
- `DOCUMENTATION_CONFLICTS` — el `orchestrator_exit=2` es el `UNKNOWN` previo
  al `--finalize` (el veredicto final es `PASS`); el check `transport_origin`
  queda `ok=false` con `required=false` por el transporte loopback, por lo que
  el PASS local no es una acreditación Binance. El dashboard se restauró al
  entorno canónico (catálogo 931, no las 2 entradas de prueba).

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

**Sincronización de reloj:** la actualización de vista se centraliza tras
cada respuesta autoritativa (`applyAuthoritative`). Si `clock_ms` cambia —
incluido `Entrar` (avanza T) — indicadores y contexto se corresponden con
ese T: se descarta el contexto anterior y se recarga para el nuevo T con la
identidad autoritativa de la sesión. Mientras se actualizan, no se muestran
valores previos como actuales (contexto suspendido hasta que se recarga).
Probado: entrada, paso, salida, reinicio y recuperación.

**Mecánica conservada:** recuperación real (header siempre renderizado; vista
reconstruida desde estado autoritativo del backend); regla de ingeniería
ENGINEERING-MINA-1M-v1 (entry_px fijado antes de evaluar; dos prefijos A/B);
UNKNOWN del flujo sin cobertura (no se inventan valores); política de parada
(sin inventar cierre); 0 peticiones Binance; cadena dashboard → BFF → Python
→ dashboard.

**Pruebas:** npx tsc --noEmit 0; npx eslint 0 (archivos nuevos);
npx vitest run src/test/paper-lab-live-api.test.ts 9/9;
npx vitest run src/test/session-lab.test.ts 4/4;
npx vitest run src/test/engineering-session.test.tsx 5/5;

python run_tests.py -q 1290 OK / 2 skipped; next build OK.
BUILD_ID servido: yeIE931T35_a8l_k-WiqW (SHA fuente del árbol 933606b841afc3c705acd1a3a04593b2e8c02fb5, frontend del commit
933606b más los cambios de esta sesión).

**Límites pendientes:** conexión a Binance público (ventana aparte,
autorización explícita); selector automático de varios símbolos; monitor en
vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; indicadores
provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos
continuos.

**6. Evidence:** frontend/src/components/session-lab/EngineeringSession.tsx
+ SessionStatusPanels.tsx + EngineeringSession.module.css;
frontend/src/lib/session-lab.ts;
frontend/src/app/api/v1/market-series/route.ts;
frontend/src/app/market-lab/page.tsx;
frontend/src/test/session-lab.test.ts;
frontend/src/test/engineering-session.test.tsx;
docs/evidence/engineering-session-browser-evidence.html;
src/microstructure_probe/paper_lab_engine.py; scripts/paper_lab_session.py; BFF frontend/src/app/api/v1/paper-lab/sessions/*.

**7. Last update:** 2026-10-27.
### Cierre (siete campos, obligatorios)

- DECISIONS_REVIEWED — docs/DECISIONS.md (sesión de ingeniería — transporte local, refinamiento 2026-10-27), docs/CURRENT_STATE.md, docs/TASK_QUEUE.md, docs/DESKTOP_FIRST_SCOPE_20261020.md.
- NEW_DECISIONS_RECORDED — DECISIONS 2026-10-27: alcance de --no-fetch (read_only=1, ingeniería cero upstream; explorador normal conserva adquisición bajo demanda); recuperación por identidad autoritativa (config.symbol/config.interval, no defaults del componente); sincronización de reloj T centralizada (applyAuthoritative; entrada/paso/salida/reinicio/recuperación; sin valores previos como actuales).
- FEATURES_IMPLEMENTED — control iniciar/detener sesión; alcance de --no-fetch vía read_only=1; seis paneles; vista de operación completa; compartición de session_id/símbolo/tiempos/config_hash; regla de ingeniería versionada; dos prefijos de demostración.
- FEATURES_VERIFIED — backend: crear→evaluar→step→cerrada por horizonte vía HTTP; frontend: tsc/eslint 0, vitest session-lab 4/4 + engineering-session 5/5 + paper-lab-live-api 9/9; E2E navegador: iniciar→evaluar→entrar→gestión→recarga abierta; dos prefijos HTTP (A admite, B se abstiene); fuente solo lectura 0 upstream; reloj T sin futuros.
- DEFERRED_FEATURES — conexión a Binance público; selector automático; monitor en vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; indicadores provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos continuos.
- BACKLOG_UPDATED — yes: esta sección + CURRENT_STATE, DECISIONS, FEATURE_BACKLOG.
- DOCUMENTATION_CONFLICTS — ninguna contradictoria; se aclara que "sesión de ingeniería/replay sobre caché" ≠ "sistema completo autónomo" y que "fuente LOCAL SIMULADA" ≠ Binance LIVE; el backend es la autoridad de decisión y estado económico.

## Sesión de ingeniería — modo autónomo (2026-10-27, base `9a24308`, rama `feat/ingenieria-autonoma`)

**1. Title:** Modo autónomo de la sesión de ingeniería (`/market-lab`): con un solo "Iniciar sesion" el backend avanza la sesión de forma incremental (datos → cálculos → regla → entrada pendiente → fill simulado → gestión → cierre) sin pulsar "Entrar" ni "Paso a paso"; el navegador solo observa y solicita iniciar/detener.

**2. Approval status:** DECIDED dentro del alcance autorizado (desktop; transporte local incremental simulado sobre caché; sin conexión pública Binance; sin monitor, paper prospectivo, órdenes ni pagos; sin estrategia nueva; regla `ENGINEERING-MINA-1M-v1` hipótesis no validada, sin rentabilidad).

**3. Implementation status:** IMPLEMENTED. Bucle autónomo en el frontend (`EngineeringSession.tsx`) reutilizando el endpoint existente `POST /api/v1/paper-lab/sessions/[id]/step` (un proceso Python por acción vía `spawnSync`; sin gestor, motor ni servidor paralelo). Arranque automático solo tras evaluación con `en_espera`/`abierta`; abstenciones (`SIN_ENTRADA`/`DESCARTADO`/`sin_iniciar`) nunca abren el bucle; fin de transporte (sin avance de reloj en `en_espera`/`sin_iniciar`) detiene el bucle con causa visible (`session-transport-cause`) y política `open_at_end` sin cierre inventado; "Detener sesion" libera primero el temporizador propio del navegador; "Entrar"/"Paso a paso" deshabilitados durante la autonomía; recarga recupera estado sin re-enganchar autonomía ni duplicar efectos. Corrección adyacente: `changePrefix` ahora fija la elección de prefijo antes de iniciar (preexistente: la ignoraba sin sesión, contradiciendo la instrucción de la propia página).

**4. Evaluation status:** `npx tsc --noEmit` 0; `npx eslint` 0 (componente + test); `npx vitest run src/test/engineering-session.test.tsx` 8/8 (5 previas + 3 autónomas: A entrada+cierre automáticos con botones deshabilitados, B `sin_iniciar` sin autonomía ni pasos, C fin de transporte con causa visible y sin `exitSessionApi`); suite frontend completa 596 passed / 1 skipped. E2E navegador real sobre `http://127.0.0.1:3020/market-lab` (build `next`, red pública no utilizada; `read_only=1` → `--no-fetch`, 0 upstream): A un Iniciar → ABIERTA (fill) → CERRADA por horizonte (`exit_px=0.06302`, `realized_net=3.98`, `exit_executed=true`, `open_at_end=false`); B sesión HTTP con stop ya vulnerado en T → DESCARTADO sin posición; recuperada en navegador sin chip ni pasos; C HTTP: pasos sin avance de reloj (cursor/clock invariantes), sin entrada nueva; D recarga con ABIERTA → mismo session_id/config_hash, un único evento de entrada, cierre completado manualmente tras recarga; E "Detener sesion" con posición abierta → `detenida`, posición congelada (`result=null`, sin evento de salida), paso posterior no-op. Suite Python completa: 1476 tests, 2 fallos PREEXISTENTES en HEAD (no causados por este bloque; motor/rutas sin tocar): `test_paper_lab_engine.py::test_public_dict_vela_solo_open_sin_ohlc`, `test_market_stream_window.py` (FAIL≠UNKNOWN); 2 skipped.

**5. Limitaciones:** no conecta a Binance público (ventana aparte, autorización explícita); un solo token candidato; la autonomía es un conductor del frontend que programa pasos (el reloj solo avanza cuando el backend responde; no hay proceso backend periódico); prefijo B no garantiza abstención con la caché actual (abstención demostrada vía HTTP); tope de 200 pasos por arranque de autonomía; sin rentabilidad probada.

**6. Evidence:** `frontend/src/components/session-lab/EngineeringSession.tsx`; `frontend/src/test/engineering-session.test.tsx`; `frontend/src/app/api/v1/paper-lab/sessions/[session_id]/step/route.ts`; `src/microstructure_probe/paper_lab_engine.py` (sin cambios); `scripts/paper_lab_session.py` (sin cambios); capturas `docs/evidence/INGENIERIA_AUTONOMA_A_ABIERTA.png`, `INGENIERIA_AUTONOMA_B_ABSTENCION.png`, `INGENIERIA_AUTONOMA_E_DETENIDA.png`; sesiones de evidencia en `paper-lab-sessions/` (`PL-MINAUSDT-LONG-1793140455322-00b0c1d8` A cerrada; `PL-MINAUSDT-LONG-1793140611158-38daa21c` E detenida con posición abierta; `PL-MINAUSDT-LONG-1793141041362-ed3a8dcb` B DESCARTADO; `PL-MINAUSDT-LONG-1793141138821-d5ee9168` C detenida).

**7. Last update:** 2026-10-27.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — `docs/DECISIONS.md` (modo autónomo 2026-10-27), `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md` (desktop only; sin trabajo móvil).
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-27: autonomía como conductor del frontend reutilizando `/step` (spawnSync por paso, 1500 ms, tope 200); arranque solo con `en_espera`/`abierta`; abstención sin autonomía; fin de transporte con causa visible y `open_at_end` sin cierre inventado; parada libera solo recursos propios del navegador; corrección de selección de prefijo antes de iniciar.
- `FEATURES_IMPLEMENTED` — bucle autónomo (chip visible, causa de transporte, botones manuales gated, limpieza al desmontar, referencias anti-closure); selección de prefijo aplicable antes de iniciar.
- `FEATURES_VERIFIED` — unidad 8/8 (incluidas A/B/C autónomas); suite frontend 596/1 skip; tsc/eslint 0; E2E navegador A/B/D/E + C vía HTTP; 0 upstream (`read_only=1` → `--no-fetch`).
- `DEFERRED_FEATURES` — conexión a Binance público; selector automático de símbolos; monitor en vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; IA; indicadores provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos continuos; autonomía con proceso backend propio (no requerido).
- `BACKLOG_UPDATED` — yes: esta sección + `CURRENT_STATE`, `TASK_QUEUE`, `DECISIONS`.
- `DOCUMENTATION_CONFLICTS` — ninguna contradictoria; se aclara que el prefijo B no garantiza abstención con la caché actual (se corrige la expectativa previa de "B se abstiene" como no-verificada con datos reales; abstención real = stop ya vulnerado/evidencia insuficiente vía HTTP) y que la autonomía no implica un proceso backend periódico.

## Sesión de ingeniería — autonomía en backend (2026-10-27/28, base `0aa98f5`, rama `feat/ingenieria-autonoma`)

**1. Title:** Conducción de la sesión de ingeniería movida a un servicio
backend Python residente (`engineering-session-service/v1`, puerto 8797
por defecto, reutiliza `paper_lab_engine`; sin motor ni gestor paralelo):
el navegador es SOLO observador, cerrar la pestaña NO detiene la sesión y
reabrir recupera el estado correcto; avance SOLO por eventos REVEAL del
transporte local con cadencia.

**2. Approval status:** DECIDED dentro del alcance autorizado (desktop;
transporte local incremental simulado sobre caché; 0 Binance público, 0
upstream, 0 órdenes; sin monitor ni paper prospectivo; sin estrategia
nueva; regla `ENGINEERING-MINA-1M-v1` hipótesis no validada, sin
rentabilidad).

**3. Implementation status:** IMPLEMENTED. Servicio
`src/microstructure_probe/engineering_session_service.py` + CLI
`scripts/engineering_session_service.py` (start/stop, `--pid-file`,
`POST /shutdown`; servidor de biblioteca estándar con ruido de apagado
silenciado). BFF `frontend/src/app/api/v1/engineering-sessions/**` (env
`ENGINEERING_SERVICE_URL`, guardia de origen) + cliente
`frontend/src/lib/session-lab.ts` (`createBackendSession`,
`fetchBackendSession`, `controlBackendSession`; formas uniformes
`{session, drive}` con drive hermana). Componente observador
`frontend/src/components/session-lab/EngineeringSession.tsx`: chip de
conducción con causa (`DRIVE_CAUSE_TEXT`), timer del navegador como
autoridad de avance ELIMINADO (implementación del modo anterior), todas
las acciones manuales vía control. Semántica en `paper_lab_engine.py`:
`SIN_ENTRADA` = abstención temporal (reevalúa ante cada evento nuevo),
`DESCARTADO` = descarte terminal; causalidad del dict público (sin velas
futuras); reintentos de escritura/lectura de sesión en Windows (5×,
backoff 20 ms, `IDENTITY_UNCERTAIN` solo para corrupción real).

**4. Evaluation status:** backend `tests/test_engineering_session_service.py`
8/8 (abstención temporal → evento confirmatorio → entrada/salida única sin
intervención; END_OF_TRANSPORT sin cierre inventado; DESCARTADO terminal no
reabre; 409 REVISION_CONFLICT/DRIVE_ACTIVE, 400/404; persistencia entre
reinicios del controlador con posición manejable; start idempotente;
`/shutdown`); frontend `engineering-session.test.tsx` 8/8; suite Python
completa **1530 passed / 2 skipped** (3 fallos PREEXISTENTES de la base
corregidos: causalidad del dict público; presupuesto interno de benchmark
de la ventana en `scripts/market_stream_window.py` + tests fijados); suite
frontend 604 passed / 1 skipped; `tsc`/`eslint` 0. Aceptación navegador
real sobre `http://127.0.0.1:3020/market-lab` (BUILD_ID
`r5poURhuj3RQc4CjC6Kyz`; servicio de aceptación 8797 con dir de sesiones
aislado): S1 ciclo autónomo completo (solo 2 POST: create+start; resto
GET); S2 cierre de pestaña → backend cerró la sesión solo (rev 33→38,
`SESSION_CLOSED`) y reabrir recupera sesión cerrada con panel de
exportación; S3 detener con posición abierta → `detenida` sin salida
inventada (`OPERATOR_STOP` visible); S4 prefijo B → cerrada por horizonte
(net_pnl 4.944281; kinds protección=2/entrada=1/marca=1/salida=1; tras
recuperación 24 GET / 0 POST).

**5. Limitaciones:** con la caché real de MINAUSDT ambos prefijos (A y B)
admitían entrada — NO se fabricó abstención en datos reales; la separación
abstención temporal/terminal y la confirmación posterior quedan probadas
determinísticamente en suites (no en la demo de navegador); no conecta a
Binance público (ventana aparte, autorización explícita); un solo token
candidato; sin rentabilidad probada; servicio y dashboard canónicos son
procesos separados (arranque manual de cada uno); separación bedrock sin
cambios: el navegador no decide nada económico.

**6. Evidence:** `docs/evidence/engineering-backend-2026-10-27/` (13 piezas
+ `acceptance-summary.json`); `tests/test_engineering_session_service.py`;
`tests/test_market_stream_window.py`; `tests/test_market_stream_transport.py`;
`frontend/src/test/engineering-session.test.tsx`;
`src/microstructure_probe/engineering_session_service.py`;
`src/microstructure_probe/paper_lab_engine.py`;
`scripts/engineering_session_service.py`;
`scripts/market_stream_window.py`; BFF
`frontend/src/app/api/v1/engineering-sessions/**`;
`frontend/src/lib/session-lab.ts`;
`frontend/src/components/session-lab/EngineeringSession.tsx`;
`docs/ENGINEERING_SESSION_BACKEND_V1.md` (doc dedicada con la distinción
replay-autoavance vs autonomía en backend).

**7. Last update:** 2026-10-28.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — `docs/DECISIONS.md` (modo autónomo 2026-10-27),
  `docs/CURRENT_STATE.md`, `docs/TASK_QUEUE.md`,
  `docs/DESKTOP_FIRST_SCOPE_20261020.md` (desktop only; sin trabajo móvil).
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-28 (dos entradas):
  autonomía de la sesión de ingeniería en backend
  (`engineering-session-service/v1`, navegador solo observador, avance por
  eventos REVEAL, cierre de pestaña no detiene la conducción) y
  abstención temporal (`SIN_ENTRADA`) vs descarte terminal (`DESCARTADO`)
  + reintentos de escritura en Windows (5×, backoff, `IDENTITY_UNCERTAIN`
  explícito) + 3 fallos preexistentes de la base corregidos.
- `FEATURES_IMPLEMENTED` — servicio backend residente con controlador,
  transporte local REVEAL y coordinador (`advance_once`); endpoints
  uniformes `{session, drive}` y causas de conducción explícitas; BFF +
  cliente + componente observador con chip y causa; timer del navegador
  eliminado; abstención temporal/terminal en el motor; causalidad del
  dict público; reintentos de persistencia en Windows.
- `FEATURES_VERIFIED` — backend 8/8; frontend componente 8/8; Python
  1530/2 skip + frontend 604/1 skip; tsc/eslint 0; aceptación de navegador
  real PASS S1–S4 con red verificada (0 Binance público, 0 upstream, 0
  órdenes; solo GET tras recuperación, 0 POST de avance).
- `DEFERRED_FEATURES` — conexión a Binance público; selector automático de
  símbolos; monitor en vivo; paper prospectivo; órdenes; pagos;
  móvil/Flutter; IA; indicadores provisionales; motor paper completo
  (Etapa 5); recorrido con datos nuevos continuos; demo de abstención con
  datos reales (requiere caché disfavorable).
- `BACKLOG_UPDATED` — yes: esta sección + `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS`, `ENGINEERING_SESSION_BACKEND_V1.md` (nueva).
- `DOCUMENTATION_CONFLICTS` — ninguna contradictoria; se distingue
  explícitamente el modo autónomo anterior (replay-autoavance con timer de
  React, base `9a24308`) de la autonomía en backend (este bloque) en
  `docs/ENGINEERING_SESSION_BACKEND_V1.md`; el prefijo B no garantiza
  abstención con la caché actual (expectativa corregida).

## Acceso operativo — sesión/servicio separados (2026-10-28, base `5f24807`)

**1. Title:** Verificación de acceso operativo del bloque de autonomía en
backend desde el estado entregado (8797 detenido): error visible sin
duplicados con el servicio abajo; arranque por CLI canónico declarado
limitación deliberada (el botón NO es inicio completo); semántica separada
sesión (política de posición) / pestaña (solo observador) / servicio
(sesiones en disco intactas y recuperables); publicación en
`review/o1-funcional-v2-observacion` por fast-forward autorizado.

**2. Approval status:** DECIDED dentro del alcance autorizado (operador
autorizó fast-forward de la rama en revisión; sin Binance público, sin
órdenes, sin monitor, sin nuevas funciones de estrategia; sin suites
completas repetidas).

**3. Implementation status:** VERIFIED (operativo). Sin cambios de código
de producto: verificación en navegador real con el servicio explícito
(`python scripts/engineering_session_service.py --port 8797
--sessions-dir data/engineering-session/sessions --pid-file
data/engineering-session/service.json`); docs y evidencia nuevas.

**4. Evaluation status:** casos probados: (a) servicio abajo → banner
`data-testid="session-error"` visible, sin `session_id` en localStorage,
sin duplicados, sin procesos lanzados (BFF proxy puro); (b) S1
`…7f1f4f32` ciclo autónomo completo (`SESSION_CLOSED` rev 38, kinds
protección=2/entrada=1/marca=1/salida=1; red 1 create + 1 control + GETs);
(c) S2 `…49b05386` cierre de pestaña con drive corriendo → backend
continuó (rev 7→31→38) y cerró solo; reabrir recupera estado correcto
(net 4.944281); (d) SERVICE_STOP con drive corriendo (`…516fa8d8`) →
estado en disco intacto (`abierta` rev 11, sin evento de salida) y
servicio parado; (e) reinicio → recuperación → «Detener sesion» →
`detenida` rev 12 con posición preservada (entry 0.0626, mark 0.06256).
Identidad: BUILD_ID `r5poURhuj3RQc4CjC6Kyz`; 8792 preexistente sin tocar.

**5. Limitaciones:** el default del servicio SIN `--sessions-dir`
(`paper-lab-sessions/`) colisiona con el controlador anterior (uso
siempre de dir dedicado documentado); el mapeo `ENGINEERING_SERVICE_DOWN`
del BFF rara vez aparece (el fetch de Node oculta el `code` → la etiqueta
observada es `ENGINEERING_PROXY_ERROR`, igual 503 con error visible);
defecto abierto del panel de flujo (`ERR_INCOMPLETE_CHUNKED_ENCODING` en
`/api/v1/market-flow/stream`, impacto = stream abortado en re-render, sin
atribuirle fallos de esta sesión) queda pendiente de decisión.

**6. Evidence:** `docs/evidence/engineering-backend-2026-10-28/operational-access-2026-10-28.json`;
`docs/evidence/engineering-backend-2026-10-28/ver-case-1-detener-tras-recuperar.png`;
`docs/ENGINEERING_SESSION_BACKEND_V1.md` §8;
`docs/DECISIONS.md` (2026-10-28, acceso operativo);
`docs/CURRENT_STATE.md`; `docs/TASK_QUEUE.md`.

**7. Last update:** 2026-10-28.

### Cierre (siete campos, obligatorios)

- `DECISIONS_REVIEWED` — `docs/DECISIONS.md` (autonomía en backend y
  abstención temporal/terminal, 2026-10-28), `docs/CURRENT_STATE.md`,
  `docs/TASK_QUEUE.md`, `docs/DESKTOP_FIRST_SCOPE_20261020.md`.
- `NEW_DECISIONS_RECORDED` — DECISIONS 2026-10-28: arranque manual del
  servicio declarado (botón no-inicio-completo; CLI canónico con dir
  dedicado obligatorio); semántica separada sesión/pestaña/servicio
  (detener sesión = política de posición; cerrar pestaña = solo
  observador; detener servicio = sesiones en disco intactas, nunca cierra
  por su cuenta).
- `FEATURES_IMPLEMENTED` — ninguno nuevo (bloque de verificación);
  documentación del acceso canónico y de la semántica separada.
- `FEATURES_VERIFIED` — casos (a)–(e) de arriba en navegador real; 0
  Binance público, 0 upstream, 0 órdenes; servicios al cierre: 8797
  detenido, sin sesiones de ensayo, dashboard canónico servido.
- `DEFERRED_FEATURES` — recorrido con datos nuevos continuos (ventana
  aparte, autorización explícita); mapeo `ENGINEERING_SERVICE_DOWN`
  opcional en BFF; hotfix del defecto abierto del panel de flujo.
- `BACKLOG_UPDATED` — yes: esta sección + `CURRENT_STATE`, `TASK_QUEUE`,
  `DECISIONS`, `ENGINEERING_SESSION_BACKEND_V1.md` (§8).
- `DOCUMENTATION_CONFLICTS` — ninguna contradictoria; se declara el
  alcance del botón (no inicio completo) y el impacto del defecto abierto
  del panel de flujo sin atribuirle fallos de esta sesión.

## Inicio explicito de sesion desde la UI + defecto SSE corregido (2026-10-28, base `0bf96c6`)

**1. Title:** Control explicito unico del operador para sesion de
ingenieria local: comprobar servicio, arrancar la instancia canonica via
BFF (readiness con limite + identidad triple), crear e iniciar una sola
sesion; estado del servicio visible (checking/starting/ready/down/error);
doble clic sin duplicados; directorio de sesiones dedicado por defecto
(bug de `ROOT` corregido); causa/arreglo del defecto
`ERR_INCOMPLETE_CHUNKED_ENCODING` del panel de flujo (timeout del BFF +
bodyTimeout de undici; reconexion con misma identidad; 8792 intocado).

**2. Approval status:** DECIDIDO por el operador (2026-10-28): integrar el
arranque del servicio con el controlador canonico, sin gestor paralelo;
nada por GET ni por abrir la pagina; guardias de origen existentes;
identidad verificada, nunca reutilizar/detener PIDs desconocidos;
conservar sesiones existentes sin migracion.

**3. Implementation status:** IMPLEMENTED - `frontend/src/lib/engineering-service-manager.ts`
(spawn canonico, readiness 15 s, identidad child.pid==pid-file==health,
error de child_process manejado, kill solo del proceso propio),
`frontend/src/app/api/v1/engineering-sessions/service/route.ts` (GET
consulta pura / POST action=start con guardia de origen),
`session-lab.ts` (fetchEngineeringService/startEngineeringService),
`EngineeringSession.tsx` (chip `service-chip`, puerta explicita en el
boton, guardia sincrona `startInFlightRef`), servicio Python default
dedicado (`data/engineering-session/sessions`; ROOT corregido),
`market-flow/stream/route.ts` (agent undici bodyTimeout 0 +
headersTimeout, req.signal), `MarketFlowPanel.tsx` (reconexion 2,5 s
misma identidad, causa visible hasta onopen, liberacion en
desmonte/cambio de simbolo).

**4. Evaluation status:** VERIFIED - servicio 9/9 (nuevo test default
dedicado), frontend vitest 611 passed + 1 skip (4 nuevos
engineering-session, 3 nuevos market-flow-panel), tsc/eslint 0;
aceptacion navegador real A-G PASS
(`docs/evidence/engineering-explicit-start-2026-10-28/acceptance-summary.json`,
BUILD_ID `FQGAqw1wwcXIMQqei_fRA`, dashboard PID 14492): apertura sin
procesos, doble clic 1 sesion, identidad triple, detenida con posicion
preservada sin exit inventado, recuperacion tras reabrir pestaña, fallo
de arranque claro sin huerfanos, SSE estable 78 s + 40 s con 0 errores.

**5. Deferred:** ninguno (arreglo del defecto SSE estaba pendiente de
decision del operador: decidido y ejecutado en este bloque). Opcional
retenido: map explicito `ENGINEERING_SERVICE_DOWN` en el BFF; investigar
causa exacta del artefacto anomatico (archivo vacio sin sufijo, UNKNOWN,
no reproducible).

**6. Safety/constraints:** observe-only; sin Binance publico, sin feed
vivo, sin ordenes, sin pagos, sin movil; el servicio de flujo preexistente
(8792) no modificado; 8797 detenido al cierre; sesiones de ensayo
archivadas en evidencia y retiradas del dir en linea.

**7. Traceability:** base `0bf96c6`; DECISIONS 2026-10-28 (inicio
explicito + dir dedicado + causa SSE + hallazgo doble clic);
ENGINEERING_SESSION_BACKEND_V1.md §10 (9.1/9.3 anotadas
historico/resuelto); CURRENT_STATE + TASK_QUEUE 2026-10-28; evidencia
`docs/evidence/engineering-explicit-start-2026-10-28/`.

## Transporte market_stream en vivo de ingeniería + aceptación local PASS + fix del explorador por cola (2026-10-28, base `90b3c9b`)

**1. Title:** Transporte `market_stream` en vivo para la sesión de
ingeniería reutilizando `market-stream-service/v1` (SSE loopback):
backend con gates de feed vivo + consumo de snapshots + avance live;
frontend con runner `market_stream` desde la UI; aceptación LOCAL
completa con navegador real (3020) y productor SSE local determinista;
arreglo del defecto del explorador canónico (lectura por COLA con caches
>5000 velas).

**2. Approval status:** DECIDIDO por el operador (2026-10-28):
reutilizar el servicio de mercado existente sin colector/motor/gestor
nuevos; `paper_lab_engine` intocado; aceptación solo local/loopback (sin
Binance público); 8792/8797 intocables; 3020 restaurado al estado previo
al finalizar.

**3. Implementation status:** IMPLEMENTED -
`src/microstructure_probe/engineering_session_service.py` (gates de feed
vivo, `_consume_snapshot`, `_consume_market_closed`, `_live_advance`),
`frontend/src/components/session-lab/EngineeringSession.tsx` +
`frontend/src/lib/session-lab.ts` + `frontend/src/lib/engineering-service-manager.ts`
(runner `market_stream`),
`src/microstructure_probe/market_explorer.py` (`read_stored` por cola),
`scripts/engineering_live_local_acceptance.py` (arnés nuevo),
`scripts/indicators_v1_public_demo.py` (decodificación Windows corregida).

**4. Evaluation status:** VERIFIED - 92 tests passed (41+1
`test_market_explorer.py` con regresión de cola,
`test_engineering_service_market_stream.py`,
`test_engineering_session_service.py`, `test_paper_lab_engine.py`);
frontend tsc/eslint 0 y vitest OK (verificado previamente); aceptación
navegador real PASS
(`docs/evidence/engineering-live-local-2026-10-28/summary.json`: corrida
379,9 s, BUILD_ID `WDYGaWV_cUxErasQlce70`, 12/12 checks, 6 capturas,
8 reconexiones con watermark, 0 peticiones externas, fill
model_approximation, salida por stop, net −16,59 simulado,
`trial_sessions: []`).

**5. Deferred:** acreditación de recepción Binance real (todo loopback);
reparación REST (inexistente en local); tratamiento del churn WS ~9 s;
ciclo SSE de 10 s del adaptador en silencio; recorrido con datos nuevos
continuos (ventana aparte). Todo lo público requiere autorización
explícita.

**6. Safety/constraints:** observe-only; sin Binance público, sin feed
vivo real, sin órdenes, sin capital; proveedor público bloqueado por
diseño en la aceptación (sitecustomize + guardia del navegador + proxy
de registro); sesiones de ensayo retiradas (`trial_sessions: []`);
dashboard 3020 restaurado (estaba libre); servicios canónicos
8792/8797 intocables.

**7. Traceability:** base `90b3c9b`; DECISIONS 2026-10-28 (transporte
live + fix explorador por cola); ENGINEERING_SESSION_BACKEND_V1.md §11;
CURRENT_STATE + TASK_QUEUE 2026-10-28; evidencia
`docs/evidence/engineering-live-local-2026-10-28/`.

## Modo explícito «Demostración local — datos simulados» en /market-lab (2026-10-28, build `NRjvq90SYBCoTGgmmRzA5`)

**1. Title:** Recorrido `/market-lab` → «Iniciar demostración» → «Iniciar
sesión» con datos simulados exclusivamente propios, identidad de procesos
verificable por evidencia (cmdline del SO, no pid-file reescrito a mano),
guardas de fuente antes de crear sesiones, y verificación acotada
(arranque/readiness/parada, sin repetir la aceptación larga).

**2. Approval status:** DECIDIDO por el operador (2026-10-28): sin Binance,
sin órdenes, sin pagos, sin móvil, sin cambios de estrategia; no usar
silenciosamente 8792 ni habilitar transporte público; no matar ni adoptar
procesos desconocidos; ante registro incompatible, rechazar o reconciliar
solo con evidencia verificable; preservar el incidente del pid-file en
documentación.

**3. Implementation status:** IMPLEMENTED —
`scripts/local_demo_producer.py` (ciclo determinista RULE-CAUSAL-V1,
backfill `--backfill-from-ms` sin REST, auto-parada `--max-runtime-s`,
estado compartido entre reconexiones WS),
`frontend/src/lib/local-demo-manager.ts` (status GET puro / start / stop,
manifest, seams), `frontend/src/app/api/v1/engineering-sessions/demo/route.ts`
(BFF con guardia origen 127.0.0.1:3020), `frontend/src/lib/session-lab.ts`
(cliente demo + `market_url`),
`frontend/src/components/session-lab/EngineeringSession.tsx` (chip fuente,
tarjeta demo `data-testid="demo-card"`, guardia de fuente en `startSession`,
anti doble-clic `demoInFlightRef`), `frontend/src/lib/engineering-service-manager.ts`
(reconciliación por evidencia, `market_url` exportado). Tests nuevos:
`tests/test_local_demo_producer.py`, `frontend/src/test/engineering-service-manager.test.ts`,
`frontend/src/test/engineering-session.test.tsx`, `frontend/src/test/local-demo-manager.test.ts`.

**4. Evaluation status:** VERIFICADO — verificación acotada
`docs/evidence/engineering-local-demo-2026-10-28/summary.json`
(build `wF9Xf3Orb5Af7vgwp8_f4`, dashboard 3020): **14/14 checks PASS** en la
re-verificación integrada (E2-gridgap), más 22/23 de la verificación acotada
original (E2 documentado como FAIL con causa en la corrida 3, ahora resuelto).
PASS: A1-A4 (abrir la página no arranca nada; 8791 caído; sin productor ni
market propios; 8792 intacto con cmdline LOCAL), B1-B3 (fuente ausente →
aviso `FUENTE NO DISPONIBLE` ANTES de crear sesión, sin sesión huérfana,
chip visible), D1-D6 (demo activa y fuente lista; un solo productor y un
solo market propios identificados por cmdline del SO; chip `Fuente: lista`),
E1 (sesión creada con evidencia de stream), **E2 (operación de ingeniería:
`ENTRADA_SIMULADA` en clock 1793073120000, close 0.06291285 > entry_px
0.06285; fill simulado entry_qty=15895, entry_cost=1000, entry_ms=
1793073180000; gestión con mark_px/mfe_pct/mae_pct; cierre por regla horizon
con exit_executed=true; sesión `cerrada`)**, F1-F4 (demo detenida, manifest
cerrado, productor y 8791 detenidos y limpios, 8792 intacto), F3 (caída de
feed registrada DENTRO de la sesión), G1 (sesión detenida por el operador,
política correcta), H1-H3 (sin demo activa al final, 8792 intacto, dashboard
200).
Causa raíz de GRID_GAP (resuelta): `anchor_open` del productor se fijaba a
`current_open` en vez de a `start_open` (primera frontera del backfill), por
lo que todas las velas del backfill tenían `idx < 0` → close = PRE_CYCLE
(0.999·base) < entry_px → nunca señal. Fix: `anchor_open = start_open`.
Además, ritmo de backfill `BACKFILL_PACE_S=1.0` (no saturar la cola SSE del
consumidor) y plomado de `from_ms`/`to_ms` desde el BFF al servicio de
mercado (`deliver_from_ms`) para continuidad exacta contexto→operación.

**5. Deferred:** acreditación de recepción Binance real (todo loopback);
reparación REST (inexistente en local); recorrido con datos públicos
(`8791 --transport public`) requiere autorización y presupuesto separados.
Todo lo público requiere autorización explícita.

**6. Safety/constraints:** observe-only; sin Binance público, sin feed vivo
real, sin órdenes, sin capital; proveedor público bloqueado por diseño
(sitecustomize + guardia del navegador + proxy de registro); sesiones de
ensayo retiradas (`trial_sessions: []`); dashboard 3020 restaurado al estado
previo al finalizar (sin demo activa, manifest cerrado); servicios canónicos
8792/8797 intocables (verificado por cmdline del SO en A4/F4/H3); 8792 pid
33104 (ahora 31124 tras reinicio de seguridad) intacto durante la
verificación.

**7. Traceability:** build `wF9Xf3Orb5Af7vgwp8_f4` (dashboard 3020, SHA
fuente `a954c2a` + cambios de este bloque); evidencia
`docs/evidence/engineering-local-demo-2026-10-28/` (summary.json corrida 3,
corrida1/ preservada, summary-integration.json de E2); evidencia
`docs/evidence/engineering-local-demo-2026-10-28/e2-gridgap/` (E2 integrada);
ENGINEERING_SESSION_BACKEND_V1.md §11.7–§11.8; CURRENT_STATE + TASK_QUEUE +
DECISIONS 2026-10-28; `docs/FEATURE_BACKLOG.md` esta entrada. Próximo
objetivo declarado en docs: mismo recorrido con datos públicos
(8791 `--transport public`), autorización/presupuesto separados.

## Precisión documental mínima — fallos y correcciones del modo demo

Este bloque separa tres cosas que la documentación previa mezclaba:

### a) Fallo del ancla y ausencia de señal (corrida 3, 2026-10-28)
El productor `scripts/local_demo_producer.py` fijaba `anchor_open = current_open`
(minuto del primer connect del WS) en vez de `start_open` (primera frontera
del backfill, `cache_end + paso`). Como todas las velas del backfill tenían
`open_ms < anchor_open`, el índice `idx = (open_ms - anchor) // STEP_MS` era
negativo y `close_of()` devolvía `PRE_CYCLE = 0.999·base` para **todas** las
velas del backfill. Con `entry_px = base`, ninguna vela del backfill generaba
señal LONG (`close < entry_px` siempre). La ausencia de señal era, por tanto,
un defecto del ancla del precio, no una ausencia legítima de oportunidad.

### b) Discontinuidades/backfill y GRID_GAP (corrida 4, 2026-10-29)
El productor enviaba el backfill a ritmo acelerado (`BACKFILL_PACE_S=0.02`,
~50 velas/segundo). El `market_stream_service` recicla su socket WS cada
~8-15 s (churn observado). Al reconectar, el catch-up del productor partía
desde `state["open"]` (avanzado por velas ya puertas en el buffer del WS pero
no entregadas al consumidor), saltándose las velas intermedias. Resultado: el
servicio de mercado recibió 6681 velas cerradas pero la sesión solo 34, con
huecos de rejilla entre `1793115900000→1793148480000` (~55 min) y
`1793156160000→1793273880000` (~129 min). `_grid_holes()` detectó el hueco
frontera-contexto→operación y el hueco entre velas, bloqueando
`evaluate_session` con `GRID_GAP` permanente. No hubo señal porque la puerta
de evaluación nunca se abrió (`gate.ok = False`).

### c) Correcciones que resolvieron cada uno
- **Ancla:** `anchor_open = start_open` (primera frontera del backfill), no
  `current_open`. Así cada vela del backfill recibe su `close` del ciclo
  determinista según su índice real, y las velas de operación (idx ≥ 1) tienen
  `close > base = entry_px`, generando señal LONG por RULE-CAUSAL-V1.
- **Ritmo de backfill:** `BACKFILL_PACE_S = 1.0` (1 vela/segundo), lo bastante
  lento para que el consumidor reciba cada vela antes de que el productor
  avance al siguiente `open`, evitando el desfase entre `state["open"]` y lo
  que el consumidor efectivamente recibió bajo churn.
- **Continuidad contexto→operación:** plomado de `from_ms` y `to_ms` desde
  el BFF (`CreateSessionInput.fromMs`/`toMs`) hasta `MarketServiceStreamAdapter`
  y `hub.ready(consumer, deliver_from_ms)`, con `deliver_from_ms = last_ctx_close
  + 1`. El consumidor ignora velas con `open_time_ms <= deliver_from_ms`
  (dedupe por marca de agua), por lo que no hay duplicados ni velas ya cubiertas
  por el contexto.
- **Validación de la corrección:** verificación integrada E2-gridgap 14/14 PASS:
  34 velas recibidas, ordenadas, sin duplicados, continuidad de rejilla exacta,
  `ENTRADA_SIMULADA` en clock 1793073120000, fill simulado, gestión, cierre
  por regla horizon con `exit_executed=true`. Sin GRID_GAP, sin FEED_SILENCE.

Nota de honestidad: la señal `ENTRADA_SIMULADA` es una **señal de ingeniería
del productor simulado**, no una validación estratégica ni evidencia de
rentabilidad. Cero operaciones con dinero real.

## Protocolo para el siguiente recorrido con datos públicos (sin ejecutar)

### 1. Transporte e identidad
Cadena de datos para la ventana pública:
**Binance público (WS de mercado real)** → **servicio Python de servicio**
(`market_stream_service`, `--transport public`) → **SSE loopback**
(`/stream` en `127.0.0.1:8791`) → **navegador** (EventSource vía BFF
`/api/v1/market-stream`).

Nota: "WS loopback / proveedor público bloqueado" describe la **prueba
local** (modo demo, datos simulados), no la futura ventana pública. En la
ventana pública el proveedor de Binance se activa de forma explícita.

**Cómo se activa explícitamente el transporte público:**
```
python scripts/market_stream_service.py --port 8791 --transport public --max-seconds 180
```
- `resolve_transport(mode="public", base_url=None)` resuelve
  `TRANSPORT_PUBLIC`, `recovery=True`; no hay `--base-url` (público no usa
  loopback de productor).
- El servicio declara en `/health`: `transport.mode = public`.
- El adaptador de sesión (`MarketServiceStreamAdapter`) se construye con
  `base_url=http://127.0.0.1:8791` y emite SSE en
  `http://127.0.0.1:8791/stream?symbol=...&interval=...&bars=...`.

**Cómo se restaura después (vuelta a modo local / proveedor bloqueado):**
1. Detener el servicio público:
   `python scripts/market_stream_service.py --port 8791 --stop`.
2. Verificar que `/health` declara `transport.mode = local` o que el servicio
   no responde (bloqueado).
3. Volver a modo local:
   `python scripts/market_stream_service.py --port 8791 --transport local
   --base-url ws://127.0.0.1:<productor> --max-seconds <N>`.
- El proveedor público permanece **bloqueado por diseño**
  (sitecustomize + guardia del navegador + proxy de registro) salvo que el
  operador lo active explícitamente con `--transport public`.

### 2. Presupuesto inequívoco (cifras separadas)
| Recurso | Límite exacto | Nota |
|---------|---------------|------|
| Conexiones WS simultáneas | 1 | una sola conexión combinada del servicio a Binance pública; MINAUSDT y BTCUSDT viajan en la misma conexión multiplexada |
| Reconexiones acumuladas | ≤ 3 | backoff exponencial acotado (`RECONNECT_MAX_S=30`); al agotarse, `_park_until_new_consumer` |
| Streams | 2 | `MINAUSDT@kline_1m`, `BTCUSDT@kline_1m` (dentro de `MAX_SUBSCRIPTIONS=6`) |
| Consumidores SSE simultáneos | 3 | 2 en el hub (uno por símbolo) + 1 navegador vía BFF; `MAX_TOTAL_CONSUMERS=12` es el tope del servicio, no el presupuesto de la ventana |
| Intentos REST upstream (páginas + reintentos) | ≤ 4 | modo público: ≤ 2 páginas por intento y ≤ 2 reintentos (máx. 4 intentos REST por ventana); `LedgerAttemptGate` es el mecanismo de reserva, no una cifra de presupuesto por sí misma; 0 en modo local |
| Tiempo global | ≤ 180 s | `--max-seconds` en el servicio, auto-parada |
| Almacenamiento nuevo | 0 filas canónicas | caché aislado en `data/market-cache/`; no se escribe en `microprobe.db` ni `historical.db` |

### 3. Contexto actualizado (cobertura verificable antes de abrir)
No se presupone que una caché antigua alcance el presente en 180 s. Antes de
crear la sesión:
- Paso 1: leer caché local (`read_stored`, `client=None`, `--no-fetch`) para
  `MINAUSDT` 1m y `BTCUSDT` 1m.
- Paso 2: calcular `last_ctx_close` de MINAUSDT. Si
  `ahora - last_ctx_close > tolerancia` (p. ej. > 2 pasos de rejilla, > 2 min
  sin cobertura continua), la caché es antigua y NO cubre el presente.
- Paso 3 (regla de decisión): si el caché de MINAUSDT no tiene velas cerradas
  continuas hasta `from_ms - step` (última vela cerrada adyacente al inicio de
  operación), **abortar antes de la ventana** (no inventar mercado, no forzar
  continuidad).
- Paso 4 (BTC): `client=None` **no garantiza** cobertura contemporánea.
  Verificar explícitamente que `BTCUSDT` 1m tiene velas cerradas en el mismo
  rango temporal que MINAUSDT; si falta, BTC se marca `NO_COVERAGE` y se sigue
  con MINAUSDT sola (contexto BTC omitido, no inventado).
- Paso 5 (si falta cobertura): adquisición inicial acotada (máx. 2 páginas
  REST, `LedgerAttemptGate`) para cerrar el tramo faltante, **o** abortar la
  ventana antes de abrirla si no se puede cubrir.

### 4. Final de ventana
- Si hay posición abierta al finalizar: congelar conducción (`stop` en el
  drive), conservar posición abierta y marca no realizada; **no inventar
  fill ni comisión de salida**.
- `exit_reason = "horizon"` **solo** si el horizonte se alcanzó y la salida
  fue ejecutada por el motor (`exit_executed = true`).
- Terminar la ventana **no equivale a cerrar una operación**; la posición
  puede quedar abierta con mark no realizado.

### 5. Aceptación
- Ventana inicial = integración con datos públicos (aceptación A).
- Cero operaciones es un resultado válido.
- No se exige cerrar una operación de horizonte 30 min dentro de 180 s.
- No cambiar umbrales, horizontes ni reglas para producir entradas.
- Aceptación B (operación paper con entrada/fill/gestión/cierre) solo si se
  cumplen las condiciones de la regla (RULE-CAUSAL-V1: `close > entry_px`
  LONG con stop no vulnerado); el fill es `model_approximation`.

Tabla final de límites (resumen del presupuesto):
| Recurso | Límite exacto |
|---------|---------------|
| Conexiones WS simultáneas | 1 |
| Reconexiones acumuladas | ≤ 3 |
| Streams | 2 |
| Consumidores SSE simultáneos | 3 |
| Intentos REST upstream (páginas + reintentos) | ≤ 4 |
| Tiempo global | ≤ 180 s |
| Almacenamiento nuevo | 0 filas canónicas |

Comando exacto (ventana pública):
```
python scripts/market_stream_service.py --port 8791 --transport public --max-seconds 180
```
Restaurar modo local:
```
python scripts/market_stream_service.py --port 8791 --stop
python scripts/market_stream_service.py --port 8791 --transport local --base-url ws://127.0.0.1:<productor> --max-seconds <N>
```

Criterios PASS / FAIL / UNKNOWN:
- **PASS:** feed llega, velas cierran en orden sin huecos, `from_ms` respetado,
  `GRID_GAP` no se dispara por hueco de contexto, sesión se abstiene con causa
  visible si no hay señal, cero operaciones es válido, ventana cierra sin
  inventar fill/salida, 8792/8797 intocables, `--transport public` activado y
  restaurado explícitamente.
- **FAIL:** hueco de rejilla (GRID_GAP) en frontera contexto→operación,
  relleno/interpolación de velas, fill o comisión de salida inventados,
  `exit_reason="horizon"` sin salida ejecutada por el motor, 8792/8797 tocados,
  cambio de umbral/horizonte/regla para forzar entrada, conexión pública sin
  autorización separada.
- **UNKNOWN:** cobertura de BTC contemporánea no verificable, caché antigua
  sin adquisición inicial, comportamiento del proveedor público real no probado
  en loopback.

### 6. Dos aceptaciones distinguidas
**A. Integración con mercado real (recepción, cálculos, decisiones trazables,
abstención y recuperación):** se considera exitosa si el feed llega, las velas
se cierran en orden sin huecos, el motor calcula decisiones sobre el prefijo
conocido sin lookahead, y ante falta de señal la sesión se abstiene con causa
visible. Cero operaciones es un resultado válido.
**B. Operación paper (entrada/fill/gestión/cierre solo si se cumplen las
condiciones de la regla):** solo si `close > entry_px` (LONG) con stop no
vulnerado, el motor publica `ENTRADA_SIMULADA`; el fill es
`model_approximation` (open de la vela revelada, no liquidez observada); la
gestión marca mark/no-realizado; el cierre es por stop, horizon o `open_at_end`.
Sin llenar profundidad, spread ni funding.

### 7. Supuestos del modelo y bloqueos reales
- **Supuestos:** las velas cerradas del WS son el único dato de mercado;
  el fill es aproximación del modelo; funding es UNKNOWN; no hay latencia
  modelo ni redondeo de lotes.
- **Bloqueos reales:** requiere autorización separada para conexión pública
  Binance (`--transport public`); el `market_stream_service` en modo local no
  repara desde REST; el churn WS consume presupuesto de consumidores; cero
  upstream REST significa que el histórico previo al caché no se puede
  recuperar.

## Seguridad del alcance

- **No existe camino de órdenes reales:** el recorrido es observe-only;
  `paper_lab_engine` es la autoridad económica única y no coloca órdenes;
  el BFF es proxy de consulta; el navegador solo solicita acciones de
  arranque/parada observando estados.
- **No se necesitan claves privadas ni API keys de Binance:** todo es
  loopback (`127.0.0.1`) con datos simulados o caché local; el proveedor
  público está bloqueado por diseño (sitecustomize + guardia del navegador +
  proxy de registro).
- **La siguiente ventana será paper de ingeniería, no validación de
  rentabilidad:** su conexión pública requiere autorización separada y
  presupuesto explícito; no se declara ventaja ni edge.



## research/universe-liquidity-v1 (2026-11-03)

**1. Title:** Investigación de hipótesis económica y selección automática de candidatos sobre el universo elegible (liquidez vs flujo agresor).

**2. Approval status:** PROPUESTO (investigación autorizada; sin conexión pública, sin órdenes, sin cambios de reglas operativas ni económicas).

**3. Implementation status:** INVESTIGACIÓN EN CURSO en rama 
esearch/universe-liquidity-v1. Documento docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md con protocolo breve, tabla de cobertura y resultado descriptivo nivel A.

**4. Evaluation status:** diagnóstico computado de insuficiencia. Hipótesis NO testeable hoy sobre outcomes resueltos (0 filas de profundidad/libro en el instante T para la ventana resuelta; universo resuelto = 6 símbolos = 1.15% de 522 elegibles; retorno forward medio ≈ 0 en BTC/ETH/SOL). No es otro simulador.

**5. Evidence:** docs/evidence/research/universe_liquidity_v1/coverage.json, descriptive.json; scripts/research_universe_liquidity_inventory.py (read-only sobre SQLite).

**6. Verdict:** insuficiencia computada; plan mínimo de adquisición propuesto (no ejecutado).

**7. Next step:** adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato y, si el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar.


## research/universe-liquidity-v1 (2026-11-03)

**1. Title:** Autoselección de candidatos para investigación sobre el universo elegible (liquidez vs flujo agresor).

**2. Approval status:** PROPUESTO (investigación autorizada; sin conexión pública, sin órdenes, sin cambios de reglas operativas ni económicas).

**3. Implementation status:** IMPLEMENTADO (mecanismo + pruebas) en rama 
esearch/universe-liquidity-v1. Documento docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md con protocolo, tabla de cobertura, matriz de aprovechamiento, política de autoselección y comparador.

**4. Evaluation status:** diagnóstico computado de insuficiencia. Cobertura útil liquidez+flujo+resultado posterior = 1 de 14 símbolos research (BTCUSDT, solo 1h). Hipótesis NO testeable hoy sobre universo representativo. No es otro simulador.

**5. Evidence:** docs/evidence/research/universe_liquidity_v1/coverage.json, descriptive.json, joint_coverage.json; scripts/research_universe_liquidity_inventory.py y scripts/research_selector.py; 	ests/test_research_inventory.py (10) y 	ests/test_research_selector.py (11).

**6. Verdict:** insuficiencia computada; plan mínimo de adquisición propuesto (no ejecutado).

**7. Next step:** adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato; si el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar.


## research/universe-liquidity-v1 (2026-11-03)

**1. Title:** Autoselección de candidatos para investigación sobre el universo elegible (liquidez vs flujo agresor).

**2. Approval status:** PROPUESTO (investigación autorizada; sin conexión pública, sin órdenes, sin cambios de reglas operativas ni económicas).

**3. Implementation status:** IMPLEMENTADO (mecanismo + pruebas) en rama 
esearch/universe-liquidity-v1. Documento docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md con protocolo, tabla de cobertura, matriz de aprovechamiento, política de autoselección y comparador.

**4. Evaluation status:** diagnóstico computado de insuficiencia. Cobertura útil liquidez+flujo+resultado posterior = 1 de 14 símbolos research (BTCUSDT, solo 1h). Hipótesis NO testeable hoy sobre universo representativo. No es otro simulador.

**5. Evidence:** docs/evidence/research/universe_liquidity_v1/coverage.json, descriptive.json, joint_coverage.json; scripts/research_universe_liquidity_inventory.py y scripts/research_selector.py; 	ests/test_research_inventory.py (10), 	ests/test_research_selector.py (15), 	ests/test_research_joint_coverage.py (4).

**6. Verdict:** insuficiencia computada; plan mínimo de adquisición propuesto (no ejecutado).

**7. Next step:** adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato; si el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar.


## research/universe-liquidity-v1 (2026-11-04)

**1. Title:** Corrida final de la tabla de observaciones libro+flujo y reconciliación de disponibilidad publicada (`as_of_ms`).

**2. Approval status:** PROPUESTO (investigación autorizada; solo lectura de SQLite local, sin Binance, sin órdenes, sin cambios de reglas operativas ni económicas).

**3. Implementation status:** IMPLEMENTADO y ejecutado UNA vez sobre las DBs reales en solo lectura. `scripts/research_observations_table.py` (procedimiento v2) clasifica `as_of_ms` por fuente en NULL / `<= bucket_end` / `> bucket_end`, separa estado descriptivo de estado causalmente evaluable, y `tests/test_research_joint_coverage.py` ejecuta `main()` completo contra SQLite temporal (24 pruebas). Añadidos `research_availability_counts.py` y `research_observations_validate_sample.py`.

**4. Evaluation status:** 1930 observaciones (1827 parejas); **0 causalmente evaluables**, 121 descriptivas (BTCUSDT 1h), 1809 descartadas. Disponibilidad: libro 1776 NULL / 0 en T / 54 posterior; flujo 1855 NULL / 15 en T / 57 posterior. Corregida la causa anterior: el 97,04 % de las parejas tiene al menos una fuente con `as_of_ms` NULL, no publicación posterior a T (2,96 %). Hipótesis liquidez-vs-flujo: NO TESTEABLE, no refutada. Pruebas: research 49 passed; suite completa 1661 passed / 2 skipped / 12 fallos PREEXISTENTES ajenos (fixtures de `test_engineering_live_window_local.py`, `test_market_stream_window.py`, `test_session_new_public_market.py`).

**5. Evidence:** `docs/evidence/research/universe_liquidity_v1/observaciones.jsonl`, `observaciones_resumen.json`, `disponibilidad_as_of.json`, `validacion_muestra.json`, `run_final_stdout.txt`, `run_final_hashes.json`; `docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md` §5.5.

**6. Verdict:** insuficiencia de trazabilidad computada; la validación independiente de 26 observaciones da 529 comprobaciones comparables y 0 discrepancias.

**7. Next step:** adquirir liquidez en el instante T con `available_at` propio y persistir `as_of_ms` desde el inicio de la captura; sin eso no se puede pasar de descripción a evaluación causal.

## research/piloto-prospectivo-v1 (2026-11-04)

**1. Title:** Piloto prospectivo local: cadena universo → autoselección (research-selector-v2) → libro/flujo → precios forward (5m/15m/60m) → evaluación reproducible, contra proveedores loopback y SQLite temporal.

**2. Approval status:** PROPUESTO (investigación autorizada; solo lectura local, cero conexiones públicas de mercado, sin órdenes, sin cambios de reglas operativas ni económicas; presupuesto público requiere autorización separada).

**3. Implementation status:** IMPLEMENTADO (reconciliado 2026-11-05). `scripts/research_pilot.py` (CLI acotado; `--status-file`/`--decision-gate-file`/`--stop-file` solo con `--clock manual`), `tests/test_research_pilot.py` (28 passed: frescura independiente por fuente, ventana incompleta con motivo, `decision_ms` no retrotraído, presupuesto efectivo antes del transporte, separación local/público, cadena sincronizada sin sleeps de avance, horizontes 5m/15m/60m por avance controlado, rotación con resultado del símbolo retirado, contadores WS, manifiesto/hashes y resumen regenerado, contabilidad de 2 aperturas WS por rotación; política de pendientes: fin normal → settle madura, fin de settle → pendiente con causa, parada explícita → sin consultas adicionales, presupuesto agotado → siguiente envío bloqueado). `src/microstructure_probe/research_recorder.py` acepta reloj inyectable (no cambia el comportamiento por defecto). `scripts/research_selector.py` registra ranking completo del ciclo.

**4. Evaluation status:** cadena completa verificada en loopback con sincronización explícita (fijar instante → publicar → confirmar libro/flujo → autorizar evaluación → avanzar). Frescura demostrada por fuente (libro obsoleto con flujo fresco y viceversa; edades 60000 vs 0 ms, `max_data_age_ms=5000` sin cambios) y ventana incompleta con motivo `flujo_ventana_incompleta`. Horizontes 5m/15m/60m resueltos con `desfase_ms=0` y `horizonte_efectivo_ms` exacto. Política de pendientes verificada: settle acotado madura lo programado; fin de settle persiste `pendiente` con `ventana_de_settle_agotada`; parada explícita persiste `pendiente` con `parada_operador` sin nuevas consultas; presupuesto agotado bloquea antes del transporte y persiste `pendiente` con `presupuesto_agotado`. Cada corrida publica `diagnostico.json` (edades, cobertura, instante y motivos). Sin Binance; no declara ventaja, rentabilidad ni representatividad.

**5. Evidence:** `docs/evidence/research/universe_liquidity_v1/pilot_sync/` (diagnóstico de frescura, diagnóstico/resumen de horizontes, `pytest_pendientes.txt`, salida pytest); `docs/evidence/research/universe_liquidity_v1/pilot_local/` (manifiesto.json, resumen.json, observaciones_muestra.jsonl, presupuesto.json histórico 4 h); `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/` (presupuesto vigente 1 h + 70 min, config efectiva, hash y verificación; no ejecutado); dataset completo fuera de Git; `docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md` §9; `docs/CURRENT_STATE.md` bloque piloto.

**6. Verdict:** piloto local ejecutado y reproducible; el salto a evaluación causal requiere adquirir liquidez en T con `available_at` propio (ver FEATURE_BACKLOG research/universe-liquidity-v1 punto 7).

**7. Next step:** autorizar o rechazar la propuesta pública 1 h + 70 min de §9.3 (presupuesto generado con `--budget-only`, no ejecutado); no ejecutar contra Binance sin autorización separada; seguir adquiriendo liquidez en T.

## research/piloto-coordinacion (2026-11-05, base `0c5bccb`)

**1. Title:** Corregir la coordinacion automatica del piloto (seleccion -> suscripcion -> recepcion confirmada -> evaluacion) con calentamiento propio de 60 s y sin barrera manual.

**2. Approval status:** EJECUTADO (correccion autorizada en esta tarea; solo lectura local, proveedores loopback, sin Binance, sin ordenes, sin cambios economicos ni de reglas operativas).

**3. Implementation status:** IMPLEMENTADO en `scripts/research_pilot.py`: `DECISION_FLOW_HORIZON = "1m"` y `symbol_warmup_ms = FLOW_HORIZONS_MS["1m"]` (60 s) sustituyen a `selection_seconds`; solo nuevos/reincorporados renuevan `symbol_first_seen_ms`; `_ready_symbols`/`_earliest_ready_ms` gobiernan el corte; `_symbols_evaluated_this_cycle` limita a una observacion por simbolo y ciclo; el corte se reprograma al primer calentamiento pendiente y una readiness intra-ciclo se evalua antes de la siguiente seleccion; `decision-gate-file` queda solo como control de pruebas. Estado expone `symbol_warmup_ms`, `symbol_first_seen_ms`, `symbols_evaluated_this_cycle`.

**4. Evaluation status:** PASS en loopback. `tests/test_research_pilot.py` 28 passed (7 de `TestCadenaSincronizada` adaptadas conservando sus controles) + `tests/test_recorrido_productivo.py` 6 passed (incluye reincorporacion con nuevo periodo) = 34/34; conjunto relacionado de 6 archivos 76 passed con `EXITCODE=0`. Antes: 7 failed en la base aislada y en el arbol de trabajo.

**5. Evidence:** `docs/evidence/coordinacion-20261105/` (`fallos_antes.txt`, `base_aislada_0c5bccb.txt`, `fallos_despues.txt`, `suite_completa.txt`, `suite_relacionada.txt`, `validacion_final.txt`, `traza_instancia.json`, `diagnostico.md`); `docs/DECISIONS.md` 2026-11-05; `docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md` seccion 9.7; `docs/CURRENT_STATE.md`; `docs/TASK_QUEUE.md`.

**6. Verdict:** coordinacion temporal coherente y verificable; no se declara ventaja economica ni latencia real de produccion (el calentamiento es una cota derivada de la ventana de flujo).

**7. Next step:** mantener el calentamiento de 60 s y no introducir barreras manuales; cualquier captura publica sigue requiriendo autorizacion separada.