# Protocolo de experimento operativo v2 — research/universe-liquidez-v1

**Estado:** diseño de alcance cerrado y demostrado localmente. No se ejecuta en producción. No hay órdenes reales, no hay conexión nueva a Binance, no hay infraestructura nueva, no hay cambios económicos productivos. Este documento actualiza y reemplaza el alcance de `docs/EXPERIMENTO_OPERATIVO_V1.md` (diseño de alcance v1); no se borra el v1, se conserva como referencia histórica.

**Base:** HEAD `6a10c30701cbbf695b422ba4a83206e1dd872132` (rama `research/universe-liquidez-v1`). Dataset de referencia para diagnóstico: `public-pilot-1h-20261106a` (una sola hora, 2026-11-06, 216 observaciones, 168 aptas, 504 resultados). Análisis v4 como punto de partida.

**Nota de alcance:** el SHA `6071481315054954ed4300a78b31f6ca8332f30b` citado en el encargo no existe como objeto en el repositorio local (`git cat-file -t` → `could not get object info`). No hay actualizaciones documentales publicadas bajo ese identificador que incorporar. Se trabaja sobre HEAD actual preservando cambios existentes y ajenos.

## 1. Cobertura real de ambos tipos de contrato futuro

El producto debe cubrir futuros perpetuos y futuros con vencimiento. Hoy solo está acreditada la cobertura de perpetuos; los vencimientos no están acreditados como soporte de estrategia.

### 1.1 Tabla de cobertura por tipo de contrato

| Tipo de contrato | Cobertura disponible hoy | Componentes reutilizables | Datos o comportamiento que falta acreditar | Cobertura propuesta para este experimento |
|---|---|---|---|---|
| Futuros perpetuos USD-M | Parcial (solo prueba piloto 1 h, un universo reducido, símbolos con `move_24h` disponible) | `research_selector.select_candidates`, `ResearchPolicy`, `build_comparator`, `paper_lab_engine` (RULE-CAUSAL-V1), `backtest_offline` (BacktestConfig) | Precio de ejecución causalmente posible (fill), comisiones, funding, slippage, fills acreditados, estabilidad entre regímenes | **Sí** — experimento inicial sobre perpetuos USD-M (un solo tipo) |
| Futuros con vencimiento (trimestrales/trimestrales perpétuos no estándar) | Ninguna acreditada | Ninguna (el selector filtra `contract_type == "PERPETUAL"`) | Contrato concreto, fecha de vencimiento, moneda de margen/liquidación, tamaño/unidades, calendario de financiación por símbolo, roll, liquidación, datos de precio por vencimiento | **No** — queda fuera de este experimento; se declara explícitamente pendiente |

### 1.2 Requisitos de datos para vencimientos (no acreditados, pendiente)

Si en una fase posterior se cubren futuros con vencimiento, se deberá acreditar, por símbolo y vencimiento:
- Contrato concreto (símbolo de venue), fecha de vencimiento, moneda de margen y de liquidación.
- Tamaño/unidades del contrato (contract size), tick, lote mínimo.
- Requisitos de datos: precio deマーク/último, libro, profundidad, OI, funding (cuando corresponda, separado del vencimiento y de la liquidación), roll de vencimiento.
- Distinción explícita: funding (pago periódico por posición) ≠ vencimiento (expiración del contrato) ≠ liquidación (cierre forzado por margen insuficiente) ≠ roll (rotación de posición al vencimiento próximo).

### 1.3 Orden incremental justificado

El experimento inicial cubre **un solo tipo: futuros perpetuos USD-M**. Pregunta que resuelve: ¿una regla operativa previa, aplicada a candidatos autoseleccionados (perpetuos), produce resultados netos diferentes (bajo costes y riesgo declarados) que la misma regla aplicada a comparadores, en windows separadas? Queda pendiente del objetivo de ambos tipos: la cobertura de futuros con vencimiento (contrato, vencimiento, margen, roll, funding por símbolo) no se aborda en este bloque y requiere un diseño de adquisición separado.

**No se abren dos implementaciones paralelas.** El experimento usa solo perpetuos; los vencimientos se documentan como pendiente sin implementar soporte parcial.

## 2. Tabla de capacidades existentes (mapeo al objetivo operativo)

Se inspeccionan exclusivamente componentes ya disponibles. No se propone otro motor, supervisor, dashboard ni agente de IA.

| Capacidad | Existe | Probado funcionalmente | Evaluado económicamente | Observaciones |
|---|---:|---:|---:|---|
| Selección de candidatos (UP/DOWN, bounded set, ambos lados) | Sí (`select_candidates`, `ResearchPolicy`) | Sí (tests research_selector) | No | Selecciona para investigación, no para entrada. Sin rotación ni permanencia (diferidos en `ResearchPolicy`). |
| Dirección LONG/SHORT | Parcial | No | No | Selector emite `side` UP/DOWN (dirección de movimiento, hipótesis). No hay regla que traduzca UP→LONG o DOWN→SHORT. |
| Condición de entrada | Sí (`RULE-CAUSAL-V1`, `_evaluate_signal_causal_v1`) | Sí (tests paper_lab_engine) | No | Señal usando solo prefijo conocido en T; nunca usa velas futuras, P&L ni comisiones como confirmación. Abstiene si no hay close conocido o stop vulnerado. |
| Momento y precio posible de fill | Sí (`step_forward`, `_apply_entry`, `_finalize_exit`) | Sí (tests paper_lab_engine) | No | Fill en open de vela conocida o al stop; exit en stop/horizonte/open_at_end. Nunca inventa fill ni salida. |
| Stop loss | Sí (`stop_px`, `stop_distance_pct`, `_admit_risk`) | Sí (tests paper_lab_engine) | No | Stop debe estar alejado de entry_px; admisión deniega stop no válido por dirección. |
| Salida y horizonte | Sí (`horizon_ms`, salida por stop/horizonte/open_at_end/manual) | Sí (tests paper_lab_engine) | No | `open_at_end` es marca, nunca salida ejecutada ni P&L realizado. |
| Costes y riesgo | Sí (`fee_bps`, `spread_bps`, `slippage_bps`, `notional_usdt`, `_gross_pnl`, `FundingCalendar` por símbolo) | Sí (tests paper_lab_engine / backtest) | No | Funding ausente = UNKNOWN (nunca cero). `_admit_risk` valida notional/entry/stop/dirección estáticamente. |
| Trazabilidad de decisión | Sí (`decision_evidence`, `config_hash`, `input_hash`, `engine_version`, `session_to_dict`) | Sí (tests) | No | Cada decisión/ejecución tiene evidencia en T, regla versión y hashes. |

**Nota:** Una prueba técnica de RULE-CAUSAL-V1 o de `select_candidates` no es evidencia de ventaja económica. Ninguna de estas capacidades ha sido evaluada económicamente sobre datos reales con costes.

## 3. Hipótesis operativa única y comprobable

**Pregunta principal:** ¿Una regla previamente definida, aplicada a los candidatos autoseleccionados (perpetuos USD-M), produce resultados netos diferentes que la misma regla aplicada a comparadores, bajo condiciones de ejecución y riesgo equivalentes?

**Hipótesis de continuación (se elige una sola; reversión es hipótesis distinta, no probada aquí):** reconocer que está influenciada por resultados ya vistos de la captura 20261106a (candidatos mostraron retornos medios positivos descriptivos), por lo tanto debe probarse en ventanas separadas y no se asume superioridad.

**Regla candidata completa (demostrada localmente con `paper_lab_engine` / `backtest_offline`, NO implementada en producción, NO aprobada por documentarla):**

| Elemento | Valor / condición explícita |
|---|---|
| Información disponible al decidir | `side` (UP/DOWN) del selector en T, `move_24h_pct`, precio de libro `libro_mid` en T, cobertura y frescura (`disponibilidad.<= decision_ms + tolerancia`). Nada del futuro. |
| Condición de señal y dirección | Si `side == UP` → LONG; si `side == DOWN` → SHORT. Si `side` es None → SIN_ENTRADA. Solo si existe vela 1m plenamente conocida en T y su close opera a favor vs `entry_px` y stop no vulnerado (misma lógica de abstención que RULE-CAUSAL-V1). |
| Entrada y primera ejecución posterior causalmente posible | `entry_px` = close de la vela 1m plenamente conocida en T (precio conocido en T). Primera ejecución: fill al **open de la vela 1m siguiente** a la de señal (primera ejecución posterior causalmente posible; nunca el open pasado de la vela que confirmó la señal, nunca precio futuro). Demostrado localmente con `step_forward` → `_apply_entry` → `run_backtest`. |
| Stop inicial y tratamiento de gaps | `stop_px = entry_px × (1 − stop_distance_pct)` para LONG; `entry_px × (1 + stop_distance_pct)` para SHORT. `stop_distance_pct = 0.5` (0,5 %). Gap: si el open de la vela siguiente cruza el stop, se sale al stop (precio del stop, no al open); stop no vulnerable en T → SIN_ENTRADA. |
| Tamaño y riesgo por operación | `notional_usdt = 1000` (fijo). Riesgo por operación = `stop_distance_pct × notional_usdt = 5 USDT`. |
| Límite de exposición y concurrencia | `max_concurrent = 1` (una posición a la vez). |
| Salida, horizonte y posiciones abiertas al finalizar | Horizonte fijo `horizon_ms = 3 600 000` (60 m). Salida al stop (touch) o al horizonte con close conocido. Si no hay close conocido al horizonte → `open_at_end` (marca, no salida ejecutada, P&L = UNKNOWN). Posiciones abiertas al finalizar se mantienen abiertas, sin salida inventada. |
| Abstención por falta de datos o señal | Si no hay cobertura (`coverage_ok=false`), no hay vela 1m plenamente conocida en T, stop vulnerado en T, o `side` es None → SIN_ENTRADA, sin entrada, sin coste, registrado con motivo. |

**Supuestos de ejecución declarados (no medidos):** precio de ejecución = open de vela 1m conocida (causal); funding = UNKNOWN sin calendario real por símbolo; slippage/spread según `BacktestConfig` (no medidos en ejecución real). Los fills son estimaciones causales, no ejecuciones acreditadas. La configuración propuesta no queda aprobada por documentarla.

## 4. Aplicación de la misma regla a candidatos y comparadores

**Problema expreso:** los comparadores actuales del piloto carecen de `side` (el campo `side` del JSONL es None para todos los comparadores; `move_24h_pct` es None en todo el dataset). Por tanto, la dirección no puede derivarse del rol candidate/comparator ni de `side` del comparador.

**Resolución:** la dirección y la señal se derivan **exclusivamente** de información de mercado disponible para ambos grupos mediante la misma regla:
- Para cada símbolo (candidate o comparator) con observación emitida y apta, se calcula `side` del símbolo en T desde `move_24h_pct` (si estuviera disponible) o, en su defecto, se declara `side = None` y SIN_ENTRADA.
- **El rol candidate/comparator no determina por sí mismo LONG o SHORT.** Ambos grupos pasan por la misma regla de señal y la misma condición de entrada, stop, tamaño, horizonte y abstención.
- Si un comparador no tiene `side` acreditado (como ocurre en el piloto), recibe SIN_ENTRADA por falta de señal, no se le asigna una dirección arbitraria.

**Condiciones equivalentes:** mismos `notional_usdt`, `stop_distance_pct`, `horizon_ms`, `max_concurrent`, costes (`fee_bps`, `spread_bps`, `slippage_bps`), y misma regla de frescura (`max_data_age_ms=5000`) para candidatos y comparadores.

**Señales simultáneas:** si varios símbolos dan señal en el mismo ciclo, se ejecutan hasta `max_concurrent=1` (una posición a la vez); el resto queda en WATCH/SIN_ENTRADA por límite de concurrencia, no por sus resultados posteriores. Nunca se eligen operaciones mirando el retorno posterior.

**Registro:** todas las selecciones, descartes, abstenciones y operaciones se registran con motivo. No se comparan operaciones simuladas de candidatos con simples retornos de comparadores; se comparan resultados de la regla aplicada a ambos grupos.

## 5. Comprobación de que los datos previstos permiten evaluar la regla

| Condición operativa | Dato necesario | ¿Disponible en piloto 20261106a? | Tratamiento |
|---|---|---|---|
| `side` del símbolo en T | `move_24h_pct` o equivalente | No (siempre None en observaciones; `side` None en comparadores) | UNKNOWN para comparadores; SIN_ENTRADA sin `side` acreditado |
| `entry_px` (close de vela 1m conocida en T) | `klines_apertura_1m` / close de vela cerrada en T | Sí (precio posterior del piloto) | Reutilizable con desfase declarado |
| Fill causalmente posible | open de vela 1m siguiente a la señal | No directamente (solo precio posterior de horizonte fijo) | Estimación causal, declarada como tal |
| Stop (touch) | rango alta/baja de velas intermedias | No (piloto solo guarda precio posterior por horizonte fijo) | UNKNOWN para stops intermedios; solo stop en close de vela conocida |
| Salida al horizonte | precio en `target_ms` | Sí (precio posterior por horizonte) | Reutilizable con desfase declarado |
| Costes | comisiones, spread/slippage por ejecución | No | Supuestos declarados (`BacktestConfig`), no medidos |
| Funding | calendario por símbolo | No | UNKNOWN (nunca cero sin calendario) |
| Frescura | `disponibilidad.* <= decision_ms + 1 000 ms` | Sí (verificado en piloto) | Reutilizable |

**Conclusión de viabilidad de datos:** los precios por horizonte del piloto **no garantizan** que se puedan reconstruir entradas, stops y salidas intermedias (open de vela siguiente, rango intra-vela para stop). Solo se pueden reutilizar: precio base (`libro_mid`), precio posterior por horizonte fijo (`klines_apertura_1m`), cobertura y frescura. Lo que debe conservarse: trazabilidad de decisión, observation_id, decision_ms, cobertura por rol. Lo que no puede evaluarse honestamente: fill al open de vela siguiente, stop touch intra-vela, funding real → permanece UNKNOWN.

**Tratamiento de ambigüedades:** intravela (open/high/baja/close de vela no cerrada) → UNKNOWN, nunca se usa como ejecutado; huecos en datos → observación excluida con motivo, no rellenada; frescura → `max_data_age_ms=5000` se mantiene, no se relaja; datos ausentes → motivo explícito, nunca cero.

**Costes:** se distinguen datos medidos (ninguno de ejecución real) de supuestos (fee/spread/slippage según `BacktestConfig`, funding UNKNOWN sin calendario). Nunca se convierte UNKNOWN en cero. No se declara rentabilidad por añadir comisiones.

## 6. Calendario, presupuesto y decisión

**Calendario propuesto (fechas/horarios fijados antes de observar resultados):** 3 ventanas independientes, no sobrepostas a `public-pilot-1h-20261106a` (2026-11-06 05:17–07:14 UTC), cada una: 1 h de captura + 70 min de settle (protocolo v3, `cycle_seconds=300`, `selection_seconds=300`, ventana 60 s, `max_data_age_ms=5000`, `max_symbols=20`). Fechas concretas por definir en la autorización, en regímenes de mercado no seleccionados a posteriori. No se presupone independencia estadística entre ventanas.

**Presupuesto coherente con datos realmente necesarios (por ventana):**

| Concepto | Valor (por ventana) | Total (3 ventanas) | Notas |
|---|---|---|---|
| Ventanas de captura | 3 × 1 h | 3 | Mismo protocolo v3 |
| HTTP intentos | ≤2000 | ≤6000 | Sujeto a nueva autorización de presupuesto |
| HTTP peso | ≤5000 | ≤15 000 | Tabla ASSUMED_WEIGHTS, no cabeceras reales |
| HTTP reintentos | ≤50 | ≤150 | |
| WS conexiones simultáneas (pico por ventana) | ≤20 | ≤20 (pico, no acumulado) | Límite de conexiones al mismo tiempo; no se suma entre ventanas |
| WS aperturas acumuladas (total en el tiempo) | ≤20 | ≤60 | Conteo de aperturas de conexión a lo largo de las 3 ventanas |
| WS mensajes | ≤5 000 000 | ≤15 000 000 | |
| WS reconexiones | ≤20 | ≤60 | |
| Almacenamiento | ≤128 MB | ≤384 MB | JSONL + SQLite + aux |
| Duración de captura y maduración | 1 h + 70 min settle (130 min por ventana) | 6 h 30 min total (3 × 130 min) | |
| Max símbolos | 20 | 20 | Por ventana |
| Max candidatos/comparadores | 12/8 | 12/8 | Por ventana, techo conjunto 20 |

**Generación local de presupuesto sin conexiones públicas.** No se copian límites de ventanas antiguas del dashboard. Cada ventana requiere su propia autorización de presupuesto separada.

**Métrica principal neta y denominador:**
- Métrica principal: `neto_por_operación = (precio_salida − precio_entrada) × qty × dirección − costes − funding`, en USDT, por operación ejecutada (fill causalmente posible).
- Denominador: número de operaciones ejecutadas (no observaciones, no retornos brutos).
- Incluye: pérdidas, riesgo por operación (`stop_distance_pct × notional_usdt`), exposición simultánea (`max_concurrent`), abstenciones (contadas como 0 operaciones, no como 0 P&L).
- Drawdown: realizado únicamente (cerrado-trade net equity), nunca mark-to-mayor.

**Criterios previos de decisión (fijados antes de ejecutar):**
- **Candidatos mejores que comparadores:** `neto_por_operación` medio de candidatos > medio de comparadores, con cobertura razonable en ambos grupos (no se ignora desigualdad de cobertura).
- **Resultado neto positivo bajo el modelo:** `neto_por_operación` > 0 con supuestos de costes declarados y defendibles.
- **Evidencia suficiente para generalizar:** consistencia entre ventanas, símbolos no concentrados (ningún símbolo domina el resultado), cobertura de ambos roles por ciclo.

**Una diferencia favorable con ambos grupos perdiendo no acredita una estrategia rentable.** Si ambos grupos pierden neto pero candidatos pierden menos, no es evidencia de edge positivo.

**Criterios de continuación/reformulación/detención/insuficiencia (antes de ejecutar):**
- **Continuar:** si nivel C (resultado neto positivo con supuestos defendibles) se cumple en las 3 ventanas y la regla se ejecutó sin incumplimientos de causa.
- **Reformular:** si el nivel A no muestra diferencia consistente o la cobertura es muy desigual (<50 % de ciclos con ambos grupos aptos).
- **Detener la línea:** si el nivel C muestra neto negativo consistente o los costes devoran el edge descriptivo.
- **Declarar insuficiencia:** si tras las 3 ventanas no se alcanza nivel B completo (regla no ejecutada conforme al modelo) o faltan precios para simular fills honestamente. La insuficiencia **no autoriza automáticamente más capturas**; requiere una nueva decisión de alcance y presupuesto.

**7. Acción exacta que requeriría autorización posterior**

Ejecutar las 3 ventanas del protocolo con la regla candidata congelada, bajo el presupuesto propuesto, y evaluar contra los criterios de decisión A/B/C. Ninguna captura, orden real, ni integración de ramas se ejecuta sin esa autorización separada.

**Bloqueo material identificado:** los precios del piloto solo dan precio posterior por horizonte fijo; no dan open de vela siguiente ni rango intra-vela para stop. El mínimo trabajo para resolverlo sería adquirir datos de velas 1m con open/close conocidos causalmente y calendario de funding por símbolo, antes de autorizar cualquier captura operativa. Mientras tanto, el experimento queda en diseño, no listo para ejecutar.

**Referencias en estado y cola:** `docs/TASK_QUEUE.md` y `docs/CURRENT_STATE.md` se actualizan brevemente con referencia a este protocolo v2 (diseño de alcance, no ejecutado, pendiente de autorización).

## 8. Estado de este bloque (camino productivo cerrado localmente, 2026-11-09)

Este bloque se cerró localmente sobre `research/universe-liquidez-v1` (base
`510485a4d01a83430d56f2838404b8e08390963d`), reutilizando `paper_lab_engine`,
`backtest_offline`, `research_pilot` y `research_operativo_adapter` sin Binance,
sin nuevas capturas públicas, sin órdenes reales, sin nuevos servicios ni
motores paralelos. Se reprodujeron y corrigieron los ocho defectos del encargo sobre la base
revisada (cinco del bloque previo más tres materiales en esta revisión), y se
acreditó el recorrido productivo local del experimento operativo v2 mediante el
CLI real (`scripts/research_pilot.py`) como subproceso con proveedores HTTP/WS
loopback, almacenamiento aislado y reloj controlado.

Pruebas: `tests/test_operativo_cli_integrado.py` (3 passed, incluida la
aceptación integrada del CLI) + `tests/test_operativo_capacidad_presupuesto.py`
(6 passed: capacidad A-E y presupuesto observado vs plan) +
`tests/test_research_pilot.py` (28 passed)
+ regresiones de `paper_lab_engine`, `experimento_operativo_local`,
`backtest_offline`, `backtest_funding` y `operativo_local_v2` (**129 passed**
en el conjunto focalizado).

**Rectificación 2026-11-10 (base `b551ced3ab08e7dfc377f2a136e2fd434e6ab023`):**
las afirmaciones de D, E y F de este bloque se reprodujeron como defecto
material sobre esa base: el replay perdía los intervalos de ocupación al
cerrar una operación y admitía exposures solapadas; el presupuesto publicado
no contaba las consultas repetidas del resolver (1 180 llamadas del resolver
frente a 40 consultas publicadas); y la prueba integrada de funding dependía
de un fichero externo (`/tmp/fund_test/calendario_cli.json`) que, al
apartarlo, hacía fallar la aceptación. D, E y F quedan por tanto
**rectificados** con el comportamiento descrito abajo, y la aceptación
propia queda en `tests/test_operativo_capacidad_presupuesto.py` (6 passed) más
la prueba integrada con calendario propio. El cierre de 2026-11-09 se
conserva en el historial de este bloque y en el historial del repositorio.

### Defectos reproducidos y corregidos

A. **Proveedor cronológico (loopback):** `MarketHttp` ya consulta el reloj
   compartido en cada petición (`clock_ms_fn`), respeta `startTime`,
   `endTime` y `limit`, no devuelve aperturas posteriores al reloj, no presenta
   como definitivos el high/low/close de una vela aún abierta (close=None para
   velas provisionales), y distingue apertura conocida de OHLC final. Se
   demostró que un `endTime` futuro no permite obtener datos antes de tiempo.

B. **Pendientes resueltos prematuramente:** `_resolver_operativos_pendientes`
   ya no marca `resuelta=True` por recibir cualquier lista no vacía. Solo se
   marca terminal cuando hay salida ejecutada (stop/horizonte) o agotamiento
   de datos tras el horizonte (`open_at_end` y `now >= decision_ms +
   horizon_ms`). Las velas provisionales se usan para gestionar pero no se
   confunden con velas cerradas.

C. **Prueba integrada que no sustituye al producto:** `test_cli_productivo_integrado`
   lanza `research_pilot.py` como subproceso real y todo lo produce el CLI bajo
   su presupuesto. No detiene el piloto ni crea un adaptador externo ni un
   `HistoryClient` con `attempt_gate=None`.

D. **Concurrencia compartida (rectificado 2026-11-10):** la puerta de
   capacidad ya no borra la exposición al salir. El adaptador conserva el
   historial de ocupación `intervalos_ocupacion` por `observation_id` con el
   intervalo semiabierto `[entry_ms, exit_ms)` (mismo criterio que
   `backtest_offline`: `s <= t < e`), de modo que una entrada posterior no
   puede solaparse con una exposición que existió, y una salida desconocida
   (`open_at_end`, sin salida acreditada) mantiene la ocupación abierta: no se
   libera capacidad de forma inventada. La prioridad es determinista por
   `(decision_ms, symbol, observation_id)`; el rol candidate/comparator no
   participa del orden, de la dirección ni de las reglas, y no se consulta
   ningún desenlace posterior para admitir. Los resultados terminales se
   cachean por `observation_id` (`_es_terminal`): reprocesar una observación no
   la bloquea contra sí misma, no duplica admisiones, operaciones ni
   resultados, y los contadores son idempotentes (`_contar`, `_marcar_admitida`).
   El rechazo por capacidad es terminal: una señal rechazada no vuelve a
   admitirse más adelante.

E. **Funding vía CLI (rectificado 2026-11-10):** `main()` carga calendarios de
   funding por símbolo desde `--funding-calendars` (fichero sintético
   identificado como tal en pruebas; no se abre adquisición pública) y falla
   de forma explícita (código 2) si el fichero no existe o no es válido: no hay
   paso silencioso a un calendario vacío. Solo se acredita el importe si el
   calendario declara cadencia nominal y la contabilidad de funding de la
   posición (`funding_accounting_complete` de `backtest_offline`) está
   explícitamente completa: sin exposición sin cubrir, settlement desconocido
   ni hueco interior aplicable. La integridad es por posición, no solo global
   del calendario; si falta o es desconocida, el importe no se acredita. En
   otro caso (sin calendario, sin cadencia, cobertura incompleta, settlement
   desconocido o hueco interior) el funding queda UNKNOWN, nunca cero ni
   parcial. Cada fila persistida publica el detalle de cobertura
   (`funding_cuenta_completa`, `funding_sin_cubrir_ms`, `funding_huecos_ms`,
   `funding_settlements_desconocidos`, símbolo, versión y hash del
   calendario). La prueba integrada genera su propio calendario sintético en
   su directorio temporal y lo pasa por `--funding-calendars`: no depende de
   ningún fichero externo y verifica el importe con un cálculo independiente
   (`qty × marca causal del settlement × rate_bps/10000`).

   **Rectificación adicional 2026-11-10 (base `9580983`):** se reprodujo una
   fila con `funding=0.1`, `funding_estado="settlement-calendar"`,
   `funding_cuenta_completa=false` y `funding_sin_cubrir_ms=60000`. El
   adaptador ahora usa el veredicto por posición de `backtest_offline` y
   falla cerrado: esa fila persiste `funding=null`, estado explícito UNKNOWN y
   el neto numérico queda identificado como condicionado, no completo. El
   diagnóstico del motor no se modificó.

F. **Presupuesto coherente con la frecuencia real (rectificado 2026-11-10):**
   `compute_budget` separa tres cosas: la estimación base (preparación + UNA
   consulta de trayectoria por observación apta + un precio por observación y
   horizonte), las reservas (peticiones repetidas, ≤1 por observación, y
   reintentos por fallo, ≤50) y los techos efectivos (2 000 intentos /
   5 000 peso / 50 reintentos / 128 MB). La política del resolver ya no
   sondea: consulta la trayectoria de una observación solo cuando puede estar
   disponible (`now >= decision_ms + horizon_ms + step_ms`) y como máximo
   `MAX_CONSULTAS_TRAYECTORIA_POR_OBS = 2` veces (1 planificada + 1 repetida).
   Una petición repetida no es un reintento por fallo: se cuentan y reservan
   por separado. La estimación base no es un máximo garantizado y no se
   presenta como tal; el límite efectivo es el techo configurado. La reserva
   ocurre antes del transporte (`RunBudget`) y un bloqueo conserva el
   pendiente con su motivo real, sin inventar resultados ni devolver cupos.

### Recorrido productivo acreditado por el CLI real

- Observación apta persistida en T (decision_ms, move_24h_pct, rol, configuración
  y motivo de señal/abstención), sin resultado futuro.
- Trabajo operativo pendiente registrado sin consultar trayectoria futura.
- Resolución posterior del CLI usando el mismo `HistoryClient` y puerta de
  presupuesto; se distingue resultado terminal conocido de trayectoria
  insuficiente.
- Cada resultado terminal persistido una sola vez; los pendientes no resueltos
  se conservan con causa real al parar/agotar settle/bloqueo presupuestario.
- Dos señales solapadas no producen dos posiciones admitidas (max_concurrent=1
  compartido); prioridad determinista con información disponible al decidir.
- Funding entra por la configuración real del CLI (cobertura completa con
  evento en exposición → contabilizado; cobertura completa sin evento
  aplicable → cero; cobertura incompleta o calendario ausente → UNKNOWN).
- Presupuesto reservado antes del transporte: intento bloqueado no aumenta el
  contador del proveedor.
- Una parada conserva pendientes y libera solo los recursos propios.

### Presupuesto efectivo (--budget-only, 1 ventana)

Calculado con `python scripts/research_pilot.py --budget-only` (sin red):

| Concepto | Por ventana | Techo | Estado |
|---|---|---|---|
| HTTP intentos (estimación base) | ≤984 | ≤2000 | Dentro |
| HTTP intentos (base + reservas) | ≤1 274 | ≤2000 | Dentro |
| HTTP peso (estimación base) | ≤1 452 | ≤5000 | Dentro |
| HTTP peso (base + reservas) | ≤3 692 | ≤5000 | Dentro |
| HTTP reintentos | ≤50 | ≤50 | Dentro |
| WS conexiones simultáneas | 2 (pico) | — | /public + /market |
| WS aperturas acumuladas | ≤46 | — | inicial + rotación + reconexión |
| Almacenamiento | ≤2 915 072 B (≈2,8 MB) | ≤128 MB | Dentro |

La estimación base (984 intentos / 1 452 peso) y las reservas (290 intentos /
2 240 peso: 240 peticiones repetidas + 50 reintentos por fallo) se publican
separadas; el techo efectivo sigue siendo 2 000 intentos / 5 000 peso por
ventana. Pesos de `ASSUMED_WEIGHTS` (tabla interna, no cabeceras Binance
reales). No se aumentaron cupos silenciosamente.

### Qué NO acredita este bloque

- Rentabilidad ni expectativa neta favorable (ni autoriza ejecución).
- Las tres ventanas de captura pública ni su presupuesto público (requieren
  autorización separada de adquisición).
- Cobertura de futuros con vencimiento (pendiente; solo perpetuos USD-M).

El experimento queda en **diseño verificado localmente, no listo para ejecutar
contra Binance**; requiere autorización separada de presupuesto y ventana
pública antes de cualquier adquisición.

## 9. Camino productivo para recoger los datos y reproducir la regla

### 9.1 Adaptador de conexión (integrado en research_pilot)

`scripts/research_operativo_adapter.py` implementa el adaptador mínimo que conecta:

```
seleccion (research_pilot) -> datos de mercado en T ->
direccion comun (derivar_direccion_desde_movimiento) ->
senal -> motor existente (paper_lab_engine) ->
entrada/gestion/salida simuladas -> resultado reproducible
```

El adaptador (`scripts/research_operativo_adapter.py`) está integrado en
`scripts/research_pilot.py` (`ResearchPilot`). Cada observación apta
(`kind=observacion`) se registra como trabajo operativo pendiente y se resuelve
mediante replay posterior: tras finalizar la captura, se leen las observaciones
persistidas, se obtienen las velas 1m mediante el mismo `HistoryClient` del
piloto (puerta de presupuesto incluida), y se ejecuta la regla operativa sobre
`paper_lab_engine`. El resultado se persiste en
`<out_dir>/resultado_operativo.jsonl` (`kind=resultado_operativo`).

- Reutiliza `paper_lab_engine` y `backtest_offline` como única autoridad
  económica.
- No abre Binance, no envía órdenes, no crea servicios ni motores paralelos.
- Deriva la dirección EXCLUSIVAMENTE de `move_24h_pct`; el rol
  candidate/comparator no determina dirección ni elude riesgo o capacidad.
- Usa velas 1m conocidas causalmente (open en `open_time_ms`, OHLC en
  `close_time_ms`) para reconstruir entrada posterior, stops, gaps y salida.
- No rellena huecos ni convierte ausencias en cero.
- Persiste resultados en JSONL para replay posterior sin usar resultados
  futuros para decidir.
- Una falla en el adaptador no derrumba el piloto: se registra en
  `stop_reason` y se sigue con el siguiente símbolo.
- Las operaciones se resuelven por replay posterior (no en tiempo real durante
  el ciclo del piloto), lo que permite usar trayectoria completa conocida sin
  depender de relojes futuros.

### 9.2 Datos a conservar (candidatos y comparadores)

Con identidad y unidades explícitas, separados entre datos disponibles al
decidir y datos posteriores para resolver el resultado:

| Dato | Campos | Disponible al decidir | Posterior (resultado) |
|---|---|---|---|
| Dato de movimiento | `move_24h_pct` (%), `disponibilidad_ms` | Sí | — |
| Ciclo, selección, rol | `cycle_id`, `role`, `symbol`, `priority` | Sí | — |
| Instante de decisión | `decision_ms`, `decision_iso` | Sí | — |
| Referencia de señal | `entry_px` (close de vela 1m conocida en T) | Sí | — |
| Configuración versionada | `config_hash`, `rule_version`, `engine_version` | Sí | — |
| Velas 1m | `open_time_ms, open, high, low, close, close_time_ms` | Sí (hasta T) | Sí (tras T, para fill/stop/salida) |
| Precio de fill | `entry_px`, `entry_ms`, `qty` | No (posterior a T) | Sí |
| Stop | `stop_px`, `stop_distance_pct` | Sí (referencia) | Sí (efectivo tras fill) |
| Salida | `exit_px`, `exit_ms`, `exit_reason`, `exit_executed` | No | Sí |
| Funding | `funding`, `funding_estado`, `funding_calendar` | No (calendario por símbolo) | Sí (settlements en holding) |
| Costes | `fee_bps`, `spread_bps`, `slippage_bps`, `fees`, `spread_slip` | Sí (supuestos) | Sí (ejecutados) |
| Cobertura/frescura | `disponibilidad.libro_ms`, `.flujo_ms`, `.seleccion_ms` | Sí | — |

### 9.3 Regla congelada (sin optimización)

- Baseline: continuación (derivada de `move_24h_pct`, no del rol).
- `stop_distance_pct = 0.5` → `stop_fraction = 0.005`.
- `notional_usdt = 1000`, riesgo nominal = 5 USDT antes de costes/gaps.
- `horizon_ms = 3 600 000` (60 min).
- `max_concurrent = 1` (una posición a la vez).
- Mismo `notional`, `stop_distance_pct`, `horizon_ms`, costes y frescura para
  candidatos y comparadores.
- `max_data_age_ms = 5000` (sin relajar).

### 9.4 Funding y resultado económico

- Se contabilizan únicamente eventos de funding dentro del período de exposición
  (`entry_ms <= settlement_ms < exit_ms`).
- La acreditación del total exige el veredicto explícito
  `funding_accounting_complete=true` de `backtest_offline` para la posición,
  además de cero exposición sin cubrir, cero settlements desconocidos y cero
  huecos aplicables. La integridad es por posición; un estado ausente o
  desconocido falla cerrado y no se infiere desde la integridad global.
- Funding cero requiere cobertura suficiente que acredite que no corresponde
  cargo ni abono.
- Calendario ausente o cobertura incompleta → `funding=null` y estado
  explícito UNKNOWN. Si se conserva un neto numérico sin funding completo,
  `neto_estado=CONDICIONADO_SIN_FUNDING_COMPLETO`; no se presenta como neto
  completo. Ningún importe parcial sustituye al total desconocido.
- Tasas conocidas posteriormente solo para contabilidad, nunca para decidir
  una entrada anterior.
- Comisiones y spread/slippage distinguidos de supuestos del modelo. Los fills
  simulados no se presentan como ejecuciones reales.

### 9.5 Presupuesto efectivo (calculado localmente, sin mercado público)

Generado con `scripts/research_pilot.py --budget-only` (sin red), desde el
plan real de solicitudes: ciclos de decisión, símbolos simultáneos, velas 1m
para entrada y para resultados (3 horizontes), y reintentos. Pesos contra
la tabla interna `ASSUMED_WEIGHTS` de `history_client` (no cabeceras
Binance reales, que no se han registrado).

Con la configuración del protocolo (3 ventanas × 1 h captura + 70 min
settle, `cycle_seconds=300`, `selection_seconds=300`, `max_symbols=20`,
3 horizontes 5m/15m/60m):

| Concepto | Por ventana | Total (3 ventanas) | Notas |
|---|---|---|---|
| exchangeInfo (REST) | 12 intentos / peso 12 | 36 / 36 | 1 por ciclo de selección (12 ciclos) |
| ticker 24h (REST) | 12 intentos / peso 480 | 36 / 1 440 | Movimiento 24h por selección |
| klines trayectoria operativa (REST) | 240 intentos / peso 240 | 720 / 720 | 1 por observación apta; la serie 1m cubre entrada, gestión y salida. Se consulta cuando la trayectoria del horizonte puede estar disponible (decisión + horizonte + un paso), no en cada tick |
| klines resultado (REST) | 720 intentos / peso 720 | 2 160 / 2 160 | 1 por observación × 3 horizontes |
| HTTP intentos (estimación base) | ≤984 | ≤2 952 | 24 preparación + 240 trayectoria + 720 resultados |
| HTTP peso (estimación base) | ≤1 452 | ≤4 356 | Dentro del techo 5 000/ventana |
| Reserva peticiones repetidas | ≤240 / peso ≤240 | ≤720 / ≤720 | ≤1 por observación (1 planificada + 1 repetida); distinto del reintento por fallo |
| Reserva reintentos por fallo | ≤50 / peso ≤2 000 | ≤150 / ≤6 000 | `max_http_retries` por ventana |
| HTTP intentos (base + reservas) | ≤1 274 | ≤3 822 | Techo efectivo 2 000/ventana |
| HTTP peso (base + reservas) | ≤3 692 | ≤11 076 | Techo efectivo 5 000/ventana |
| HTTP reintentos | ≤50 | ≤150 | Dentro del presupuesto |
| WS conexiones simultáneas | 2 | 2 (pico) | /public (depth) + /market (aggTrade) |
| WS aperturas acumuladas | ≤24 | ≤72 | Inicial + rotaciones + reconexiones |
| WS mensajes | ≤5 000 000 | ≤15 000 000 | Límite del piloto |
| WS reconexiones | ≤20 | ≤60 | Límite del piloto |
| Almacenamiento | ≤128 MB | ≤384 MB | JSONL + SQLite + aux |
| Captura + settle | 1 h + 70 min (130 min) | 6 h 30 min | 3 ventanas |
| Max símbolos | 20 | 20 | Por ventana |
| Max candidatos/comparadores | 12/8 | 12/8 | Techo conjunto 20 |

**Peso HTTP observado vs configurado:** los pesos son de `ASSUMED_WEIGHTS`
(tabla interna, no cabeceras Binance). El consumo real se reconstruye desde
el ledger de `HistoryClient`. La estimación base (1 452/ventana) y la base con
reservas (3 692/ventana) están dentro del techo de 5 000/ventana, por lo que
no se requiere aumento de cupos. La estimación base no es un máximo
garantizado: el límite efectivo es el techo configurado (2 000 intentos /
5 000 peso / 50 reintentos / 128 MB).

**Contraste con lo observado:** la aceptación
`tests/test_operativo_capacidad_presupuesto.py` ejecuta el CLI real con
proveedores loopback y reloj controlado, avanza por los intervalos de
planificación (no salta al final del horizonte) y compara las llamadas
recibidas por el proveedor, el consumo de la puerta de presupuesto y el plan
publicado: coinciden (ticker 1 + catálogo 1 + trayectoria 5 + precios 15 = 22
intentos en la corrida de aceptación, con el mismo peso en la puerta).

**Justificación del uso mínimo de REST/WS:** klines 1m por REST es el mínimo
necesario para reconstruir fills al open de vela siguiente, stops y gaps.
No se captura flujo/libro adicional más allá de lo que ya adquiere el piloto,
ni datos sin necesidad operativa concreta.

### 9.6 Comandos (NO EJECUTADOS)

Todos los comandos se proponen **sin ejecutar**; requieren autorización
separada de presupuesto y de ventana pública antes de cualquier adquisición.

**a) Validación de presupuesto (sin solicitudes de mercado):**

```
python scripts/research_pilot.py \
  --mode local \
  --budget-only \
  --run-id exp-v2-ventana-1 \
  --out-dir data/evidence/operativo_v2/ventana-1
```

Genera `presupuesto.json` en `<out-dir>/` sin abrir red ni mercado.

**b) Comando local con endpoints loopback (pruebas, sin Binance):**

```
python scripts/research_pilot.py \
  --mode local \
  --duration-seconds 3600 \
  --settle-seconds 4200 \
  --cycle-seconds 300 \
  --selection-seconds 300 \
  --max-symbols 20 \
  --max-candidates 12 \
  --max-comparators 8 \
  --min-quote-volume 1000000 \
  --horizons "5m=300000,15m=900000,60m=3600000" \
  --price-interval 1m \
  --price-tolerance-ms 90000 \
  --price-delay-ms 2000 \
  --max-data-age-ms 5000 \
  --max-observations 20000 \
  --max-bytes 134217728 \
  --max-messages 5000000 \
  --max-http-attempts 2000 \
  --max-http-retries 50 \
  --max-http-weight 5000 \
  --max-ws-reconnects 20 \
  --tick-ms 20 \
  --clock manual --clock-file <reloj-de-prueba.txt> \
  --run-id exp-v2-ventana-1 \
  --out-dir data/evidence/operativo_v2/ventana-1 \
  --rest-base http://127.0.0.1:<puerto-loopback> \
  --ws-public-base ws://127.0.0.1:<puerto-loopback> \
  --ws-market-base ws://127.0.0.1:<puerto-loopback> \
  --status-file <estado.json> \
  --decision-gate-file <gate.json> \
  --stop-file <paro.json>
```

**Modo `local`:** rechaza endpoints públicos antes de cualquier envío
(require endpoints loopback explícitos). `--clock manual` con
`--decision-gate-file`/`--stop-file` son opciones de prueba; el camino
productivo automático no las requiere.

**c) Comando público propuesto (NO EJECUTADO):**

```
python scripts/research_pilot.py \
  --mode public --activar-publico \
  --duration-seconds 3600 \
  --settle-seconds 4200 \
  ...
```

Requiere autorización separada de presupuesto y de ventana pública.
**No se ejecuta contra Binance sin esa autorización.**

**Identificación de corrida:** `--run-id` único por ventana. Los datos se
persisten en `<out-dir>/` (`observaciones.jsonl`,
`resultado_operativo.jsonl`, `resumen.json`).

### 9.7 Evidencia para aceptar o rechazar el experimento

Aceptar solo si, tras las 3 ventanas autorizadas:
- Nivel A: diferencia consistente de `neto_por_operación` entre candidatos
  y comparadores, con cobertura ≥50% de ciclos con ambos grupos aptos.
- Nivel B: regla ejecutada conforme al modelo (causalidad respetada, sin
  lookahead, fills en open de vela siguiente, stops al precio real tras gap).
- Nivel C: `neto_por_operación` medio > 0 con supuestos de costes declarados
  y defendibles, en las 3 ventanas.

Rechazar o declarar insuficiencia si falta cualquiera de los anteriores. La
insuficiencia no autoriza automáticamente más capturas.

La prueba local **no acredita rentabilidad ni autoriza** las tres ventanas ni
ejecución real. Queda pendiente: velas 1m con open/close causales, calendario
de funding por símbolo, y autorización separada de presupuesto.
