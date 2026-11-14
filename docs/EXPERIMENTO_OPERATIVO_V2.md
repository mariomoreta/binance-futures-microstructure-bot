# Protocolo de experimento operativo v2 — research/universe-liquidez-v1

**Estado:** diseño de alcance cerrado y demostrado localmente. Desde la decisión humana de 2026-11-11, la **vía A** (espera contable con liquidaciones observadas, §10.6) es el método preparado para la primera ventana; la **opción B** de cobertura histórica de funding (§10.5) se conserva implementada y queda **diferida**. Actualización 2026-11-12: la ventana única quedó **autorizada por decisión humana explícita** (2026-11-11/12) y el monitor de observabilidad de solo lectura está integrado y verificado localmente (§10.7); la ventana **aún no se ha ejecutado** y no se ha abierto Binance ni ningún endpoint público de mercado. No hay órdenes reales, no hay conexión nueva a Binance, no hay infraestructura nueva, no hay cambios económicos productivos. Este documento actualiza y reemplaza el alcance de `docs/EXPERIMENTO_OPERATIVO_V1.md` (diseño de alcance v1); no se borra el v1, se conserva como referencia histórica.

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

> Estos importes son el estado histórico del recorrido local con
> `funding_source=none`. El presupuesto vigente de la primera ventana con
> funding real está en el bloque 10.

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

> **Nota de supersesión:** los importes de esta sección correspondían al
> recorrido local sin adquisición automática de funding (`funding_source=none`).
> Para la primera ventana con funding real, el presupuesto vigente es el del
> bloque 10. Este bloque se conserva como historial.

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

> **Nota de supersesión:** los comandos de este subapartado pertenecen al
> recorrido local histórico (`run_id exp-v2-ventana-1`, sin funding
> automático). El comando vigente de la primera ventana, con funding real y
> `run_id exp-v2-ventana-1-20261110a`, está en el §10.2 y §10.3 y no debe
> reutilizar el identificador anterior.

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
ejecución real. El camino local de velas 1m y funding real por símbolo quedó
preparado en el bloque 10, pero la evidencia pública, la cobertura real de
funding y la autorización separada siguen pendientes.

## 10. Preparación local de la primera ventana (2026-11-10, NO EJECUTADA)

**Base revisada:** `6d321a27e333d8e416f429f525d766b4cfac7aef`, rama
`research/universe-liquidez-v1`. Se conserva el trabajo posterior y los cambios
ajenos. No se abrió ninguna conexión pública de mercado ni se ejecutó la
ventana.

### 10.1 Cerrajes mínimos para hacer evaluable la ventana

1. **Funding real por símbolo observado.** `research_pilot` consulta
   `GET /fapi/v1/fundingRate` por símbolo después de que la trayectoria del
   horizonte puede estar disponible. La consulta usa el mismo `HistoryClient`,
   `RunBudget` y ledger HTTP del piloto. Las filas realizadas se convierten en
   el `FundingCalendar` existente; la cadencia nominal solo se infiere de
   deltas repetidos de settlements regulares. No hay calendario sintético en
   esta ruta y `--funding-source exchange` excluye
   `--funding-calendars`.
2. **Comparadores con movimiento real.** El movimiento 24 h de un comparador se
   conserva desde el ticker observado en T. La dirección se deriva de ese
   movimiento con la misma función usada para candidatos. El rol no determina
   LONG/SHORT ni modifica entrada, stop, horizonte, coste o capacidad.
3. **Separación de netos.** El resumen reconstruido desde filas persistidas
   separa `COMPLETO` de `CONDICIONADO_SIN_FUNDING_COMPLETO`; un funding
   desconocido nunca se convierte en cero. La comparación de roles solo se
   publica si ambos tienen operaciones completas y al menos el 50 % de los
   ciclos tiene ambos roles aptos.
4. **Trazabilidad HTTP y almacenamiento.** Cada intento registra peso
   configurado y reservado, resultado, cabeceras observadas y SHA-256 de la
   respuesta. El tope de 128 MB incluye los JSONL de datos, ledger HTTP,
   calendarios de funding, SQLite y auxiliares, sin doble conteo.
5. **Cotas de reintento.** El reintento número 51 se bloquea antes del
   transporte; un intento bloqueado no consume el límite compartido de
   `/fapi/v1/fundingRate` (500/5 min).

### 10.2 Presupuesto local calculado, sin red

`--budget-only` se reejecutó con el código final y la configuración exacta
propuesta; terminó con código 0, `stderr` vacío y sin abrir red. Artefacto
fuera de Git:
`C:\Users\adonm\AppData\Local\Temp\opencode\binance-futures-operativo-v2\exp-v2-ventana-1-20261110a\presupuesto.json`
(SHA-256 `eb2f93dea16bac8c2c911654dac51482f565a801d0531c574cdd4780f97ccec3`).

Comando exacto de validación, sin red:

```powershell
$runDir = 'C:\Users\adonm\AppData\Local\Temp\opencode\binance-futures-operativo-v2\exp-v2-ventana-1-20261110a'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
python scripts/research_pilot.py `
  --mode public --activar-publico --budget-only `
  --duration-seconds 3600 `
  --settle-seconds 4200 `
  --cycle-seconds 300 `
  --selection-seconds 300 `
  --decision-delay-seconds 5 `
  --max-symbols 20 `
  --max-candidates 12 `
  --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m `
  --price-tolerance-ms 90000 `
  --price-delay-ms 2000 `
  --max-data-age-ms 5000 `
  --max-observations 20000 `
  --max-bytes 134217728 `
  --max-messages 5000000 `
  --max-http-attempts 2000 `
  --max-http-retries 50 `
  --max-http-weight 5000 `
  --max-ws-reconnects 20 `
  --tick-ms 20 `
  --funding-source exchange `
  --run-id exp-v2-ventana-1-20261110a `
  --out-dir $runDir `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com `
  --ws-market-base wss://fstream.binance.com `
  --status-file (Join-Path $runDir 'estado.json') `
  > (Join-Path $runDir 'budget-only.stdout.log') 2> (Join-Path $runDir 'budget-only.stderr.log')
$code = $LASTEXITCODE
$code | Set-Content -LiteralPath (Join-Path $runDir 'budget-only.exit_code.txt') -Encoding ascii
```

| Concepto | Una ventana | Techo efectivo | Estado |
|---|---:|---:|---|
| HTTP intentos, base | 1 224 | 2 000 | Dentro |
| HTTP intentos, base + reservas | 1 754 | 2 000 | Dentro |
| HTTP peso, base | 1 692 | 5 000 | Dentro |
| HTTP peso, base + reservas | 4 172 | 5 000 | Dentro |
| HTTP reintentos | 50 | 50 | Dentro |
| Funding, máximo concentrado 5 min | 90 | 500 | Dentro (supuesto de planificador) |
| Almacenamiento previsto | 7 310 872 B | 134 217 728 B | Dentro (5,45 %) |
| Almacenamiento con cuotas reservadas | 54 363 648 B | 134 217 728 B | Dentro (40,5 %) |
| Duración captura + settle | 3 600 + 4 200 s | 7 800 s | Ventana única |
| Símbolos / candidatos / comparadores | 20 / 12 / 8 | 20 conjuntos | Dentro |

La implementación de la opción B no cambia el número de consultas necesarias: la
misma consulta histórica de funding se conserva y solo se amplía su
procedencia y validación. Por esa razón no se recalcula `--budget-only`; el
presupuesto, las reservas y los topes publicados siguen siendo el control
efectivo de esta variante.

La base incluye 24 llamadas de preparación, 240 trayectorias operativas, 720
precios por horizonte y 240 consultas de funding real. Las reservas incluyen
240 repeticiones de trayectoria, 240 repeticiones de funding y 50 reintentos
por fallo. No se aumentó ningún cupo.

Desglose de almacenamiento previsto: 3 072 000 B de JSONL de datos, 960 000 B
de calendarios de funding, 1 227 800 B de ledger HTTP, 1 920 000 B estimados de
SQLite y 131 072 B de auxiliares WAL/SHM. En runtime, SQLite queda limitado por
`PRAGMA max_page_count` a una cuota de 33 554 432 B y el ledger HTTP a una
reserva de 16 777 216 B; con las reservas, el total contabilizado es
54 363 648 B. `resumen.json`, `manifiesto.json` y `estado.json` son índices
finales y no forman parte del tope de datos de la ventana.

El gate de `--budget-only` falla cerrado: con un plan sobre presupuesto el
proceso escribe `presupuesto.json` y devuelve código 3, y el modo público se
niega a arrancar con el mismo código. El `funding_maximo_concentrado_5m=90` es
una asunción del planificador (20 símbolos × su repetida + 20 + 50 reintentos),
no un límite derivado y probado; los 530 intentos de funding reservados son
acumulados de la hora, no de 5 minutos. El límite real de 500/5 min se aplica
en runtime y bloquea antes del transporte.

### 10.3 Comando público propuesto (NO EJECUTADO, BLOQUEADO)

Requiere autorización humana específica para **una sola ventana** y la
evidencia de venue que sigue pendiente en el §10.5. No autoriza las otras dos.

```powershell
$runDir = 'C:\Users\adonm\AppData\Local\Temp\opencode\binance-futures-operativo-v2\exp-v2-ventana-1-20261110a'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
python scripts/research_pilot.py `
  --mode public --activar-publico `
  --duration-seconds 3600 `
  --settle-seconds 4200 `
  --cycle-seconds 300 `
  --selection-seconds 300 `
  --decision-delay-seconds 5 `
  --max-symbols 20 `
  --max-candidates 12 `
  --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m `
  --price-tolerance-ms 90000 `
  --price-delay-ms 2000 `
  --max-data-age-ms 5000 `
  --max-observations 20000 `
  --max-bytes 134217728 `
  --max-messages 5000000 `
  --max-http-attempts 2000 `
  --max-http-retries 50 `
  --max-http-weight 5000 `
  --max-ws-reconnects 20 `
  --tick-ms 20 `
  --funding-source exchange `
  --run-id exp-v2-ventana-1-20261110a `
  --out-dir $runDir `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com `
  --ws-market-base wss://fstream.binance.com `
  --status-file (Join-Path $runDir 'estado.json') `
  > (Join-Path $runDir 'stdout.log') 2> (Join-Path $runDir 'stderr.log')
$code = $LASTEXITCODE
$code | Set-Content -LiteralPath (Join-Path $runDir 'exit_code.txt') -Encoding ascii
```

Artefactos esperados: `manifiesto.json`, `resumen.json`, `presupuesto.json`,
`http_requests.jsonl`, `funding_adquisicion.jsonl`, `funding/*.json`,
`observaciones.jsonl`, `resultado_operativo.jsonl`, `research.db`, `estado.json`,
`stdout.log`, `stderr.log` y `exit_code.txt`.

### 10.4 Lectura económica y paradas

La pregunta de esta ventana es de **viabilidad y exploración**, no de
rentabilidad generalizable: ¿la regla causal se ejecuta de extremo a extremo
con datos y funding identificables, y qué diferencia descriptiva aparece entre
candidatos y comparadores bajo la misma regla? Si el funding no cubre la
exposición, el neto completo permanece `UNKNOWN` y solo puede publicarse el
neto condicionado. Una diferencia aislada no acredita edge.

Paradas obligatorias: cualquier violación causal; fills, stops, gaps o
posiciones abiertas sin acreditación; presupuesto excedido; almacenamiento
excedido; o fallo que impida reconstruir el ledger y el resumen desde lo
persistido. La insuficiencia no renueva automáticamente esta ventana ni las
otras dos.

Cobertura: solo perpetuos USD-M. Los futuros con vencimiento siguen pendientes.
GARCH continúa diferido. Esta preparación no autoriza órdenes, cuentas,
claves, paper deployment ni ejecución real.

### 10.5 Revisión independiente, opción B autorizada e implementación local

Una revisión independiente de la preparación (2026-11-10) reprodujo cinco
defectos técnicos y un defecto económico/metodológico. Los defectos técnicos se
cerraron en este bloque. La persona autorizó después la **opción B**; las
opciones A y C quedan excluidas. El contrato de cobertura B está implementado y
aceptado localmente, pero la ruta Binance real conserva un P0 de evidencia que
impide cerrar la primera ventana pública.

**Defectos técnicos cerrados (verificados con la suite):**

1. El gate de presupuesto consultaba `max_comparadores` con el nombre del
   `ResearchPolicy` (`max_comparadores`), de modo que `compute_budget` fallaba
   con `AttributeError` y `--budget-only` no podía validar nada. Corregido al
   nombre real de `PilotConfig` (`max_comparators`).
2. La ampliación de `FundingSettlement` (marca, tipo de tasa) cambió el `repr`
   del calendario y, con él, el `config_hash` de `BacktestConfig`, que entra en
   los manifiestos publicados de `docs/evidence/eval-census-v2-package`. La
   reconstrucción published→replay pasó a 168 celdas fallidas. Se estabilizó el
   texto del calendario para que el `config_hash` de las corridas publicadas
   siga siendo reproducible, mientras `calendar_hash()` sí compromete la
   procedencia nueva. Regresión cubierta por
   `tests/test_backtest_funding.py::PublishedConfigHashTest`.
3. El límite de reintentos era global pero se contaba por texto de resultado:
   los errores de conexión no consumían cupo. Ahora `RunBudget.before_send`
   cuenta el reintento cuando `retry > 0`, global entre peticiones.
4. Un intento bloqueado antes del transporte quedaba indistinguible de uno
   enviado. Ahora se registra `result="blocked_before_send"` con
   `block_reason` y marcas absolutas, sin consumir cupo ni peso.
5. El ledger y el resumen solo se escribían en la salida normal. Ahora se
   reconstruyen en el `finally` de la corrida, también ante excepción o señal,
   y el drenaje del recorder se amplía a 30 s.

**Defecto económico/metodológico P0 (abierto, requiere decisión): cobertura de
funding al cierre de la exposición.**

`backtest_offline` acredita el funding por posición: la exposición
`[entry_ms, exit_ms)` queda sin cubrir cuando el calendario no lista ningún
settlement posterior a `exit_ms` (`uncovered = exit_ms - último_settlement`).
La consulta de funding se hace cuando la trayectoria del horizonte ya puede
estar disponible, es decir, alrededor de `exit_ms + 1 min`. Por tanto, para
que la cobertura sea completa hace falta un settlement en la ventana
`(exit_ms, consulta]`, de aproximadamente uno o dos minutos.

Reproducción local con el motor canónico (sintética, sin mercado): cadencia de
8 h, exposición de 60 min y consulta un minuto después del cierre dejan
`funding_accounting_complete=false` con `uncovered holding 3 540 000 ms`; con un
settlement ya posterior al cierre, la misma posición queda `fully settled, no
gaps, no uncovered holding`. Con cadencia de 8 h, la probabilidad de que un
boundary cae en esa ventana de uno o dos minutos es del orden del 0,4 % por
posición.

Consecuencia sobre la ventana tal como está definida: la mayoría de las
operaciones quedarían `CONDICIONADO_SIN_FUNDING_COMPLETO` en lugar de
`COMPLETO`, y la comparación candidate/comparator, que solo se publica con
operaciones `COMPLETO` en ambos roles, quedaría `INSUFICIENTE`. El importe de
funding realmente liquidado se conservaría como dato, pero el neto completo
seguiría `UNKNOWN`. **No se debilita `funding_accounting_complete` ni se
convierte `UNKNOWN` en cero para forzar un resultado.**

**Decisión humana registrada (2026-11-10):** se autoriza y se implementa solo la
**opción B**. No se implementan A ni C:

- **Opción A, adquirir y retener un settlement posterior.** Excluida. No se
  alarga el settle, no se fabrica un settlement posterior y no se infiere una
  cadencia fija.
- **Opción B, extender el contrato del calendario con límites de cobertura y
  horario de venue probados.** Seleccionada. La cobertura puede acreditar la
  cola sin settlement posterior únicamente cuando la evidencia del intervalo
  consultado demuestra ausencia de eventos y un retraso de publicación
  verificable.
- **Opción C, modelar como cubiertos los intervalos entre settlements
  regulares.** Excluida. No se interpola ni se modela la ausencia por cadencia.

> **Actualización posterior (2026-11-11):** la decisión humana cambió y la
> **opción A** vuelve a ser el método de la primera ventana, con una espera
> contable acotada y liquidaciones realmente observadas. **B se conserva y queda
> diferida**, sin cambios en su contrato ni en sus validaciones. El detalle
> está en §10.6; lo anterior se conserva como registro histórico.

**Contrato implementado `funding-coverage/v1`.** `FundingCoverage` es un
campo aditivo de `FundingCalendar`; un calendario sin `coverage` conserva
exactamente la semántica legacy. El contrato identifica instrumento y fuente,
venue, intervalo inequívoco `[interval_start_ms, interval_end_ms)`, instants de
adquisición y disponibilidad, método y evidencia, petición, respuesta,
símbolos, hashes, paginación, digest de settlements y límite de retraso de
publicación con su evidencia. Los estados son `complete`, `incomplete` y
`unknown`.

Una reclamación `complete` solo es válida si reúne todas estas pruebas:

1. símbolo e intervalo temporal coherentes entre calendario, evidencia,
   petición y respuesta;
2. respuesta completa y no truncada, con paginación cerrada, símbolos
   coherentes, `row_count` igual a las filas cargadas y ningún settlement
   fuera del intervalo solicitado;
3. digest de settlements coherente con las filas cargadas, incluidos
   duplicados exactos;
4. evidencia admitida de ausencia de eventos, vinculada a símbolo, venue,
   intervalo y fuente, con referencia de artefacto inmutable y hash
   coherente;
5. máximo de retraso de publicación conocido, con evidencia del mismo tipo y
   símbolos/intervalo/venue vinculados, y disponibilidad posterior a que
   haya transcurrido ese retraso;
6. hashes y procedencias presentes, consistentes y utilizables.

`FundingCoverage.from_dict` degrada a `unknown` una reclamación `complete` que
no supera esas validaciones. El motor nunca acredita evidencia inválida.

**Contabilidad por posición.** La exposición sigue siendo el intervalo
semiabierto `[entry_ms, exit_ms)`. Con cobertura `complete` sobre esa
exposición y sin settlement aplicable, el funding conocido es cero. Con un
pago aplicable se contabiliza su importe mediante la fórmula vigente de
`backtest_offline`. Con cobertura parcial, ambigua o desconocida, el total de
funding es `UNKNOWN`; un importe parcial observado no sustituye el total
desconocido. El veredicto económico por posición de `backtest_offline` sigue
siendo la autoridad.

**Compatibilidad.** La cobertura no reescribe la representación legacy del
calendario ni altera `repr`, `calendar_hash()` o `config_hash()` cuando
`coverage=None`. El hash publicado `2e34e9d48595d5db` no cambia y los
resultados históricos no se reclasifican. Los hashes nuevos sí comprometen la
cobertura y su configuración.

**Publicación operativa.** Cada fila persistida publica el funding conocido o
`UNKNOWN`, el estado efectivo y la integridad de la cobertura, el intervalo,
la procedencia, el hash, los errores y el motivo por posición. Una reclamación
inválida se persiste degradada a `unknown`, sin conservar un estado `complete`
contradictorio en el objeto anidado. El neto es `COMPLETO` solo con funding
acreditado y salida ejecutada; en otro caso queda
`CONDICIONADO_SIN_FUNDING_COMPLETO`. Una posición `open_at_end` mantiene su
marca diagnóstica, pero su P&L realizado y su estado de neto permanecen
`UNKNOWN`.

**Ruta Binance real.** `research_pilot` conserva parámetros, estado HTTP, tamaño
y número de elementos de la respuesta, hashes, símbolo, truncamiento y
procedencia. La documentación pública de Binance consultada no ofrece una
garantía general de completitud ni un máximo de retraso de publicación. En
consecuencia, HTTP 200 o una respuesta vacía no acreditan ausencia de
liquidaciones: la ruta Binance permanece `unknown` o `incomplete` según la
respuesta y nunca declara `complete` por status o ausencia de filas.

**Aceptación local A-F.** La nueva aceptación cubre: A, cero conocido con
cobertura completa; B, pago conocido y fórmula vigente; C, cobertura parcial con
total `UNKNOWN`; D, evidencia inválida, respuesta truncada, símbolo
contradictorio, digest contradictorio y retraso de publicación ausente; E,
calendario legacy y hash publicado; F, límites `[entry_ms, exit_ms)`,
equivalencia, compromiso por hashes, loaders, persistencia del adaptador y
recorrido CLI real con calendario sintético temporal. No se usó un adaptador
externo ni se abrió una conexión pública.

**P0 real que sigue abierto.** Para habilitar la ruta Binance se necesita una
prueba oficial y trazable que: cubra el intervalo solicitado; vincule símbolo,
parámetros, respuesta y hashes; pruebe la ausencia de settlements; y fije un
máximo de retraso de publicación verificable para ese símbolo e intervalo.
Sin esa prueba, la primera ventana pública sigue en **NO-GO** y sus netos no
pueden declararse `COMPLETO`. Cerrar el P0 exige evidencia nueva y
autorización separada; no autoriza abrir Binance por sí mismo.

**Límites vigentes:** cobertura solo de perpetuos USD-M; futuros con
vencimiento pendientes; GARCH diferido; la primera ventana, si se autoriza,
solo demuestra viabilidad y evidencia exploratoria, no rentabilidad
generalizable. La insuficiencia no renueva cupos ni ventanas.

### 10.6 Vía A de la primera ventana: espera contable con liquidaciones observadas (decisión humana 2026-11-11)

**Decisión registrada (2026-11-11).** Se retoma la **opción A** para la primera
ventana: el funding se resuelve **después**, con liquidaciones realmente
observadas. `funding-coverage/v1` (opción B) **se conserva y queda diferido**: no
se amplía ningún validador para exigir una garantía de publicación que no se ha
encontrado. La elección de vía es **explícita** (`--funding-method`); no hay
fallback silencioso, no se borran metadatos `unknown` y no se reclasifican
resultados históricos. Este bloque autoriza **preparación, implementación
mínima y pruebas locales**: no autoriza Binance, adquisición pública, órdenes
reales ni la ejecución de ventanas.

#### 10.6.1 Separación de captura, operación y espera contable

Se mantiene sin cambios la captura de 3600 s, la selección y decisión cada
300 s, el máximo de 12 candidatos y 8 comparadores (unión máxima 20), la
frescura de 5000 ms, el flujo de 60 s, el stop del 0,5 %, el notional de 1000
USDT, el horizonte operativo de 60 min, `max_concurrent=1` compartido y las
mismas reglas y costes para ambos roles.

Al terminar la captura **los feeds se cierran**. Los precios posteriores y las
operaciones siguen resolviéndose según sus horizontes originales: la espera de
funding **no** abre nuevas selecciones, entradas ni posiciones y no altera la
exposición. La contabilidad se evalúa siempre sobre `[entry_ms, exit_ms)`: una
liquidación posterior a `exit_ms` puede aportar **evidencia de cobertura**, pero
**no es un coste** de esa posición.

La vía A añade una tercera fase, **espera contable**, después del settle:

- durante la espera solo se consulta el histórico de funding y se publica la
  contabilidad resultante; no hay decisiones ni operaciones nuevas;
- termina antes si no queda trabajo, al vencer el plazo máximo (sin prórroga),
  o ante parada del operador o presupuesto agotado.

#### 10.6.2 Adquisición diferida y acotada

Se reutilizan el cliente, la puerta de presupuesto, el ledger y los pendientes
existentes: no hay segundo servicio, supervisor ni motor, ni otro camino de
acceso a la venue.

- **No se compra funding durante la resolución de la trayectoria.** La salida se
  decide y se persiste con su regla, con la contabilidad de funding en estado
  `PENDIENTE`.
- **Una consulta diferida por símbolo con posición cerrada**, no por
  observación. La ventana cubre desde antes de la entrada (con el lookback
  histórico de 48 h) hasta el instante actual.
- **La planificación usa la cadencia observada de ese símbolo**, no una
  cadencia supuesta: el siguiente instante previsto es `última liquidación
  observada + cadencia observada + 30 min de margen de publicación`. Si la
  cadencia todavía no se puede inferir, se reintenta con un intervalo fijo de
  30 min. No se sondea en cada tick.
- **La evidencia anterior y posterior es la que decide.** El calendario se
  construye con las liquidaciones realmente devueltas por la venue; el
  veredicto canónico por posición de `backtest_offline` evalúa la cobertura
  sobre el intervalo real de la posición. Si hay huecos, cadencia ambigua o
  cobertura insuficiente, el total queda `UNKNOWN` con su motivo.
- **Límites:** espera máxima **32 400 s (9 h)** y **3 consultas por símbolo**
  como máximo. Ninguna cifra se amplía por CLI: superar cualquiera de los dos
  topes es un error de configuración.

La contabilidad usa la función canónica de `backtest_offline` sobre el intervalo
real `[entry_ms, exit_ms)` de la posición, sin recalcular la operación y sin
duplicar la lógica económica. El importe acreditado es el que la venue liquidó
dentro de la exposición; un importe parcial no sustituye a un total desconocido.

#### 10.6.3 Una sola corrida y un solo presupuesto

El mismo `run_id` y el mismo consumo acumulado cubren captura, resolución de
precios y espera contable. La espera no devuelve cupos ni crea otra corrida.
`--budget-only` se recalculó incluyendo preparación y captura, trayectorias
operativas, resultados por horizonte, consultas diferidas de funding, peticiones
repetidas y reintentos por fallo (separados), y almacenamiento y artefactos. Los
topes existentes se conservan: 2000 intentos HTTP, peso 5000, 50 reintentos,
128 MB y el control compartido de funding por ventana temporal.

Presupuesto efectivo de la primera ventana (`--budget-only`, calculado localmente
sin red, **no ejecutado**):

| Concepto | Valor |
|---|---|
| Duración de captura | 3600 s |
| Settle | 4200 s |
| Espera contable máxima | 32 400 s (9 h) |
| Duración máxima total | 40 200 s (11 h 10 min) |
| Intentos base | 1004 |
| Intentos con reservas (repetidas + reintentos) | 1334 / 2000 |
| Peso base | 1472 |
| Peso con reservas | 3752 / 5000 |
| Consultas de funding (base + repetidas) | 20 + 40 = 60 |
| Funding concentration 5 min (peor caso) | 110 / 500 |
| Almacenamiento previsto / reservado | 4 696 872 B / 52 043 648 B / 134 217 728 B |
| Gate `--budget-only` | `cabe_en_limites: true`, salida 0 |

Desglose de endpoints: `exchangeInfo` 12, `ticker/24hr` 12, klines de
trayectoria 240, klines de resultado por horizonte 720 y `fundingRate` 20
(una por símbolo con posición abierta). La concentración de funding se calcula
de forma conservadora con todas las consultas de la ventana a la vez; en
ejecución real se reparten por símbolo y por boundary observado.

#### 10.6.4 Condiciones de cierre e insuficiencia

| Situación | Resultado publicado |
|---|---|
| Cobertura acreditable (liquidación posterior observada, sin huecos) | `ACREDITADA`, funding acreditado, `neto_estado=COMPLETO` |
| Falta solo la liquidación posterior a la salida | `PENDIENTE` con el diagnóstico (`funding_sin_cubrir_ms`), sin acreditar importe |
| Hueco interior observado, cadencia ambigua o marca inservible | `UNKNOWN` con el motivo; nunca cero |
| Vencimiento del plazo de espera | `UNKNOWN`, motivo `plazo_maximo_de_espera_agotado` |
| Consultas de funding agotadas | `UNKNOWN`, motivo `consultas_de_funding_agotadas` |
| Parada del operador o presupuesto agotado | `PENDIENTE` con la causa real (no se confunde "interrumpido" con "evidencia insuficiente") |
| Posición abierta (`open_at_end`) | `UNKNOWN` en el P&L realizado, con marca diagnóstica aparte |

Ninguna vía prorroga el plazo, devuelve cupos ni convierte `UNKNOWN` en cero.

#### 10.6.5 Aceptación local (CLI real, proveedores loopback, reloj controlado)

`tests/test_operativo_funding_espera_contable.py` (5 pruebas) ejecuta el CLI
real como subproceso, con proveedores HTTP/WS loopback, reloj controlado y
almacenamiento temporal aislado. La venue simulada publica cada liquidación
solo cuando ya ha ocurrido, de modo que una liquidación futura no puede
inventarse.

- **A.** La captura termina y los feeds se cierran (`connected_now=false`).
- **B.** La operación sale por su regla (`exit_reason=horizon`) con el funding
  todavía pendiente: la fila se publica con `contabilidad_funding_estado=PENDIENTE`
  y `funding=null`.
- **C.** La liquidación posterior todavía no publicada no se inventa: la fila
  diagnostica `funding_sin_cubrir_ms>0` sin acreditar ningún importe.
- **D.** Al aparecer la evidencia, el mismo recorrido completa la contabilidad:
  la fila final queda `ACREDITADA` con `neto_estado=COMPLETO`.
- **E.** Un pago posterior a la salida no se cobra: solo se contabiliza la
  liquidación dentro de `[entry_ms, exit_ms)`; la liquidación posterior figura en
  el calendario observado y no en los eventos cobrados.
- **F.** Cobertura insuficiente o vencimiento de espera → `UNKNOWN` con motivo.
- **G.** Parada del operador → el pendiente se conserva con su causa y el
  cierre auditable se escribe desde lo persistido.
- **H.** Proveedor, gate y planificación presupuestaria coherentes: las
  consultas diferidas quedan en el ledger HTTP con parámetros, estado y hash de
  respuesta; el plan `--budget-only` de la vía A cabe en los topes.

No se completó el trabajo por fuera del CLI con otro adaptador o cliente: el
recorrido usa el mismo cliente, la misma puerta de presupuesto y el mismo
ledger que la corrida real.

#### 10.6.6 Comando exacto propuesto (NO EJECUTADO)

```bash
python scripts/research_pilot.py \
  --mode public --activar-publico \
  --run-id exp-v2-ventana-1-20261111a \
  --out-dir data/experiments/exp-v2-ventana-1-20261111a \
  --duration-seconds 3600 --settle-seconds 4200 \
  --cycle-seconds 300 --selection-seconds 300 --decision-delay-seconds 5 \
  --max-symbols 20 --max-candidates 12 --max-comparators 8 \
  --min-quote-volume 1000000 \
  --horizons 5m=300000,15m=900000,60m=3600000 \
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 \
  --max-data-age-ms 5000 --max-observations 20000 \
  --max-bytes 134217728 --max-messages 5000000 \
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 \
  --max-ws-reconnects 20 --tick-ms 500 \
  --funding-source exchange \
  --funding-method observed-settlements \
  --funding-wait-seconds 32400 \
  --funding-wait-max-queries 3
```

`--budget-only` con esa misma configuración devuelve `cabe_en_limites: true`
(salida 0) y es el único comando que se ha ejecutado: **la ventana no se ha
ejecutado** y no se ha abierto Binance ni ningún endpoint público de mercado.

#### 10.6.7 Qué podrá concluir la primera ventana y qué seguirá `UNKNOWN`

Si la evidencia llega dentro del plazo, la primera ventana podrá concluir, por
posición y por rol: entrada, salida y motivo; cobertura del funding observada;
importe liquidado dentro de `[entry_ms, exit_ms)`; neto completo o
condicionado; y la comparación candidate/comparator con el criterio de ciclo
congelado, publicada solo con operaciones completas en ambos roles. Es
evidencia exploratoria de viabilidad, **no** rentabilidad generalizable.

Seguirá `UNKNOWN` aunque la ventana se ejecute: la ausencia de una liquidación
que la venue no publique dentro del plazo; los huecos o la cadencia ambigua del
histórico de un símbolo; el P&L realizado de las posiciones abiertas; y todo lo
que dependa del **P0 de B** (prueba de ausencia de liquidaciones y máximo de
retrasy de publicación verificables), que sigue abierto y cuya evidencia no
puede inventarse.

#### 10.6.8 Límites de este bloque

Sigue sin cobertura de futuros con vencimiento (solo perpetuos USD-M), GARCH
continúa diferido, y la apertura de la ventana requiere autorización humana
explícita y posterior. No se ha ejecutado ninguna ventana pública ni se ha
tocado ningún dataset, base de datos o servicio existente.

### 10.7 Ventana única autorizada: monitor de observación y comando efectivo (2026-11-12)

La autorización humana de 2026-11-11/12 cubre tres cosas y solo tres: (1) la
integración mínima de un monitor de observabilidad del piloto real en el
dashboard existente, (2) su verificación local **sin mercado público** y (3) si
esas comprobaciones pasan, la ejecución **supervisada de una única ventana**
pública por la vía A con la configuración congelada, su cierre y el análisis
exploratorio de sus registros persistidos. No autoriza órdenes reales, cuentas
privadas, claves, cambios de apalancamiento, fondos reales, otras ventanas ni
relanzamientos.

#### 10.7.1 Monitor de observación (solo lectura, dentro de `/market-lab`)

El monitor no es una aplicación nueva: es un modo de vista del dashboard
Next.js que ya sirve el puerto 3020,
`http://127.0.0.1:3020/market-lab?vista=piloto&run=<run_id>`. En ese modo no
se montan los componentes que abren streams o descargas ajenas al ledger, y el
panel no inicia, reinicia ni detiene la corrida: el lanzamiento es solo por
CLI. El backend lee los artefactos ya persistidos de la corrida (snapshot
atómico de `--status-file`, `observaciones.jsonl`, `resultado_operativo.jsonl`,
`resumen.json`, `manifiesto.json`) desde una ruta acotada: el cliente envía
solo un `run_id` validado, nunca una ruta. No hay peticiones públicas
adicionales y el navegador no calcula decisiones, funding ni P&L.

Para que el estado exista, el piloto expone lo que ya tenía: el snapshot
atómico publica `run_id`, `mode`, `activar_publico`, los contadores
autoritativos de presupuesto (`RunBudget.status()`) y almacenamiento
(`RunStorageBudget.status()`), `duracion_maxima_total_ms` y
`espera_contable_plazo_max_ms`; la fila operativa publica `stop_px`, que la
regla congelada ya calculaba. Son exposición pura: no cambian decisiones,
cálculos económicos, hashes de configuración ni resultados históricos.

Aceptación local superada con navegador real y build de producción en 3020
(corrida real del piloto en modo local, proveedores loopback y reloj
controlado): Captura → Resolución → Espera contable → Finalizada observadas
**sin recargar**; una sola operación con actualizaciones contables 0→1→2
(UNKNOWN/PENDIENTE → ACREDITADA), tiempos históricos de entrada y salida
conservados, feeds cerrados con aviso explícito de que el mercado no está
LIVE, contadores de presupuesto autoritativos y cero peticiones fuera de
`127.0.0.1:3020` ni procesos nuevos al abrir y recargar la vista. Evidencia:
`docs/evidence/monitor-piloto-20261112/`.

#### 10.7.2 Comando efectivo de la única ventana

El comando de §10.6.6 se conserva como registro histórico del diseño. El
comando **efectivo** de la ventana autorizada añade las bases públicas
reales, porque el CLI **no** cambia de base por sí solo en modo público (los
defaults siguen siendo `127.0.0.1`), y fija el destino durable fuera de Git:

```powershell
$runId = 'exp-v2-ventana-1-20261112a'
$runDir = "C:\proyectos\binance-futures-data\$runId"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
python scripts/research_pilot.py `
  --mode public --activar-publico `
  --run-id $runId `
  --out-dir $runDir `
  --status-file (Join-Path $runDir 'estado.json') `
  --duration-seconds 3600 --settle-seconds 4200 `
  --cycle-seconds 300 --selection-seconds 300 --decision-delay-seconds 5 `
  --max-symbols 20 --max-candidates 12 --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 `
  --max-data-age-ms 5000 --max-observations 20000 `
  --max-bytes 134217728 --max-messages 5000000 `
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 `
  --max-ws-reconnects 20 --tick-ms 500 `
  --funding-source exchange `
  --funding-method observed-settlements `
  --funding-wait-seconds 32400 `
  --funding-wait-max-queries 3 `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com `
  --ws-market-base wss://fstream.binance.com
```

> ⚠ **RECTIFICADO (2026-11-12, §10.9).** Las dos últimas líneas de este
> comando son **incorrectas** y fueron el error de configuración de la ventana
> ejecutada: la base correcta lleva la categoría (`/public` para el feed de
> libro y `/market` para el de flujo). Con la raíz sin categoría el piloto se
> suscribió a la **URL antigua**, retirada por el venue el 2026-04-23. El
> comando corregido y su evidencia están en §10.9. Este bloque se conserva tal
> cual porque es el registro del comando realmente ejecutado; no se reescribe
> como si hubiera sido correcto.

La configuración, los topes y la vía **no cambian** respecto de §10.6: solo se
declaran las bases públicas que el modo público exige y la ruta durable de la
evidencia. `--budget-only` con este comando efectivo se revalida antes de
lanzar y su salida se conserva junto al SHA real de ejecución. El dataset, los
logs y los derivados voluminosos quedan fuera de Git; al cierre solo se
publican manifiesto, hashes, evidencia compacta y documentación.

#### 10.7.3 Reglas de ejecución y cierre

- Una sola corrida, un solo `run_id` y un solo presupuesto acumulado: captura,
  resolución y espera contable comparten cupos; la espera no devuelve cupos ni
  crea otra corrida.
- Antes de abrir mercado se comunican la URL exacta del monitor, el `run_id`,
  el directorio de evidencia, la duración máxima total (40 200 s) y el comando
  efectivo. La stdout, la stderr y el exit code reales se persisten.
- Si aparece un bloqueo material que exija cambiar regla, duración máxima o
  presupuesto, se detiene la corrida antes de abrir mercado y se explica.
- Si la corrida falla, se registra la causa y se conserva lo obtenido: no se
  relanza, no se crea otro `run_id` y no se amplían plazos ni cupos.
- El cierre se reconstruye **desde los registros persistidos** y se informa en
  tres capas: (1) funcionamiento técnico, (2) calidad y suficiencia de los
  datos, (3) resultado económico exploratorio. `INSUFICIENTE` es un resultado
  válido y no autoriza otra ventana.
- Una ejecución simulada no acredita ejecuciones reales ni rentabilidad
  generalizable. La cobertura sigue limitada a PERPETUAL/TRADING/USDT; los
  futuros con vencimiento y GARCH quedan fuera de alcance.

### 10.8 Resultado de la ventana única del 2026-11-12 (ejecutada, INSUFICIENTE)

La ventana única autorizada por la vía A se ejecutó **una sola vez** el
2026-11-12 y quedó **INSUFICIENTE en la capa de datos**. Informe completo en
tres capas:
[INFORRE-CIERRE](evidence/exp-v2-ventana-1-20261112a/INFORRE-CIERRE.md).

- **Identidad:** `run_id exp-v2-ventana-1-20261112a`; SHA de ejecución
  `4b83498def6ae303795d50b2d8fe5276159312e5` (local == remoto); directorio
  `C:\proyectos\binance-futures-data\exp-v2-ventana-1-20261112a` (fuera de
  Git); monitor en
  `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-1-20261112a`.
- **Presupuesto:** `--budget-only` con el comando efectivo → `cabe_en_limites:
  true` (13/13). Real: 24 peticiones HTTP, 0 fallos, 0 reintentos, peso
  reservado 492/5000, 53 100 224 B de 134 217 728 B.
- **Funcionamiento técnico:** terminación por la ruta de éxito del CLI
  (`phase=fin`, `stop_reason=duracion`, stderr vacío) tras 3605.431 s. El
  `settle` y la `espera_contable` no se abrieron porque su disparador es la
  existencia de trabajo pendiente y no hubo observaciones aptas. El exit code
  numérico no quedó persistido por un defecto del envoltorio de supervisión;
  se documenta la ruta de terminación, no un código observado.
- **Calidad y suficiencia:** 232 observaciones, **0 aptas**, 232 descartadas
  (`sin_flujo` 232, `dato_obsoleto_libro` 3); cobertura de flujo 0/232;
  `research_flow_10s/1m` con 0 filas frente a 1200 filas de libro. Causa raíz
  aislada: el feed `/market` (`aggTrade`) abierto una hora con `messages=0`,
  `errors=0`, `last_error=null` y sin reconexiones, en paralelo a `/public`
  con 467 764 frames. Causa raíz final **UNKNOWN**: aislarla exigiría tráfico
  público adicional, que no se abrió.
- **Resultado económico exploratorio:** **vacío, no en cero**. 0 entradas, 0
  salidas, 0 posiciones abiertas, 0 operaciones COMPLETO/CONDICIONADO/UNKNOWN,
  comparación de roles `INSUFICIENTE`. La vía A **no llegó a ejercitarse** en
  su parte esencial (espera contable, liquidaciones observadas, neto
  completo vs. condicionado).
- **Consecuencias:** `INSUFICIENTE` es un resultado válido y **no autoriza otra
  ventana**. No se relanzó, no se creó otro `run_id`, no se ampliaron plazos ni
  cupos y no se modificó código ni configuración durante la captura. El
  bloqueo que queda abierto es de datos (ausencia de flujo), y su resolución
  es condición previa para que una ventana futura pueda producir embudo; ver
  `docs/TASK_QUEUE.md`.

> ⚠ **RECTIFICADO (2026-11-12, §10.9).** El diagnóstico de esta sección
> queda ampliado: la configuración ejecutada **no usaba las URLs vigentes**
> (raíz antigua en lugar de `/public` y `/market`), lo que constituye una
> incompatibilidad verificable con la arquitectura documentada. El exit code
> histórico sigue **UNKNOWN**. Detalle:
> [RECTIFICACION-20261112](evidence/exp-v2-ventana-1-20261112a/RECTIFICACION-20261112.md).

### 10.9 Rectificación de las rutas WS y del envoltorio de salida (2026-11-12)

**10.9.1 Qué se corrigió.** La configuración persistida de la ventana
(`ws_public_base = ws_market_base = wss://fstream.binance.com`) era
incompatible con la arquitectura vigente: `build_stream_url()` añadía
`/stream?streams=…` a la base, de modo que **ambas** conexiones usaron la
**URL antigua**, retirada por el venue el 2026-04-23 (cinco meses antes de la
ventana). Documentación oficial consultada el 2026-11-12: aviso de rutas
(<https://www.binance.com/en/support/announcement/detail/ebf9b0aa9eca4ff3804eef6fb09ba32a>)
y registro de cambios
(<https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Important-WebSocket-Change-Notice>):
`/public` sirve libro de alta frecuencia (`depth`, `bookTicker`), `/market`
sirve datos de mercado (`aggTrade`, `markPrice`, `kline`, `ticker`), las URLs
antiguas se retiran el 2026-04-23 y las suscripciones combinadas deben usar el
modo `stream` (`?streams=`).

Precedente del propio repo: la captura pública `public-pilot-1h-20261106a`
usó `/public` y `/market` y recibió **55 265** mensajes de `aggTrade` y 6 391
filas de flujo, con 168 observaciones aptas de 216. La ventana del 2026-11-12
usó la raíz antigua y recibió **0** mensajes de `aggTrade` y 0 filas de flujo.
La relación con el silencio es una **hipótesis fuerte** (documentada y
coherente con ambas observaciones), **no una causalidad pública demostrada**:
no se abrió ningún socket para comparar ambas formas de URL y no se atribuye
el fallo al venue. Evidencia completa:
[RECTIFICACION-20261112](evidence/exp-v2-ventana-1-20261112a/RECTIFICACION-20261112.md).

**10.9.2 Comandos ejecutados antes frente a los corregidos.**

| | Ejecutado (2026-11-12) | Corregido |
|---|---|---|
| Libro | `wss://fstream.binance.com/stream?streams=…@depth20@100ms` (URL antigua) | `wss://fstream.binance.com/public/stream?streams=…@depth20@100ms` |
| Flujo | `wss://fstream.binance.com/stream?streams=…@aggTrade` (URL antigua) | `wss://fstream.binance.com/market/stream?streams=…@aggTrade` |
| Base CLI | `--ws-public-base wss://fstream.binance.com` / `--ws-market-base wss://fstream.binance.com` | `--ws-public-base wss://fstream.binance.com/public` / `--ws-market-base wss://fstream.binance.com/market` |

**10.9.3 Comando efectivo corregido** (idéntico salvo las dos bases; topes,
vía, presupuesto y duración **no cambian**):

```powershell
python scripts/run_pilot_window.py `
  --out-dir C:\proyectos\binance-futures-data\<run_id> `
  --mode public --activar-publico `
  --run-id <run_id> `
  --status-file C:\proyectos\binance-futures-data\<run_id>\estado.json `
  --duration-seconds 3600 --settle-seconds 4200 `
  --cycle-seconds 300 --selection-seconds 300 --decision-delay-seconds 5 `
  --max-symbols 20 --max-candidates 12 --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 `
  --max-data-age-ms 5000 --max-observations 20000 `
  --max-bytes 134217728 --max-messages 5000000 `
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 `
  --max-ws-reconnects 20 --tick-ms 500 `
  --funding-source exchange `
  --funding-method observed-settlements `
  --funding-wait-seconds 32400 `
  --funding-wait-max-queries 3 `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com/public `
  --ws-market-base wss://fstream.binance.com/market
```

El envoltorio `scripts/run_pilot_window.py` espera la finalización real del
proceso, **lee** el código de salida (`Popen.wait()`) y persiste `stdout.log`,
`stderr.log`, `exit_code.txt` y `launcher.json`. El código **nunca** se
infiere de `phase=fin`, del stdout ni de un stderr vacío. En modo predeterminado
**propaga el directorio**: el piloto recibe el mismo `--out-dir` que el lanzador
(§10.10.1), de modo que logs y artefactos comparten directorio.

**10.9.4 Verificación local (sin mercado público).** `--budget-only` con el
comando corregido: `cabe_en_limites: true` (13/13), con los mismos números
que la ventana ejecutada (1334/2000 intentos con reservas, 3752/5000 peso,
110/500 funding 5 min, 52 043 648 B reservados): la corrección de rutas no
altera el presupuesto. Pruebas del contrato de rutas (A–F) y del envoltorio
(salidas 0 y no cero): `tests/test_pilot_ws_rutas.py`,
`tests/test_pilot_launcher_exit_code.py`.

**10.9.5 Lo que sigue sin comprobarse.** Que `/market/stream?streams=…@aggTrade`
reciba frames contra el venue real: requiere una comprobación pública
autorizada, que **no se ha ejecutado** (comando preparado en §10.10).
La vía A sigue sin ejercitarse. El exit code histórico permanece **UNKNOWN**.

### 10.10 Dos defectos corregidos y comprobación pública preparada (2026-11-12)

**10.10.1 Directorio del lanzador (corregido).** El envoltorio consumía
`--out-dir` para los logs pero no lo reenviaba al piloto, que acababa usando su
directorio por defecto. Ahora: en modo predeterminado el piloto recibe el
mismo `--out-dir` (logs y artefactos en el mismo sitio; un `--out-dir` del
hijo distinto → error explícito por directorios contradictorios; el mismo
directorio repetido no es ambiguo y se propaga una sola vez); en modo comando
explícito (tras `--`) los argumentos del hijo se respetan tal cual y **no** se
le inyecta ninguna opción de `research_pilot.py`. La captura del código real
con `Popen.wait()` no cambia.

**10.10.2 Validación exacta de bases WS (corregida).**
`normalizar_base_ws()` aceptaba rutas con prefijos (`…/otra/market`) y en
mayúsculas (`…/MARKET`), y las conservaba en la URL efectiva pese a declarar
validación estricta. Contrato vigente: raíz sin ruta → se añade la categoría
del feed; ruta **exacta** `/public` o `/market` (barra final opcional) → se
conserva solo si corresponde al feed; se rechazan prefijos o segmentos
adicionales, mayúsculas, categorías cruzadas, `/stream` preincluido, query,
fragmento y credenciales. En modo público se exige `wss` y el host
`fstream.binance.com`. El modo local (`ws` + loopback), el nombre `aggTrade`
y la suscripción por URL en modo `stream` se conservan. La validación ocurre
antes de abrir conexiones, con los helpers existentes.

**10.10.3 Comprobación pública de recepción — PREPARADA, NO EJECUTADA.**
`scripts/diagnostico_ws_recepcion.py` reutiliza el transporte productivo
(`StreamFeed`, `build_stream_url`) y los motores (`BookEngine`, `FlowEngine`),
y distingue la escalera de evidencia: conexión, frames de datos, frames de
control, eventos válidos y eventos procesados. Sin REST, sin órdenes, sin
dataset de investigación (solo `diagnostico.json` compacto). Comando exacto en
`docs/TASK_QUEUE.md` (NEXT_TASKS 1). Criterios **PASS / INSUFICIENTE / FAIL**
y códigos de salida (0 / 10 / 11) están en el propio script. En este bloque
**no se abrió ningún socket público**; la verificación fue solo en loopback
(`tests/test_diagnostico_ws_recepcion.py`).

### 10.11 Comprobación pública de recepción ejecutada — PASS (2026-11-12)

Ejecutada **una sola vez** con autorización humana acotada al alcance de
recepción (`diag-ws-recepcion-20261112a`, SHA de ejecución
`37b779c456c5aed234171bbb0fe3421b979bb150`, local == remoto). Comando efectivo
y evidencia completa en
[INFORRE](../evidence/diag-ws-recepcion-20261112a/INFORRE.md); artefactos
publicados en `docs/evidence/diag-ws-recepcion-20261112a/`.

**URLs efectivas.** Flujo: `wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade`;
libro: `wss://fstream.binance.com/public/stream?streams=btcusdt@depth20@100ms`.
Suscripción por URL en modo `stream`, símbolo en minúsculas, `aggTrade` intacto.

**Resultado por feed.** Trades `/market`: 1 conexión, 0 reconexiones, 0 errores,
**773 frames de datos, 773 eventos válidos, 773 procesados por `FlowEngine`**.
Libro `/public`: 1 conexión, 0 reconexiones, 0 errores, **552 frames de datos,
552 eventos válidos, 552 procesados por `BookEngine`**. Cero frames de control
(un ACK no acreditó flujo) y cero frames inválidos. Dos aperturas iniciales en
total.

**Límites y cierre.** 1 325 frames ≪ 200 000 (`limite_mensajes_alcanzado:
false`); 2 360 B ≪ 1 MB; sin REST, sin órdenes y sin dataset de investigación
(el directorio de corrida, 3.41 KB, solo contiene los cinco artefactos).
Código de salida observado **0**, leído de `Popen.wait()` (`exit_code.txt` y
`launcher.json.returncode`), `stderr.log` vacío; proceso terminado,
`connected_now: false` y sin proceso propio vivo.

> ⚠ **RECTIFICADO (2026-11-12, §10.12.1).** El plazo global de 60 s **NO
> CUMPLE**: el proceso duró **65.034 s** (diagnóstico) y **65.557 s**
> (lanzador). La configuración de 60 s **no es una medición independiente** de
> la duración efectiva de observación; el cierre de sockets es **compatible**
> con el exceso pero **no lo convierte en cumplimiento** (el artefacto no
> separa observación de cierre). El veredicto vigente es **PASS limitado a
> recepción y procesamiento, con el plazo global NO CUMPLE**. La afirmación
> previa de cumplimiento global sin reservas queda **retirada**. Los
> artefactos y sus hashes se conservan intactos, incluido el `PASS` emitido
> por el script. Rectificación:
> [RECTIFICACION-20261112](../evidence/diag-ws-recepcion-20261112a/RECTIFICACION-20261112.md).

**Veredicto:** **PASS en recepción y procesamiento** (773 eventos de flujo y
552 de libro válidos y procesados), contrastado con los artefactos y no solo
con la salida del script; **NO CUMPLE** el plazo global de 60 s; **NO EVALUADA**
la economía.

**Lo que cambia y lo que no.** El bloqueo material de datos que vació el
embudo de `exp-v2-ventana-1-20261112a` **queda resuelto para el transporte**:
con la ruta por categoría vigente hay flujo real. En cambio: (a) la **causa
raíz histórica sigue `UNKNOWN`** — no se abrió la URL antigua contra el
venue, así que su relación con el silencio anterior es un indicio adicional y
no una prueba; (b) el **exit code histórico** de esa ventana sigue **UNKNOWN**
(su `exit_code.txt` continúa con 0 bytes, sin rellenar); (c) el **resultado
económico no se evalúa**: no hubo señales, decisiones, operaciones, órdenes ni
cuentas, y 60 s de un símbolo no acreditan cobertura de universo, ciclos,
horizontes ni estabilidad prolongada. Este diagnóstico **no habilita** ninguna
ventana operativa: esa requiere autorización humana nueva y explícita. La vía A
(espera contable, liquidaciones observadas, neto COMPLETO vs. CONDICIONADO)
sigue sin ejercitarse.

### 10.12 Rectificación del veredicto temporal y propuesta de una ventana única (2026-11-12)

#### 10.12.1 Rectificación del veredicto del diagnóstico (documental)

Se retira de las conclusiones vigentes la afirmación de **cumplimiento global
sin reservas** del diagnóstico de recepción. Veredicto vigente, punto por
punto: recepción y procesamiento **PASS** (773 eventos de flujo y 552 de libro,
válidos y procesados por sus motores); mensajes, almacenamiento, conexiones y
errores **dentro de los límites observados**; código de salida **0 acreditado**;
**plazo global de 60 s NO CUMPLE** (65.034 s el diagnóstico, 65.557 s el
lanzador); la configuración de 60 s **no es una medición independiente** de la
duración efectiva de observación; el cierre de sockets es **compatible** con el
exceso pero **no lo convierte en cumplimiento**; economía **NO EVALUADA**;
causa raíz y exit code históricos **UNKNOWN**.

No se repite el diagnóstico, no se abre la URL antigua y **no se toca ningún
artefacto ni hash**: el `PASS` emitido por el script se conserva como
antecedente. Detalle:
[RECTIFICACION-20261112](../evidence/diag-ws-recepcion-20261112a/RECTIFICACION-20261112.md).

#### 10.12.2 Propuesta de UNA ventana por la vía A — PREPARADA, NO EJECUTADA

Detalle completo en
[PROPUESTA](../evidence/exp-v2-ventana-2-20261112a-propuesta/PROPUESTA.md).
En este bloque **no se abrió mercado**: solo `--budget-only` (sin red).

- **Identidad reservada:** `run_id exp-v2-ventana-2-20261112a` (nuevo, nunca
  ejecutado) y directorio
  `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a` (fuera de
  Git, **no creado todavía**). No reutiliza ninguna corrida anterior ni
  presenta su presupuesto como renovación.
- **Configuración congelada:** captura 3 600 s, settle 4 200 s, espera
  contable ≤ 32 400 s con funding real `observed-settlements` (≤ 3 consultas
  por símbolo), selección y decisión cada 300 s, 12 candidatos + 8
  comparadores (máximo conjunto 20), frescura 5 000 ms, stop 0,5 %, notional
  1 000 USDT, horizonte 60 min, capacidad global 1 y los mismos techos HTTP,
  peso, reintentos, WS y almacenamiento. Rutas WS corregidas `/public` y
  `/market`.
- **Contrato temporal:** captura (3 600 s) → resolución de resultados (settle,
  ≤ 4 200 s) → espera contable (≤ 32 400 s) → cierre y persistencia final
  (margen **propuesto de 300 s**, no autorizado). Máximo del CLI 40 200 s;
  **total máximo propuesto 40 500 s (11 h 15 min)**. El margen no amplía
  captura, exposición ni consultas; si al cumplirse el máximo del CLI el
  proceso siguiera vivo, es un incidente material a registrar. Este máximo
  **dejó de ser solo declarativo el 2026-11-12**: ver §10.13.
- **Presupuesto (`--budget-only`, sin mercado):** `cabe_en_limites: true`
  (13/13); intentos 1 004 base / **1 334 con reservas** de 2 000; peso 1 472
  base / **3 752 con reservas** de 5 000; almacenamiento previsto 4 696 872 B
  y **reservado máximo 52 043 648 B** de 134 217 728 B; funding **110
  intentos reservados** con máximo concentrado 110/500 por 5 min; WS con **2
  conexiones simultáneas**, 2 aperturas iniciales, 11 rotaciones (22
  aperturas) y **46 aperturas acumuladas** como máximo, pico de 40 streams.
  Los pesos son **estimaciones de la política, no consumo medido por
  Binance**.
- **Monitor:** `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-2-20261112a`.
- **Qué deberá evaluar (fijado antes de ejecutar):** cadena completa selección
  → datos aptos → señal/abstención → entrada simulada → gestión/salida;
  identidad y causalidad verificables; capacidad global respetada; costes y
  funding conocidos o `UNKNOWN`; netos `COMPLETO` separados de
  `CONDICIONADO_SIN_FUNDING_COMPLETO`; denominadores por rol y por decisión
  (descartes y rechazos por capacidad incluidos); resultado económico
  reconstruible desde lo persistido. **Cero operaciones o cobertura
  insuficiente son resultados válidos**: la ausencia de operaciones no se
  presenta como P&L cero. El monitor presenta artefactos; las operaciones
  reconstruidas son simulaciones, no órdenes en vivo.
- **Bloqueos que quedan:** falta autorización humana explícita (incluido el
  margen de cierre); causa raíz y exit code históricos `UNKNOWN`; economía
  aún sin evaluar; sin garantía de datos aptos (el precedente
  `public-pilot-1h-20261106a` dio 168 aptas de 216; la ventana anterior, 0 por
  la URL antigua); la espera contable puede terminar en `UNKNOWN`; la
  recepción está acreditada para 60 s, no para 1 h con 11 rotaciones; la
  cobertura sigue limitada a PERPETUAL/TRADING/USDT. On-chain, indicadores
  nuevos, GARCH, patrones nuevos, futuros con vencimiento y cambios de
  dashboard quedan **fuera de esta ventana**.

### 10.13 Control temporal efectivo del lanzador (2026-11-12, local, sin mercado)

El defecto era real: `scripts/run_pilot_window.py` esperaba con `proc.wait()`
**sin timeout**, de modo que el máximo de 40 500 s **no existía como control**
—solo la duración propia del hijo acotaba la espera. Defecto reproducido con
un hijo local trivial que ignora la parada (esperó exactamente lo que el hijo
decidió durar, sin ninguna vía de acotarla): evidencia en
[ANTES](../evidence/lanzador-control-temporal/ANTES/).

**Implementación** (se reutiliza el lanzador; no se crea otro supervisor,
servicio ni planificador): dos opciones **propias del lanzador**, que **no
llegan al parser del piloto**:

| Opción | Significado | Valor de la ventana |
|---|---|---|
| `--work-timeout-seconds` | plazo de **trabajo** del hijo | **40 200** |
| `--shutdown-grace-seconds` | margen **exclusivo** de parada, cierre y persistencia | **300** |

Total máximo efectivo **40 500 s**. Reloj **monotónico** y deadlines
**absolutos**: enviar la señal o esperar otra vez **no reinicia** el
presupuesto temporal. Al vencer el plazo de trabajo se **solicita la parada
limpia** por el mecanismo existente del piloto; dentro del margen se reserva
un tranche final (5 s con margen de 300 s) para la **terminación forzada** y
la **persistencia**, de modo que el proceso **no se mata en el último
instante** del máximo total. Si el hijo no termina, se fuerza la terminación
**solo de recursos propios** (`taskkill /F /T /PID` sobre el árbol propio del
hijo en Windows; nunca búsquedas globales). El margen **no autoriza**
selecciones, entradas, consultas ni ampliación de exposición: tras la parada
el piloto no inicia trabajo nuevo (una petición **ya en curso** puede
terminar; una **adquisición nueva** no se arranca) y conserva los pendientes
**con su causa** (`senal_externa`).

**Windows (plataforma real del proyecto):** el hijo se lanza con
`CREATE_NEW_PROCESS_GROUP` y la parada limpia se entrega con
`CTRL_BREAK_EVENT` (→ SIGBREAK, que el piloto ya registraba como parada
limpia). `terminate()` en Windows es `TerminateProcess` (mata sin dar
oportunidad de persistir) y **no** se usa como parada limpia. Se comprobó
también que un hijo bloqueado en un `sleep` largo puede no atender la señal
hasta el siguiente retorno al intérprete: por eso el margen existe y por eso
la terminación forzada está acotada.

**Códigos y resultados (sin ambigüedad):** `exit_code.txt` conserva el
**código real del hijo** (no observado → `UNKNOWN`, nunca inventado). El
veredicto del lanzador se publica **por separado** en `estado_lanzador.json`
y en los campos nuevos de `launcher.json` (`resultado_lanzador`,
`causa_terminacion`, `cumplimiento_normal`, `codigo_lanzador`,
`codigo_hijo_observado`, `parada_solicitada`, `terminacion_forzada`,
`limpieza`, límites y tiempos). Plazo vencido con parada limpia → lanzador
**124**; con terminación forzada → **125**. Un hijo que devuelve **0** tras
el plazo **no** es cumplimiento normal. Distinciones al cerrar: **cierre
normal** (terminó por su cuenta dentro del plazo) · **timeout de trabajo** (se
agotaron los 40 200 s) · **cierre forzado** (`terminacion_forzada: true`) ·
**exceso del máximo total** (`exceso_maximo_total_s` > 0, incidente material).
Seguir vivo durante el margen de cierre **no** es, por sí mismo, un
incumplimiento.

**Pruebas locales (sin red, sin mercado):** `tests/test_pilot_launcher_temporal.py`
— A normal 0 · B normal no cero · C plazo vencido con parada limpia efectiva ·
D hijo que ignora la parada y exige terminación forzada · E hijo que devuelve
0 tras el timeout (el incumplimiento no desaparece) · F proceso ajeno conservado
· G argumentos y directorios compatibles en ambos modos (las opciones del
lanzador no llegan al piloto; tras `--` los argumentos son del hijo) · H
evidencia persistida y ausencia de procesos propios residuales; más el lado
del piloto (la parada impide iniciar trabajo nuevo y conserva los pendientes
con su causa). **14 passed**. Regresiones directamente afectadas: lanzador y
rutas WS 50 passed, `test_research_pilot.py` 45 passed, operativo/CLI 9 passed.
Cero pruebas públicas de mercado.

**Presupuesto revalidado** con la forma final del comando (ya con las dos
opciones del lanzador), `--budget-only` **sin red**: salida real **0**,
`stderr` vacío, gate **13/13**, cifras idénticas.

**Lo que este bloque NO hace:** no abre mercado, no ejecuta la ventana, no
toca órdenes, claves, cuentas, datasets, DBs, dashboard ni el servicio 8792.
Los 300 s siguen siendo **margen propuesto sin autorización**.

### 10.14 Dos defectos materiales del lanzador corregidos (2026-11-13, local, sin mercado)

El control temporal de §10.13 era efectivo en lo esencial, pero tenía **dos
defectos materiales**, reproducidos contra el código publicado (`d53d8ad`) y
corregidos en este bloque. Detalle y evidencia:
[RESUMEN](../evidence/lanzador-control-temporal/DEFECTOS/RESUMEN.md).

#### 10.14.1 Las esperas de terminación podían superar el plazo global

`_terminar_forzado()` concedía **30 s fijos** a `taskkill` y después
`_esperar_hijo()` concedía **10 s fijos** al reap del hijo; además, la ruta de
interrupción del operador esperaba **30 s** fijos. Ninguna de esas esperas se
descontaba del plazo global. Caso de referencia (trabajo 1 s, margen 4 s,
total 5 s, `taskkill` que no responde, hijo que no confirma su salida): la
ruta podía acumular **45 s** (3 s hasta el deadline de forzada + 30 + 10 +
reserva de persistencia) frente a un plazo global de 5 s.

**Corrección mínima:** un único reloj monotónico y un único deadline global.
**Toda** espera y llamada de terminación se acota al **restante** de ese
deadline; no queda ninguna espera fija. El margen de cierre se reparte de
forma explícita: reserva de **persistencia** (25 % del margen, máximo 5 s),
reserva de **reap** (máximo 2 s, para que el hijo confirme su salida tras la
terminación forzada) y el resto para la parada limpia y la terminación
forzada. Se añade un **límite duro de limpieza** (`deadline_limpieza`): pasado
ese instante el lanzador deja de esperar y publica el exceso.

Resultado en el mismo caso de referencia: `taskkill` recibe **1,5 s** (el
restante), el reap **0 s** y el acumulado con persistencia queda en **5,0 s**
= el plazo global (antes: 45 s).

#### 10.14.2 El lanzador acreditaba recursos cerrados sin evidencia

Con el código del hijo **no observado** (`exit_code.txt: UNKNOWN`), el estado
publicado seguía declarando `proceso_hijo_terminado: true` —porque solo se
había *intentado* matar— y `alimentaciones_cerradas: true` de forma
incondicional, sin que el lanzador pudiera certificar los sockets del hijo.

**Corrección mínima:** el bloque `limpieza` se sustituye por un bloque
`cierre` que separa explícitamente:

| Campo | Significado |
|---|---|
| `parada_solicitada` / `parada_mecanismo` | lo **solicitado** (se envió la señal) |
| `terminacion_forzada_solicitada` / `terminacion_forzada_mecanismo` | lo **solicitado** (se pidió la terminación forzada) |
| `terminacion_hijo_observada` | lo **observado**: solo `true` si `Popen.wait()` devolvió el código |
| `codigo_salida_observado` / `codigo_salida_estado` | el código real, o `UNKNOWN` si no se pudo observar |
| `alimentaciones_lanzador_cerradas` | lo **propio** del lanzador (sus tuberías), acreditado por el propio cierre |
| `recursos_hijo` | **UNKNOWN**: el lanzador genérico no puede certificar los sockets ni el teardown del hijo |
| `evidencia_piloto` | estado del piloto como **evidencia diferenciada**: se lista, no se interpreta ni se certifica |

#### 10.14.3 Duración medida, exceso honesto y alcance real del control

La duración publicada **incluye la persistencia**: `duracion_total_s` se mide
después de escribir `exit_code.txt` y `launcher.json`, y `cierre.json`
publica la medición definitiva (después del veredicto). Si la persistencia
lleva el reloj más allá del plazo global, el exceso se **publica**
(`exceso_maximo_total_s > 0`, `incumplimiento_plazo_global: true`) y el
lanzador devuelve **126** (`plazo_global_excedido`): no se oculta con
tolerancias ni reiniciando el reloj.

**Alcance real del control:** acota el tiempo que el lanzador **espera y
concede**; **no** es una garantía del sistema operativo. Si una llamada del
sistema ignora su propio timeout, el exceso se **mide** y se publica
(`excedio_la_concesion: true`) como incumplimiento. Se conservan la parada
limpia de Windows (`CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT`) y la
terminación forzada **solo sobre el árbol propio** (`taskkill /F /T /PID`
sobre el PID del hijo; nunca búsquedas globales).

**Pruebas (Windows, sin red, sin mercado):**
`tests/test_pilot_launcher_temporal.py` → **19 passed** (14 previos + 5
nuevos: `taskkill` que agota su espera, hijo cuya salida no puede confirmarse,
persistencia que consume parte de la reserva, exceso temporal registrado
honestamente y ninguna espera por encima del restante); se conservan fin
normal, salida no cero, parada limpia, terminación forzada y proceso ajeno
preservado. Regresiones directamente afectadas: lanzador 50,
`test_research_pilot.py` 45, operativo/CLI 9 → **123 passed** en el conjunto
afectado. Cero pruebas públicas de mercado.

**Ejecución real en Windows (casos cortos):** normal → 0 (0,056 s, sin
exceso); plazo + parada limpia → **124** (1,074 s); plazo + terminación
forzada → **125** (2,717 s); en los tres, `exceso_maximo_total_s: 0,0`,
`recursos_hijo: UNKNOWN` y terminación del hijo **observada** (taskkill la
confirma en Windows).

**Lo que este bloque NO hace:** no abre Binance, no ejecuta el diagnóstico
público ni la ventana operativa; no cambia estrategia, selección, funding,
contabilidad, exposición, presupuestos económicos ni la duración propuesta
(40 200 s + 300 s); no toca `opencode.json`, archivos ajenos, datasets, DBs,
el dashboard de 3020 ni el servicio 8792; no añade servicios, gestores,
dependencias ni nuevas capas de infraestructura.

### 10.15 Ventana `exp-v2-ventana-2-20261112a` — EJECUTADA y cerrada (2026-11-14)

**Autorización humana del 2026-11-14:** «UNA SOLA VENTANA DEL EXPERIMENTO
OPERATIVO V2» — cubre adquisición pública, simulación operativa, resolución de
resultados, espera contable y cierre. **No** autoriza órdenes reales, cuentas,
claves privadas, fondos, nuevas ventanas ni relanzamientos.

Se ejecutó **una sola vez** el comando literal de
[PROPUESTA](../evidence/exp-v2-ventana-2-20261112a-propuesta/PROPUESTA.md) §5
(con `--work-timeout-seconds 40200 --shutdown-grace-seconds 300`, sin
`--budget-only`), desde `git_head ab97b02203cb5ac49c04bf2c9a8472f181b74a49`
(código del lanzador `b0fdb52…`), con el monitor de 3020 en **solo lectura**.
Detalle y evidencia:
[INFORME](../evidence/exp-v2-ventana-2-20261112a/INFORME.md).

#### 10.15.1 Cierre: dentro de plazo y acreditado por separado

| Artefacto | Contenido |
|---|---|
| `exit_code.txt` | **0** — código real del proceso **hijo** (`Popen.wait()`) |
| `estado_lanzador.json` | `resultado: normal`, `causa_terminacion: terminacion_natural`, `cumplimiento_normal: true`, `codigo_lanzador: 0`, `terminacion_hijo_observada: true`, `codigo_salida_estado: observado`, `recursos_hijo: UNKNOWN`, `exceso_maximo_total_s: 0,0`, `incumplimiento_plazo_global: false` |
| `cierre.json` (definitivo) | igual, con `duracion_total_s: 7803,176` y `fin_iso_utc: 2026-11-14T04:35:09` |

Duración total **7 803,176 s** (2 h 10 min) frente al máximo autorizado de
**40 500 s** → 19,3 %. Sin parada solicitada ni terminación forzada. El
**código 0 del hijo coincide** con el veredicto del lanzador, pero **no se
presenta como cumplimiento normal por inercia**: aquí `cumplimiento_normal` es
`true` porque no hubo timeout y no hubo exceso. Los sockets del hijo siguen
**UNKNOWN**; el estado del piloto (`feeds_closed: true`) se conserva como
**evidencia diferenciada**.

Fases observadas: captura **3 600 s** (12/12 ciclos, 0 saltados) → settle
**4 200 s** (537/537 resultados resueltos, 0 pendientes, 0 no evaluables) →
**espera contable NO abierta** (`inicio_ms: null`; no había posición abierta,
0 consultas de funding) → cierre y persistencia.

#### 10.15.2 Cobertura: el bloqueo de datos queda resuelto

| Rol | Seleccionadas | Observadas | Sin observación | Aptas | Descartadas |
|---|---|---|---|---|---|
| `candidate` | 144 | 138 | 6 | 131 | 7 |
| `comparator` | 96 | 81 | 15 | 48 | 33 |
| **Total** | **240** | **219** | **21** | **179 (81,7 %)** | **40** |

Cobertura de ciclos con ambos roles aptos: **12/12** (`1,0`). Motivos de
descarte: `dato_obsoleto_flujo` 29, `flujo_ventana_incompleta` 13,
`dato_obsoleto_libro` 1. Consumo: 740 intentos HTTP (0 reintentos) con peso
reservado 1 208/5 000; 22 conexiones WS de un techo de 46, 845 161 mensajes,
0 reconexiones, 0 errores; 6 183 860 B de almacenamiento de 134 217 728 B;
`ResearchRecorder` con 9 384 escrituras, 0 drops y 0 errores.

#### 10.15.3 Resultado económico: INSUFICIENTE por un defecto del borde de la consulta

179 señales con dirección (LONG 88 · SHORT 91) → **179 abstenciones
(`SIN_ENTRADA`)** → **0 entradas**, 0 rechazos de capacidad, 0 salidas, 0
posiciones abiertas. Neto **COMPLETO** `n = 0` y **CONDICIONADO** `n = 0`, todos
los campos `null` (**no** se convierte la ausencia en cero). La comparación
candidato/comparador queda **`INSUFICIENTE`** con motivo
`sin_operaciones_completas_*`: con cobertura de datos 12/12, lo que faltó fue
la **capa de ejecución**.

**Causa raíz (diagnosticada con el ledger HTTP persistido, sin re-ejecutar
nada):** el piloto pide la trayectoria 1 m con
`klines(startTime = decision_ms − 60 000)` y Binance filtra
`openTime >= startTime`. La última vela 1 m **plenamente cerrada en T** abre en
`floor(T/60000)*60000 − 60 000`, **anterior** a ese `startTime` cuando
`decision_ms` no está alineado al minuto. **Ninguna** de las 179 decisiones lo
estaba (0/179; el segundo del minuto fue 12, 13, 14, 15 o 19 porque la
decisión se toma en el corte + 5 s): la vela de referencia quedaba excluida en
los 179 casos y la primera vela devuelta **cerraba después de T**. Sin precio
de referencia conocido en T, la regla solo podía abstenerse. Código:
`scripts/research_pilot.py::_consultar_trayectoria_operativa` y
`scripts/research_operativo_adapter.py::_vela_plenamente_conocida_en`.

No es una ausencia de datos de mercado, ni un límite de presupuesto, ni la
capacidad compartida, ni una restricción del selector. **Defecto secundario de
etiquetado:** las abstenciones (`qty = 0`, `entry_px = null`,
`open_at_end = false`) llevan `neto_motivo` de "posición abierta", texto
genérico que describe una posición **inexistente** (el `neto_estado = UNKNOWN`
sí es correcto).

#### 10.15.4 Lo que este bloque NO hace

No corrige el defecto del borde de la consulta (es un **cambio de
metodología**: exige autorización humana explícita, un `run_id` nuevo y una
ventana nueva), no relanza ni reutiliza `exp-v2-ventana-2-20261112a`, no
amplía duración, exposición, consultas ni cupos, no toca estrategia, selección,
funding, contabilidad ni presupuestos económicos, no añade indicadores,
on-chain, GARCH, futuros con vencimiento ni infraestructura, no reconstruye el
frontend ni añade pantallas o servicios, y no toca `opencode.json`, archivos
ajenos, DBs canónicas ni el servicio 8792. El bloque **termina con el cierre
de esta única ventana**, aunque el resultado sea INSUFICIENTE.
