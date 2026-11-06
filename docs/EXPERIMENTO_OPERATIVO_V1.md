# Protocolo de experimento operativo v1 — research/universe-liquidez-v1

## Precedencia y bloqueos antes de autorizar — 2026-11-06

Dirección canónica: [PRODUCT_GOAL](PRODUCT_GOAL.md). Esta propuesta fue entregada
en `6a10c307`; es diseño para revisión, no una regla aprobada ni un experimento
listo para lanzar. No reiniciar el inventario ni construir otro motor.

Para cerrar el diseño solo falta resolver lo que puede impedir una comprobación
económica válida:
- **Causalidad del fill:** una señal decidida al cierre no puede ejecutarse al
  open anterior de esa misma vela. Debe fijarse una ejecución posterior a la
  decisión y su disponibilidad, con precio/modelo acreditable; si los datos no
  lo permiten, el resultado operativo es UNKNOWN.
- **Misma regla en comparadores:** los comparadores actuales no tienen `side`
  UP/DOWN. Definir antes de capturar cómo evaluar la misma regla en ambos grupos
  sin usar el rol candidate/comparator para asignar dirección ni forzar entradas.
  Contar también abstenciones; no comparar operaciones con meros retornos.
- **Contrato operativo:** sustituir ejemplos por valores versionados de entrada,
  stop, tamaño/riesgo, horizonte, exposición y métrica con su denominador. Fijar
  criterios de decisión y tratamiento de costes/funding UNKNOWN antes de pedir
  autorización. No escogerlos por el resultado favorable de la captura anterior.
- **Adquisición y presupuesto:** comprobar que los datos previstos permiten
  reconstruir la regla completa, sus entradas, stops y salidas. El viejo piloto
  guardó precios por horizonte; repetirlo no garantiza precios suficientes para
  operar. Fijar calendario, comando, datos y presupuesto agregado, separando
  conexiones WS simultáneas, aperturas acumuladas, rotaciones y reconexiones.

No se reabren las capturas previas para completar 60m ni se declara rentabilidad
al añadir comisiones. La pregunta es si una regla causal puede aprovechar
movimientos extremos con expectativa neta y riesgo defendibles. La autonomía
operativa es el objetivo final; la autorización actual cubre diseño/revisión,
no adquisición, despliegue paper ni órdenes reales.

**Estado:** diseño de alcance y decisión. No se ejecuta. No hay órdenes reales, no hay conexión nueva a Binance, no hay infraestructura nueva, no hay cambios económicos productivos. Este documento es revisable antes de cualquier autorización de adquisición.

**Base:** `e624758a9de3d2f2f9ea77f659b0135d2808a1b6` (commit esperado). Analiza v4 como punto de partida. Dataset de referencia: `public-pilot-1h-20261106a` (una sola hora, 2026-11-06, 216 observaciones, 168 aptas, 504 resultados).

## 1. Cierre de la captura actual como exploratoria

La captura `public-pilot-1h-20261106a` y su análisis v4 demuestran, y solo demuestran, lo siguiente:

**Qué demuestra:**
- La autoselección (`research_selector`, `research-selector-v2`) emitió 240 selecciones (144 candidate + 96 comparator) en 12 ciclos; 216 observaciones se emitieron (136 candidate + 80 comparator), 168 aptas, 48 descartadas (38 comparadores por `dato_obsoleto_flujo`, 10 candidatos por diversos motivos), 24 selecciones sin observación.
- Descriptivamente, en los tres horizontes (5m/15m/60m) los candidatos mostraron retornos medios superiores a los comparadores (+0,33 pp, +0,92 pp, +3,23 pp), consistentes entre ponderación agrupada, por ciclo e igual por símbolo, y en UP y DOWN por separado. A 60m la mediana de candidatos (0,56 %) no supera la de comparadores (0,61 %).
- Asociación exploratoria débil-positiva entre flujo agresor neto / profundidad top-20 y retorno posterior (Pearson +0,037 / +0,112 / +0,144 en 5m/15m/60m).
- Sensibilidad por símbolo: AKEUSDT y JCTUSDT concentran parte de la diferencia positiva; la diferencia conserva signo al excluir cualquier símbolo.

**Qué NO demuestra:**
- No demuestra capacidad de entrada, salida o rentabilidad. `neto_estado=UNKNOWN` en los 504 resultados; sin costes, comisiones, funding, slippage ni fills acreditados.
- No demuestra que UP signifique comprar ni que DOWN signifique vender. Continuación y reversión son hipótesis distintas, no resueltas.
- No demuestra ventaja predictiva del selector; una media favorable sobre una sola hora no es evidencia de edge.
- Los retornos de tres horizontes sobre una misma observación no son independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son.

**Límites de cobertura, concentración, precios y costes:**
- Cobertura asimétrica: 126 aptas candidate vs 42 aptas comparator; 4 de 12 ciclos con un solo comparador apto. No se puede atribuir diferencia de retorno al selector ignorando esta desigualdad.
- Concentración en símbolos: AKEUSDT y JCTUSDT aportan gran parte de la diferencia.
- Precio: `libro_mid` (inicial) → `klines_apertura_1m` (posterior), proxy de fuentes mixtas con desfase por horizonte; no es mark-to-mid ni precio ejecutable.
- Costes: `neto_estado=UNKNOWN`; no existen comisiones, funding, slippage ni fills acreditados. No se presentan retornos brutos como ganancias simuladas retrospectivas.

## 2. Tabla de capacidades existentes (mapeo al objetivo operativo)

Se inspeccionan exclusivamente componentes ya disponibles: `scripts/research_selector.py` (selector), `src/microstructure_probe/paper_lab_engine.py` (motor de simulación/paper + regla de decisión), `src/microstructure_probe/backtest_offline.py` (motor de backtest mecánico), `src/microstructure_probe/engineering_session_service.py` (servicio de sesión). No se propone otro motor, supervisor, dashboard ni agente de IA.

| Capacidad | Existe | Probado funcionalmente | Evaluado económicamente | Observaciones |
|---|---:|---:|---:|---|
| Selección de candidatos (UP/DOWN, bounded set, ambos lados) | Sí (`select_candidates`, `ResearchPolicy`) | Sí (tests research_selector) | No | Selecciona para investigación, no para entrada. Sin rotación ni permanencia (diferidos). |
| Dirección LONG/SHORT | Parcial | No | No | Selector emite `side` UP/DOWN (dirección de movimiento, hipótesis). No hay regla que traduzca UP→LONG o DOWN→SHORT. |
| Condición de entrada | Sí (`RULE-CAUSAL-V1`, `_evaluate_signal_causal_v1`) | Sí (tests paper_lab_engine) | No | Señal usando solo prefijo conocido en T; nunca usa velas futuras, P&L ni comisiones como confirmación. Abstiene si no hay close conocido o stop vulnerado. |
| Momento y precio posible de fill | Sí (`step_forward`, `_apply_entry`, `_finalize_exit`) | Sí (tests paper_lab_engine) | No | Fill en open de vela conocida o al stop; exit en stop/horizonte/open_at_end. Nunca inventa fill ni salida. |
| Stop loss | Sí (`stop_px`, `stop_distance_pct`, `_admit_risk`) | Sí (tests paper_lab_engine) | No | Stop debe estar alejado de entry_px; admisión deniega stop no válido por dirección. |
| Salida y horizonte | Sí (`horizon_ms`, salida por stop/horizonte/open_at_end/manual) | Sí (tests paper_lab_engine) | No | `open_at_end` es marca, nunca salida ejecutada ni P&L realizado. |
| Costes y riesgo | Sí (`fee_bps`, `spread_bps`, `slippage_bps`, `notional_usdt`, `_gross_pnl`) | Sí (tests paper_lab_engine) | No | Funding ausente = UNKNOWN (nunca cero). `_admit_risk` valida notional/entry/stop/dirección estáticamente. |
| Trazabilidad de decisión | Sí (`decision_evidence`, `config_hash`, `input_hash`, `engine_version`, `session_to_dict`) | Sí (tests) | No | Cada decisión/ejecución tiene evidencia en T, regla versión y hashes. |

**Nota:** Una prueba técnica de RULE-CAUSAL-V1 o de `select_candidates` no es evidencia de ventaja económica. Ninguna de estas capacidades ha sido evaluada económicamente sobre datos reales con costes.

## 3. Hipótesis operativa única y comprobable

**Pregunta principal:** ¿Una regla previamente definida, aplicada a los candidatos autoseleccionados, produce resultados mejores que la misma regla aplicada a comparadores, bajo condiciones de ejecución y riesgo equivalentes?

**Regla existente revisada:** `RULE-CAUSAL-V1` (`_evaluate_signal_causal_v1`) existe y está probada funcionalmente, pero:
- Opera sobre `entry_px` y `stop_px` ya fijados en `PaperSessionConfig` (no los deriva del selector).
- No deriva dirección LONG/SHORT del `side` (UP/DOWN) del selector.
- No define tamaño de posición ni stop por volatilidad; los recibe como parámetros de config.
- **Vacío:** no existe una regla completa que parta del `side` del selector, fije dirección, entry, stop, tamaño y horizonte de forma previa y invariable. No es válido usar los retornos ya vistos (captura 20261106a) para elegir dirección o umbrales.

**Regla candidata propuesta (para revisión, NO implementada todavía):**

Hipótesis de **continuación** (se justifica porque el selector prioriza `|move_24h|` por encima del umbral y la captura mostró retornos positivos medios en candidatos; reconocer: está influida por resultados ya vistos, por eso debe probarse en ventanas separadas):
- Información disponible al decidir: `side` (UP/DOWN) del selector en T, `move_24h_pct`, precio de libro `libro_mid` en T, cobertura y frescura (`available_at <= decision_ms`, con referencia temporal acreditada; sin admitir información futura por tolerancia). Nada del futuro.
- Dirección y condición de entrada: si `side == UP` → LONG; si `side == DOWN` → SHORT. Entrada solo si existe vela plenamente conocida en T y su close opera a favor vs `entry_px` y stop no vulnerado (misma lógica de abstención que RULE-CAUSAL-V1). Si no, abstención (SIN_ENTRADA), nunca entrada forzada.
- Primera ejecución causalmente posible: **POR DEFINIR antes de autorizar**. Una decisión que usa el cierre de una vela no puede ejecutarse al open pasado de esa misma vela. Fijar disponibilidad de señal, primera ejecución posterior, precio y modelo de fill; si no hay datos suficientes, no se estima P&L operativo.
- Stop: `entry_px × (1 ∓ stop_distance_pct)`, con `stop_distance_pct` fijado previamente (ej. 0,5 % como referencia del backtest_offline, sujeto a revisión), stop por debajo para LONG y por encima para SHORT.
- Salida y vencimiento: salida al stop (touch), o al horizonte fijo (ej. 60 m) con marca de close conocida (`open_at_end` si no hay close conocido → no salida ejecutada, P&L = UNKNOWN). Vencimiento forzado al horizonte.
- Tamaño de posición y límite de riesgo: `notional_usdt` fijo por operación (ej. notional del piloto, sujeto a revisión), riesgo por operación acotado por `stop_distance_pct × notional_usdt`. Máximo una posición concurrente (max_concurrent=1).
- Abstención cuando falten datos o no exista señal: si no hay cobertura (`coverage_ok=false`), no hay vela conocida, stop vulnerado en T, o `side` es None → SIN_ENTRADA, sin entrada, sin coste.

**No se optimizan umbrales con esta captura ni se prueban variantes hasta encontrar una ganadora.** La regla candidata queda para revisión previa a cualquier autorización.

## 4. Diseño de comprobación independiente y acotada

**Períodos separados de la captura ya analizada.** Se proponen ventanas no sobrepostas a la de `public-pilot-1h-20261106a` (2026-11-06 05:17–07:14 UTC), usando el mismo protocolo de captura (protocolo v3, 3600 s captura + 4200 s settle, `cycle_seconds=300`, `selection_seconds=300`, ventana 60 s, `max_data_age_ms=5000`, `max_symbols=20`, candidatos+máx comparadores según `ResearchPolicy`).

- Número de ventanas: propuesta de 3 ventanas separadas; no se presume independencia estadística.
- Duración de cada ventana: 1 h de captura + 70 min de settle (idéntica al piloto), para tener denominador completo en 60m y en candidatos/comparadores.
- Calendario: tres días distintos, en regímenes de mercado no seleccionados a posteriori (fechas por definir en la autorización, no optimizadas sobre esta captura).
- Política de selección y comparadores: idéntica al piloto (`research-selector-v2`, `max_candidatos=12`, `max_comparadores=8`, `max_deep_analysis_total=20`, `max_per_side=10`, `selection_seconds=300`, semilla comparador=42, muestreo aleatorio sin reposición). Iguales para todas las ventanas.
- Regla operativa y parámetros congelados: la regla candidata de §3 con `stop_distance_pct`, `notional_usdt`, `horizon_ms` fijados antes de ejecutar cualquier ventana. Sin cambios entre ventanas.
- Datos imprescindibles para evaluar decisiones y ejecución: `libro_mid` (precio base), `klines_apertura_1m` (precio posterior), cobertura de flujo y libro (`disponibilidad`, `ventana_completa`), `side`, `move_24h_pct`, decision_ms, observation_id, trazabilidad de decisión (evidencia en T).
- Presupuesto total HTTP/WS, almacenamiento y duración: idénticos al piloto autorizado (HTTP ≤2000 intentos/≤5000 peso/≤50 reintentos; WS ≤5 000 000 mensajes/≤20 reconexiones; almacenamiento ≤128 MB por ventana). Conexiones simultáneas y aperturas acumuladas deben presupuestarse por separado antes de autorizar; los totales agregados siguen siendo propuesta.
- Tratamiento de descartes, abstenciones, pendientes y posiciones abiertas al finalizar: descartes con motivo explícito (nunca convertidos en cero ni en rentabilidad); abstenciones (SIN_ENTRADA) registradas como tal, no como operaciones; pendientes al agotar settle con causa (`ventana_de_settle_agotada`); posiciones abiertas al finalizar quedan marcadas `open_at_end`, sin salida inventada, sin P&L realizado.

**Cobertura de candidatos y comparadores:** se comprueba por ciclo que ambos grupos tengan observaciones emitidas; se reporta la tasa de aptas por rol (candidate vs comparator) y se declara explícitamente cualquier asimetría. Repetir el mismo protocolo no garantiza corregir la desigualdad de cobertura observada (38 comparadores descartados vs 10 candidatos en el piloto). No se relaja frescura ni se sustituyen comparadores descartados según sus resultados.

**No se reutilizan automáticamente presupuestos de antiguas ventanas del dashboard**; cada ventana requiere su propia autorización de presupuesto.

## 5. Qué resultados permitirían decidir

Se separan tres niveles de evidencia, de menor a mayor exigencia:

| Nivel | Qué requiere | Qué permitiría afirmar | Qué NO permitiría afirmar |
|---|---|---|---|
| A. El selector identifica movimientos diferentes | Retornos de candidatos vs comparadores en ventanas separadas, con cobertura reportada | Que los candidatos mostraron retornos descriptivos diferentes a comparadores en esas ventanas | Capacidad predictiva, rentabilidad, o que el selector cause el movimiento |
| B. La regla aprovecha una parte de esos movimientos bajo un modelo explícito | Resultados de la regla candidata (§3) en ventanas separadas, con entry/stop/salida y razón de cada decisión trazables | Que la regla ejecutó entradas/salidas conforme al modelo, con trazabilidad completa | Que el modelo sea rentable o resista costes |
| C. El resultado resiste costes y supuestos de ejecución defendibles | Nivel B + costes (fee/spread/slippage) y funding acreditados o modelados con supuestos explícitos; P&L neto por operación | Un resultado neto estimado con supuestos declarados | Rentabilidad real, expectancy probada, o capacidad de ejecución en vivo |

**Métrica principal operativa:** `neto_por_operación = (precio_salida − precio_entrada) × qty × dirección − costes − funding`, en USDT, por operación ejecutada, con `precio_entrada` y `precio_salida` posteriores a sus respectivas decisiones o disparadores y respaldados por un modelo causal explícito; no se usa un open pasado como fill después de conocer el cierre. Incluye pérdidas, riesgo (stop_distance_pct × notional) y abstenciones (contadas como 0 operaciones, no como 0 P&L). **No se presentan medias brutas como P&L.**

**Supuestos declarados:** precio/modelo de ejecución posterior a la decisión POR DEFINIR (nunca open pasado de la vela que confirma la señal), funding = UNKNOWN sin calendario real, slippage/spread según `PaperSessionConfig` (no medidos en ejecución real), una posición concurrente.

**Qué puede estimarse con los datos previstos:** retornos descriptivos por horizonte, tasas de cobertura por rol, motivos de descarte, asociación exploratoria flujo/profundidad, trazabilidad de decisiones.

**Qué permanecería UNKNOWN:** rentabilidad neta real, fills ejecutados, comisiones reales, funding real, slippage real, capacidad predictiva del selector, estabilidad entre regímenes, representatividad del universo.

**Criterios de decisión (fijados antes de ejecutar):**
- **Continuar:** si el nivel C muestra `neto_por_operación` positivo con supuestos defendibles y cobertura razonable en las 3 ventanas, y la regla se ejecutó sin incumplimientos de causa.
- **Reformular:** si el nivel A no muestra diferencia consistente o la cobertura es muy desigual (p. ej. <50 % de ciclos con ambos grupos aptos).
- **Detener la línea:** si el nivel C muestra `neto_por_operación` negativo consistente o los costes devoran el edge descriptivo.
- **Evidencia insuficiente:** si tras las 3 ventanas no se alcanza nivel B completo (regla no ejecutada conforme al modelo) o faltan precios para simular fills honestamente. En ese caso no se deriva automáticamente en más capturas indefinidas; se requiere una nueva decisión de alcance y presupuesto.

**Limitación previa a autorizar adquisición:** si faltan precios de ejecución honestos (fill causalmente posible) o información de costes/funding para simular, se identifica esa limitación antes de cualquier nueva captura y se declara UNKNOWN el correspondiente nivel C.

## 6. Presupuesto propuesto

| Concepto | Valor (por ventana) | Total (3 ventanas) | Notas |
|---|---|---|---|
| Ventanas de captura | 3 × 1 h | 3 | Mismo protocolo v3, 3600 s + 4200 s settle |
| HTTP intentos | ≤2000 | ≤6000 | Sujeto a nueva autorización de presupuesto |
| HTTP peso | ≤5000 | ≤15 000 | Tabla ASSUMED_WEIGHTS, no cabeceras reales |
| HTTP reintentos | ≤50 | ≤150 | |
| WS conexiones simultáneas / aperturas acumuladas | POR CONFIRMAR / POR CALCULAR | POR CALCULAR | Separar iniciales, rotaciones y reaperturas; no confundir con símbolos ni reconexiones |
| WS mensajes | ≤5 000 000 | ≤15 000 000 | |
| WS reconexiones | ≤20 | ≤60 | |
| Almacenamiento | ≤128 MB | ≤384 MB | JSONL + SQLite + aux |
| Duración por ventana | 1 h + 70 min settle | 6 h 30 min total | Máximo propuesto de 3 × 130 min; no incluye pausas entre días |
| Max símbolos | 20 | 20 | Por ventana |
| Max candidatos/comparadores | 12/8 | 12/8 | Por ventana, techo conjunto 20 |

**Presupuesto separado del piloto:** cada ventana es una adquisición distinta que requiere su propia autorización. No se reutilizan presupuestos de antiguas ventanas del dashboard.

## 7. Referencias en estado y cola

- `docs/TASK_QUEUE.md`: referencia breve añadida en `NEXT_TASKS` del bloque research/universe-liquidez-v1 (protocolo de experimento v1, no ejecutado, pendiente de autorización).
- `docs/CURRENT_STATE.md`: referencia breve en la sección de la captura pública 20261106a, señalando que el análisis v4 es exploratorio y que el siguiente paso es un protocolo de experimento con autorización separada.

**No se ejecuta el experimento.** Este documento queda concreto y revisable para que la autorización posterior corresponda a un alcance y presupuesto definidos.
