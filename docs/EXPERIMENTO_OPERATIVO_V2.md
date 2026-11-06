# Protocolo de experimento operativo v2 — research/universe-liquidez-v1

**Estado:** diseño de alcance cerrado y revisable. No se ejecuta. No hay órdenes reales, no hay conexión nueva a Binance, no hay infraestructura nueva, no hay cambios económicos productivos. Este documento actualiza y reemplaza el alcance de `docs/EXPERIMENTO_OPERATIVO_V1.md` (diseño de alcance v1); no se borra el v1, se conserva como referencia histórica.

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

**Regla candidata completa (para revisión, NO implementada, NO aprobada por documentarla):**

| Elemento | Valor / condición explícita |
|---|---|
| Información disponible al decidir | `side` (UP/DOWN) del selector en T, `move_24h_pct`, precio de libro `libro_mid` en T, cobertura y frescura (`disponibilidad.<= decision_ms + tolerancia`). Nada del futuro. |
| Condición de señal y dirección | Si `side == UP` → LONG; si `side == DOWN` → SHORT. Si `side` es None → SIN_ENTRADA. Solo si existe vela 1m plenamente conocida en T y su close opera a favor vs `entry_px` y stop no vulnerado (misma lógica de abstención que RULE-CAUSAL-V1). |
| Entrada y primera ejecución posterior causalmente posible | `entry_px` = close de la vela 1m plenamente conocida en T (precio conocido en T). Primera ejecución: fill al **open de la vela 1m siguiente** a la de señal (primera ejecución posterior causalmente posible; nunca el open pasado de la vela que confirmó la señal, nunca precio futuro). |
| Stop inicial y tratamiento de gaps | `stop_px = entry_px × (1 − stop_distance_pct)` para LONG; `entry_px × (1 + stop_distance_pct)` para SHORT. `stop_distance_pct = 0.5` (0,5 %). Gap: si el open de la vela siguiente cruza el stop, se sale al open de esa vela (primer precio disponible tras el gap, no al stop nominal); stop no vulnerable en T → SIN_ENTRADA. |
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
| WS conexiones | ≤20 | ≤60 | |
| WS mensajes | ≤5 000 000 | ≤15 000 000 | |
| WS reconexiones | ≤20 | ≤60 | |
| Almacenamiento | ≤128 MB | ≤384 MB | JSONL + SQLite + aux |
| Duración de captura y maduración | 1 h + 70 min settle | 5 h 30 min total | |
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
