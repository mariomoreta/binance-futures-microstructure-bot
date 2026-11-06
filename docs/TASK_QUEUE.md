# Cola vigente — objetivo operativo, 2026-11-06

`CURRENT_PHASE`: investigación de una regla operable sobre perpetuos extremos;
revisión/cierre del diseño de comprobación independiente. No es declaración de promoción formal.

`CURRENT_OBJECTIVE`: evaluar si la autoselección del universo elegible, unida a
una regla causal de dirección, entrada, stop-loss, gestión y salida, permite una
expectativa neta favorable con riesgo controlado. Más movimiento por sí solo no
satisface el objetivo. Dirección canónica: [PRODUCT_GOAL](PRODUCT_GOAL.md).

`ACTIVE_TASK`: revisar y cerrar la propuesta ya entregada por el agente en
[EXPERIMENTO_OPERATIVO_V1](EXPERIMENTO_OPERATIVO_V1.md) (`6a10c307`, no ejecutada).
Resolver solo sus bloqueos declarados, sin reiniciar el diseño. Entregables: mapa breve de capacidades reutilizables,
una hipótesis/regla candidata para revisión, datos y ejecución necesarios,
períodos, comparadores/cobertura, métrica principal y criterio de
continuar/reformular/detener/insuficiencia, presupuesto y límites. Solo diseño;
la regla y el presupuesto propuestos no quedan aprobados por documentarlos.

`NEXT_TASKS`:
1. Revisar y cerrar ese protocolo, sin otro inventario general ni expansión
   de código. Reutilizar selector, book/flow y simulación/riesgo existentes.
2. Decidir sobre la adquisición/evaluación concreta por autorización separada.
   No comenzar capturas ni cambiar parámetros/presupuestos automáticamente.
3. Ejecutado un experimento autorizado, tomar la decisión económica prevista.
   La insuficiencia no renueva automáticamente duración ni cupos.

`CLOSED`: análisis exploratorio v4 de `public-pilot-1h-20261106a`; los 168
resultados de 60m existen, no es necesario repetir para completarlos. Los
límites de cobertura, costes, precios e identidad siguen explícitos; ver
[CURRENT_STATE](CURRENT_STATE.md) e informe v4.

`OUT_OF_SCOPE`: ampliación de dashboard/Paper Lab, nuevos gestores, indicadores,
conectores/IA y auditorías generales. Solo arreglos materiales que identifiquen
qué experimento o decisión económica desbloquean; límites no decisivos se
registran sin ciclos indefinidos de reparación.

Este bloque sustituye las prioridades operativas de las colas históricas
inferiores; no borra evidencia, no cambia SUCCESS_GATES y no interrumpe al agente
en curso. Preservar `opencode.json`, archivos ajenos, DBs y servicios existentes.

---

## Piloto prospectivo v1 — propuesta pública 1 h + 70 min (2026-11-05)

`CURRENT_PHASE`: investigación local del universo/liquidez (solo lectura, sin
Binance, sin órdenes; presupuesto público requiere autorización separada).

`CURRENT_OBJECTIVE`: cumplido — ejecutar UNA vez la propuesta pública 1 h + 70 min
(public-pilot-1h-20261106a, SHA f122fbc). La corrida cerró con causa acreditada
(duración) y código de salida 0. Resultado: 12 ciclos, 12 evaluaciones,
216 observaciones (168 aptas, 48 descartadas con motivo explícito), 504
resultados (168 × 3 horizontes, 0 pendientes). Consumo dentro de límites:
HTTP 641 attempts/1 109 weight/0 retries (máx 2000/5000/50); WS 20 conexiones/
960 114 mensajes/0 reconnects (máx 5 000 000/20); almacenamiento 5,2 MB/128 MB
(3,9 %). 0 fechas futuras (protocolo v3). Traza:
docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/.
Dataset fuera de Git; manifiesto y hashes publicados.

`ACTIVE_TASK`: cerrado — captura pública ejecutada una sola vez; resultado
publicado y reconciliado (docs/evidence/coordinacion-recepcion-20261106/
captura_publica_20261106a/). No se relanzó ni se creó otro run_id.
Publicados originales: manifiesto.json, resumen.json, status.json (SHA-256
verificados contra origen). Reconciliaciones: intervalos entre decision_ms
(intervalo 2→3 = 283 007 ms, desviación 16 993 ms), peso HTTP (1 109 y
6 890 son contadores internos con tabla ASSUMED_WEIGHTS, no cabeceras
Binance), código de salida UNKNOWN (no hay evidencia directa).
Recorrido productivo reproducido localmente con proveedores loopback y el CLI
del piloto (`tests/test_recorrido_productivo.py`, 6 pruebas): creación →
selección → motores/suscripción → recepción confirmada → evaluación automática.
**Coordinación automática corregida en `scripts/research_pilot.py` (2026-11-05, protocolo de captura 3 desde 2026-11-06):**
`symbol_warmup_ms = FLOW_HORIZONS_MS["1m"]` (60 s), independiente de
`selection_seconds`; solo entradas/reincorporaciones renuevan
`symbol_first_seen_ms`; el primer corte espera cobertura observada real
(ventana de flujo completa del motor y ambas fuentes frescas), no el instante
nominal `first_seen + 60 s`: si aún no hay cobertura se reprograma dentro del
mismo bucle con espera máxima explícita (`WARMUP_MAX_WAIT_MS = 60 s`) y, al
agotarla, se evalúa con motivo explícito del motor sin marcar apto nada sin
datos. Los datos se publican/confirman antes de alcanzar el corte, sin
`decision-gate-file` en el camino productivo. Versión del protocolo de captura:
`capture_protocol_version=3`. Se mantienen todos los límites, tolerancias,
selección research-selector-v2 y definición de precios.
`tests/test_research_pilot.py` 28 passed (incluye las 7 de
`TestCadenaSincronizada`, adaptadas conservando sus controles) +
`test_recorrido_productivo.py` 6 passed (reincorporación con periodo nuevo y
fuente ausente con espera acotada) +
`test_aceptacion_coordinacion_recepcion.py` 1 passed (corte con recepción
cronológica y evidencia de fechas futuras cero) +
`test_tres_ciclos_decision.py` 1 passed (3 ciclos × 18 símbolos, 54
observaciones) = 36/36 en los archivos del piloto y el recorrido; conjunto
relacionado 78 passed, `EXITCODE=0`.
- Renovación del ciclo de decisión (2026-11-06): en el limiar de cada ciclo
  de decisión los símbolos seguidos recuperan su oportunidad de evaluación;
  dentro del ciclo los reintentos de calentamiento no la renuevan y la selección
  no decide si hay nueva evaluación.
- Captura p�blica public-pilot-1h-20261106a (2026-11-06): ejecuci�n �nica
  autorizada, SHA f122fbc, 3600 s captura + 4200 s settle, 12 ciclos, 12
  evaluaciones, 216 observaciones (168 aptas, 48 descartadas con motivo
  explícito), 504 resultados. Consumo dentro de l�mites: HTTP 641 attempts/
  1109 weight/0 retries; WS 20 conexiones/0 reconnects; almacenamiento
  3.9% del tope. 0 fechas futuras. Traza:
  docs/evidence/coordinacion-recepcion-20261106/traza_captura_publica_20261106.md.
Cero órdenes, cero claves privadas, cero cambios de estrategia ni tolerancias.

`NEXT_TASKS`:
1. Mantener `max_data_age_ms=5000`; no tocar dashboard 3020, servicio 8792,
   `opencode.json` ni archivos ajenos; no relanzar la corrida ni crear otro
   run_id.
2. No interpretar retornos brutos como P&L ni presentar la captura como
   suficiencia del dataset.
3. Siguiente paso que más reduciría incertidumbre: repetir la captura con cierre
   acreditado y settle completado para 60m (para tener denominador completo en
   60m y en candidatos/comparadores), sin cambiar reglas ni tolerancias. No se
   repite automáticamente solo porque falte 60m: primero se define el problema
   que resolvería la adquisición.
4. (CERRADO 2026-11-05) Las 7 pruebas de `TestCadenaSincronizada` quedaron
   adaptadas al calentamiento de 60 s y pasan conservando sus controles; no
   queda reescritura pendiente. Cualquier nueva captura sigue requiriendo
   autorización explícita y no se relanza automáticamente.

**Análisis offline research/universe-liquidez-v1 (v4) — completado 2026-11-06.**
Script `scripts/analisis_universo_liquidez_v2.py`, pruebas
`tests/test_analisis_universo_liquidez_v2.py` (16 passed), tabla e informe en
`docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/`.
Embudo reconstruido desde registros de ciclo con vínculo
seleccion_ms==reference_ms: 240 seleccionados (144 candidate + 96 comparator),
24 selecciones sin observación emitida, 216 observaciones emitidas (168 aptas,
48 descartadas), 504 resultados (168 × 5m/15m/60m). Asociación
flujo/profundidad: 3 observaciones excluidas por importe bruto negativo
(error de punto flotante ~1e-14), parejas válidas 165/horizonte (no 168);
identidad de corrida es UNKNOWN (registros sin campo run_id); duplicados y
mezcla de corrida son controles separados. Diferencia
candidatos-comparadores positiva en los 3 horizontes (+0,33 pp a 5m, +0,92 pp
a 15m, +3,23 pp a 60m) pero con cobertura asimétrica de comparadores (42 aptas
vs 126 candidate; ciclos 1/7/9/11 con un solo comparador apto) y mediana de
candidatos inferior a comparadores a 60m (0,56 % vs 0,61 %). Asociación
exploratoria flujo/profundidad débil-positiva (Pearson +0,037 / +0,112 /
+0,144). `neto_estado=UNKNOWN` en los 504. Sensibilidad reproducible por
símbolo: AKEUSDT y JCTUSDT concentran parte del resultado; la diferencia
conserva signo al excluir cualquier símbolo. Los 168 resultados de 60m ya
existen; no se recomienda repetir la captura solo para completarlos.

5. (DISEÑO DE ALCANCE, no ejecutado) Protocolo de experimento operativo v1
   en `docs/EXPERIMENTO_OPERATIVO_V1.md`: tabla de capacidades existentes
   (selector, RULE-CAUSAL-V1, motor paper/backtest, costes, trazabilidad),
   hipótesis operativa única (continuación, regla candidata para revisión),
   diseño de comprobación independiente y acotada (3 ventanas separadas,
   presupuesto propio, niveles A/B/C de decisión), sin ejecutar ni abrir
   Binance. Pendiente de autorización de alcance y presupuesto separados.

## Piloto prospectivo v1 — política de pendientes y publicación (2026-11-05)

`CURRENT_PHASE`: investigación local del universo/liquidez (solo lectura, sin
Binance, sin órdenes; presupuesto público requiere autorización separada).

`CURRENT_OBJECTIVE`: cumplido — publicar el trabajo existente en la rama y
dejar inequívoca la política de pendientes, sin abrir otro bloque de
infraestructura.

`ACTIVE_TASK`: cerrado — `scripts/research_pilot.py` distingue fin normal de
captura (el settle solo madura lo ya programado), fin de settle (pendiente con
causa), parada explícita (`--stop-file` en pruebas; SIGINT/SIGTERM en
producción) y presupuesto agotado (bloqueo antes del transporte).
`tests/test_research_pilot.py` 27 passed en ese bloque (28 con la regresión de
rotación de 2026-11-05); evidencia en
`docs/evidence/research/universe_liquidity_v1/pilot_sync/pytest_pendientes.txt`.
sin cambios de tolerancias, presupuestos, estrategia ni conexiones públicas.

`NEXT_TASKS`:
1. Revisar el presupuesto público concreto (§9.3) para su autorización separada;
   no ejecutar ventana pública sin ella.
2. Mantener `max_data_age_ms=5000`; no ajustar el reloj para forzar aptas.
3. No tocar dashboard 3020, servicio 8792, `opencode.json` ni archivos ajenos.

## Piloto prospectivo v1 — sincronización reloj/prueba (2026-11-04)

`CURRENT_PHASE`: investigación local del universo/liquidez (solo lectura, sin
Binance, sin órdenes; presupuesto público requiere autorización separada).

`CURRENT_OBJECTIVE`: cumplido — eliminar la carrera reloj/proveedor en la cadena
completa y demostrar frescura por fuente, ventana completa y horizontes
5m/15m/60m sin relajar tolerancias.

`ACTIVE_TASK`: cerrado — `scripts/research_pilot.py` acepta `--status-file` y
`--decision-gate-file` (solo `--clock manual`); `tests/test_research_pilot.py`
reescrito con pasos explícitos fijar instante → publicar → confirmar
procesamiento → autorizar evaluación → avanzar (23 passed). Evidencia en
`docs/evidence/research/universe_liquidity_v1/pilot_sync/`.

`NEXT_TASKS`:
1. Mantener `max_data_age_ms=5000`; no ajustar el reloj para forzar aptas.
2. No ejecutar contra Binance sin autorización separada del presupuesto (§9.3).
3. Resuelto (2026-11-05): el settle por parada de duración madura los
   resultados ya programados; lo no resuelto al agotarse el settle queda
   `pendiente` con causa. Ver bloque superior.

## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `bf974f2`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo autorización
explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cumplido - corregir semántica de costes y verificar aceptación
local integrada.

`ACTIVE_TASK`: cerrado - costes corregidos (estado autoritativo, no _executed > 0),
regresiones añadidas, aceptación A-J 11/11 PASS, evidencia publicada.

`NEXT_TASKS`:
1. 3020 dejado disponible con build verificado y sin demo activa.
2. Servicio 8797 detenido (residual de prueba, no afirmarse "todos los procesos
   propios terminados").
3. No bloqueantes pendientes.

## Corrección semántica de costes y aceptación A-J del dashboard (base `bf974f2`)

## Corrección semántica de costes y aceptación A-J del dashboard (2026-11-03, base `ead35d2`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo autorización
explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cumplido - corregir semántica de costes y verificar aceptación A-J
desde el navegador real.

`ACTIVE_TASK`: cerrado - costes corregidos (estado autoritativo, no _executed > 0),
regresiones añadidas, aceptación A-J 11/11 PASS, evidencia publicada.

`NEXT_TASKS`:
1. 3020 dejado disponible con build verificado y sin demo activa.
2. Servicio 8797 detenido (residual de prueba, no afirmarse 'todos los procesos
   propios terminados').
3. No bloqueantes pendientes.

## Corrección semántica de costes y aceptación A-J del dashboard (base `ead35d2`)

## Recorrido visible en dashboard V2 - /market-lab (2026-11-03, base `2e3830a`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo autorización
explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cumplido - llevar el recorrido backend ya acreditado al control visible del
dashboard en /market-lab.

`ACTIVE_TASK`: cerrado - implementación de interfaz, cableado a servicios existentes y aceptación
local integrada (11/11 PASS desde navegador real).

`NEXT_TASKS`:
1. Sesión dejada abierta y congelada (posición paper simulada, sin orden real): conservar, no
   inventar salida/comisión/realizado.
2. 3020 dejado disponible con build verificado y sin demo activa.
3. No bloqueantes: literal histórico del detalle `build_served` ("árbol e2243c9").

## Recorrido visible en dashboard V2 - implementación (base `2e3830a`)

## Recorrido visible en el dashboard V2 - /market-lab (2026-11-03, base `4b35d2c`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo autorización
explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: llevar el recorrido backend ya acreditado al control visible del
dashboard en /market-lab: sesión → datos nuevos → evaluación con decisión y motivo →
señal pendiente → posición paper.

`ACTIVE_TASK`: implementar interfaz, cableado a servicios existentes y aceptación local
integrada (pruebas, typecheck, lint, build, evidencia reproducible).

`NEXT_TASKS`:
1. Verificar navegación principal → /market-lab con acceso al recorrido.
2. Aceptación local desde el navegador (A-J): no arranca procesos al abrir, un solo arranque,
   datos nuevos cambian gráfico/evaluación sin recargar, SIN_ENTRADA con motivo, señal
   pendiente vs fill, recarga sin duplicados, detener conserva posición, fuente caída retira
   LIVE, limpieza de procesos propios.
3. Tipo de cambio, lint y build pasan; pruebas apropiadas a los cambios.
4. Commit selectivo y push normal en la misma rama (sin integrar a main).
5. Dashboard disponible en 3020 con entorno canónico limpio y sin demo activa.

## Reconciliación de `eng-run-public-20261102d` completada (2026-11-03, base `88c5d2c`)

## Reconciliación de `eng-run-public-20261102d` completada (2026-11-03, base `88c5d2c`)

`ACTIVE_TASK`: cerrado - reconciliación documental de la ventana pública (addendum publicado; sin cambios de
código, sin repetir ventana, 8792 y dashboard 3020 preservados, `opencode.json` fuera de los commits).

`NEXT_TASKS`:
1. Sesión abierta y congelada (posición paper-lab simulada, sin orden real): conservar, no inventar salida/comisión/realizado.
2. Siguiente bloque de producto propuesto: llevar el recorrido ya acreditado al control visible del dashboard (Dashboard V2).
   No implementar en este bloque.
3. No bloqueantes: literal histórico del detalle `build_served` ("árbol e2243c9") y reparar la fixture desfasada de
   `tests/test_engineering_live_window_local.py`.

## Ventana pública `eng-run-public-20261102d` completada - PASS (2026-11-03, base `d307fc7`)

## Ventana pública `eng-run-public-20261102d` completada - PASS (2026-11-03, base `d307fc7`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cumplido - ejecutar UNA ventana pública autorizada y acreditar el recorrido:
HUB → SSE → adaptador → cierre admitido → avance de T → evaluación vinculada con decisión y motivo.

`ACTIVE_TASK`: **cerrado** - ventana pública ejecutada una sola vez, sin relance, sin cambios de código durante la ventana, 8792 y dashboard 3020 preservados, `opencode.json` fuera de los commits.

`NEXT_TASKS`:
1. Sesión abierta y congelada (posición paper-lab simulada, sin orden real): conservar, no inventar salida/comisión/realizado. No requiere acción inmediata.
2. No bloqueantes pendientes: literal histórico del detalle `build_served` ("árbol e2243c9") y reparar la fixture desfasada de `tests/test_engineering_live_window_local.py`.

## Resultado ventana pública única `eng-run-public-20261102c` y corrección local SSE (2026-11-02, bases `a11c02e` / `4e141a7`)

## Corrección local del tramo SSE completada (2026-11-02, base `4e141a7`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado - reproducir y corregir localmente el tramo
HUB → SSE → adaptador → cierre admitido → T → evaluación, con el arnés,
servicios y motor EXISTENTES (sin Binance, sin ventana pública):

1. Diagnóstico por relojes (conexión HTTP / espera entre lecturas SSE /
   silencio de mercado / deadline global) con su configuración exacta y
   lectura de la ventana `20261102c`; no se atribuyó todo a TimeoutError ni
   se aumentó límite alguno.
2. Defecto raíz confirmado: `events_processed` nunca se incrementaba en
   `_run_drive_market` (falso cero); las 5 desconexiones fueron de fase
   LECTURA; la rev 2 con clock avanzado era admisión legítima de un cierre
   real (no transición oculta).
3. Corrección mínima: clasificación de desconexiones, contadores reales
   (`events_processed`, `cierres_admitidos`), `gates_rechazadas` duraderas,
   identidad en evaluaciones, drain acotado en el HUB; motor intacto.
4. Veredicto del arnés endurecido (cierres + evaluación vinculada
   obligatorios; SIN_ENTRADA con motivo válida; sin revisiones = UNKNOWN).
5. Reproducción local del adaptador productivo: heartbeats estables,
   silencio con clasificación y reconexión acotada, recuperación del cierre
   pendiente única con contadores por alcance.
6. 98 pruebas PASS; evidencia loopback en
   `docs/evidence/engineering-sse-local-20261102b/`.

`ACTIVE_TASK`: **cerrado** (sin Binance; 8792 y dashboard 3020 intactos;
`opencode.json` fuera de los commits).

`NEXT_TASKS`:
1. Solicitar **nueva autorización** explícita del operador para UNA ventana
   pública con un `run_id` NUEVO (no reutilizar
   `eng-run-public-20261102c`, presupuesto agotado 7/7) y acreditar el
   recorrido completo con el veredicto corregido (adhoc: cierre nuevo
   admitido POR la sesión + evaluación vinculada).
2. Revisiones posteriores (no bloquean): literal histórico del detalle
   `build_served` ("árbol e2243c9") y
   `tests/test_engineering_live_window_local.py` (fixture desfasada).

## Resultado ventana pública `eng-run-public-20261102c` y siguiente tarea (2026-11-02, base `a11c02e`)

## Resultado ventana pública `eng-run-public-20261102c` y siguiente tarea (2026-11-02, base `a11c02e`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: EJECUTADA la única ventana pública autorizada
`eng-run-public-20261102c` con el arnés corregido en a11c02e. Presupuesto
exacto 7/7 (5 `/time` + 2 klines), adquisición 174.5 s < 180 s, sesión creada
(`PL-MINAUSDT-LONG-1793669229096-9d935300`,
`config_hash=4a339c046cc3ad63`), contexto cerrado no-futuro correcto
(600 velas contiguas, vela en curso excluida), WS pública sin reconexiones y
3 cierres nuevos admitidos POR EL HUB. La cadena se rompió en el adaptador
SSE de ingeniería (60/237 frames, 5 desconexiones `TimeoutError`, conexión
efectiva a los ~147 s): `eventos_procesados=0`, sin evaluación ni decisión.
Veredicto global: **FAIL** (`EVALUACION_NO_ALCANZADA`); el PASS interno del
arnés no acredita el recorrido completo. Evidencia en
`docs/evidence/engineering-live-public-20261102c/` (`RESULTADO.md`,
`summary.json`, …). Limpieza verificada: 8791/8797/18799/18800 libres,
pid-file 8792 intacto, DBs canónicas hash-igualadas, 3020 disponible.

`ACTIVE_TASK`: **corregir el adaptador SSE del servicio de ingeniería**
(`engineering-session-service`): por qué conecta ~147 s tarde, por qué se
repite `TimeoutError: timed out` (5 desconexiones) y por qué los 60 frames
tardíos no incrementaron `eventos_procesados` (sesión `sin_iniciar`,
`clock_ms` avanzó 1793669219999 → 1793669280000 sin evento registrado:
causa UNKNOWN). Trabajo local con loopback; sin Binance.

`NEXT_TASKS`:
1. Corrección local del adaptador SSE + respuesta de `eventos_procesados`
   con pruebas loopback del recorrido completo (WS → servicio → SSE →
   adaptador → evento → evaluación).
2. Solicitar **nueva autorización** explícita del operador para UNA ventana
   pública con un `run_id` NUEVO (no reutilizar `eng-run-public-20261102c`,
   presupuesto agotado 7/7) y acreditar el cierre nuevo admitido por la
   sesión, T anterior/nuevo por evento, evento disparador, contador de
   evaluaciones y decisión con motivo.
3. Revisiones posteriores (no bloquean): literal histórico del detalle
   `build_served` ("árbol e2243c9") y
   `tests/test_engineering_live_window_local.py` (fixture desfasada).

## Corrección del contexto cerrado + pid-files aislados (2026-11-02, base `f033c06`)

## Corrección del contexto cerrado + pid-files aislados (2026-11-02, base `f033c06`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — corrección en código del arnés
(`scripts/engineering_live_window.py`) que causó el FAIL de
`eng-run-public-20261102b`, SIN ejecutar Binance ni nueva ventana pública:

1. Contexto cerrado: la referencia sale del reloj público sincronizado del
   servicio de ingeniería con su validez comprobada
   (`public_sincronizado`/`available`/`offset_ms` finito/`age_ms` presente;
   nunca el reloj del navegador). La ventana termina en la última vela cuyo
   cierre ya ocurrió (el cierre exactamente igual a la referencia se admite)
   y cada fila recibida se valida individualmente (`close_time` posterior a
   la referencia → excluida como no disponible, nunca OHLC en contexto
   cerrado). Identidad por símbolo, continuidad y calentamiento conservados.
2. Si tras filtrar falta contexto: aborta con motivo explícito
   (`CONTEXTO_*`) sin nuevas descargas automáticas y SIN crear sesión
   (`_prepare_context` entre arranque de servicios y `_create_session`).
3. Aislamiento: `--pid-file` explícito y exclusivo por servicio y corrida
   (`sessions_dir/market-service.json`,
   `sessions_dir/engineering-service.json`); `data/market-stream/service.json`
   del 8792 intacto; limpieza borra solo lo propio.
4. Pruebas locales (cero Binance, loopback): 7 PASS nuevas
   (`tests/test_engineering_context_closed.py`), recorrido local completo
   2 PASS (`tests/test_engineering_live_window_local_recorrido.py`),
   regresiones 32 PASS (`test_engineering_clock_readiness.py` +
   `test_engineering_clock_budget.py`) y 40 PASS
   (`test_market_stream.py`).

`ACTIVE_TASK`: **cerrado** (sin Binance; sin tocar 8792, 3020 ni DBs
canónicas; `opencode.json` se mantiene fuera de los commits).

`NEXT_TASKS`:
1. Solicitar **nueva autorización** explícita del operador para UNA ventana
   pública con un `run_id` NUEVO (no reutilizar
   `eng-run-public-20261102b`, presupuesto agotado 7/7).
2. En esa ventana: acreditar sesión creada, cierre nuevo admitido, T
   anterior/nuevo, evento disparador, contador de evaluaciones y decisión
   con motivo. Sin relanzamiento; FAIL/ERROR/UNKNOWN con motivos.
3. Pueden quedar como revisiones posteriores (no bloquean): el literal
   histórico del detalle `build_served` («árbol e2243c9») y la respuesta de
   `tests/test_engineering_live_window_local.py` (fixture desfasada).

## Ventana pública única 2026-11-02 — FAIL por vela en curso en el contexto (base `d2ca1cb`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado con **FAIL** — la ventana pública única
autorizada (run_id `eng-run-public-20261102b`, deadline 180 s) no creó
sesión: el contexto incluía la vela del minuto en curso y el servicio la
rechazó con `VALIDATION_ERROR: CONTEXTO_FUTURO`. Sin sesión no hay cierre
nuevo, T, evento, contador ni decisión. Reloj público válido (5/5 muestras),
presupuesto 7/7 (5 `/time` + 2 `klines`), limpieza y DBs canónicas
correctas. Detalle: `docs/evidence/engineering-live-public-20261102b/RESULTADO.md`.

`ACTIVE_TASK`: **cerrado** (sin relanzamiento; presupuesto del run_id
agotado 7/7).

`NEXT_TASKS`:
1. Corregir `scripts/engineering_live_window.py::_load_recent_context` para
   excluir toda vela con `close_time_ms` posterior a la referencia (nunca
   enviar la vela en curso) y añadir una prueba local que lo fije.
2. Verificar en local (transporte local/loopback, cero Binance) que el
   contexto enviado solo contiene velas cerradas y que la sesión se crea.
3. Solicitar **nueva autorización** explícita para otra ventana pública con
   un `run_id` NUEVO; no reutilizar `eng-run-public-20261102b`.
4. No declarar completo el recorrido público hasta acreditar sesión, cierre
   nuevo, T anterior/nuevo, evento, contador y decisión con motivo.

## Modo «Demostración local — datos simulados» + reconciliación por evidencia (2026-10-28, base `643e0b9`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — modo explícito «Demostración local — datos
simulados» desde la UI (sin comandos ni variables manuales): recursos
exclusivamente propios identificados y acotados (productor WS loopback con
parada automática, 8791 `--transport local` con `--max-seconds`, 8797 con
identidad verificada), guardas anti doble-clic, rechazo explícito de fuente
extraña, aviso `FUENTE NO DISPONIBLE` ANTES de crear sesión (sin
huérfanas), parada solo con identidad doble verificada (manifest +
pid-file) y pérdida de feed registrada dentro de la sesión. Además, el
controlador reconcilia el pid-file SOLO con evidencia verificable (health
canónico + sessions_dir canónico + pid vivo + cmdline del SO); sin la
cadena completa rechaza sin adoptar ni matar. Evidencia acotada:
`docs/evidence/engineering-local-demo-2026-10-28/summary.json`
(BUILD_ID `wF9Xf3Orb5Af7vgwp8_f4`). Detalles: V1 §11.7–§11.8.

`ACTIVE_TASK`: **cerrado**.

`NEXT_TASKS`: revisión del operador de las capturas
`shot-01..07` de esta entrega; a continuación, el objetivo ya declarado:
el mismo recorrido con datos públicos (8791 `--transport public`),
con presupuesto y autorización explícitos separados. NO declarar completo:
selector multiactivo, riesgo completo, paper prospectivo, estrategia
rentable.
E2 verificado PASS (14/14 en verificación integrada E2-gridgap): decisión
`ENTRADA_SIMULADA`, fill simulado, gestión y cierre por regla horizon.
GRID_GAP resuelto (productor: `anchor_open=start_open`, `BACKFILL_PACE_S=1.0`;
plomado `from_ms`/`to_ms` al servicio de mercado).

## Entrega utilizable del transporte live local + identidad de la evidencia (2026-10-28, base `efa7700`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — entrega utilizable del bloque live local:
dashboard 3020 en producción (BUILD_ID `0-HCAplwLhRPpYHuuAPC2`, árbol
`efa7700`), servicios verificados sin tocarlos (8797 ready con pid-file
reconciliado; 8792 identificado como LOCAL y NO usado; 8791 caído con
condición explícita al pulsar «Iniciar»), e identidad de la evidencia
aclarada (la aceptación corrió sobre árbol sin commitear sobre `90b3c9b`;
implementación probada = commits `b85f389`+`5c9f409`+`557a1a8`).

`ACTIVE_TASK`: **cerrado**.

`NEXT_TASKS`: **próximo objetivo concreto** — adaptar y verificar este
mismo recorrido (`/market-lab` → «Iniciar sesión») con datos públicos
(8791 `--transport public`), con presupuesto y autorización separados del
operador (incluye acreditación de recepción Binance real, reparación REST,
churn WS ~9 s, ciclo SSE de 10 s). NO declarar completo: selector
multiactivo, riesgo completo, paper prospectivo, estrategia rentable.

## Transporte `market_stream` en vivo de ingeniería: aceptación local PASS (2026-10-28, base `90b3c9b`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — transporte `market_stream` en vivo para la
sesión de ingeniería (backend + frontend) y aceptación LOCAL completa con
navegador real y productor SSE local determinista, sin Binance público.
Evidencia: `docs/evidence/engineering-live-local-2026-10-28/summary.json`
(12/12 checks, 6 capturas, 8 reconexiones, 0 peticiones externas,
`trial_sessions: []`, 3020 restaurado). Incluye el arreglo del defecto del
explorador canónico (lectura por cola con regresión) y el arnés
`scripts/engineering_live_local_acceptance.py`.

`ACTIVE_TASK`: **cerrado**.

`NEXT_TASKS`: revisión del operador de las capturas shot-01..06; para
feed público (REQUIERE autorización explícita): acreditación de recepción
Binance real, reparación REST, tratamiento del churn WS ~9 s y del ciclo
SSE de 10 s del adaptador; opcional: recorrido con datos nuevos continuos
(ventana aparte).

## Inicio explícito completo desde la UI + arreglo del defecto SSE (2026-10-28, base `0bf96c6`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — «Iniciar sesión» como inicio completo
explícito (comprueba servicio → arranca la instancia canónica vía BFF con
readiness+identidad → crea e inicia UNA sesión), directorio de sesiones
dedicado por defecto (bug del `ROOT` corregido), y causa/arreglo del
defecto del panel de flujo (`ERR_INCOMPLETE_CHUNKED_ENCODING`: timeout del
BFF + `bodyTimeout` de undici; reconexión con misma identidad; 8792
intocado). Evidencia:
`docs/evidence/engineering-explicit-start-2026-10-28/acceptance-summary.json`
(casos A–G, navegador real, incl. fallo de arranque sin huérfanos).

`ACTIVE_TASK`: **cerrado**.

`NEXT_TASKS`: revisión del operador de las capturas; recorrido con datos
nuevos continuos (ventana aparte, autorización explícita — la fuente
aggTrade local lleva ~26 h sin inyectar); opcional: map explícito
`ENGINEERING_SERVICE_DOWN` en el BFF (hoy el fetch de Node oculta `code`
y el banner muestra `ENGINEERING_PROXY_ERROR`, igual 503 con error
visible); opcional: investigar el artefacto anómalo de la primera carrera
de doble clic (archivo vacío sin sufijo; causa UNKNOWN, no reproducible,
`load_session` lo rechaza).

## Acceso operativo y publicación en revisión (2026-10-28, base `5f24807`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — acceso operativo del bloque de autonomía en
backend verificado desde el estado entregado (8797 detenido): fallo visible y
sin duplicados con el servicio abajo; arranque por CLI canónico declarado
limitación deliberada; semántica sesión/pestaña/servicio verificada
punto por punto; publicación de la rama en
`review/o1-funcional-v2-observacion` por fast-forward autorizado (sin
reset ni force).

`ACTIVE_TASK`: **cerrado**. Evidencia:
`docs/evidence/engineering-backend-2026-10-28/operational-access-2026-10-28.json`
+ captura `ver-case-1-detener-tras-recuperar.png`. Casos: servicio abajo
(error `data-testid=session-error`, sin procesos lanzados, sin duplicados);
S1 ciclo completo autónomo (`SESSION_CLOSED`, red 1 create + 1 control +
GETs); S2 cierre de pestaña (backend rev 7→31→38, `SESSION_CLOSED`);
SERVICE_STOP con drive corriendo (estado en disco intacto, rev 11, sin
salida inventada); reinicio + recuperación + «Detener sesion» → `detenida`
rev 12 con posición preservada. Servicios al cierre: 8797 detenido,
sesiones de ensayo eliminadas, dashboard 3020 con
`r5poURhuj3RQc4CjC6Kyz`, 8792 preexistente sin tocar.

`NEXT_TASKS`: defecto abierto del panel de flujo (`ERR_INCOMPLETE_CHUNKED_ENCODING`
en `/api/v1/market-flow/stream`) — decidir arreglo; revisión del operador
de las capturas; recorrido con datos nuevos continuos (ventana aparte,
autorización explícita); opcional: map explícito `ENGINEERING_SERVICE_DOWN`
en el BFF (hoy el fetch de Node oculta `code` y el banner muestra
`ENGINEERING_PROXY_ERROR`, igual 503 con error visible).

## Autonomía de la sesión de ingeniería en backend (2026-10-27/28, base `0aa98f5`, rama `feat/ingenieria-autonoma`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — la conducción de la sesión de ingeniería vive
en un servicio backend Python residente (`engineering-session-service/v1`,
port 8797 por defecto) que reutiliza `paper_lab_engine` y avanza SOLO por
eventos REVEAL del transporte local; el navegador es observador y NO
programa el avance. Cerrar el navegador no detiene la sesión; detener con
posición abierta congela sin salida inventada; `SIN_ENTRADA` reevalúa ante
nueva información y `DESCARTADO` es terminal.

`ACTIVE_TASK`: **cerrado**. Implementación:
`src/microstructure_probe/engineering_session_service.py` + CLI
`scripts/engineering_session_service.py`; BFF
`frontend/src/app/api/v1/engineering-sessions/**`; cliente
`frontend/src/lib/session-lab.ts`; componente observador
`frontend/src/components/session-lab/EngineeringSession.tsx` (chip de
conducción + causa, timer del navegador eliminado). Pruebas: backend
`tests/test_engineering_session_service.py` 8/8 (abstención temporal →
confirmación → entrada/salida única por evento; DESCARTADO terminal;
409/400/404; persistencia entre reinicios del controlador; `/shutdown`);
frontend `engineering-session.test.tsx` 8/8; Python completo 1530 passed /
2 skipped (corregidos 3 fallos PREEXISTENTES de la base: causalidad del
dict público y presupuesto de fanout/benchmark interno de la ventana);
frontend 604 passed / 1 skipped; `tsc`/`eslint` 0. Aceptación navegador
real PASS en `docs/evidence/engineering-backend-2026-10-27/` (S1 ciclo
autónomo; S2 pestaña cerrada → backend cierra solo y reabrir recupera; S3
detener con posición → `detenida` sin salida inventada; S4 prefijo B →
cierre por horizonte; red: solo GET tras recuperación, 0 POST de avance).
Detalle y distinción contra el modo autónomo anterior (replay-autoavance
React): `docs/ENGINEERING_SESSION_BACKEND_V1.md`.

`NEXT_TASKS`: revisión del operador de las capturas
(`eng-*.png`); recorrido con datos nuevos continuos (ventana aparte,
autorización explícita); decidir si el error de consola preexistente
ERR_INCOMPLETE_CHUNKED_ENCODING (`/api/v1/market-flow/stream`) merece
arreglo; resto del backlog (ver FEATURE_BACKLOG).

## Modo autónomo de la sesión de ingeniería (2026-10-27, base `9a24308`, rama `feat/ingenieria-autonoma`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrado — la sesión de ingeniería avanza sola con un
solo "Iniciar sesion" (entrada pendiente → fill simulado → gestión → cierre)
reutilizando el endpoint `/step` de "Paso a paso"; el navegador solo observa
y solicita iniciar/detener; abstención sin autonomía; fin de transporte con
causa visible; parada sin cierre inventado; recarga sin duplicar efectos.

`ACTIVE_TASK`: **cerrado**. Implementación en
`frontend/src/components/session-lab/EngineeringSession.tsx` (bucle autónomo:
`AUTONOMOUS_STEP_DELAY_MS=1500`, `MAX_AUTONOMOUS_STEPS=200`, referencias
anti-closure, limpieza al desmontar, botones manuales deshabilitados durante
la autonomía); corrección de selección de prefijo antes de iniciar
(`changePrefix` ya no ignora la elección sin sesión). Pruebas: unidad A/B/C
en `frontend/src/test/engineering-session.test.tsx` (8/8); suite frontend
596 passed / 1 skipped; `tsc`/`eslint` 0. E2E navegador: A autónomo completo
(ABIERTA→CERRADA por horizonte, sin botones), B abstención sin chip ni pasos,
D recarga con posición abierta sin duplicar, E detener con posición congelada
(paso posterior no-op). C vía HTTP (sin avance de reloj, sin entrada) +
unidad de la causa visible. Evidencia: `docs/evidence/INGENIERIA_AUTONOMA_*.png`.
Pendiente documentado: 2 fallos PREEXISTENTES de la suite Python en HEAD
(test_paper_lab_engine velas solo-open; test_market_stream_window FAIL≠UNKNOWN)
— fuera de alcance de este bloque, motor y rutas sin tocar.

`NEXT_TASKS`: revisión del operador de las capturas; decidir los 2 fallos
preexistentes de la suite Python; recorrido con datos nuevos continuos
(ventana aparte, autorización explícita); resto del backlog (ver
FEATURE_BACKLOG).
## Operativo restaurado tras el bloque de contexto BTC (2026-10-26, HEAD `3c2e7ab`, sin Binance)

El dashboard canónico se restauró en 127.0.0.1:3020 tras el trabajo del
bloque, con entorno limpio (sin `MICROPROBE_*`/`MARKET_EXPLORER_*`),
frontend recompilado (`next build`) y el servidor previo detenido:
node **8776**, `Ready`, escucha `127.0.0.1:3020`. Verificado: `/market-lab`
y `/` HTTP 200; catálogo canónico solo desde caché (932 contratos, TTL 6 h
vigente; `market_fetch_ledger` sin crecimiento); servicio local de datos
**detenido** (`/api/v1/market-stream/status` → `available:false`); sin
escuchas en 8792/65375; único proceso `next` del sistema = el canónico.
Evidencias intactas en sus rutas aisladas; DBs canónicas sin escritura.

Separación de acreditaciones (obligatoria al leer cualquier informe):
**indicadores `market-indicators/v1` PASS con transporte local**; **contexto
BTC compartido `market-btc-context/v1` PASS con transporte local**;
**recepción incremental Binance NO acreditada aún** (ventana requiere
autorización explícita); **inspección visual** hecha por el agente y
**separada del DOM**; revisión del operador de las capturas sigue pendiente
en TASK_QUEUE. Servidor final: SHA `3c2e7ab`, BUILD_ID
`Bibj_gkaZK9si2ABtSsAb`.

## Contexto BTC compartido `market-btc-context/v1` (2026-10-26, base `3c2e7ab`, sin Binance)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: bloque de contexto BTC compartido cerrado y
documentado (bloque aditivo `context_btc` + frame SSE `event: context`,
suscripción BTC compartida sin duplicar, demo de transporte local PASS,
0 peticiones públicas).

`ACTIVE_TASK`: **cerrado**. Backend `kline_btc_context.py` (`ret_btc_bps_5`,
`ret_diff_bps_5`, alineación por `open_time_ms`, `unknown(BTC_*)` sin
arrastre, base común declarada); integración `series_payload.context_btc`
(client=None, 0 upstream); frame SSE `event: context` y suscripción BTC
compartida en `market_stream_service`; frontend
`market-chart-contract.ts`/`market-stream.ts`/`use-market-stream.ts` +
`PriceChart.tsx` (badge con unidad + tira normalizada `BtcCompareStrip`).
Pruebas: 13 unidad + integración `series_payload`; 6 SSE del servicio
(snapshot, cierre token/BTC, suscripción compartida, símbolo=BTC sin
bloque, intervalo inválido). Demo
`scripts/btc_context_public_demo.py`: **PASS 12/12**, 0 peticiones
públicas (browser_external 0, ledger 0, 1 carga de página, sin recarga),
evidencia en `docs/evidence/btc-context-public-2026-10-26/`.
Documentación: `SHARED_INDICATORS_V1.md` §6, `BTC_CONTEXT_V1_PLAN.md`,
DECISIONS 2026-10-26, CURRENT_STATE, TASK_QUEUE.
Gates: backend 171 PASS, frontend 592 PASS/1 skip, `tsc`/`eslint` 0.

## market-indicators/v1: hilo incremental + demo de entrega (transporte local) PASSED (2026-10-25, base `2ffdede`, sin Binance)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrar la entrega pública de `market-indicators/v1`
(contrato verificado, hilo incremental por cierre y demo de navegador con
transporte local) y sostener las tareas top del presupuesto.

`ACTIVE_TASK`: **cerrado**. Recalculo incremental en el servicio
(`market_stream_service.py`: snapshot lleva el bloque; en cada `closed`
fusión por `open_time`, recálculo y frame SSE `event: indicators` antes de
`closed`; vela provisional excluida) + frontend sin recarga
(`applyStreamIndicators`: sanitización, guard de identidad, unión nuevo
gana, badge con unidades). Demo `scripts/indicators_v1_public_demo.py`:
**PASS 15/15** verificaciones DOM (valores badge=backend al cursor,
GAP→UNKNOWN con motivo, cierre sin reload, provisional excluido,
BTCUSDT→MINAUSDT sin arrastre), **0 solicitudes Binance** probadas (browser_external 0, ledger 0, guardia DNS), BUILD_ID
`e_lib1MO18w7gv6PJG2rm`, URL `http://127.0.0.1:3020`,
`docs/evidence/indicators-v1-public-2026-10-25/` (3 capturas + logs).
Aprendizaje de infraestructura registrado en DECISIONS: un `next start`
huérfano en 3020 con cache de otra corrida falseaba las comparaciones; la
demo ahora verifica la identidad del dashboard y aborta lo contrario.
Gates: backend 171 PASS, frontend 592 PASS/1 skip, `tsc`/`eslint` 0.

`NEXT_TASKS`:
1. **Nueva ventana Binance (solo con autorización explícita)** reutilizando
   el arnés automatizado ya implementado (`market_stream_local_acceptance.py
   --transport public`): el `FAIL` medido de 2026-10-24 se mantiene.
2. Las tareas de la sección top del presupuesto (aviso de servicio detenido,
   Next.js 16.4.1, retención de caché, `build_recovery` al
   ledger como vecino opcional) siguen vigentes tal cual.
3. Revisión visual de las 3 capturas del demo por el operador (la verificación
   DOM ya está hecha y distinguida; la visual queda en evidencia).
4. Volatilidad realizada y estructura sobre velas cerradas: siguiente
   subconjunto DESPUÉS de decidir ventana/semántica (no la heredada del feed);
   sin optimizar nada.
5. Fuentes ausentes (aggTrades/libro/OI/contexto BTC en el canal de velas)
   y F-PAPER-01: diferidos hasta nueva autorización; mantener diferido
   stops/objetivos arrastrables y móvil/Flutter.

## Indicadores compartidos — primera integración vertical (2026-10-25, base `09632f4`, sin Binance)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: primera integración vertical de indicadores compartidos
en `/market-lab` con el backend como autoridad y salida versionada única.

`ACTIVE_TASK`: **cerrado**. Inventario verificado (retornos/velocidad P1-04/05
mark price, flow P1-06 aggTrades, spread/profundidad P1-07 libro, OI P1-07
REST, VWAP P1-08 flow: ninguna de esas fuentes viaja en el canal de velas →
declinados con motivo, no derivables de OHLC; volumen relativo nuevo).
Subconjunto `market-indicators/v1` sobre velas cerradas: `log_return_bps`,
`velocity_bps_5`, `rel_volume_10`, `vwap_typical_10` + `vwap_dev_bps_10`
(aproximación típica, no el VWAP de negociación). Hueco/warmup → UNKNOWN con
motivo, sin ceros; sin lookahead; vela provisional excluida (sin indicadores
provisionales en V1); disponibilidad al cierre (`available_at_ms`). Integrado:
payload con bloque opcional, modelo con guard de identidad, badge con valores
al cursor, fusión de bloques sin recálculo, sin arrastre al cambiar
símbolo/intervalo. Precisiones de la pasada anterior documentadas:
`execution_id` es etiqueta de atribución por petición (no id de corrida; el
ámbito compartido es la ventana de 60 s del ledger, filtrada solo por tiempo)
y la automatización del navegador ya está implementada (solo falta ejecutarla
con autorización en ventana real). Pruebas: backend `test_kline_indicators` 18
+ explorador 56; frontend 51/51 en 4 suites, `tsc`/`eslint` 0. Evidencia:
`docs/evidence/indicators-v1-2026-10-25.json` (0 llamadas Binance).

## Presupuesto REST upstream — alcance verificado y corregido (2026-10-25, base `309aee1`, sin Binance)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: verificar el alcance del control de presupuesto REST y
corregir lo insuficiente reutilizando mecanismos existentes.

`ACTIVE_TASK`: **cerrado**. Verificado en `309aee1` y corregido: (1) reserva
transaccional por intento (`BEGIN IMMEDIATE`) en el ledger compartido
`market_fetch_ledger`, en lugar de contabilizar tras el envío; (2) cada
intento HTTP —páginas y reintentos— reserva ANTES del transporte
(`LedgerAttemptGate` + `UpstreamBudgetExceeded` sin abrir socket; bloqueo
auditado con `requests=0`); (3) filas persistidas y vinculadas a
`execution_id` (migración idempotente, históricas NULL = UNKNOWN);
(4) dashboard → BFF → CLI propaga `--execution-id bff-<uuid>`; (5)
defecto latente del limitador per-instancia corregido (`_window_weight` nunca
acumulaba). Alcance excluido: `build_recovery` y el régimen de peso Binance siguen
fuera del presupuesto compartido, documentado. Demostrado con transporte
local: dos procesos reales del CLI comparten límite=2 (2 upstream), tercer
intento bloqueado antes del transporte (0 hits), reintentos (500→reintento)
consumen 2 cupos y bloquean al 4º, reconstrucción del consumo desde el ledger
tras la muerte de los procesos. Baseline: 147 pruebas focalizadas PASS;
`tsc`/`eslint` 0; vitest explorador 48/48. Evidencia:
`docs/evidence/rest-budget-scope-2026-10-25.json`. 0 llamadas Binance.

**Precisiones de alcance (2026-10-25, segunda pasada):**

1. **Tres identificadores distintos, no confundir:** (a)
   `execution_id` es una etiqueta de ATRIBUCIÓN por ejecución/petición —
   `bff-<uuid>` nuevo por cada petición HTTP del dashboard al BFF, o el que
   pase el CLI — y solo sirve para reconstruir el consumo de esa ejecución
   concreta con `fetch_rows_by_execution`; (b) el identificador de **corrida**
   de observación (O1/O2, run id) es otra cosa y NO viaja en este ledger; un
   clic del dashboard y una invocación del CLI son ejecuciones distintas
   aunque pertenezcan a la misma corrida; (c) el **ámbito que realmente
   comparte el presupuesto** es la ventana móvil de 60 s del archivo del
   ledger: la consulta de reserva filtra SOLO por tiempo (`at_ms`), sin
   `execution_id`, sin símbolo y sin proceso — toda ejecución que comparta
   `market_fetch_ledger` (colas, reintentos y paginaciones incluidos) dibuja
   del mismo vaso, sea cual sea su etiqueta.
2. **La automatización del lado navegador YA está implementada**, no es
   una tarea por construir: `scripts/market_stream_local_acceptance.py`
   (2026-10-24, base `6be44b9`) conduce al navegador Playwright por el
   procedimiento completo (LIVE, captura #1, paginación, captura #2,
   liberación, reconexión, parada, aviso y captura #3, con máximos por fase)
   y verificó dos recorridos consecutivos PASS con transporte loopback.
   Lo pendiente NO es implementarla, sino ejecutar ese MISMO arnés en una
   ventana Binance real (`--transport public`), que requiere autorización
   explícita del operador y no se repite sin ella. El veredicto `FAIL`
   medido de la ventana 2026-10-24 se mantiene.

`NEXT_TASKS`:
1. **Nueva ventana Binance (solo con autorización explícita)** reutilizando
   tal cual el arnés automatizado ya implementado
   (`scripts/market_stream_local_acceptance.py --transport public`); sin
   autorización no se repite la ventana y el `FAIL` medido se mantiene.
2. Las demás tareas de la sección "Segunda ventana real cerrada (2026-10-24
   14:04Z)" siguen vigentes tal cual (aviso de servicio detenido, decisión de
   seguridad Next.js 16.4.1, revisión visual NOT_REVIEWED, retención de
   `data/market-cache/`).
3. Vecino opcional del presupuesto: conectar `build_recovery` al ledger
   compartido si el operador autoriza ampliar el alcance (hoy documentado
   como fuera).
4. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Segunda ventana real cerrada (2026-10-24 14:04Z, base `2f2f9ea`): FAIL de aceptación

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrar la ventana ejecutada sin repetirla y convertir el
lado navegador en un paso automatizado y acotado.

`ACTIVE_TASK`: **cerrado**. La ventana de `14:04:37.065Z` a `14:05:43.957Z`
(66,89 s de 180 s) midió la cadena real (BTCUSDT 46 eventos, MINAUSDT 12,
cierre + siguiente vela, BFF 46, 0 huecos, 3 consumidores, parada limpia, DBs
intactas) y 2 peticiones REST de velas; el veredicto es `FAIL` por
`consumers_released` (la desconexión del navegador no se ejecutó en los 20 s),
`browser_reconnected`, `dom_state_live`, `dom_update_fresh`,
`dom_pagination_preserved` y `dom_after_stop`, con `dom_candles_grew` ausente.
La captura #2 llegó después de la parada porque la paginación superó el `hold`
de 20 s. Evidencia: `docs/evidence/market-stream-window-2026-10-24.json` + tres
DOM. No se repite la ventana.

`NEXT_TASKS`:
1. **Automatizar el lado navegador** (sin abrir Binance; probar con transporte
   local): un script de Playwright que capture #1, pagine y capture #2 dentro
   del `hold`, desconecte al aviso y reconecte, y capture #3 al aparecer el
   aviso; medir la latencia de la paginación para dimensionar el `hold`.
2. **Aviso de servicio detenido**: revisar por qué `explorer-stream-down` no
   apareció con el SSE del BFF abierto (hook/`/status`), sin cambiar el
   producto sin decisión.
3. **Nueva ventana solo con autorización explícita** y procedimiento revisado;
   sin autorización no se repite y el `FAIL` medido se mantiene.
4. **Decisión de seguridad Next.js**: evaluar `16.4.1` cuando el operador lo
   autorice (condiciones actuales no cumplidas).
5. Revisión visual por modelo (`NOT_REVIEWED`).
6. Retención/poda de `data/market-cache/`.
7. Indicadores compartidos y paper prospectivo: fuera de alcance hasta nueva
   autorización.

## Market Lab — transporte aislado y paginación acotada (2026-10-24, base `5dec9ff`, sin ventana)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público solo bajo
autorización explícita; sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: eliminar las conexiones accidentales y las descargas
encadenadas sin abrir Binance ni actualizar Next.js.

`ACTIVE_TASK`: **cerrado**. (1) `--transport` obligatorio y falla cerrado:
`local` exige WS loopback, desactiva la reparación REST y no tiene fallback;
`public` es la activación explícita; sin transporte válido el servicio sale con
código 2 (`TRANSPORT_CONFIG`) antes de abrir ningún socket. (2) La paginación se
decide al terminar un gesto (`frontend/src/lib/earlier-gate.ts`), el encuadre se
conserva por índice exacto aunque el feed actualice la última vela, y el
explorador no abre peticiones concurrentes ni repite el mismo rango; cancelación,
agotamiento y fallo se distinguen y el fallo conserva el gráfico con reintento
manual. Causa de la cadena de 12: el evento de rango disparaba la descarga tras
anteponer cuando `isSuffix` fallaba por un tick del feed (la primera interacción
de la cadena sigue `UNKNOWN`; una segunda cadena de 6 peticiones en `ACTUSDT`,
17,4 s, confirma el patrón antes de la corrección). Pruebas: backend 29/29 +
25/25 + 13/13; frontend
gate 5/5, PriceChart 9/9, explorador 12/12, contrato 13/13; `tsc`/`eslint` 0;
`next build` OK. Evidencia:
`docs/evidence/market-stream-transport-failclosed-2026-10-24.json`,
`docs/evidence/market-lab-pagination-cascade-2026-10-24.json` y
`docs/evidence/nextjs-security-diagnosis-2026-10-24.json` (advisories verificadas
en la API oficial y contrastadas con `package-lock.json`; actualización **no**
ejecutada).

`NEXT_TASKS`:
1. **Nueva ventana (solo con autorización explícita)**: repetir el procedimiento
   corregido; capturar #2 con `LIVE` (paginar antes del cierre o ampliar el
   `hold`) y #3 con el aviso de desconexión ya visible. Sin autorización no se
   repite; el `FAIL` medido se mantiene.
2. **Decisión de seguridad Next.js**: evaluar la actualización a `16.4.1`
   (patch) cuando el operador lo autorice. Condiciones actuales no cumplidas:
   sin Server Actions registradas, sin `cacheComponents`, `sharp 0.35.5`,
   SVG rechazado por el optimizador, win32 y `127.0.0.1`.
3. Revisión visual por modelo de las capturas controladas (hoy `NOT_REVIEWED`).
4. Retención/poda de `data/market-cache/` antes de uso intensivo.
5. Decidir si el servicio se deja arrancado por defecto o sigue manual (hoy
   manual y detenido).
6. Indicadores compartidos: capacidad posterior con contrato y presupuesto
   propios.
7. Re-ejecutar `/antislop` end-to-end en sesión nueva; sigue PENDIENTE.
8. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Market Lab — cierre del expediente F-CHART-BINANCE-04 con causa demostrada (2026-10-24, base `965ab87`)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público bajo
demanda, sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: cerrar el bloque de la ventana `FAIL` **sin repetirla**:
propagar cierre/error/cancelación entre servicio, BFF y navegador; retirar `LIVE`
por frescura con causa inmediata; corregir la paginación `300→303`.

`ACTIVE_TASK`: **cerrado** el bloque de correcciones acotadas. El veredicto
medido de la ventana sigue `FAIL` y su evidencia no se reescribe. Causa: el BFF
devolvía `upstream.body` en crudo (sin fin/error/causa ni aborto al cancelar) y
el hook no cambiaba nada visible en `onerror`. Corrección: BFF con
`AbortController` + frames `event: error` + `cancel()`; hook con frescura local
(ticker 1 s) y causa inmediata; servicio despierta al consumidor al cerrar el
cliente; paginación pide el bloque estrictamente anterior y antepone con
`mergeEarlierSeries`. Medido con transporte controlado: liberación 1 → 0 en
14 ms (servicio vivo), EOF + causa en 6025 ms al parar, DOM `DESCONECTADO` con
causa en 12 ms. Base `965ab87`; BUILD_ID `XozH8PXJA4yZR59XphpyH` (PID 33444);
backend 29/29 + 25/25; frontend focalizado 28/28; contrato 13/13; `tsc`/`eslint`
0; DBs canónicas intactas; servicio 8791 **detenido**.

`NEXT_TASKS`:
1. **Nueva ventana (solo con autorización explícita)**: repetir el procedimiento
   corregido; capturar #2 con `LIVE` (paginar antes del cierre o ampliar el
   `hold`) y #3 con el aviso de desconexión ya visible. Sin autorización no se
   repite; el `FAIL` actual se mantiene.
   - Antes de repetirla, investigar la cadena de 12 descargas de "anteriores"
     observada el 2026-10-24 (3.552 velas de `0GUSDT` 1h añadidas a la caché
     derivada): una sola interacción no debería encadenar más de un bloque.
2. **Decisión de seguridad Next.js**: evaluar la actualización a `16.4.1`
   (patch) cuando el operador lo autorice; hoy la app no cumple los prerrequisitos
   de las tres advisories. Diagnóstico en
   `docs/evidence/nextjs-security-diagnosis-2026-10-24.json`.
3. Revisión visual por modelo de las capturas controladas (hoy `NOT_REVIEWED`).
4. Retención/poda de `data/market-cache/` antes de uso intensivo.
5. Decidir si el servicio se deja arrancado por defecto o sigue manual (hoy
   manual y detenido).
6. Indicadores compartidos: capacidad posterior con contrato y presupuesto
   propios.
7. Re-ejecutar `/antislop` end-to-end en sesión nueva; sigue PENDIENTE.
8. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Market Lab — ventana real ejecutada, veredicto FAIL por evidencia DOM (2026-10-24, F-CHART-BINANCE-04)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público bajo
demanda, sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: demostrar con una sola ventana acotada que un mensaje real
de Binance llega al gráfico por la cadena real. **Conseguido en la cadena; no
acreditado por el veredicto** por dos checks DOM.

`ACTIVE_TASK`: cerrar el expediente de la ventana ejecutada el 2026-10-24
(`00:47:04Z`–`00:48:27Z`, 83,46 s, 3 consumidores, 1 WS, `BTCUSDT`+`MINAUSDT`
1m) con veredicto `FAIL` (exit 1): `acquired=true`, 19 checks de cadena/servicio/
presupuesto/DBs en verde y solo `dom_state_live` + `dom_after_stop` en rojo.
Evidencia: `docs/evidence/market-stream-window-2026-10-23.json` y las tres
capturas `…-dom-1.json`, `…-dom-2.json`, `…-dom-stop.json`.

Estado: **implementado + probado con transporte controlado + servido + ventana
real ejecutada una vez**, con veredicto medido `FAIL` (no `PASS`). Base
`4956dee`; BUILD_ID `eiXlHvN4lJBLWcuOopsh_` (PID 33960); focalizado backend
53/53; explorador 12/12; `tsc --noEmit` 0; `eslint` 0; DBs canónicas con mtime
2026-10-15 11:46:27; servicio **detenido**, puerto 8791 libre, PID file ausente.

`NEXT_TASKS`:
1. **Corregir el procedimiento de captura**: paginar antes del cierre o ampliar
   `--hold-seconds` (solo con nueva autorización de ventana), y capturar #2
   mientras el panel siga en `LIVE`. Sin nueva autorización no se repite.
2. **Aviso de servicio detenido**: el panel pasa a `DESCONECTADO` pero no muestra
   `explorer-stream-down` si el BFF mantiene el SSE abierto; decidir si el BFF
   debe cerrar el stream al caer el upstream o si el hook debe reconsultar
   `/status` periódicamente.
3. **Paginación del explorador**: el contador subió `300→303` con ~45 KB nuevos
   en caché; verificar si el bloque anterior se antepone de verdad (posible
   defecto, no corregido en la ventana).
4. Decidir si el servicio se deja arrancado por defecto o sigue manual (hoy
   manual y detenido).
5. Retención/poda de `data/market-cache/` antes de uso intensivo.
6. Indicadores compartidos: capacidad posterior con contrato y presupuesto
   propios.
7. Re-ejecutar `/antislop` end-to-end en sesión nueva; sigue PENDIENTE.
8. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Market Lab — ventana por el camino real preparada (2026-10-22, F-CHART-BINANCE-04)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público bajo
demanda, sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: poder demostrar, con una sola ventana acotada y autorizada,
que un mensaje real de Binance llega al gráfico por la cadena real, sin abrir esa
conexión todavía.

`ACTIVE_TASK`: entrega del orquestador sobre el servicio existente, el evaluador
de aceptación separado de la adquisición, las pruebas controladas de la cadena y
el procedimiento exacto con presupuesto, reglas de parada y limpieza.

Estado: cerrado como **implementado + probado con transporte controlado +
servido**; **NO verificado con Binance** (la ventana sigue pendiente de
autorización explícita). Base `a2d0824`; BUILD_ID `n6FZutTsk5m8FFilTlxIo` servido
por 3020; focalizado backend 48/48; BFF 5/5; `tsc --noEmit` 0; `eslint` 0; DBs
canónicas con mtime 2026-10-15 11:46:27; servicio **detenido**.

`NEXT_TASKS`:
1. **Decisión humana**: ejecutar o no la ventana de
   `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` (1 conexión, `BTCUSDT` + `MINAUSDT`
   1m, ≤180 s, 1200 mensajes, 3 consumidores SSE) con las capturas DOM indicadas.
2. Si se ejecuta: registrar `PASS`/`FAIL`/`UNKNOWN` con el `--finalize` del script
   y actualizar `CURRENT_STATE` sin mezclar los cuatro planos de verificación.
3. Solo tras esa ventana: decidir si el servicio se deja arrancado por defecto o
   sigue siendo arranque manual (hoy manual y detenido).
4. Decidir política de retención/poda de `data/market-cache/` antes de uso
   intensivo (hoy sin poda automática).
5. Indicadores compartidos sobre el mismo feed: capacidad posterior, requiere su
   propio contrato, presupuesto y autorización.
6. Re-ejecutar `/antislop` end-to-end en una sesión nueva; sigue PENDIENTE.
7. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Market Lab — actualización continua de velas (2026-10-21, F-CHART-BINANCE-03)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación (WS público bajo
demanda, sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: que la vela en formación del contrato seleccionado se
actualice sola, con conexión compartida, estados honestos, reconexión y
reparación declarada de huecos, reutilizando el explorador y el gráfico.

`ACTIVE_TASK`: entrega documentada y commiteada del hub `market-stream/v1`, el
servicio SSE local, el panel de estado del feed, las pruebas A–I con transporte
controlado, el build re-servido y el plan de ventana viva (no ejecutada).

Estado: cerrado como **implementado + probado con transporte controlado +
servido**; **NO verificado con Binance** (ventana viva pendiente de autorización
explícita). Base `469e282`; BUILD_ID `n6FZutTsk5m8FFilTlxIo`, PID 18112,
`http://127.0.0.1:3020/market-lab`; suite backend 1405 passed + 2 skipped
(focalizado 28/28); frontend 538 passed + 1 skipped; `tsc` 0; `eslint` 0
errores/5 warnings preexistentes; `next build` OK. Sin inspección visual por
modelo: no se declara PASS visual. Servicio continuo **detenido**.

`NEXT_TASKS`:
1. Autorizar y ejecutar la ventana viva acotada de
   `docs/MARKET_STREAM_LIVE_WINDOW_PLAN.md` (1 conexión, `BTCUSDT` + `MINAUSDT`
   1m, 60 s, 400 mensajes) y registrar recepción, cadencia y cierre reales.
2. Solo tras esa ventana: decidir si el servicio se deja arrancado por defecto o
   sigue siendo arranque manual (hoy manual y detenido).
3. Decidir política de retención/poda de `data/market-cache/` antes de uso
   intensivo (hoy sin poda automática; retirada manual documentada).
4. Indicadores compartidos sobre el mismo feed: **capacidad posterior, no
   prometida**; requiere su propio contrato, presupuesto y autorización.
5. Re-ejecutar `/antislop` end-to-end en una sesión nueva; sigue PENDIENTE.
6. Revisar el fallo intermitente de `backtest-guard-regressions` (C1) bajo carga
   de suite completa; no se tocó en este bloque.
7. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01,
   ejecución con capital.

## Próximo recorrido — 2026-10-21

F-NAV-V2-ACCESS-01: accesos corregidos y servidos; ver CURRENT_STATE. No volver a pedir al usuario rutas ocultas: Mercado / Gráficos, Paper Lab — Simulación y Replay histórico están en navegación.

Siguiente objetivo funcional del usuario: gráfico Binance con actualización continua para contratos elegibles, reutilizando feed/lector/gráfico existentes. Primero definir ciclo de suscripción y recuperación + pruebas controladas; luego ventana acotada. Se conservan las restricciones y autorizaciones específicas de corridas; este cambio no inicia ninguna. Indicadores compartidos y paper vivo son capacidades posteriores explícitas, no prometidas por la entrega del explorador histórico.

> Actualización 2026-10-21: el ciclo de suscripción, la reconexión, la
> reparación de huecos y las pruebas controladas A–I están entregados en
> `F-CHART-BINANCE-03` (ver arriba). Lo único pendiente de este objetivo es la
> **ventana viva acotada**, que requiere autorización explícita.

## Market Lab — explorador de contratos USD-M e histórico paginado (2026-10-21, F-CHART-BINANCE-02)

`CURRENT_PHASE`: dashboard V2 de escritorio + observación con REST público acotado (sin websocket, sin monitor, sin órdenes).

`CURRENT_OBJECTIVE`: buscar contratos Binance USD-M Futures y visualizar su histórico paginado bajo demanda reutilizando el gráfico, sin feed continuo, sin indicadores y sin mezclar marcas de Paper Lab.

`ACTIVE_TASK`: entrega documentada y commiteada del catálogo cacheado, el histórico bajo demanda, la paginación, las correcciones (a)/(b) de Paper Lab, las pruebas A–H y la verificación REST acotada.

Estado: cerrado y documentado en `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`, `docs/MARKET_EXPLORER_CONTRACT_V1.md`, `docs/ACUERDOS_GRAFICO_BINANCE_V1.md` y `docs/FEATURE_BACKLOG.md`. Base `9689f3e`; build `9xXiQvrFIA0YaC3Vc_61F`, PID 16164, `http://127.0.0.1:3020/market-lab`, HTTP 200. Backend `pytest tests -q` 1375 passed + 2 skipped; focalizado 41/41; frontend 520 passed + 1 skipped; `tsc --noEmit` 0; `eslint src` 0 errores/5 warnings preexistentes. REST público: 16 peticiones, 0 reintentos, 0 fallos; catálogo 931 contratos; BTCUSDT y MINAUSDT 1h verificados (299 → 556 velas al paginar; 43 huecos reales del canónico en MINAUSDT). Sin inspección visual por modelo: no se declara PASS visual.

`NEXT_TASKS`:
1. Adaptar el feed existente a un contrato de gráfico vivo con reconexión, recuperación de huecos e indicadores compartidos (**requiere autorización separada; no ejecutado**).
2. Decidir política de retención/poda de `data/market-cache/` antes de uso intensivo (hoy sin poda automática; retirada manual documentada).
3. Re-ejecutar `/antislop` end-to-end en una sesión nueva y registrar el resultado; sigue PENDIENTE.
4. Revisar el fallo intermitente de `backtest-guard-regressions` (C1) bajo carga de suite completa; no se tocó en este bloque.
5. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01, ejecución con capital.

## Paper Lab — contrato de gráfico v1 y Lightweight Charts sobre fixtures (2026-10-21, F-CHART-BINANCE-01)

`CURRENT_PHASE`: dashboard V2 de escritorio + Paper Lab sobre fixtures (observación; sin Binance, sin órdenes).

`CURRENT_OBJECTIVE`: contrato versionado de datos/tiempos/IDs y gráfico financiero interactivo alimentado solo por el backend, primero sobre fixtures, con la corrección económica de F-PAPER-03 preservada.

`ACTIVE_TASK`: entrega documentada y commiteada del contrato `paper-chart/v1`, el componente Lightweight Charts, pruebas, build re-servido y evidencia de navegador A–H.

Estado: cerrado y documentado en `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`, `docs/PAPER_CHART_CONTRACT_V1.md` y `docs/FEATURE_BACKLOG.md`. Base `ac716d3`; build `PPE-Io-M4ivYg3dvJRqwh`, PID 27612, `http://127.0.0.1:3020/paper-lab-live`, HTTP 200. Backend focalizado 38/38; suite completa 1290 OK (2 skipped); frontend 484 passed + 1 skipped; `tsc --noEmit` 0; `eslint` 0 errores. Aceptación A–H con controles reales (contexto sin futuros, señal pendiente sin fill, fill 78,537.18/78,144.49, cierre automático 95.95/-51.56 sin salida 80, fin de datos sin cierre inventado, recuperación tras refresco, cambio de sesión sin residuos, zoom/pan/ajuste y cursor fecha·precio). Inspección visual por modelo no disponible: no se declara PASS visual.

`NEXT_TASKS`:
1. Reutilizar `paper-chart/v1` para búsqueda de contratos elegibles e histórico paginado bajo demanda (no ejecutado en este bloque).
2. Adaptar el feed existente a un contrato de gráfico vivo con procedencia, frescura, desconexión y reconexión (requiere autorización separada; no ejecutado).
3. Re-ejecutar `/antislop` end-to-end en una sesión nueva y registrar el resultado; sigue PENDIENTE.
4. Revisar fixtures restantes bajo la regla causal antes de usarlas como demostración de stop/horizonte.
5. Mantener diferido: stops/objetivos arrastrables, móvil/Flutter, F-PAPER-01.

## Paper Lab — corrección económica del stop y cierre automático verificado (2026-10-21, F-PAPER-03)

`CURRENT_PHASE`: dashboard V2 de escritorio + Paper Lab sobre fixtures (observación; sin Binance, sin órdenes).

`CURRENT_OBJECTIVE`: paridad económica Paper Lab ↔ `run_backtest` en el orden temporal del stop, publicación del stop efectivo que gobierna la operación y cierre automático desde los controles reales.

`ACTIVE_TASK`: entrega documentada y commiteada de la corrección, pruebas completas, build re-servido y evidencia de navegador/HTTP.

Estado: cerrado y documentado en `docs/CURRENT_STATE.md` y `docs/DECISIONS.md` (2026-10-21). Base `5572ee3`; commit inicial del bloque `d48a224`. Build `MzvbhIwIOPI7PNIKJlAve`, PID 24060, `http://127.0.0.1:3020/paper-lab-live`. Python 1290 OK (2 skipped, exit 0); frontend 471 passed + 1 skipped; `tsc --noEmit` 0. Evidencia de navegador con sesión `PL-BTCUSDT-LONG-1792627398136-5241b33a`: entrada 101.00, stop 95.95, cierre automático por stop 95.95 (no gap 80), neto realizado -51.56, funding UNKNOWN.

`NEXT_TASKS`:
1. Inventariar velas/indicadores existentes y fijar contrato de datos/tiempos/IDs (punto 2 de "Prioridad del recorrido gráfico/paper").
2. Lightweight Charts con fixtures, velas, volumen, zoom, histórico y marcas backend; instalación y QA de escritorio en ese bloque (**no** en esta entrega; no instalado).
3. Re-ejecutar `/antislop` end-to-end en una sesión nueva y registrar el resultado; si vuelve a derivar, registrarlo como defecto de integración. Queda PENDIENTE y no se reintentó en este bloque.
4. Revisar las fixtures restantes bajo la regla causal antes de usarlas como demostración de stop/horizonte (BTC horizonte termina en fin de datos; ETH se abstiene en el primer cierre).

## Piloto Anti Slop (opcional, no altera la fase) — 2026-10-21 (F-TOOL-ANTISLOP-01)

`CURRENT_PHASE` y `CURRENT_OBJECTIVE` **no cambian**: siguen siendo el dashboard V2 de escritorio y el recorrido causal de Paper Lab. Este piloto solo añade una revisión estilística opcional.

`ACTIVE_TASK` del piloto: entrega documentada y commiteada de `.opencode/skills/antislop{,-code}/`, `.opencode/commands/antislop.md` y `docs/ANTISLOP_PILOT.md`, con verificación real de descubrimiento en OpenCode.

`NEXT_TASKS` del piloto:
1. Re-ejecutar `/antislop` en una sesión nueva con el comando endurecido y registrar si termina sin derivar al asistente de modo (pendiente, no declarado; no reintentado en el bloque F-PAPER-03 del 2026-10-21).
2. Si se actualiza el upstream, re-descargar en el nuevo commit, recalcular SHA-256 y actualizar `docs/ANTISLOP_PILOT.md`.
3. Retirar el piloto si estorba: borrar los dos directorios, el comando y la línea de `AGENTS.md`.

Los `NEXT_TASKS` funcionales de la fase (inventario de velas/indicadores y contrato de datos/tiempos/IDs; Lightweight Charts) siguen como están en la sección siguiente.

## Paper Lab — tres bloqueos de `2a17088` cerrados (2026-10-21)

`CURRENT_PHASE`: dashboard V2 de escritorio + Paper Lab sobre fixtures (observación; sin Binance, sin órdenes).
`CURRENT_OBJECTIVE`: cerrar los tres bloqueos revisados de `2a17088` —fill resuelto con velas futuras, controles de vigilancia/reevaluación desconectados (`canStep`/`onDecide`) y salida stop como economía paralela sin política de hueco— y dejar el recorrido causal completo desde los controles.
`ACTIVE_TASK`: entrega de la corrección: documentación, commit selectivo, push y re-servicio del dashboard con `BUILD_ID` verificado.
`NEXT_TASKS`:
1. Reanudar el punto 2 de "Prioridad del recorrido gráfico/paper": inventariar velas/indicadores existentes y fijar contrato de datos/tiempos/IDs.
2. Gráfico Lightweight Charts con fixtures, velas, volumen, zoom, histórico y marcas backend (instalación y QA de escritorio en ese bloque; **no** en esta entrega).
3. Revisar el contenido de las fixtures bajo la regla causal (BTC termina en fin de datos; ETH se abstiene en el primer cierre) antes de usarlas como demostración de stop/horizonte.

Estado de la corrección (detalle en `docs/CURRENT_STATE.md` y `docs/DECISIONS.md`, 2026-10-21): el diseño causal solo pasa el prefijo conocido en T a `run_backtest`, una señal sin precio ejecutable queda como entrada pendiente sin fill/cantidad/coste, el backend publica `can_step`, `onDecide` va al backend con `request_id` + `expected_revision`, y stop/gap/`_finalize_exit_from_bt`/`manual_exit` comparten `_finalize_exit`.

La pasada real de navegador (Playwright/Chromium) ya se ejecutó sobre `http://127.0.0.1:3020/paper-lab-live` (build `cqYJQQU1Vh-vQGU-6bioV`, PID 23688): crear → abstención sin evidencia → señal pendiente → entrada → gestión → cierre manual, con orden de hooks, `can_step` y cursor corregidos. Pruebas focalizadas finales: motor 27/27, integración A–E 5/5, frontend Paper Lab 67/67, `tsc --noEmit` limpio, `eslint` del panel 0 errores. Sigue sin ser rentabilidad ni paper Binance vivo.

## Prioridad del recorrido gráfico/paper — 2026-10-21

Contrato de objetivo: [Acuerdos de gráfico Binance V1](ACUERDOS_GRAFICO_BINANCE_V1.md) (F-CHART-BINANCE-01). Plan documentado; no declarar código implementado.
Orden para este recorrido, sin reabrir ni duplicar colectores/Backtest:
1. Cerrar los tres bloqueos revisados de Paper Lab en 2a17088: futuro en fills, controles de vigilancia/reevaluación y stop/gap compartido. Evidencia integrada con mismo prefijo/futuros distintos, controles reales y salida reconciliada. *(CERRADO 2026-10-21: ver sección superior; la verificación de navegador queda pendiente.)*
2. Inventariar velas/indicadores existentes y fijar contrato de datos/tiempos/IDs.
3. Gráfico Lightweight Charts compartido con fixtures, velas, volumen, zoom, histórico y marcas backend; QA escritorio.
4. Búsqueda del catálogo Binance Futures y adaptación del feed existente, histórico paginado/caché acotada, reconexión y suscripciones por consumidor. Abrir pestaña no inicia monitor ni orden.
5. Ventana pública acotada solo tras autorización separada y preflight. Completar después selector y gestión/riesgo/caja/funding/evaluación, sin declarar estrategia rentable.

Alcance actual de este registro: documentación. Sin instalación REA/bibliotecas, adquisición, monitor ni nuevas corridas. Móvil/Flutter/IA diferidos. No cambia SUCCESS_GATES.

## Cinco defectos de Backtest V2 corregidos (2026-10-20, base `37bde91`)

Trabajo actual (cerrado a la espera de push): cierre de los cinco defectos
probados de la entrega Backtest → Paper Lab — bloqueo de ciclo de vida,
identidad del ejecutor por evidencia del SO, hashes declarados completos,
retención que nunca borra una corrida activa/UNKNOWN e hipótesis/placebo
separados en la UI. Reproducción fall-antes/pasa-después: 7/7 fallan en la
base, 7/7 pasan con el arreglo. Verificado: frontend 452 passed / 1 skipped,
`tsc` limpio, `eslint` 0 errores, `next build` OK
(`BUILD_ID=7IfLc2UBHcbIAl2WG0t91`), `python run_tests.py -q` 1290 OK
(2 skips), barrera de aislamiento limpia, e2e en navegador con dos corridas
reales y replay enlazado (ver
`docs/evidence/BACKTEST_V2_E2E_BROWSER_EVIDENCE.md`). Estado: los cinco correctivos y la corrección final de `control.guard` están commiteados en `3b6340d..<sha-de-esta-sesión>`; dashboard re-servido en `http://127.0.0.1:3020` (`BUILD_ID=w1DMYZv7af8n2jO6vXlyp`, HTTP 200 en `/api/v1/runtime`, `/backtest`, `/paper-lab`). Fuera de alcance: sin Binance, monitor, paper prospectivo, órdenes, credenciales, optimización ni cambios de estrategia/mapping/costes/umbrales/motor.

## MVP Paper Lab en caliente — ingeniería, reconducido (IMPLEMENTADO, commit 1892c23, push realizado)

Backend Python como fuente de verdad
(src/microstructure_probe/paper_lab_engine.py), frontend como cliente de API
delgado. Sobre fixtures (sin Binance en vivo). Motor de sesiones de ingeniería
con configuración versionada, decisiones (VIGILANDO/SIN_ENTRADA/DESCARTADO/
ENTRADA_SIMULADA), posiciones, fills, costes ejecutados vs estimados, eventos
y resultados. La mecánica económica se delega a `backtest_offline.run_backtest`
(no segundo motor económico). API Next.js con protección de origen y
confinamiento de directorio. Control de revisión (optimistic locking) con
request_id e idempotencia hasta el navegador. Reloj de simulación causal en
el camino dashboard → BFF → Python. Sin información futura en respuestas
públicas.

Flujo integrado extremo a extremo verificado por HTTP real (servidor PID 31072,
BUILD_ID jhFu3mEN9yZAntBo_sWsC, http://127.0.0.1:3020):
crear → evaluar sin señal (SIN_ENTRADA) → avanzar (revelar vela) → evaluar con
señal (ENTRADA_SIMULADA) → step ejecuta entrada → step gestiona → step cierra
por stop → GET recupera estado idéntico. Tiempos: decision_at=899999,
entry_ms=900000 (>= decision_at), exit_px=95.95, exit_reason=stop,
exit_executed=true, realized_net=-51.56, total ~952ms. Conflictos HTTP reales:
dos steps concurrentes misma revisión → uno 200, otro 409 REVISION_CONFLICT;
sin entrada duplicada. Misma request_id con contenido distinto →
409 REQUEST_CONTENT_CONFLICT. Revisión obsoleta → 409. Sesión inexistente → 404.
Caso D (fin de datos, posición abierta): exit_executed=false,
realized_net=null, open_at_end=true, exit_fees_executed=0, posición sigue
abierta, GET idéntico.

Pruebas: 23 Python del motor + 5 integración A-E (CLI con almacenamiento real)
+ 16 backtest-offline = parte de las 1290 OK totales (2 skipped). Frontend
vitest 470 passed / 1 skipped + tsc --noEmit limpio.
No es motor paper completo (Etapa 5): no hay position manager, ledger de caja,
funding recurrente ni risk engine.

Corrección acotada (2026-10-21): `step_forward` detecta stop con la vela actual
(OHLC conocido en T) usando el mismo stop dinámico que `run_backtest`
(`entry × (1 ∓ pct)`), no el `stop_px` estático; añade `_finalize_stop_exit`
con costes ejecutados consistentes. `known_close_cutoff` en `run_backtest`
(default `horizon_end`, compatible hacia atrás). Las 5 routes del BFF +
helper `runPython` parsean stdout Y stderr del CLI para mapear
REVISION_CONFLICT/REQUEST_CONTENT_CONFLICT a HTTP 409 incluso cuando el CLI
sale con código ≠ 0.

## Próxima fase (REGISTRADA, NO implementada, requiere autorización): paper lab
con datos vivos — selector causal → decisión versionada → simulación →
gestión → cierre → exportación. Ninguno de esos pasos está iniciado.

## Alcance vigente del usuario — 2026-10-20

Aplicar `docs/DESKTOP_FIRST_SCOPE_20261020.md`: desarrollar y validar solo
web de escritorio. Movil/Flutter, optimizaciones y QA 360/390 px quedan
DEFERRED hasta completar y aceptar el alcance funcional desktop del bot/V2.
No son bloqueos ni tareas actuales. Conservar evidencias anteriores.
Esta decision prevalece sobre las menciones historicas siguientes; no altera
el bloque correctivo del agente ni declara implementado paper en caliente.

## Backtest offline funcional en V2 + enlace a Paper Lab (2026-10-20, sin push aun)
`/backtest` ejecuta una evaluacion offline versionada (unico experimento
permitido `eval-census-v2-trio`) sobre el paquete publicado EVAL-CENSUS-V2
(sha256 verificado antes de correr); estado/identidad separados del monitor
Binance; single-flight con estado persistido; resultados deterministas en
`frontend/.backtest-runs/` (ignorado). `Abrir replay` carga la operacion
exacta en Paper Lab conservando causalidad y costes; no soportada -> 422 con
motivo. Documentos: `docs/EXTREMES_EVALUABILITY_MATRIX.md` (matriz
preparatoria, no declara evaluada la estrategia completa),
`docs/BACKTEST_READ_CONTRACT_V1.md` (UNWIRED->WIRED),
`docs/PAPER_LAB_PLAN_ETAPA5.md` (enlace). Verificado: backend 1291 OK +
frontend 400/400 + typecheck + lint + build. Estado: los cinco correctivos y la corrección final de `control.guard` están
commiteados en `3b6340d..<sha-de-esta-sesión>`; dashboard re-servido en
`http://127.0.0.1:3020` (`BUILD_ID=w1DMYZv7af8n2jO6vXlyp`, HTTP 200 en
`/backtest` y `/paper-lab`). Fuera de alcance y no iniciado:
protocolo de auto-seleccion offline sobre EVAL-CENSUS-V2; residual MINA/NMR
(`build_report` INCOMPLETE); estudio W/LUMIA separado.

## Correcciones Backtest → Paper Lab, bloques A/B/C (2026-10-20, base `4e61587`)
Cierre de 8 defectos de la entrega funcional, en tres bloques verificables.
- **Bloque A (commit `84e6294`):** serialización portable del paquete
  (`-text` + renormalize); verificación estricta intacta; regresión
  `PackagePortabilityTest`. Push `4e61587..f28fd4e`.
- **Bloque B (commit `76763d7`):** identidad de ejecución única, exclusión
  entre procesos (`O_EXCL`), propiedad verificable (token+pid+started),
  reconciliación sin auto-relanzar, UNKNOWN explícito, presupuesto efectivo,
  error async de spawn, resultados/caché vinculados y verificados por hash,
  ubicación canónica `<repo>/backtest-results/` (evidencia previa preservada),
  retención acotada que nunca elimina una ejecución activa, y `PaperLabSource`
  sin mostrar la operación previa en carga/fallo.
- **Bloque C (pendiente):** métricas realizadas vs abiertas, hipótesis vs
  placebo, escenarios de coste, conteos exactos, revisión visual + capturas
  publicadas, entrega consolidada con SHAs.
Fuera de alcance: sin Binance, monitor, paper prospectivo, órdenes,
optimización, ni cambio de estrategia/umbrales/costes/motor económico.


Verificador rehecho con funciones puras (58 tests unittest: 45 puras + 3 PackageMode + 10 CLI fixtures, 0 fallos). Veredicto global PASS/FAIL/INCOMPLETE integrado. Estado actual: INCOMPLETE (0 discrepancias, 2 incompletos: MINAUSDT/1h y NMRUSDT/1h tail-edge). Causalidad VERIFICADA (9314/9314 OK, 6 UNKNOWN, 0 violaciones). Trazabilidad hasta operación: replay determinista, 0 celdas fail, 5255 trades escala 1.0 reconciliados exactamente, vinculados a eventos/candidatos. Paquete de evidencia publicado (docs/evidence/eval-census-v2-package/, 33 archivos, SHA256). Pruebas CLI: 10 casos de alteración + control; cada alteración FAIL/INCOMPLETE con exit ≠ 0, control PASS/exit 0. Campos económicos (E_net↔expectancy_net, etc.): 60 celdas, 0 discrepancias. Suite 1260 OK. Barrera aislamiento: hashes_equal=True, file_writes=0. Ledger publicado con veredicto, trazabilidad, tail-edge, campos económicos, descartes. Pendiente: incorporar manifiestos temp/opencode a Git para cerrar vínculo completo detección→operación y verificar los 2 tail-edge pendientes.

## Cierre EVAL-CENSUS-V2 + selector + QA visual 3020 (2026-10-17, sin corridas, sin push aun)
Censo CENSUS-V1 (9320/9320/0, entry>=available 9314/9314, 594 grupos
duplicados contados) + EVAL-CENSUS-V2 (5255 trades @1x, 0 celdas
elegibles, H1/H3 RECHAZADAS, H2 fade RECHAZADO como metodologia y
conservado como HIPTESIS NUEVA no aprobada). Funding 741 liquidaciones
aplicadas (0 UNKNOWN-excluded); 24/60 celdas uncovered/UNKNOWN.
Placebo TIME-PLACEBO-v1 seed 42 (una realizacion, no distribucion).
HORIZON-GRID4-V1: degeneracion 1h/1h demostrada; separacion explicita
experimento original (V1, 1h default) vs nuevo horizonte (4h/1h); no
optimizacion validada. Selector SELECTOR-EXTREME-V1: mecanismo probado
con fixtures, NO evaluado sobre censo, NO aprobado. Estrategia completa
de extremos sobre universo/liquidez: NO EVALUADA (faltan datos de
ranking/liquidez/market_cap). Artefacto census-eval-v2.json force-added
(sha256 2b74a841...d37060). QA visual 3020 PASS (2 bloques, 0 errores,
captura VISUAL_QA_CENSUS_EVAL_V2.png; defecto duplicado corregido).
Verificado: backend 1202 OK + frontend 314/314 + typecheck 0 + build OK.
V2 sirviendo 3020 PID 15480. Monitor detenido, watchers detenidos, sin
corridas. Resta: commit selectivo, push, entrega con SHA.

## Integracion objetivo movers extremos (2026-10-17, solo documental, sin corridas)
Integrada review/extreme-movers-objective-20261016 hasta 7a4e872 por
contenido (EXTREME_MOVERS_OBJECTIVE.md + HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md
restaurados + suplementos portados); evolucion actual preservada. Estos
planes no aprueban parametros ni autorizan implementarlo todo ahora:
soportes, stops dinamicos y Paper Lab conservan su secuencia. Leer
docs/EXTREME_MOVERS_OBJECTIVE.md antes del siguiente plan; completar
primero la auditoria causal/costes/paquete ya autorizada.

## Suplemento de objetivo, sin interrumpir tarea activa — 2026-10-16
Leer docs/EXTREME_MOVERS_OBJECTIVE.md antes del siguiente plan.
Completar primero la auditoria causal/costes/paquete reproducible ya autorizada.
Despues auditar selector discovery vs microestructura disponible, cobertura
bilateral fuera del trio y conexiones Movers→detalle→Backtest/Paper.
No iniciar sesiones ni implementar estrategia por este suplemento.
F-EXTREME-OBJECTIVE-01 mantiene trazabilidad. Al integrar esta rama documental,
portar solo sus cambios: preservar trabajo concurrente del agente.

## Paquete + causalidad + costes + protocolo (2026-10-17, sin corridas, sin push aun)
Manifiesto + replay verificado + IDs 1:1 + reproduce script; matriz
causal (ninguna elegible); breakeven s* + fragilidad 2x; protocolo
V1 preparado; V2 con 3 bloques lectura; tests nuevos verdes.
Resta: build, QA visual 3020, commit, push, entrega. V2 por
desplegar, monitor detenido.

## Fix artefacto offline-eval publicado (2026-10-16, sin corridas, sin push aun)
Artefacto por force-add + agregador determinista byte-identico + test 6/6
+ hashes funding reconciliados + limitacion dataset declarada. Resta:
checkout limpio, commit, push, entrega. V2 abierto, monitor detenido.

## Offline entry/exit closeout V1 (2026-10-16, sin ventana forward, sin simulacion prospectiva, sin push aun)
Auditoria de 5 puntos cerrada con re-ejecucion offline (hashes identicos)
+ informe corregido + audit JSON por operacion + barrera + QA visual.
Sin ventana forward, sin simulacion, sin mapping aprobado, sin costes
medidos, sin paper/ejecucion. Resta: commit, push, entrega. V2 abierto,
monitor detenido.

## R3 vivo PASS brief 120s (2026-10-16, autorizada 1x, sin push aun)
Unico lanzamiento V2 brief=120 reconciliado sin duplicar (la
respuesta 200 no trae run_id arriba); capturador con ambas
identidades fijadas: terminal-captured + R3 PASS en vivo.
Cierre natural exit 0, todo muerto, SQLite limpio, filas UUID
contrastadas. Resta: commit, push, entrega. V2 abierto,
monitor detenido.

## V2 08364ba publicado en 3020 (2026-10-16, deploy sin corridas)
Build 08364ba en 3020 (PID 2868, BUILD_ID v4Od5kTGmfyFhyzE-twPO);
runtime/detections/overview/system verificados 200 con las 3
claves; sin corrida activa, monitor detenido. R3 vivo pendiente
de futura ventana autorizada. Resta: commit documental, push,
entrega.

## Atribucion exacta R3 (2026-10-16, sobre a2aebc5, sin push aun)
BFF method/snapshot_run_id/timestamp + capturador PASS solo
exact-uuid con UUID registro=snapshot (3 regresiones nuevas);
frontend 304 + capturador 19 + export 6 verdes locales. Resta:
commit, push, entrega. Sin corridas/gates. V2 abierto,
monitor detenido.

## Captura R3 v2 + causalidad (2026-10-16, sobre 69d55ba, sin push aun)
Veredicto R3 separado + UUID tardio + detections verificado (6
tests); close_time/as_of + regresion intra-vela + runner conserva
tiempos. PROPOSED + mecanica intactos, sin P&L. Resta: suites,
barrera, commit, push, entrega. Sin corridas/gates. V2 abierto,
monitor detenido.

## R3 capture + prep offline (2026-10-16, push 69d55ba)
Reconciliacion 10+1 + UNKNOWN/STALE por capas; captura GET-only
lista (10 tests) con comando para la proxima ventana; inventario
H1/H2/H3 + adaptador + prep mecanico en temp (economia retenida).
Faltan: mapping, funding realizado, costes, purga. Resta: suites,
barrera, commit, push, entrega. Sin corridas/gates. V2 abierto,
monitor detenido.

## Piloto brief 120s COMPLETADO (2026-10-16, autorizado 1x, push 48445f2)
Enlace auto UUID 4303b1c5 + cierre natural COMPLETED + 89360 msgs
sanos + 54 filas UUID + V2 10/2 con enlace exacto (R3 mid-run
UNKNOWN, residual). Resta: matriz, commit, push, entrega.
V2 abierto, monitor detenido.

## V2 operativo en 3020 (2026-10-16, sobre d126141, sin corridas)
3020 unico con build d126141 (PID 23588, BUILD_ID registrado);
obsoletas detenidas; auth 403/400 en vivo + mocks 59/59 sin
monitor; visual barra + episodios; 98/4 parcial vs 245/13
completo (no equivalentes). Resta: commit, push, entrega.
Monitor detenido.

## Trazabilidad + episodios v1 (2026-10-16, push d126141)
link fenced + lector exacto + agrupacion v1 + BFF/panel + regresion
245 (fixture completo; BFF en vivo 98/4 parcial con limitacion
declarada + UNKNOWN historico). Correccion documental agrupados/sin-byte-identidad. Sin
corridas ni calibracion. Backend 1139 + frontend 300/300 + barrera
0/0/1RO + visual; commit d126141 + push. V2 en 3020, monitor
detenido.

## Reconciliacion OBS10M UUID/persistencia/funding (2026-10-16, push d7dcc70)
UUID exacto, 246 writes a historical.db (delta UNKNOWN), funding 245
= 13 episodios agrupados por regla. V2 abierto, monitor detenido.

## Corrida autorizada observation-10m 600s COMPLETADA (2026-10-15, push 10cad5c + informe 67472e0)
600s sanos supervisados (468162 msgs, 0 rechazos, cierre natural,
PIDs muertos, COMPLETED 610s, sin journal). V2 abierto, monitor
detenido.

## Correccion atribucion del feed (2026-10-16, push 8c73de2)
Sin gracia pre-start + run_id priorizado + regresion 20s A/B +
UNKNOWN sin certeza; Start/Stop/umbrales/identidad intactos.
V2 abierto, monitor detenido.

## Endurecimiento identidad UNKNOWN + feed estricto (2026-10-16, push 3f2fcea)
UNKNOWN=UNVERIFIED + terminal explicito + expiracion 30s + feed
estricto/atribuido + gates 0.05/0.5 reconciliados + tests feed y de
otro run; Start/Stop/propiedad intactos. V2 abierto, monitor
detenido.

## Visibilidad global de corridas V2 (2026-10-16, push 3544ad6)
Barra global + stop proyecto verificado + reconciliacion piloto.
Controlador canonico reutilizado. Tests backend 10 + frontend 266
verdes con fixtures/aislados; sin corridas Binance. V2 abierto,
monitor detenido.

## Piloto brief completado (2026-10-15, autorizado, sin push aun)
Ventana sana 120s completa y auditada; PIDs muertos, COMPLETED,
SQLite + V2 verificados, sin journal. Resta: commit selectivo
(con copia maintenance JSON revisada, sin DBs/backups), push,
entrega. Dashboard abierto.

## Mantenimiento recovery aplicado (2026-10-15, autorizado, sin push aun)
Apply PASS con backup; V2 reiniciado y verificado; monitor no
arrancado. Resta: commit selectivo (sin DBs/backups), push, entrega
con hashes/respaldo/SHA/URLs.

## Ventana registry + hot real + spy (2026-10-16, sobre e0b0141, sin push aun)
Lock-probe fuera; registry+re-hash; fixture hot valido; spy 1-rw
(fail-before en viejo). Resta: barrera, commit, push, entrega.
Sin aplicar, sin corridas. V2 abierto.

## Mantenimiento aplicable + deriva (2026-10-16, sobre 3a55052, sin push aun)
Backup real + re-hash pre-write + writers excluidos + auto-compare +
regresiones; destino verificado fuera/inexistente. Resta: commit,
push, entrega + comando definitivo. Sin aplicar, sin corridas.

## Correccion revision + apply/backup (2026-10-16, sobre 6264ccc, sin push aun)
Metricas renombradas + RealReceivePathTest; --apply/backup/
protecciones + 14 tests; informe reproducible publicado. Resta:
commit selectivo, push, entrega + comando exacto para autorizacion.
Sin aplicar, sin corridas. V2 abierto.

## Recovery-journal + atribucion (2026-10-15, sobre 9b78058, sin push aun)
Ensayo recovery en copia (diff 0) + procedimiento propuesto para
autorizacion (sin aplicar); queue/transit instrumentado + 5 tests.
Resta: barrera completa (probe.py tocado), commit selectivo, push,
entrega. V2 abierto, cero auto-corridas.

## Post-mortem piloto + contador/readiness (2026-10-15, sobre 51d6095, sin push aun)
ABORTED sano auditado (PIDs muertos, 0/0/0, journal intacto, umbral
intacto); contador congelado + ABORTED terminal en readiness + tests.
Resta: barrera completa (control.py tocado), commit selectivo, push,
entrega. V2 abierto, cero auto-corridas.

## Cierre defectos pre-piloto (2026-10-14, review/o1-funcional-v2-observacion sobre 972a19e, sin push aun)
202/BotControl + identidad host + migracion en fixtures: barrera 1077
exit 0, frontend 255/255, 143 dirigidas OK. Resta: commit selectivo,
push, checkpoint y plan brief 120s actualizado para autorizacion.
Piloto NO iniciado.

## Revision pre-piloto O1 (2026-10-14, review/o1-funcional-v2-observacion sobre e887287, sin push aun)
Seis puntos atendidos: presupuestos 4200/8000/65000 + reconcile 202 +
ALREADY_RUNNING; readiness por capability + storage bloqueo/aviso;
presets own-keys + 20 tests nuevos (vitest 252/252); compat 9/10+2/3
corregida + prospective schema real + eyebrow dinamico; barrera 1062
(control verde, 11 preexistentes contrastados); QA visual 10/10 + 7
capturas; docs 207186d reconciliados. Resta: commit selectivo, push,
checkpoint y plan brief 120s para autorizacion. Piloto NO iniciado.

## Entrega nueve archivos 6fd6091-base (2026-10-13, review/entrega-nueve-archivos-6fd6091, sin push aun)
R1-R7 9/9 + dirigidas 68/68 + comparador 10/10; barrera 1029 (1F+8E preexistentes,
contrastados en base). Resta: commits selectivos, push revision, matriz de entrega.
Sin merge/force, sesiones, paper, ordenes ni gates.

## Bot + V2 observacion (2026-10-13, review/bot-dashboard-v2-observacion, sin push aun)
Matriz/ciclo/preflight + ciclo aislado 4/4 + preflight 3/3 + vitest 24/24.
Resta: barrera completa, commits selectivos, push revision, entrega. Sin gates.

## Correccion tecnica de14ac1-base (2026-10-13, review/correccion-tecnica-de14ac1; push 6fd6091 completado)
Comparador M6a/M6b/M7/M8 + SELF (automatizado, 10/10) + re-verificacion MATCH legitima.
Motor: split realizado/abierto + costes hipoteticos + funding qty x mark/identidad/dedup/gaps
(contrato v4.1). Runner H1/H2/H3 por grupo + identidad por indice. Incidente v2->v3
reconciliado (canonico intacto); handoff 27b7af5 con incompatibilidad v10/v3. Resta:
suite canonica + barrera, commits selectivos, push revision, entrega con matriz. Sin gates.

## Cierre W/LUMIA documental — reproduccion aislada (2026-10-13; push phase1 bc327f1 completado)
Reproduccion DONE acotado (addendum v2 + 5 evidencias). No es integracion
dashboard ni validacion financiera. V2 exacto `27b7af59cb1e313169f49655161d66e043b5412d`
= frontend estatico `dash-v2-03-token-detail`, no el SSR backend.
Pendientes explicitos (prompt correctivo anterior, no sustituido): funding,
posiciones abiertas, runner, incidente de aislamiento, schemas V2.
Resta: commits selectivos + push a rama de revision + entrega (SHA, URL,
comparacion, remoto=local, evidencias, completados/pendientes). Sin gates.

## Correccion V2 + comparador (2026-10-13, review/w-lumia-correccion-bc327f1; push de14ac1 completado)
Addendum (historia preservada): V2 `27b7af59cb1e313169f49655161d66e043b5412d`
tiene rutas BFF + adapters SQLite (ver `route.ts` live-movers y
`canonical-market.ts` en Git); integracion parcial != feed
live/operacion verificados (UNVERIFIED declarado). Comparador con
missing-masks/tipos/especiales, exit 1/2 y 5 regresiones en temp.
phase1 avanzo bdc9ef2->bc327f1 con 21 commits (esta tarea: sus propios
commits en rama de revision, sin avanzar phase1/main). Publicar !=
aceptar correcciones anteriores. Pendientes: funding, realizados/marcas,
runner, aislamiento, schemas V2. Sin merge/force-push ni gates.

## Mejoras funding/dashboard/evaluacion — implementado (2026-10-13, sin push aun)
Resta: suite completa + barrera + copia aislada, commits acotados, push
a rama de revision coherente, entrega con siete campos.

## Cierre correctivo R1-R7 — implementado (2026-10-13, sin push aun)
Motor v3 + R6 + R7 + regresiones (22 nuevas) verdes en sitio (972).
Resta: copia aislada final, commits, push a review, entrega acotada.

## Verificacion final — DONE (2026-10-12, sin push)
950/950 en sitio y en copia aislada (1 skip esperado). Queda pendiente:
decision de alcance para research-buckets linkage, OOS real, V2,
Paper Lab y ejecucion. Nada promovido en SUCCESS_GATES.

## Cierre correctivo P1-P4 — DONE acotado (2026-10-12, sin push)
Motor v2 + aislamiento con inyeccion + linkage v10 + docs reconciliados.
Verificacion final (copia aislada) y entrega abajo. Sin rentabilidad,
V2, Paper Lab ni ejecucion; gates sin avance.

## ETAPA 5 Paper Lab plan — DONE (2026-10-12)
Design delivered; implementation gated on prior-stage validation +
authorization. Scope complete through Etapa 5 as bounded work.

## ETAPA 4 offline backtest prep — DONE (2026-10-12)
Mechanics implemented + tested in isolation; V2 read contract prepared
unwired. Next: ETAPA 5 Paper Lab design (no implementation). Validation
still blocked per Etapa 2.

## ETAPA 3 research/backtest contract — DONE (2026-10-12)
Contract written before any engine. Next: ETAPA 4 isolated offline prep
(temp fixtures, versioned contracts). No validation claimed.

## ETAPA 2 dataset readiness — DONE (2026-10-12)
Provenance closed (confirmed/probable/unknown split, all rows retained).
Dataset apt for descriptive work with explicit fixture filter; blocked for
validation (costs, versions, OOS, run linkage). Next: ETAPA 3
research/backtest contract. No runs, traffic, orders, Start or paper.

## ETAPA 1 test isolation — DONE (2026-10-12)
Prohibited writes zero (barrier exit 0); canonical 916/916 OK with stable
microprobe hash; 375/225 re-verified by pure read. Residual Routes B/C
documented with production-side blocker. Next: ETAPA 2 pure-read provenance
+ DATASET_READINESS. Report: docs/TEST_ISOLATION_ETAPA1_REPORT.md. No runs,
traffic, orders, Start, paper, V2/main changes or gate advancement.

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


# TASK_QUEUE


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


Operational next work. Updated every task. Docs-realism rule applies.



## CURRENT_PHASE



PHASE 1 — MARKET INTELLIGENCE + DASHBOARD



Traceability: `docs/FEATURE_BACKLOG.md` (stable IDs; reconcile after every task).



## CURRENT_OBJECTIVE



Execute Phase 1 in dependency order: tooling sanity → short transport

validation → persistence foundation → minimal dashboard → raw features

(returns → velocity/rank → flow → book/OI → VWAP/vol/structure) with the

dashboard growing alongside → prolonged soak with dashboard live → raw-feature

validation → state classifier v0 → signal/extreme-move UI → 24h calibration

review and gate evaluation.



Binding dependency — actual Phase 1 execution order (project decision

2026-10-06, reconciled with build sequence):



```text

P1-00 tooling → P1-01 transport validation → P1-02 persistence foundation

  → P1-03 minimal live dashboard → P1-04…P1-08 progressive raw features

  → P1-09 intelligence dashboard → P1-10 soak → P1-11 feature validation

  → P1-12 classifier → P1-13A opportunity engine DONE

  → P1-13B Professional Opportunities UX → P1-14 calibration review

```



Persistence lands before raw features so the dashboard becomes useful

progressively; raw features must still be dashboard-validated (P1-11) before

any classifier (P1-12) consumes them. No prolonged blind observation before

the dashboard exists. No classifier before raw-feature dashboard validation.



## ACTIVE_TASK — scope note (2026-10-12, corrective closeout)

The ACTIVE_TASK / NEXT_TASKS sections below preserve the Phase-1 sequence
state (P1-13A PASS through P1-14B.x, DASH-V2 slices) as historical record —
do not rewrite them. The CURRENT active work is the bounded corrective
closeout tracked in the dated blocks at the top of this file (Etapas 1–5
plus P1–P4 corrective priorities): backtest repair, isolation injection
points, run linkage, documentation reconciliation, and the five Backtest V2
defects (block lifecycle, executor identity, declared hashes, retention,
hypothesis/placebo). No P1-14C, no paper,
no execution. Phase gates advance only per docs/SUCCESS_GATES.md.


## ACTIVE_TASK



- `P1-13A` (2026-10-08) OPPORTUNITY / SETUP ENGINE V0: **PASS (corrective closeout P1-13A.1)**.

  Observe-only engine (`opportunity.py`, rules v0.1.0): 5 families,

  lifecycle DETECTED→WATCHING→ACTIVE_RESEARCH→INVALIDATED/EXPIRED→UNKNOWN,

  cooldown 60 min (3_600_000 ms), TTL 24h, max 200 candidates / 500 events,

  schema v8, fabrication guards, dashboard `/opportunities` + `/api/opportunities`.

  58 tests (all pass), 554/554 suite, 120s observe COMPLETED (3 REVERSAL_WATCH candidates),

  dashboard live v0.9.0 at http://127.0.0.1:8091. Spec: `docs/OPPORTUNITY_ENGINE_SPEC.md`.

  Documentation discrepancies corrected (cooldown 60s→60 min, max 50→200).



## NEXT_TASKS (ordered, all Phase 1)
- `P1-14A` (2026-10-08) PROSPECTIVE SETUP OUTCOME EVALUATION V0: **PASS**.
  ProspectiveRecorder (prospective.py): one-setup registration at first
  DETECTED, forward mark-price outcomes at 1m/5m/15m/1h/4h, outcome states
  COMPLETE/PENDING/INSUFFICIENT_HISTORY (no fabrication), in-memory + DB
  dedup with restart-safe rehydrate, bounded queue + telemetry
  (writes/drops/errors/inflight/high_water), hourly retention 90 days,
  persistence schema v9 (`prospective_setups` REPLACE +
  `prospective_outcomes` bounded 500/setup), dashboard `/api/prospective`
  (schema_version 9, RESEARCH ONLY banner).
   35 tests (all pass), 554/554 canonical suite, 120s observe COMPLETED
   (prospective recorders registered + observed). Spec:
   `docs/PROSPECTIVE_EVALUATION_SPEC.md`. Integration wired in probe.py
   (detect_price, recorder start/drain).

- `P1-14B` (2026-10-09) PROSPECTIVE INTEGRITY VALIDATION (RECOVERY) —
  **PASS**. Recovery of interrupted P1-14B session at SHA `e727e54`: two
  session fixes accepted (`prospective.py:106` rehydration now stores
  `setup_json` so restarts recompute COMPLETE; `dashboard.py:403` reads the
  shared store for `/api/prospective` parity); 39 new validation tests
  (`tests/test_p14b_validation.py`, P1-14B.1–.11) all pass; pilot evidence
  preserved (`p14b_pilot_monitor.py`, `logs/p14b_pilot.log`,
  `.firecrawl/*.json`); real evidence validated in `data/microprobe.db`
  (schema v9, 7 unique setups, 1 COMPLETE outcome, event-time audit PASS,
  zero duplicates/fabrication). Full suite: 593/593 OK. Report:
  `docs/P1_14B_VALIDATION_REPORT.md`.

- `P1-14B.1` (2026-10-09) TIME INTEGRITY, DATA QUALITY & PROSPECTIVE
  READINESS — **PASS**. Anomaly `elapsed=-1789712305900s` root-caused to
  monitor-side s−ms mixing (exact-constant reproduction; core clean).
  Three core defects fixed minimally with tests: (B) restart rehydration
  dead on the default path (no `db_path` in config → early return);
  (C) outcome-store bounding DELETE wiped other setups' rows (scratch-proven,
  shaped the P1-14B "single outcome" evidence); (D) `observe()` ran only on
  matched-candidate ticks, never on quiet ticks (against the per-cycle
  spec). 16 new tests (`tests/test_p14b_1_time_integrity.py`); 1 P1-14B
  restart test hardened. Full suite: 609/609 OK. Three controlled 120 s
  observe runs (exit 0) prove each fix live: reg=7 from summary #1,
  28 coexisting COMPLETE outcomes (0 dupes), safety 0/0/0. Corrected
  denominators + readiness criteria (no long run started) in
  `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`.

- `P1-14B.2` (2026-10-09) PROSPECTIVE OPERATIONAL STABILITY GATE —
  **PARTIAL**. Preflight PASS; clock audit PASS (+517 ms vs 60 s tolerance,
  deliberate no-resync). 35-min run via canonical plane (PID 32532, UTF-8
  log `logs/probe-runs/probe-20261009T015411Z.log`) aborted by controlled
  stop at 23.4 min (exit 0) on the written >5 % reject rule (5.15 %
  cumulative, ~100 % marginal episode, 3 market reconnects, markPrice stale).
  Window <30 min = INSUFFICIENT for the duration objective. Post-run audit:
  24 setups, 68/68 COMPLETE, 0 dupes, 100 % matured-cell coverage, no
  fabrication. Tests 609/609 OK (no new tests — no confirmed defect).
  Gates: CLOCK/PERSISTENCE/PROSPECTIVE/RESOURCE/SAFETY PASS; TRANSPORT
  PARTIAL (limiting). No 4–6 h run authorized. Report:
  `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`.

- `P1-14B.3` (2026-10-09) TRANSPORT FRESHNESS & PROSPECTIVE OUTCOME VALIDITY —
  **PARTIAL**. Episode root-caused (host-external delivery stall; local backlog,
  clock, HOT logic discarded with evidence). 68 rows classified read-only
  (19/28/21/0, rows preserved). Fixes: stale-mark gate (known age >120 s →
  PENDING, unknown fail-open) + freshness watchdog (accepted accounting,
  90 s/300 s budgets, cooldowns, existing retry path) + summary freshness
  block; no new motor states. 20 new tests; suite 629/629 OK. Single ≤35 min
  run (PID 34040): watchdog recovery PROVEN live (5 min zero rejects after
  forced reconnects); path outage → controlled stop at 17.1 min (exit 0).
  Post-run: 24 setups, 99/99 COMPLETE, 0 dupes; 21 missing cells explained
  (unsubscribed OGN/RLC, no defect). Gates: CLOCK/PROSPECTIVE/PERSISTENCE/
  SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL. No 4–6 h authorization. Report:
  `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`.

- `P1-14B.4` (2026-10-09) PROSPECTIVE FRESHNESS & PENDING LIFECYCLE INTEGRITY —
  **PASS**. UNKNOWN age never FRESH (strict classifier: unknown/nonfinite/future →
  PENDING; probe proven to always supply age). PENDING grace-deferred (recovery
  window = 1 horizon past maturity = det+2H bound enforced), then terminal;
  upgrade rejected with schema rationale; INSUFFICIENT immediate. Contract v1.1
  + additive telemetry. 19 new tests; 35 pytest-style tests converted to TestCase
  (canonical runner silently ran 0 — now all execute). Suite 683/683 OK.
  120 s controlled run COMPLETED (11/11, 0/0, reg=24, 0 writes/errors, DB
  identical 24/99). All 99 rows preserved. Report:
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`.

- `P1-14B.5` (2026-10-10) TRANSPORT RESILIENCE & INDEPENDENT NETWORK DIAGNOSTICS —
  **PASS (operational)**. Attribution: no episode reproduced with identical code/config/host —
  persistent host/bot defects discarded; intermittent path/provider instability (which one:
  UNKNOWN, stated). Independent netprobe (host-pinned, read-only, mirrored params, 17 tests;
  bookTicker-only limitation documented). Coincident windows agree (sub-second both, 0/0/0.00%).
  Health classifier (pure, shared, additive block; 8 tests); watchdog 10/10 re-verified.
  Single ≤35 min run COMPLETED: 2102.5 s, 20/20, 0 reconnects, 0 rejects — ≥30-min healthy
  window DEMONSTRATED. Post-run: 49 setups, 150/150 COMPLETE, 0 dupes. Suite 708/708 OK.
  Gates TRANSPORT/FRESHNESS/PERSISTENCE/SAFETY PASS. Still no 4–6 h authorization. Report:
  `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`.

- `P1-14B.6` (2026-10-10) REPRODUCIBILITY & OPERATIONAL READINESS — **PARTIAL**.
  Second window reproduced both regimes (~22.6 min pristine, then episode to 8.83%,
  abort breached unacted — supervision lost to harness timeout, demerit recorded).
  markPrice placement verified 2×2 (arrays only on /market/stream; --base-path +
  warning + two-instance reference). Vendor incident reports corroborate provider-side
  context. Fixes: heartbeat summaries, host telemetry (CPU/RSS/bytes, UNKNOWN-safe),
  shared health classifier. Discriminating evidence: CPU flat + cadence steady (local
  discarded); references healthy (server-side per-connection attribution refined).
  Post-run: 57 setups, 202/202 COMPLETE, 0 dupes. Suite 726/726 OK. Gates:
  CLOCK/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL. No 4–6 h authorization.
  Report:   `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`.

- `P1-14B.7` (2026-10-10) PERSISTENT SUPERVISION & ENFORCED ABORT GATES — **PASS**.
  `control supervise`: detached registry-leased watcher, documented abort rules (safety,
  5% rejects, 5/10-min reconnects, persistence streaks, clock streaks, DB streaks,
  watchdog-overwhelm compound; UNKNOWN-safe), one-shot verified-PID abort with persisted
  reason, lease takeover, failure budget, V2 additive contract. Identity restored via
  ctypes fallback (wmic absent). 34 new tests incl. REAL-PID abort (foreign survives).
  Suite 760/760 OK. Brief live run clean (12 cycles, zero false aborts; evidence-path
  preservation fix found+proven). 57 setups, 202/202 COMPLETE preserved. Report:
  `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`.

- `P1-14B.8` (2026-10-10) SUPERVISED MAIDEN VOYAGE & ABORT ENFORCEMENT — **PASS**.
  35-min probe (2102.147 s per final_summary, exit 0; 68 summary + one final_summary)
  supervised all 70 cycles with zero agent contact;
  post-hoc: 0.00% rejects, 0 reconnects, reg 57→66, 35 writes, 0 errors — nothing
  breached, correctly nothing aborted (long window ran supervisor-only). Sentinel layer
  completed (lease, stale/FAILED abort via canonical path, own budget, status block, CLI)
  after honest gap (first sentinel died silently pre-cycles; buffered output explains missing
  diagnostics, not the death — `-u`/flush are observability).
  Brief three-layer run clean (14+12 cycles, zero false aborts, zero orphans; DB
  identical 66/228, unchanged from its 66/228 preflight). Suite 775/775 OK. Post-run: 66 setups, 228/228 COMPLETE, 0 dupes.
  Gates all PASS incl. new SUPERVISION_GATE. No 4–6 h authorization. Report:
  `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md` (see its §7 corrections log).

- `P1-14B.8-followup` (2026-10-11) ENFORCE FENCING BOUNDED CORRECTION — **DONE**.
  Frontend review `d80fb9b` HIGH findings fixed deterministically (temp
  registries + mocked termination; 8/13 new fencing tests fail on `8648366`,
  13/13 pass corrected): locked STOPPING acquisition with run/lease/marker
  re-verification, refused/failed marker never terminates, ABORTED/FAILED
  fenced, real `aborted_by`, locked+fenced `sentinel_once`, owned-lease
  heartbeat proof (4x25, 11/22 retained) + sentinel single-winner race.
  Suite 808/808 OK. No probes, P1-14C, long runs or paper trading. DB/logs
  preserved. Historical healthy windows stay historical; no new supervised
  window on the corrected SHA. V2 supervised start still PENDING/separate.
  SUCCESS_GATES untouched.

- `P1-14B.8-V2-51` (2026-10-11) OPERATION-BOUNDARY + READONLY BOUNDED CORRECTION — **DONE (acotado)**.
  Frontend review `35401f9` HIGH findings fixed deterministically (temp
  registries + mocked termination/processes; 15 new boundary/readonly tests
  fail on `0786617`, all pass corrected): locked verify-and-kill inside the
  registry lock with handle-bound `_terminate_verified_pid(pid, ctime)`,
  run-bound `_owner_lease_valid` (watched==run, ACTIVE, ctime) at
  acquisition/pre-kill/marking (x2 owners), pure `status_readonly()` +
  fenced `_reconcile_stale_record` (never overwrites terminals/markers) +
  readonly dashboard GET path, locked `try_register`/`start_probe`/
  `_mark_terminal`/`stop_probe`, multiprocess heartbeat/claim proof
  (counted writes, one winner, all exit 0). Suite 826/826 OK. No probes,
  P1-14C, long runs,   paper or Start. DB/logs/evidence preserved. V2/main
  untouched. No new supervised window on the corrected SHA. Transactional
  supervised start still PENDING/separate. SUCCESS_GATES untouched.

- `DASH-V2-71B` (2026-10-11) SYSTEM DATA CONTRACTS — **DONE (acotado)**.
  V2 checkpoints (`dash-v2-03-token-detail` `f52b68f`) read from Git only:
  already synced at `9f3e084`, no reset/clean/force.
  `docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md`: per-field availability
  matrix (reader/table/column, units, observation-vs-read timestamps,
  nullability, scope/limits, historical-vs-current, side effects),
  safe-reader allowlist, NOT_AVAILABLE host resources (verified absent on
  schema v9/live DB) and ops audit log, V1 diffs, real record examples,
  frontend decisions, retirement blockers. `tests/test_read_purity.py`
  proves the battery mutates nothing (temp fixtures; no defect found → no
  source change). Suite 906/906 OK. No probes, backfills, P1-14C, long
  runs, paper, orders, Start, main merge, or SUCCESS_GATES. SQLite/logs/
  evidence intact.

- `DASH-V2-67-BACKEND` (2026-10-11) HELPER EXTRACTION — **DONE (acotado)**.
  Handoff `8712dfb` read from Git only: audited all helper imports/callers/
  cycles/patch-targets (only `control.py` imported from `dashboard`; views
  use labels/version only); moved the 5 helpers VERBATIM to new
  `host_process.py` (stdlib only); `dashboard.py` re-exports identical
  objects; `control.py` top-level binding with 16 lazy imports removed
  (+1 indentation repair); retargeted 24 `control.pid_is_ours` + 7
  `host_process.process_info` test patches; new boundary tests H1–H4
  failing-first on base. V2-64 doc 5-point corrections applied. Suite
  909/909 OK. No probes, backfills, traffic, P1-14C, long runs, paper,
  orders, Start, main merge, SUCCESS_GATES, formula, or accepted-fix
  changes. No old-UI/file retirement executed. SQLite/registry/logs intact.

- `DASH-V2-64-BACKEND` (2026-10-11) RECONCILIATION + READ CONTRACTS — **DONE (acotado)**.
  V2 checkpoints (`dash-v2-03-token-detail` `8780da2`) read from Git only:
  reconciled `da231b9..c635938` by fast-forward (clean worktree, zero Python
  processes, terminal registry, unheld lock — no reset/clean/kill); deployed
  identity verified (V2 imports this worktree `/src` + `status_readonly()`,
  canonical DB readOnly; deployed == accepted `c635938`).
  `docs/DASHBOARD_V1_READ_CONTRACTS.md`: 7 pages + 25 JSON APIs inventoried
  (fields/units/nullability/timestamps/limits/empty semantics), universe/
  search/history/events/prices specified, persisted-vs-absent split, range
  anchoring (old request-time vs V2 retained-sample) + CSV/JSON metadata,
  diagnostics purity + future-run evidence list, old-server dependency audit
  (blocker: `control.py` imports helpers FROM `dashboard.py`) + reversible
  retirement plan PROPOSED, NOT executed. New pinning tests
  `tests/test_dashboard_get_purity.py` (G1–G3; mutation check fails G1/G3).
  Only additive test file added, no source change. Suite 905/905 OK. No
  probes, backfills, P1-14C, long runs, paper, orders, Start, or gate
  advancement. Frontend reviews the exact SHA before consuming.

- `P1-14B.8-V2-55` (2026-10-11) SUPERVISED TRANSACTIONAL LAUNCH PREPARATION — **DONE (acotado)**.
  Contract-first (`docs/SUPERVISED_LAUNCH_CONTRACT.md`) disabled backend per
  V2-55 acceptance (`7b2b5e75`): `launch_supervised_transaction` refuses
  while disabled with zero side effects; `_launch_supervised_impl` reuses
  `start_probe`/leases/identity/verified termination/lock with finite-budget
  pure verification and kill-only rollback; confirmed/rejected/uncertain
  envelope (point-in-time only); 23-test failure matrix incl. concurrent
  single-confirmation and zero-write purity. No HTTP/CLI wiring, Start stays
  disabled; enablement needs explicit authorization + V2 review of the exact
  SHA. Suite 873/873 OK. No probes, market traffic, P1-14C, long runs, paper,
  orders or Start. V2/main/SUCCESS_GATES intact. No phase advanced.

- `P1-14B.8-V2-54` (2026-10-11) BOOL + LOG-HANDOFF BOUNDED CORRECTION — **DONE (acotado)**.
  Frontend review `d4d82c9` R1/R2 fixed with failing-first hermetic tests:
  exact 32-bit Win32 BOOL signatures + ABI 0/1/256 marshalling proof (7
  tests; width-1 + 256-misread on `b801ab0`), real-`try_register()`
  child-first log handoff under lock with PID+ctime+state revalidation (8
  start-race cases; association None on `b801ab0`), valid evidence
  preserved, foreign/terminal/enforcement races refuse without touching,
  handoff failure keeps the live child with association unconfirmed, C1
  scope qualified (barrier + counted writes + in-window finals only).
  Suite 850/850 OK. No probes, backfills, P1-14C, long windows, paper,
  trading or Start. V2/main/SUCCESS_GATES intact. `status_readonly()` kept.
  Transactional supervised start still separate.

- `P1-14B.8-V2-52` (2026-10-11) NATIVE + START-RACE BOUNDED CORRECTION — **DONE (acotado)**.
  Frontend review `066577e` H1/H2 fixed with failing-first hermetic tests:
  explicit HANDLE-width native signatures + BOOL propagation + bounded
  GetLastError + guaranteed close (9 tests; `0` returned True on `55efaa2`),
  same-child PID+ctime adoption preserving RUNNING+evidence with zero kills
  (5 tests; child-first killed on `55efaa2`), foreign/reused still refused
  with exactly one orphan kill, C1 barrier + [t0,t1] advancement proof.
  Suite 840/840 OK. No probes, P1-14C, long runs, paper, trading or Start.
  V2/main/SUCCESS_GATES intact. `status_readonly()` kept. Transactional
  supervised start still separate.

- `P1-10R` PROLONGED ≥6H SOAK RE-RUN — P1-10 FAIL stays FAIL (truncated at
  4.91h); re-run with dashboard live, blocking survivable launch, merged

  stdout+stderr as UTF-8 (see `docs/DECISIONS.md` launch rule).

- Intended full sequence (binding order):

  P1-11A Raw Feature + Movers Integrity (DONE) → P1-11B Historical Data

  Foundation (DONE) → P1-11B.1 Probe Lifecycle + Run Control (DONE) →

  P1-11C Historical Event Studies (DONE) → P1-10R Formal ≥6h soak

  re-run (DONE — PASS) → P1-12A Market State Classifier v0

  (DONE — PASS) → P1-12B Dynamic Live Universe (DONE — PASS) →

  P1-13A Opportunity / Setup Engine (NEXT candidate) →

  P1-13B Professional Opportunities UX

  → P1-14 Historical Backtester → P1-15 Forward Paper Trading → P1-16 Paper

  Portfolio / Dynamic Exit.

- `P1-13` SIGNAL / EXTREME-MOVE UI — add `/signals`, `/extreme-moves`.

- `P1-14` 24H CALIBRATION REVIEW — thresholds vs real crossings + Phase 1 gate

  evaluation per `docs/SUCCESS_GATES.md`.



Out of phase (do NOT start): full event labeling/outcomes (P2), backtests and

strategies (P3), paper engine/positions (P4), execution (P5).



## BLOCKED



- Nothing currently blocked. `P1-13A` is the next candidate pending

  explicit instruction. Later tasks remain sequenced; each starts after

  its predecessor's evidence is recorded.



## COMPLETED



- `P1-12B.1` (2026-10-08) DYNAMIC UNIVERSE INTEGRITY AUDIT: **PASS**.

  Both review concerns reproduced and fixed: fail-closed ticker-

  timestamp gate (missing/malformed/unit/old/future reject; 60s skew

  tolerance) and single authoritative stream accounting (canonical 11,

  connections≠streams, globals once). Docs re-fetch empty — caps stay

  UNVERIFIED. 496/496 tests (18 new). 240s observe COMPLETED: strict

  gate blocks nothing healthy (3 promotions all LIVE, 0 skips).

  P1-12B PASS record preserved (append-only correction).



- `P1-12B` (2026-10-08) DYNAMIC LIVE UNIVERSE V0: **PASS**.

  Bounded HOT selection + lifecycle (`universe_manager.py`, v0) on two

  managed connections (canonical pair untouched): 3 HOT slots default,

  fail-closed budgets, deterministic movement rank, dwell 1800s,

  demotion cooldown 3600s, CORE never evicted. Engine allow/forget

  (flow/book/returns/structure/classifier/OI) + OI HOT poll list +

  recorder per-symbol PARTIAL finalize. 300s observe validation:

  6 proposals → 3 promotions (OGN/MET/GRIFFAINUSDT) all reaching LIVE,

  0 reconnects/rejects, HOT research buckets captured, 6 symbols

  classified, COMPLETED naturally, 0 orders. 478/478 tests (31 new).

  Spec: `docs/UNIVERSE_SPEC.md`. Transport caps stay UNVERIFIED

  (docs unfetchable here) — re-check before raising budgets.

- `BRAIN-00` (2026-10-06) PROJECT_BRAIN infrastructure: AGENTS.md + 20 docs.

- `P1-00` (2026-10-06) REPOSITORY / TOOLING SANITY: canonical test command

  `python run_tests.py` works from repo root, 28/28 green, no app behavior change

  (new root runner only, prepends `src/` to `sys.path`).

- `ORDER-01` (2026-10-06) PHASE1_ORDER_REFINED: P1-00…P1-14 dependency order

  adopted (dashboard-progressive, classifier-after-validation).

- `P1-01` (2026-10-06) SHORT TRANSPORT VALIDATION: **PARTIAL**. 1805s

  observe-only run, exit 0, 11/11 streams, uptime 98.5%/95.0%, but 58

  reconnects (`ConnectionClosedError`, no close frame), corrected delivery

  lags p50 15–38s / p95 45–76s, 147417 skew-rejections (~85%), depth gaps

  50/49/49, 26 funding events judged sampling artifacts (not signals).

  Evidence: `logs/p1-01/probe-1800s.log` (local, git-ignored). Tests 28/28

  before and after. Gates G2–G4 cannot pass on this evidence.

- `P1-02` (2026-10-06) PERSISTENCE FOUNDATION: **PASS**. SQLite

  (`data/microprobe.db`, git-ignored), 3 tables + 9 indexes, schema v1 with

  version gate + column migration. Write path wired in probe (valid

  observations incl. markPrice MULTI records, skew-rejections to rejection

  table only, periodic snapshots on every summary). Non-blocking verified

  (schedule p50 0.021ms/p95 0.039ms; 2000-row drain 9.2s off-loop).

  47/47 tests green (19 persistence incl. probe write-path integration).

  P1-03 may read via `latest_telemetry()` / `latest_observations()`.

- `P1-03` (2026-10-06) MINIMAL LIVE DASHBOARD: **PASS**. Stdlib-only server

  (`dashboard.py`, v0.3.0, no new deps); routes `/overview`, `/system`,

  `/api/health`, `/api/snapshot` on P1-02 reads. Live at

  http://127.0.0.1:8091 (PID file `logs/dashboard.pid`), health `ok` at

  startup, all routes 200. Live-verified fix: dedicated snapshot writer

  (executor starvation → 0 snapshot rows; +regression test). 66/66 tests

  (18 dashboard). Seeded with real 40s probe data (no mocks).

- `P1-04` (2026-10-06) SYMBOL UNIVERSE + MULTI-TIMEFRAME RETURNS: **PASS**.

  Universe trio preserved with explicit metadata; mark-price log returns

  (7 TFs, 10s buckets, tolerance max(60s, tf/20), UNKNOWN never 0);

  sampling gate (accepted 36/dropped 858 counted in run); schema v2 + tested

  migration; dashboard Symbol Returns + `/api/features/returns` live.

  Live 240s clean run (exit 0, final_summary): 11/11 streams, 5 reconnects,

  11448 skew-rejects (~93% degraded env), engine 46 samples/symbol, 0 invalid,

  inflight high-water 345 drained to 0, safety 0/0/0. 106/106 tests.

- `P1-05` (2026-10-06) DISCOVERY + VELOCITY/ACCEL/RANKING: **PASS**. REST

  discovery (924 seen → 449 eligible → 475 filtered; core pinned); HOT 6

  small sharp movers (USUSDT +41%, 龙虾USDT +35%, BR/ORCA/NMR/GRIFFAIN),

  vote/dwell hysteresis, no WS changes; velocity/accel/ranks live on trio

  (accel honestly warming); intel UI + `/api/discovery` +

  `/api/features/momentum`; persistence v3 + tested migrations; forceOrder

  never-missing; health blocks separated. Clean 240s run (exit 0): 11/11,

  0 reconnects, 0 rejects, 143659 msgs, engine 91 samples/symbol, sampling

   accepted 1888/dropped 141k, high-water 6 → 0, safety 0/0/0. 144/144 tests.

- `P1-06` (2026-10-07) VOLUME + AGGRESSIVE TRADE FLOW: **PASS**. Official

  aggTrade docs + live payload verified (`m`/RPI-`nq`/`E`/`st`);

  `flow.py` engine (6 trailing horizons, 4 baselines, acceleration,

  same-E arrival fix after run 1 proved `<=` undercounts); schema v4 +

  tested migrations; dashboard v0.5.0 (flow table, split bars, DISCOVERY

  ONLY labels, `/api/features/flow` + `/volume`). Healthy 363s run

  (exit 0): 11/11, 0 reconnects, 0 rejects, 4027/4027 aggTrades into the

  engine (746 persisted raw — sampling provably lossless to flow),

  168/168 buckets, latency p50 0.030ms/p95 0.069, queue 0/0, safety 0/0/0.

   190/190 tests (46 new). Evidence: `logs/p1-06/` (local, git-ignored).

- `P1-07` (2026-10-08) ORDER BOOK + OPEN INTEREST: **PASS**. Depth/OI docs

  + live payloads verified (full-snapshot `pu`-chain, OI shape);

  `book.py` (spreads, top-N sums, imbalances, microprice, slopes,

  concentration, gap→DEGRADED recovery) + `open_interest.py` (60s bounded

  poller, 1m/5m/15m deltas, accel, descriptive contexts); schema v5 +

  tested migrations; dashboard v0.6.0 (book/OI tables, NO LIVE FLOW/BOOK,

  `/api/features/book` + `/open-interest`). Live 363s run (exit 0):

  11/11, 1 reconnect, book 7309/7309 valid (1 gap/symbol recovered),

  OI 18/18 polls ok, flow 5684 intact, sampling lossless, safety 0/0/0.

   239/239 tests (49 new). Evidence: `logs/p1-07/` (local, git-ignored).

- `P1-08` (2026-10-09) VWAP + VOLATILITY + STRUCTURE: **PASS**. Zero new

  sources (flow-VWAP, bucket vol/range/structure, mark reference);

  `market_structure.py` (stateless over peer state; displacement, raw

  `sqrt(sum(r²))`, median/z expansion, confirmed pivots, breakout tags;

  resilience deferred); schema v6 + tested migrations; dashboard v0.7.0

  (structure table + vwap/volatility/structure APIs, P1-09-ready

  contracts). Live 372s run (exit 0): 11/11, 2 reconnects, STRUCT 27

  evals p50 0.84ms, flow/book/OI intact, sampling lossless, safety 0/0/0.

  277/277 tests (38 new). Evidence: `logs/p1-08/` (local, git-ignored).

- `P1-09` (2026-10-09) MARKET-INTELLIGENCE DASHBOARD: **PASS**. Terminal IA

  (OVERVIEW/MOVERS/`/symbol/:symbol`/SYSTEM + search), capability/tier

  vocabulary, mark-price chart + CSV APIs (bounded, no new source), book

  integrity copy, code split (data/components/views). Dashboard v0.8.0

  live at http://127.0.0.1:8091. Live 360s run (exit 0): 11/11, 0

  reconnects, 0 rejects, lags p50 ~180–260ms, all engines green, safety

  0/0/0; 22 routes 200; discovery-only honesty verified (龙虾USDT).

  312/312 tests (35 new). Evidence: `logs/p1-09/` (local, git-ignored).

  P1-10 NOT started; P1-01R still owed before it.

- `P1-01R` (2026-10-07) TRANSPORT RE-VALIDATION: **PASS**. Attached

  2700s observe-only run (exit 0): 11/11 streams, 0 reconnects, 0 rejects,

  corrected lags p50 171–251ms / p95 ≤390ms, gaps 0, clock 5/5 ok,

  engines green, persistence drained, safety 0/0/0; dashboard `ok`

  while fed, honest `stale` after. Evidence: `logs/p1-01r/`

  (local, git-ignored). P1-10 soak gate unblocked; P1-10 NOT started.

- `P1-10` (2026-10-07) PROLONGED SOAK: **FAIL** (truncated). Requested

  21600s, one continuous process, but killed externally at 17677.9s

  (4.91h, 81.8%) with no `final_summary` and unknown exit. 554 gap-free

  periodic summaries fully audited: bookTicker core stayed P1-01R-grade

  (p50 ~190–200ms) while aggTrade ETH/SOL (p50 90–152s), depth/markPrice

  tails and a final-hour reconnect storm (29 reconnects + 366k rejects in

  55 min) regressed to P1-01-grade. Engines/persistence/dashboard/safety

  all behaved (details in `docs/CURRENT_STATE.md`). Evidence:

  `logs/p1-10/probe-21600s.log` (local, git-ignored). Requires `P1-10R`.

- `P1-11A` (2026-10-07) RAW FEATURE + MOVERS INTEGRITY AUDIT: **PASS**.

  Used the valid 4.91h of P1-10 evidence (P1-10 stays FAIL). Movers

  shared-`_v` contamination bug found, root-caused, fixed narrowly

  (per-category display keys; sources/sorts/units/formatters unchanged;

  5 new `MoversIntegrityTest` tests fail 4/5 on old code, pass 5/5 fixed).

  All feature families measured trustworthy as raw research inputs

  (scales/availability in `docs/FEATURE_MODEL.md`; healthy-vs-degraded

  comparison: degradation starves honestly, OI isolated, no corruption).

  Design-only plans added: `docs/SIGNAL_RESEARCH_PLAN.md` (BTC context,

  exhaustion, absorption, opportunity lifecycle, backtest/paper sim),

  `docs/HISTORICAL_RESEARCH_PLAN.md` (P1-11B/C). 317/317 tests.

- `P1-11A.1` (2026-10-07) MOVERS VELOCITY SEMANTICS: **PASS**. Sign-filtered

  leader tables (positive only >0, negative only <0; zero/None/NaN/inf in

  neither; honest empty notes). 5 new `MoversVelocitySemanticsTest` tests

  fail 5/5 on old code. Live-verified after restart. 322/322 tests.

- `P1-11B` (2026-10-07) HISTORICAL DATA FOUNDATION: **PASS**. Docs site

  unfetchable → 7 contracts verified live (klines/mark/aggTrades/OI-hist/

  exchangeInfo/weights/limits in `docs/MARKET_DATA.md`). Separate research

  DB schema v1 (mark table structurally volume-free); bounded pagination +

  resume + idempotency + adaptive limiter + 429/418 policy; listing-aware

  ingest (BTC Sep-2019 … ORCA Dec-2024 geneses recorded); CLOSED candles

  only; gaps stay UNKNOWN. Pilot 13 series ratio 1.0 (OI capped at 500

  rows/~41.6h served; aggTrades recent-only; no book reconstruction).

  CLI + `/api/history/*` + token coverage card live. 353/353 tests.

- `P1-11B.1` (2026-10-07) PROBE LIFECYCLE + DASHBOARD RUN CONTROL: **PASS**.

  Canonical `control.py` + registry + probe self-registration (direct

  launches converge); single-instance refusal; verified-PID-only stop;

  merged UTF-8 run logs; POST-only localhost control API (nonce+Origin);

  MARKET ENGINE header UI with polling (Continuous/6h/6H-Validation).

  Live roundtrip proven (dashboard start→RUNNING→STALE→ok→stop; external

  start auto-discovered; 90s run COMPLETED; dashboard survived).

  376/376 tests (23 new).

- `P1-12A` (2026-10-08) MARKET STATE CLASSIFIER V0: **PASS**.

  Deterministic explainable classifier (`classifier.py`, rules v0.1.0,

  all-HYPOTHESIS): NORMAL/IGNITION/EXPANSION/EXHAUSTION/REVERSAL +

  UNKNOWN, UP/DOWN/NONE/UNKNOWN, evidence for/against, missing list,

  validity, transitions with hysteresis (2-eval dwell) + 2-eval reversal

  confirmation, cold-restart memory, no forced sequence, no probabilities.

  Schema v7 (`state_features` + `state_transitions` ≤500); probe

  evaluates per summary (~0.2ms); token-page state panel (no new HTTP

  contract; no Next.js changes). 120s observe run COMPLETED: 9 evals,

  states + 4 transitions persisted, 0 rejects/reconnects, 0 orders.

   447/447 tests (25 new classifier + 2 new persistence). Spec:

   `docs/CLASSIFIER_SPEC.md`.

- `P1-10R-FIX-01` (2026-10-08) WINDOWS CONSOLE POPUPS: **FIXED**.

  `dashboard.no_window_flags()` (CREATE_NO_WINDOW, POSIX-neutral) applied

  to tasklist/wmic identity checks + probe spawn; semantics preserved.

  420/420 tests (12 new, mocked). Dashboard restarted 30984 → 28440;

  75s observe lifecycle COMPLETED naturally with feed HEALTHY while fed.

  P1-10R PASS and P1-12 READINESS unchanged.

- `P1-10R` (2026-10-08) FORMAL ≥6H SOAK RE-RUN: **PASS**. One continuous

  WMI-detached process (PID 19084, 00:48:20Z → 06:48:23Z, 21603.9s ≥

  21600s), registry COMPLETED + duration-reached + exit 0, final_summary

  present, 699 gap-free summaries. Transport: 11/11 streams, 19.0M msgs,

  10 reconnects (all auto-recovered), 0.76% skew-rejects, uptime

  99.10%/99.95%, p50 170–250ms; worst episode ~04:20–04:29Z (~9.5min,

  market handshake timeouts, self-recovered); final hour perfectly clean

  (0 reconnects, 0 rejects) — no P1-10-style collapse. Engines all

  monotonic (flow 566k, book 587k, returns 3886/symbol over 31.5h, OI

  1029/1029, discovery 36 scans). Research recorder drained STOPPED:

  8273 writes, 0 drops, 0 errors (+6191/+1041/+1041 rows, ~96% of

  estimate). DBs bounded (microprobe +32MB at retention caps;

  historical +1.6MB) and integrity-ok. Dashboard alive and truthful;

  popup defect stayed cosmetic. Safety 0/0/0. 408/408 tests.

  Evidence: `logs/p1-10r/probe-20261008T0048Z.log` (local, git-ignored).

   Full analysis in `docs/CURRENT_STATE.md`.

- `P1-11C` (2026-10-07) HISTORICAL EVENT STUDIES + PROSPECTIVE CAPTURE:

  **PASS**. No-lookahead engine (`events.py`, 6 versioned HYPOTHESIS

  families) + schema-v2 event tables in the historical DB + probe-owned

  async flow-10s/1m + book-1m recorder (starts/drains with MarketProbe;

  drops-with-telemetry; failure-isolated; idempotent; bounded retention).

  Pilot 38 runs (6 families × pilot symbols on stored 1h/15m bars; NMR

  added via 2-request bounded extension, 719 bars ratio 1.0). Short live

  verification 153s COMPLETED via the canonical control plane (writes 60,

  drops 0, errors 0). Dashboard `/api/research/status` + `/api/events/*`

  + token research card live. 408/408 tests (32 new).



## LAST_VERIFICATION

- 2026-10-11 DASH-V2-62: 902/902 OK, 160.768s, exit 0; 52 focused. Disabled launch corrections; report linked in latest checkpoint.



- 2026-10-11 (DASH-V2-71B): `python run_tests.py` → 910/910 OK (902 + 3 + 4 + 1 read-purity).
  System data contracts per V2 handoff (`f52b68f`); synced at `9f3e084`, no
  reset/clean/force; matrix + purity proof, no source change (no defect in
  read paths). No probes, backfills, P1-14C, long runs, paper, orders,
  Start, main merge, or SUCCESS_GATES. SQLite/logs/evidence intact. Next:
  frontend exact-SHA review; P1-14C needs explicit instruction.

- 2026-10-11 (DASH-V2-67-BACKEND): `python run_tests.py` → 909/909 OK (905 + 4 boundary).
  Helper extraction per handoff `8712dfb` (audit + verbatim move + re-export
  compat + 24/7 patch retargets + H1–H4 failing-first). V2-64 doc corrections
  applied. No probes, backfills, traffic, P1-14C, long runs, paper, orders,
  Start, main merge, or SUCCESS_GATES. SQLite/registry/logs intact. Next:
  frontend exact-SHA review; P1-14C needs explicit instruction.

- 2026-10-11 (DASH-V2-64-BACKEND): `python run_tests.py` → 905/905 OK (902 + 3 GET-purity pins).
  Reconciliation + read contracts per V2 handoff (`8780da2`); FF `da231b9..c635938`
  with zero processes/conflicts; deployed identity verified; inventory +
  diagnostics + history/export contracts + retirement proposal (blocked on
  helper extraction); mutation check fails G1/G3. No probes, backfills, P1-14C,
  long runs, paper, orders, Start, or gate advancement. V2/main/SQLite/logs
  intact. Next: frontend exact-SHA review; P1-14C needs explicit instruction.

- 2026-10-11 (P1-14B.8-V2-55): `python run_tests.py` → 873/873 OK (850 + 23 supervised-launch).
  Contract-first disabled preparation per V2-55 acceptance (`7b2b5e75`):
  envelope confirmed/rejected/uncertain, finite-budget pure verification,
  kill-only rollback, 23-test failure matrix (full path, per-component spawn
  failures, lease matrix, death/reuse, timeout, unreadable, takeover/terminal
  interleaves, uncertain rollbacks, concurrent single-confirmation, repeat
  rejection, zero-write purity). Found+fixed in passing: per-thread global
  Popen patches leak process-wide (single parent-held patch now). No probes,
  market traffic, P1-14C, long runs, paper, orders or Start; V2/main/
  SUCCESS_GATES intact; `status_readonly()` kept. No new supervised window.
  Transactional enablement still needs explicit authorization + V2 review.

- 2026-10-11 (P1-14B.8-V2-54): `python run_tests.py` → 850/850 OK (840 + 7 win32-bool + 3 start-race delta).
  R1/R2 corrected per frontend review `d4d82c9` (key cases fail on `b801ab0`,
  all pass corrected; C1 wording qualified, M1 assertions unchanged in count).
  No probes, backfills, P1-14C, long windows, paper, trading or Start;
  DB/logs/evidence preserved; V2/main/SUCCESS_GATES intact; `status_readonly()`
  kept. No new supervised window on the corrected SHA. Transactional supervised
  start still separate. Next: backend SHA review; P1-14C needs explicit instruction.

- 2026-10-11 (P1-14B.8-V2-52): `python run_tests.py` → 840/840 OK (826 + 9 native + 5 start-race).
  H1/H2 corrected per frontend review `066577e` (key cases fail on `55efaa2`,
  all pass corrected; C1 barrier + window proof strengthened in place).
  No probes, P1-14C, long runs, paper, trading or Start; DB/logs/evidence
  preserved; V2/main/SUCCESS_GATES intact; `status_readonly()` kept. No new
  supervised window on the corrected SHA. Transactional supervised start
  still separate. Next: backend SHA review; P1-14C needs explicit instruction.

- 2026-10-11 (P1-14B.8-V2-51): `python run_tests.py` → 826/826 OK (808 + 8 boundary + 7 readonly + 3 multiprocess).
  Operation boundary + readonly corrected per frontend review `35401f9`
  (15 new tests fail on `0786617`, all pass corrected; heartbeat counting
  fails before the bool-return change). No probes, P1-14C, long runs, paper
  or Start started; DB/logs/evidence preserved; V2/main untouched.
  No new supervised window on the corrected SHA (historical windows stay
  historical). Transactional supervised start still PENDING/separate. Next:
  backend SHA review before operational integration; P1-14C needs explicit
  instruction.

- 2026-10-11 (P1-14B.8-followup): `python run_tests.py` → 808/808 OK (794 + 13 fencing + 1 sentinel race).
  Enforce fencing corrected per frontend review `d80fb9b` (8/13 new tests fail on `8648366`,
  13/13 pass corrected; owned-lease heartbeat proof replaces the no-op fixture).
  No probes, P1-14C, long runs or paper trading started; DB/logs preserved.
  No new supervised window on the corrected SHA (historical windows stay historical).
  V2 supervised start still PENDING/separate. Next: backend SHA review before
  operational integration; P1-14C needs explicit instruction.

- 2026-10-10 (P1-14B.8): `python run_tests.py` → 775/775 OK (760 + 15 sentinel).
  35-min supervised window post-audited (2102.1 s, 0/0/0.00%, 70 supervised cycles,
  natural completion); brief three-layer validation clean (supervisor 14 + sentinel 12
  cycles, zero false aborts, zero orphans, DB identical). Next: repeat advisable before
  any 4–6 h authorization; P1-14C needs explicit instruction.



- 2026-10-10 (P1-14B.7): `python run_tests.py` → 760/760 OK (726 + 34 supervisor).
  Brief live run (150 s probe + 12-cycle supervisor) clean: claimed, heartbeated to
  natural completion, zero false aborts; probe 11/11, 0/0, DB byte-identical.
  Next: supervised ≥30 min healthy run before any 4–6 h authorization; P1-14C needs
  explicit instruction.



- 2026-10-10 (P1-14B.6): `python run_tests.py` → 726/726 OK (708 + 18: path, warning,
  heartbeat, host telemetry). Single ≤35 min run COMPLETED naturally (2102.5 s, exit 0)
  with concurrent dual reference (bookTicker + array, both attempts 1, errors {});
  post-run 57 setups / 202 COMPLETE / 0 dupes. Verdict PARTIAL (22.6 min healthy <30;
  abort breached unacted — supervision lost). Next: supervised ≥30 min healthy run before
  any 4–6 h authorization; P1-14C needs explicit instruction.



- 2026-10-10 (P1-14B.5): `python run_tests.py` → 708/708 OK (683 + 17 netprobe + 8 health).
  Single ≤35 min run COMPLETED naturally (2102.5 s, 20/20, 0 reconnects, 0 rejects,
  exit 0) with concurrent 40-min reference (attempts 1, errors {}); post-run 49 setups /
  150 COMPLETE / 0 dupes. ≥30-min healthy window demonstrated with reference agreement.
  Next: repeat advisable before any 4–6 h authorization (recurrence risk); P1-14C needs
  explicit instruction.



- 2026-10-09 (P1-14B.4): `python run_tests.py` → 683/683 OK (648 + 19 new
  lifecycle tests + 16 net from executing the converted test_prospective).
  120 s controlled run COMPLETED naturally (11/11, 0 reconnects/rejects,
  reg=24, 0 writes/errors, DB byte-identical). Contract v1.1 enforced.
  Next: ≥30 min healthy run before any 4–6 h authorization; P1-14C needs
  explicit instruction.



- 2026-10-09 (P1-14B.3): `python run_tests.py` → 629/629 OK (609 + 20 new
  transport-freshness tests). Single ≤35 min run aborted at 17.1 min
  (watchdog recovery proven live, then path outage; exit 0, controlled stop,
  evidence preserved); post-run 24 setups / 99 COMPLETE / 0 dupes. Verdict
  PARTIAL (duration insufficient; transport limiting). Next: clean 10-min
  pre-window + ≥30 min healthy run before any 4–6 h authorization; P1-14C
  needs explicit instruction.



- 2026-10-09 (P1-14B.2): `python run_tests.py` → 609/609 OK (no code/test
  changes — no confirmed defect). 35-min stability run aborted at 23.4 min
  per the >5 % reject rule (exit 0, controlled stop, evidence preserved);
  post-run audit 24 setups / 68 COMPLETE / 0 dupes. Verdict PARTIAL
  (duration insufficient; transport limiting). Next: clean 10-min pre-window
  + ≥30 min healthy run before any 4–6 h authorization; P1-14C needs
  explicit instruction.



- 2026-10-09 (P1-14B.1): `python run_tests.py` → 609/609 OK (593 + 16
  new time-integrity tests; 1 P1-14B restart test hardened to the
  no-re-emission contract). Three controlled 120 s observe runs COMPLETED
  (exit 0, safety 0/0/0): rehydration live (reg=7), per-cycle observation
  live (27 + 24 emissions), cross-key accumulation live (28 rows, 0 dupes).
  Next: prolonged-run readiness blockers (30+ min healthy window, clock
  resync note) before any 4–6 h run; P1-14C needs explicit instruction.



- 2026-10-08 (P1-12B.1): `python run_tests.py` → 496/496 OK (478 + 18

  new freshness/accounting tests; toy-epoch fixtures migrated to

  realistic ms epochs). 240s observe COMPLETED (strict gate live-proven).

  Next: P1-13A candidate (needs explicit instruction).



- 2026-10-08 (P1-12B): `python run_tests.py` → 478/478 OK (447 + 31 new

  universe/manager/transport/recorder/classifier tests). 300s observe

  validation COMPLETED via WMI-detached canonical module (temp 60s-scan

  config; repo config untouched): 3 promotions all LIVE, HOT research +

  classifier + dashboard verified, 0 orders. Next: P1-13A candidate

  (needs explicit instruction).

- 2026-10-08 (P1-12A): `python run_tests.py` → 447/447 OK (420 + 25 new

  classifier + 2 new persistence). 120s observe run COMPLETED via the

  canonical plane (9 evals ~0.2ms, states + transitions persisted, token

  pages render, dashboard restarted for the new panel). Next: P1-12B

  candidate (needs explicit instruction).

- 2026-10-08 (P1-10R-FIX-01): `python run_tests.py` → 420/420 OK (408 +

  12 new mocked identity tests; one pre-existing Popen fake extended for

  the new kwarg). Dashboard 30984 → 28440; 75s observe run COMPLETED;

  both frontends 200. P1-10R PASS / P1-12 READY unchanged.

- 2026-10-08 (P1-10R): **PASS**. `python run_tests.py` → 408/408 OK

  (no app changes). 21603.9s continuous, COMPLETED + duration-reached +

  exit 0, final_summary present. Transport/honest-episode analysis,

  research drain (8273/0/0), and gate matrix in `docs/CURRENT_STATE.md`.

  Next: P1-12 READY (needs explicit instruction; thresholds HYPOTHESIS).

- 2026-10-07 (P1-11C): `python run_tests.py` → 408/408 OK (376 + 32 new

  event/recorder tests). Pilot 38 bounded runs stored (NMR extension:

  2 requests, 719 bars, ratio 1.0). Short live verification 150s →

  COMPLETED naturally (research writes 60, drops 0, errors 0). New

  research/event APIs live-verified (200). P1-10R now PASS (see above).

- 2026-10-07 (P1-11B.1): `python run_tests.py` → 376/376 OK (353 + 23 new

  lifecycle/API tests). Live roundtrip verified (dashboard + external

  starts, feed transitions honest, dashboard survived all stops). P1-11C

  DONE. P1-10R still pending (6H-Validation preset mechanics ready;

  audit decides PASS).

- 2026-10-07 (P1-11B): `python run_tests.py` → 353/353 OK (322 + 31 new

  mocked-HTTP history tests). Pilot 13 series ratio 1.0 in

  `data/historical/historical.db`; CLI + history APIs live-verified.



- 2026-10-07 (P1-11A): `python run_tests.py` → 317/317 OK (312 + 5 new

  `MoversIntegrityTest`). Movers fix + full feature validation recorded in

  `docs/CURRENT_STATE.md` + `docs/FEATURE_MODEL.md`; P1-10 stays FAIL.

- 2026-10-07 (P1-10 closure): `python run_tests.py` → 312/312 OK (no app

  code changed during the soak; HEAD still `cca1b78`). Soak FAIL closed

  (17677.9s/21600s, truncated, evidence in `docs/CURRENT_STATE.md` +

  `logs/p1-10/`).



- 2026-10-07 (P1-01R): `python run_tests.py` → 312/312 OK (before run;

  no code changed). 2700s transport run PASS (0 reconnects, 0% rejects,

  sub-second lags). Full evidence in `docs/CURRENT_STATE.md` +

  `logs/p1-01r/`.

- 2026-10-09 (P1-09): `python run_tests.py` → 312/312 OK. Terminal live

  (v0.8.0, 22 routes 200, chart + CSV + search verified, safety 0/0/0).

  Full evidence in `docs/CURRENT_STATE.md` + `logs/p1-09/`.

- 2026-10-09 (P1-08): `python run_tests.py` → 277/277 OK. Structure

  eval live (27 evals, p50 0.84ms); dashboard v0.7.0 with structure

  table + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.

- 2026-10-08 (P1-07): `python run_tests.py` → 239/239 OK. Book engine live

  (7309/7309, p50 0.15ms); OI 18/18 polls; dashboard v0.6.0 with book/OI

  tables + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.

- 2026-10-07 (P1-06): `python run_tests.py` → 190/190 OK. Flow engine live

  (4027/4027 accepted, 0 late, 0 invalid); dashboard v0.5.0 `ok`-while-fed

  with flow table + APIs (200). Full evidence in `docs/CURRENT_STATE.md`.

- 2026-10-06 (P1-05): `python run_tests.py` → 144/144 OK. Discovery live

  (449 eligible, HOT 6 small movers, promotions logged); momentum/ranks live

  on trio; clean 240s run exit 0 with final_summary

  (`logs/p1-05/probe-240s-clean.log`); dashboard `ok`-while-fed,

  STALE/DEGRADED honestly after. Full evidence in `docs/CURRENT_STATE.md`.

- 2026-10-06 (P1-04): 106/106 OK; dashboard live at http://127.0.0.1:8091.

- 2026-10-06 (P1-01): 1805s observe-only probe: exit 0, safety 0/0/0

  throughout; transport unhealthy in this environment (58 reconnects, p50 lags

  15–38s, 85% skew-rejected). Full evidence in `docs/CURRENT_STATE.md`.

- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1

  (dashboard port policy evidence).

- Dashboard RUNNING at http://127.0.0.1:8091 (PID tracked in

  `logs/dashboard.pid`); snapshot STALEs honestly without a live probe feed.



## LAST_COMMIT



- Branch `phase1/market-intelligence-dashboard` published to private

  `mariomoreta/binance-futures-microstructure-bot` (origin in sync).

  P1-05 implementation/docs commit follows on this branch.


## Suplemento estructura historica — 2026-10-16 (solo documental)
F-STRUCTURE-EXIT-01 en HISTORICAL_STRUCTURE_AND_EXIT_PLAN.md define contexto
multihorizonte compacto, zonas causales y politicas de stop a evaluar.
Fase causal/costes activa conserva prioridad. No datos nuevos, codigo,
backfill, servicios, sesiones ni gates cambiados. Reconciliar despues de la
entrega del agente sin sobrescribir sus archivos concurrentes.
(Integracion 2026-10-17: portado selectivo desde
review/extreme-movers-objective-20261016 hasta 7a4e872.)

## Corrección de defectos restantes de la auditoría EVAL-CENSUS-V2 — 2026-10-19 (completada, sin push aún)

Se corrigieron los defectos pendientes de la auditoría sobre el commit candidato 2677b2f (rama review/o1-funcional-v2-observacion), sin corridas Binance, sin forward/paper/órdenes, sin cambios de estrategia/mapping/costes/umbrales y sin tocar DBs canónicas, dashboard ni servicios.

- Tiempos obligatorios en vincular_trades_eventos: entry_ms/available_at/H2 close_time_ms finitas requeridas; ausencia → INCOMPLETE (nunca aceptación implícita); entrada antes de disponibilidad → FAIL; respaldo por símbolo/resolución/familia/dirección/identidad sin cruzar resoluciones.
- Reconstrucción fail-closed (reconstruct_replay_traces.py): celda fallida no publica trazas como "verificada"; trazas fallidas van a diagnostico_celdas_fallidas.json (FALLIDA_NO_CONSUMIBLE, rechazado por el ledger); manifiesto con veredicto/cobertura/hashes validado por el ledger antes de consumir; no quedan archivos antiguos de ejecuciones previas.
- Modo temp: events_pre definido (n_in_pre_purge); --package sin segunda purga; exactamente uno de --package/--temp-dir (ambos/ninguno → error); equivalencia entre modos verificada.
- Pruebas de integración obligatorias (reconstructor → archivos → ledger): 17 casos + control; cada defecto produce FAIL/INCOMPLETE con exit ≠ 0; control PASS exit 0.
- Checkout limpio verificado: hashes paquete 33/33 OK; trades regeneradas (exit 0, COMPLETO, 168 celdas, 5255 trades); ledger (exit 1, INCOMPLETE, 0 discrepancias, trazabilidad COMPLETO). Comandos/estados/exits/hashes en C:\proyectos\binance-temp\audit_checkout_20261019\verificacion_checkout.txt.
- Veredictos separados: replay BTC/ETH/SOL = PASS (alcance explícito); censo extendido MINA/NMR = INCOMPLETE (tail-edge sin build_report). Global INCOMPLETE no rebajado.
- Residual: falta build_report para MINAUSDT/1h y NMRUSDT/1h (gap de evidencia del censo externo al replay, no defecto del replay).

Suite completa: 1274 tests OK (2 skipped). Barrera de aislamiento: hashes_equal=True, file_writes=0.

Pendiente (siguiente acción): incorporar manifiestos temp/opencode a Git y/o publicar el build_report de MINAUSDT/1h y NMRUSDT/1h para cerrar los 2 tail-edge y pasar el veredicto global a PASS; luego commit selectivo + push + entrega con SHA.

## Reconciliación plan → proyecto actual y ruta a selección automática + Paper Lab (2026-10-20, presupuesto cero)

### Estado de identidad (sin reset/clean/force)
- Rama: `review/o1-funcional-v2-observacion`, al día con `origin/review/o1-funcional-v2-observacion` (`git fetch` sin cambios remotos nuevos).
- Remoto: `https://github.com/mariomoreta/binance-futures-microstructure-bot.git` (fetch + push).
- SHA de este ciclo (inicial): `b9c27338dee21160da9a839894029c3c70b0e316`.
- Cambios locales preexistentes NO creados/stageados por este agente: `frontend/src/app/paper-lab/page.tsx`, `TopNav.tsx`, `format.ts` (modificados); Paper Lab (componentes, tests, build script, artefacto) todo **untracked**. Se preservan sin tocar.

### Correcciones al informe previo (commit b9c2733 = solo 12 líneas en PAPER_LAB_PLAN_ETAPA5.md; no reconciliación completa)
1. `audit_public_data` **NO LOCALIZADA** (ni checkout ni Git). Los 39 tests son `tests/test_p14b_validation.py` (P1-14B.1–.11), real pero ajeno a esa entrega.
2. Esquema operativo vigente: **v10** (22 tablas) + histórico **v3** (16 tablas). No describir v9 como operativo.
3. Trades 5255 desglosados: Hipótesis 2991 (5 abiertas → 2986 realizadas); Placebo 2264 (2 abiertas → 2262 realizadas); total 5255 (7 abiertas → 5248 realizadas). `realizadas = trades − abiertas`.
4. MFE/MAE = **excursión**, NO ganancia capturada por la salida.
5. V2: `/movers` real; `/paper-lab` componente real; `/backtest` **stub** (FutureWorkspace). No declarar vistas inexistentes.
6. Paper Lab: **publicado, probado y servido** en la entrega de 2026-10-20; artefacto determinista `--check` sha256 `96a5fa46...` (**actualizado a `0db0c4d0...` el 2026-10-20 con las correcciones acotadas de causalidad/gráfico/estados**); servida la operación LONG en `127.0.0.1:3020/paper-lab`. (Estado previo a la entrega: todos untracked y sin servir.)

### Selector: no sobreestimar el censo
EVAL-CENSUS-V2 evalúa reglas/variables que contiene; **no sustituye** universo histórico, ranking rolling24 ni liquidez ausentes. No ejecutar evaluación completa del selector por faltar inputs. Protocolo de adquisición escalonado preparado (universo ligero → candidatos → detalle limitado, fuentes gratuitas Binance públicas, sin colectores iniciados). Matriz detalle en `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md`.

### Paper Lab (cuatro estados, cierre funcional 2026-10-20 — antes: solo documental)
1. Trabajo local: `frontend/src/components/paper-lab/`, `frontend/src/lib/paper-lab-replay.ts`, `frontend/src/app/paper-lab/page.tsx`, `scripts/build_paper_lab_replay.py`, `frontend/src/artifacts/paper-lab-replay-v1.json`, tests. No es motor de paper.
2. Código publicado en Git: artefacto, generador, parser/player, componentes, ruta y tests publicados en la entrega de 2026-10-20. `/backtest` sigue stub.
3. Probado: `build_paper_lab_replay.py --check` PASS (sha256 `96a5fa46…`; **actualizado a `0db0c4d0…` el 2026-10-20**, ver correcciones acotadas más abajo); suite frontend 347/347 → **368/368** tras las correcciones acotadas; `tsc --noEmit` limpio; `eslint src` 0 errores; `next build` OK. Tests de fronteras t−1/t/t+1, estados, contexto y rechazos.
4. Servido: build de Next servida en `127.0.0.1:3020/paper-lab` (sin monitor activo), sirve **LONG** (`PLR-BTCUSDT-LONG-1788903900000`), no la SHORT obsoleta. Capturas desktop+mobile de tres estados generadas; verificación de contenido por árbol de accesibilidad + texto + geometría de DOM. La inspección **visual** de las PNG queda a cargo del revisor humano (APIs de visión del entorno caídas).

### Correcciones acotadas de Paper Lab (2026-10-20, sobre d9359e3)

- **Causalidad (formación vs disponibilidad):** eliminado el paso `signal` en `event_time_ms`; la detección se revela en `available_at` con `formation_time_ms` como metadata. `initial_cursor_ms` define la vista inicial (anterior a la detección) con contexto ya conocido. Invariantes en generador/parser + tests t−1/t/t+1, formación, entrada/salida y «datos posteriores no alteran la vista anterior».
- **Estados del reproductor** (`sin_iniciar`/`reproduciendo`/`pausado`/`terminado`) separados de los de posición; reiniciar restablece ambos; avanzar manual con posición abierta ya no muestra «REPOSO» (muestra PAUSADO).
- **Gráfico/etiquetas:** SVG responsive (sin recorte en 360/390px), anti-solape de etiquetas (línea conserva su precio real), leyenda, frontera contexto/replay en la primera vela del replay, eje con margen. Verificación geométrica de DOM: sin overflow de página, 0 elementos fuera de viewport, 0 textos SVG fuera de viewBox.
- **Nuevo artefacto/build:** sha256 `0db0c4d0cf1767736cbeafbae62e12a10adce512e423520bb5046c58dfbfff99`; 7 pasos (3 velas + 4 eventos); `BUILD_ID=45NLJvJuWqcMjj2IFxW-E`. Mecánica económica sin cambios (`gross=-0.02421656234419101`, `net=-1.6241971890943157`).

### Próxima acción concreta (única)
Definir y ejecutar (offline, sobre copia, presupuesto cero, sin órdenes ni capital) el protocolo de selección automática sobre EVAL-CENSUS-V2 (info disponible en T, sin lookahead, ventana incompleta → UNKNOWN), emitiendo WATCH / SIN_ENTRADA / DESCARTADO con motivo versionado. Dependencia previa al motor paper completo (Etapa 5). La entrega funcional de Paper Lab (replay histórico) ya está cerrada en esta rama; no duplica ese trabajo.

### Correcciones 2026-10-21 (identidad del artefacto y estudio retrospectivo W/LUMIA)

- **Identidad del artefacto Paper Lab (verificada en código y en build servida):** **BTCUSDT 15m LONG H1** (no SHORT). `replay_id=PLR-BTCUSDT-LONG-1788903900000`, `event_time_ms=1788903900000` (2026-09-08T21:45:00Z), `entry_ms=1788904800000` (22:00:00Z), `exit_ms=1788907500000` (22:45:00Z, salida por `horizon`), `gross_pnl=-0.0242`, `net_pnl=-1.6242` (pérdida). Artefacto determinista `frontend/src/artifacts/paper-lab-replay-v1.json` (sha256 `96a5fa46…`; **actualizado a `0db0c4d0…` el 2026-10-20**); 8 pasos (vela/evento) → **7 pasos (3 velas + 4 eventos)** + 48 velas de contexto previo real (solo visuales).
- **Frontera de revelación causal (corregida):** la cinta **separa pasos de vela de pasos de evento**; un evento se revela en su propio paso, en su ms exacto (`04:00:00.000` no es conocido con cursor `03:59:59.999`). Invariante `event.at_ms <= step.known_at_ms` verificada por generador y parser. La propuesta previa (revelar todo en el cierre de vela) era incorrecta.
- **Estudio retrospectivo W/LUMIA (auditoría, sin segunda implementación):** paquete `binance_case_study/` (12 archivos, hashes 12/12 OK). 1.499 velas 5m cerradas + 1.499 velas 1m cerradas por símbolo (WUSDT, LUMIAUSDT, BTCUSDT, GTCUSDT), corte `2026-10-12T10:57:19.690Z` (~5,2 días). `fundingIntervalHours=4` real para WUSDT/LUMIAUSDT frente al fallback `FUNDING_INTERVAL_MS = 8h` (**corregido 2026-10-20:** el motor ya acepta `FundingCalendar` por contrato; `8h` es solo el fallback sin calendario inyectado). Por tanto la fidelidad se logra inyectando el calendario real, no cambiando la constante. Casos documentados como `NOT_SIGNAL` (ex-post high/low no es señal); WUSDT subió sobrecomprada antes de corregir (−10,97% máx→último cierre); LUMIAUSDT ganadora de 24h que cayó y rebotó sin recuperación duradera. Sesgo de selección retrospectiva declarado. Sin OOS, sin calibración, sin rentabilidad. `Casos_Binance_W_LUMIA.png` no inspeccionada visualmente (`NOT_ASSESSED`).
- **Qué falta para mostrar esos casos:** calendario de funding real por símbolo y tasa liquidada; spread/profundidad/coste estimado; fills reales; serie OOS; partición cronológica; vinculación `run_id`/`event_id` con `as_of`; snapshot por evento con hash del dataset. Sin calibrar reglas ni seleccionar ejemplos por beneficio.

Tras ello, continuar con el motor de paper completo (Etapa 5); el replay histórico ya está entregado en esta rama.


## Aceptación local automatizada completada (2026-10-24, base `6be44b9`, sin ventana Binance)

**Estado.** Completada. Dos recorridos consecutivos `PASS` procedural del camino
`WS público -> servicio SSE -> BFF -> /market-lab` con transporte loopback y
aislamiento de red real; finalizer `PASS`, `failed=[]`, `missing=[]`. Cero
intentos públicos, cero consumidores residuales, parada limpia, paginación
`298 -> 599` con 1 petición, reconexión `consumers=0 -> 1` con actualización
posterior y aviso de servicio detenido con causa real. Evidencia:
`docs/evidence/local-acceptance-2026-10-24/` (SHA `6be44b9`,
`build_id=FE1Eg1exjGrbZJpHz5vRO`).

**Arnés.** `scripts/market_stream_local_acceptance.py` (cache/catálogo
temporales, raíz sombra con guarda `sitecustomize` y explorador `--no-fetch`,
proxy bloqueante, allowlist del navegador, WS falso en reloj real, fases con
máximos y límite global 180 s). Soporte: `--post-reconnect-signal` en el
orquestador; hook `useMarketStream` consulta el estado al error del
`EventSource` y declara el aviso con la causa real.

**Pruebas.** Backend 71/71; frontend focalizado 23/23; `tsc --noEmit` 0;
`eslint` 0 errores (5 avisos preexistentes).

**Estado servido.** Dashboard canónico en 3020 (PID 30216,
`BUILD_ID=FE1Eg1exjGrbZJpHz5vRO`, `/market-lab` 200, catálogo 931 entradas);
servicio 8791/8792 detenido; DBs canónicas intactas.

**NEXT_TASKS (solo con autorización explícita).**

1. Ventana real `--transport public` con el procedimiento automatizado ya
   probado; no se solicita ni se abre en este bloque. La acreditación Binance
   sigue pendiente y el PASS local no la sustituye.
2. Decidir en un worktree separado la actualización de Next.js 16.4.1
   (advisories ya diagnosticados); no ejecutada aquí.
3. Sin móvil/Flutter, sin economía, sin paper con datos vivos, sin órdenes.

## Sesión de ingeniería — transporte local (2026-10-26, HEAD 365f7eb)

**1. Title:** Control de sesión observable en el dashboard existente
(/market-lab): iniciar/detener "Sesión de ingeniería — transporte local"
con seis paneles separados (estado, fuente LOCAL SIMULADA, recepción/frescura,
evaluador, posición paper, último error/motivo de abstención) y vista de
operación completa (datos → gráfico → indicadores/contexto BTC/flujo →
candidato → decisión → posición paper → gestión → cierre → exportación).

**2. Approval status:** DECIDED dentro del alcance autorizado (desktop,
presupuesto cero, sin conexión pública Binance, sin monitor, sin paper
prospectivo, sin órdenes, sin pagos, sin móvil/Flutter; fuente LOCAL
SIMULADA = caché local client=None, 0 upstream; ventana con mercado real
diferida, autorización explícita).

**3. Implementation status:** IMPLEMENTED.
rontend/src/components/session-lab/EngineeringSession.tsx +
SessionStatusPanels.tsx + EngineeringSession.module.css +
rontend/src/lib/session-lab.ts; cableado en
rontend/src/app/market-lab/page.tsx; reutiliza controlador canónico
(scripts/paper_lab_session.py +
src/microstructure_probe/paper_lab_engine.py con mecánica de
acktest_offline.run_backtest) y servicios existentes
(BFF pi/v1/paper-lab/sessions*, pi/v1/market-series). Regla de
ingeniería ENGINEERING-MINA-1M-v1 (explícita, versionada, separada de
estrategia aprobada); candidato UN token (MINAUSDT 1m) + BTC como contexto
(BTCUSDT 1m), ambos de caché local.

**4. Evaluation status:** 
px tsc --noEmit 0; 
px eslint 0 en archivos
nuevos; 
px vitest run src/test/paper-lab-live-api.test.ts 9/9;
python run_tests.py -q 1290 OK / 2 skipped; 
ext build OK.
E2E de navegador real (Chromium headless) sobre
http://127.0.0.1:3020/market-lab: A) iniciar → recibir datos
(caché local, 0 upstream) → evaluar (ENTRADA_SIMULADA) → entrada automática
(fill por 
un_backtest) → gestión (pasos de marca) → cierre por regla
(horizonte) → exportación JSON/CSV; B) evidencia insuficiente →
SIN_ENTRADA/DESCARTADO, sin posición; C) fin de datos → sin nuevas entradas,
estado visible, posición no cerrada inventada (open_at_end);
D) recarga → recuperación del mismo estado (session_id/config_hash
idénticos) sin duplicar entrada ni cierre; E) detener → sesión detenida,
recursos propios liberados, sin afectar procesos ajenos. Transporte local
aislado, 0 peticiones Binance, cadena dashboard → BFF → Python → dashboard.
Nota: los clics de "Paso a paso" en el navegador son intermitentes
(timing React/Playwright); el camino backend → BFF → Python está verificado
por HTTP (crear → evaluar → step ×31 → cerrada por horizonte:
CERRADA en paso 31: status=cerrada, reason=horizon,
exit_px=0.06251, realized_net=-10.00).

**5. Limitaciones:** no conecta a Binance público (ventana aparte,
autorización explícita); un solo token candidato (caso de ingeniería, no
rentabilidad); no es escáner de universo ni estrategia aprobada; no inventa
spread/profundidad/funding/fills de mercado real (funding UNKNOWN, costes
ejecutados separados); no es paper prospectivo ni motor completo (Etapa 5
fuera de alcance); móvil/Flutter/IA diferidos; indicadores provisionales
fuera de alcance.

**6. Evidence:** rontend/src/components/session-lab/ (
EngineeringSession.tsx, SessionStatusPanels.tsx,
EngineeringSession.module.css); rontend/src/lib/session-lab.ts;
rontend/src/app/market-lab/page.tsx;
src/microstructure_probe/paper_lab_engine.py;
scripts/paper_lab_session.py; BFF rontend/src/app/api/v1/paper-lab/sessions/*;
pi/v1/market-series (caché local, 0 upstream). Evidencia de ejecución:
E2E de navegador real sobre http://127.0.0.1:3020/market-lab.

**7. Last update:** 2026-10-26.

### Cierre (siete campos, obligatorios)

- DECISIONS_REVIEWED — docs/DECISIONS.md (sesión de ingeniería —
  transporte local, 2026-10-26), docs/CURRENT_STATE.md,
  docs/TASK_QUEUE.md, docs/DESKTOP_FIRST_SCOPE_20261020.md (alcance
  escritorio vigente), docs/ACUERDOS_GRAFICO_BINANCE_V1.md
  (origen/autoridad del backend, sin navegador como fuente de decisión),
  docs/PAPER_CHART_CONTRACT_V1.md (gráfico sobre velas conocidas en T).
- NEW_DECISIONS_RECORDED — DECISIONS 2026-10-26: sesión de ingeniería como
  control observable en el dashboard existente sin gestor paralelo; fuente
  LOCAL SIMULADA = caché local (0 upstream); regla ENGINEERING-MINA-1M-v1
  explícita y versionada; regla de parada (detener congela, no cierra ni
  inventa salida); persistencia autoritativa en paper-lab-sessions/ con el
  puntero de sesión (no estado económico) en el navegador.
- FEATURES_IMPLEMENTED — control iniciar/detener sesión; seis paneles
  (estado, fuente, recepción/frescura, evaluador, posición paper, último
  error/abstención); vista de operación (velas incrementales + reloj,
  candidato/motivo, entrada pendiente vs fill, entrada/stop/salida en
  gráfico, posición abierta/cerrada, P&L realizado/no realizado, costes,
  funding UNKNOWN, historial eventos, exportación JSON/CSV); compartición de
  session_id/símbolo/tiempos/config_hash entre paneles.
- FEATURES_VERIFIED — backend: create→evaluate→step×31→cerrada
  por horizonte (
ealized_net calculado, unding=None) vía HTTP;
  frontend: 	sc 0, eslint 0, vitest paper-lab-live-api 9/9; E2E de
  navegador: iniciar → evaluar (ENTRADA_SIMULADA) → Entrar → abierta →
  pasos de gestión → cerrada por regla → exportación JSON; recarga recupera
  sesión idéntica sin duplicar; detener congela sesión sin cerrar; B
  (abstención SIN_ENTRADA/DESCARTADO, sin posición) verificada vía HTTP;
  C (fin de datos sin cierre inventado) verificada vía HTTP.
- DEFERRED_FEATURES — conexión a Binance público (ventana aparte,
  autorización explícita); selector automático de varios símbolos; monitor
  en vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; IA;
  indicadores provisionales; stops/objetivos arrastrables; motor paper
  completo (Etapa 5).
- BACKLOG_UPDATED — yes: esta sección + CURRENT_STATE, TASK_QUEUE,
  DECISIONS.
- DOCUMENTATION_CONFLICTS — ninguna contradictoria; se aclara que
  "fuente LOCAL SIMULADA" ≠ Binance LIVE y que el backend (no el navegador)
  es la autoridad de decisión y estado económico.

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
src/microstructure_probe/paper_lab_engine.py; scripts/paper_lab_session.py; BFF frontend/src/app/api/v1/paper-lab/sessions/*; E2E navegador sobre http://127.0.0.1:3020/market-lab.

**7. Last update:** 2026-10-27.
### Cierre (siete campos, obligatorios)

- DECISIONS_REVIEWED — docs/DECISIONS.md (sesión de ingeniería — transporte local, refinamiento 2026-10-27), docs/CURRENT_STATE.md, docs/TASK_QUEUE.md, docs/DESKTOP_FIRST_SCOPE_20261020.md.
- NEW_DECISIONS_RECORDED — DECISIONS 2026-10-27: alcance de --no-fetch (read_only=1, ingeniería cero upstream; explorador normal conserva adquisición bajo demanda); recuperación por identidad autoritativa (config.symbol/config.interval, no defaults del componente); sincronización de reloj T centralizada (applyAuthoritative; entrada/paso/salida/reinicio/recuperación; sin valores previos como actuales).
- FEATURES_IMPLEMENTED — control iniciar/detener sesión; alcance de --no-fetch vía read_only=1; seis paneles; vista de operación completa; compartición de session_id/símbolo/tiempos/config_hash; regla de ingeniería versionada; dos prefijos de demostración.
- FEATURES_VERIFIED — backend: crear→evaluar→step→cerrada por horizonte vía HTTP; frontend: tsc/eslint 0, vitest session-lab 4/4 + engineering-session 5/5 + paper-lab-live-api 9/9; E2E navegador: iniciar→evaluar→entrar→gestión→recarga abierta; dos prefijos HTTP (A admite, B se abstiene); fuente solo lectura 0 upstream; reloj T sin futuros.
- DEFERRED_FEATURES — conexión a Binance público; selector automático; monitor en vivo; paper prospectivo; órdenes; pagos; móvil/Flutter; indicadores provisionales; motor paper completo (Etapa 5); recorrido con datos nuevos continuos.
- BACKLOG_UPDATED — yes: esta sección + CURRENT_STATE, DECISIONS, FEATURE_BACKLOG.
- DOCUMENTATION_CONFLICTS — ninguna contradictoria; se aclara que "sesión de ingeniería/replay sobre caché" ≠ "sistema completo autónomo" y que "fuente LOCAL SIMULADA" ≠ Binance LIVE; el backend es la autoridad de decisión y estado económico.


## Cierre: prueba de integraciÃ³n real de sesiÃ³n nueva con contexto reciente (2026-10-31, sin Binance)

- `DECISIONS_REVIEWED` â€” AGENTS.md, WORKFLOW.md, CURRENT_STATE, DECISIONS,
  FEATURE_BACKLOG, DESKTOP_FIRST_SCOPE_20261020.
- `NEW_DECISIONS_RECORDED` â€” DECISIONS 2026-10-31: ventana explÃ­cita de
  velas cerradas en `fetchMarketSeries` y `series_payload`; `readOnly=true`
  por defecto (cero upstream); activaciÃ³n expresa (`readOnly=false`) para
  adquisiciÃ³n con presupuesto compartido.
- `FEATURES_IMPLEMENTED` â€” `tests/test_session_new_public_market_local.py`
  (integraciÃ³n real HTTP/WS locales, TemporaryDirectory, camino BFF/CLI/
  HistoryClient + servicio de mercado, sin mÃ©todos internos del motor);
  `fetchMarketSeries` sin rango `0â†’9999999999999`; `series_payload` clamp al
  reloj.
- `FEATURES_VERIFIED` â€” nueva integraciÃ³n PASS (MINAUSDT+BTCUSDT, contexto 20
  + stream 10 cierres, sin huecos ni duplicados, gate ok, sesiones detenidas);
  `test_market_explorer.py` 42/42; `test_market_stream.py`+`test_history.py`
  71/71; frontend `session-lab.test.ts` 4/4, suite 622/623, tsc/eslint 0,
  `next build` OK. 0 llamadas Binance.
- `DEFERRED_FEATURES` â€” ventana pÃºblica contra Binance (requiere autorizaciÃ³n
  explÃ­cita), selector multiactivo, riesgo completo, paper prospectivo.
- `BACKLOG_UPDATED` â€” yes: esta entrada + CURRENT_STATE + DECISIONS.
- `DOCUMENTATION_CONFLICTS` â€” ninguna; se aclara que `fetchMarketSeries` con
  `readOnly=false` habilita adquisiciÃ³n bajo demanda con presupuesto y que el
  cambio de ventana es de backend (no solo React).



## 2026-11-03 - Investigación universo y liquidez (rama research/universe-liquidity-v1, base 78371aa) - NUEVA PRIORIDAD

CURRENT_PHASE: investigación de hipótesis económica (liquidez vs flujo agresor) y selección automática de candidatos sobre el universo elegible.

CURRENT_OBJECTIVE: determinar si existe información aprovechable para seleccionar y operar sobre el universo de futuros elegible, sin conexión pública ni órdenes.

ACTIVE_TASK: investigación en curso docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md. Diagnóstico computado: insuficiencia (liquidez en T ausente para outcomes resueltos; universo resuelto 6 símbolos = 1.15% de elegibles; retorno forward ≈ 0). Plan mínimo de adquisición propuesto, NO ejecutado.

NEXT_TASKS:
1. Adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato, para unir liquidez + flujo agresor + retorno forward resuelto.
2. Si tras la adquisición mínima el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar (criterio de interrupción).
- No integrar ramas, no reset/clean/force, no borrar evidencia. opencode.json y archivos ajenos no se commitean.


## 2026-11-03 - Investigación universo y liquidez: autoselección (rama research/universe-liquidity-v1, base 2f5fc70) - NUEVA PRIORIDAD

CURRENT_PHASE: investigación de hipótesis económica (liquidez vs flujo agresor) y selección automática de candidatos sobre el universo elegible.

CURRENT_OBJECTIVE: determinar si existe información aprovechable para seleccionar y operar sobre el universo de futuros elegible, sin conexión pública ni órdenes.

ACTIVE_TASK: investigación en curso docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md. Inventario corregido, matriz de aprovechamiento (joint_coverage: 1/14 símbolos con cobertura para outcomes), autoselección implementada (research_selector.py, 11 pruebas de mecanismo), pruebas de inventario (10 pruebas). Diagnóstico: insuficiencia (solo BTCUSDT tiene precio posterior para la ventana research; horizonte 1h solo).

NEXT_TASKS:
1. Adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato, para unir liquidez + flujo agresor + retorno forward resuelto.
2. Si tras la adquisición mínima el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar (criterio de interrupción).
- No integrar ramas, no reset/clean/force, no borrar evidencia. opencode.json y archivos ajenos no se commitean.


## 2026-11-03 - Investigación universo y liquidez: autoselección e inventario corregido (rama research/universe-liquidity-v1, base 2f5fc70 -> 23a2315)

CURRENT_PHASE: investigación de hipótesis económica (liquidez vs flujo agresor) y selección automática de candidatos sobre el universo elegible.

CURRENT_OBJECTIVE: determinar si existe información aprovechable para seleccionar y operar sobre el universo de futuros elegible, sin conexión pública ni órdenes.

ACTIVE_TASK: investigación en curso docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md. Inventario corregido, matriz de aprovechamiento (joint_coverage: 1/14 símbolos con cobertura para outcomes, solo BTCUSDT 1h), autoselección implementada (research_selector.py, 15 pruebas de mecanismo), pruebas de inventario (10) y de matriz conjunta (4). Diagnóstico: insuficiencia (solo BTCUSDT tiene precio posterior para la ventana research; horizonte 1h solo; 0.2% de elegibles).

NEXT_TASKS:
1. Adquirir liquidez en el instante T (order book top-20 con available_at) para el universo candidato, para unir liquidez + flujo agresor + retorno forward resuelto.
2. Si tras la adquisición mínima el retorno forward condicionado sigue ≈ 0 tras costes en universo representativo, no escalar (criterio de interrupción).
- No integrar ramas, no reset/clean/force, no borrar evidencia. opencode.json y archivos ajenos no se commitean.
