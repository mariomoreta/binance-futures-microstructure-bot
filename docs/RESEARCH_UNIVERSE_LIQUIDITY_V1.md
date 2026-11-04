# Investigación: universo y selección por liquidez/flujo — v1

**Rama:** `research/universe-liquidity-v1` (desde `dash-v2-05-public-acceptance` @ `78371aa`)
**Estado:** investigación en curso (solo lectura de datos locales; sin conexión pública; sin órdenes; sin cambios de reglas operativas)
**Fecha:** 2026-11-03
**Evidencia:** `docs/evidence/research/universe_liquidity_v1/coverage.json` y `descriptive.json` (generados por `scripts/research_universe_liquidity_inventory.py`, read-only sobre SQLite)

---

## 1. Cambio de prioridad (decisión vigente)

Se pausa la expansión del dashboard, Paper Lab, gestores de procesos y aceptación pública.
El objetivo inmediato pasa a ser **investigar la hipótesis económica y la selección
automática de candidatos sobre el universo elegible**.

La hipótesis económica (no validada): *poca liquidez respecto al flujo agresor puede
asociarse con movimientos fuertes y con distinta probabilidad de continuación /
agotamiento-reversión*.

Resultado existente (OFFLINE_EVAL_CENSUS_V2): las configuraciones H1/H3/H2-fade
estudiadas **no demostraron ventaja** (ninguna celda supera al placebo con costes 1x y
sobrevive a 2x; H1/H3 rechazadas en 18/18 celdas 15m y 6/6 en 1h).

**Este documento no presenta el PASS de ingeniería como evidencia estratégica.** El
PASS de la aceptación pública (A-J, 14/14) es un logro de ingeniería, no evidencia de
edge de trading.

---

## 2. Protocolo de estudio (versión corta, pre-compromiso)

Se fija **antes** de calcular resultados nuevos, tal como exige el punto 5 del mandato.

| Ítem | Definición |
|---|---|
| Universo de estudio | USD-M perpetuos de Binance Futures elegibles según `contract_catalog` (522 TRADING+eligibles de 942). **No** es el catálogo actual como sustituto de universo histórico; no hay snapshot de universo en T (UNKNOWN). |
| Listados/suspensiones/exclusiones | Conocidos por `contract_catalog.status` y `exclusion_reasons` (TRADING=522, SETTLING=137, TRADIFI_PERPETUAL=234, USDC=38, …). En cada T se registraría el universo conocido y elegible; hoy solo existe catálogo estático. |
| Datos necesarios y motivo de descarte | Liquidez en T (spread/profundidad top-20), flujo agresor en T (taker buy/sell), retorno forward resuelto. Se descarta símbolo/instante si falta cualquiera de estos tres en T. |
| Política de selección | Ranking por movimiento (|retorno 24h|, volumen, liquidez) — **solo como descripción**, nunca como señal de entrada. Separar ganadores/perdedores y continuación/reversión. |
| Comparador | Selección sencilla (placeholder / exposición aleatoria equivalente) en las mismas condiciones, para medir aporte predictivo (nivel B), no solo asociación (nivel A). |
| Tratamiento de eventos repetidos/correlacionados | Denominadores y candidatos descartados conservados; dedup no implica independencia (misma ventana same-grid). |
| Costes | Medidos frente a supuestos (COST-ASSUME-v1: 5/1/2 bps, escalas 1x/2x/3x). Nunca cero. Resultado económico operable solo tras costes. |
| Niveles de evidencia | A = asociación descriptiva; B = aporte predictivo vs comparador; C = resultado económico operable tras costes. Este bloque solo puede aspirar a A. |

---

## 3. Inventario real de datos (solo lectura)

Generado con `scripts/research_universe_liquidity_inventory.py` (SQLite `mode=ro`; ninguna escritura en DBs canónicas).

### Tabla de cobertura (resumen)

| Fuente | Datos | Símbolos | Filas | Disponible | Resolución | Notas clave |
|---|---|---:|---:|---|---|---|
| `contract_catalog` | universo catálogo (estático) | 942 | 942 | — | snapshot | 522 TRADING+eligibles USDT perp. No es snapshot de universo en T. |
| `market_klines` | OHLCV + taker_buy (flujo proxy por vela) | 10 | 12 818 | 2026-05-27 → 2026-11-03 | 1m/15m/1h | Hasta hoy. Incluye BTC, **no ETH ni SOL**. Sin forward-outcome resuelto. |
| `historical_klines` | OHLCV + taker_buy (ventana resuelta) | 6 | 17 270 | 2026-09-07 → 2026-10-07 | 15m/1h | Solo BTC/ETH/SOL/MINAU/NMR/ORCA. |
| `event_instances` + `event_outcomes` | eventos + forward_return resuelto (MF/MAE) | 6 | 2 831 eventos / 16 986 outcome-rows | 2026-09-08 → 2026-10-07 | detección (same-grid) | 16 548 outcome-rows utilizables. `label` siempre NULL. Universo resuelto = 6 símbolos (1,15% de los 522 elegibles). |
| `research_book_1m` | libro agregado (spread, desequilibrio, microprice) | 14 | 1 830 | 2026-10-07 22:43 → 2026-10-16 | 1m | **Reciente, resultados NO resueltos.** No se une con `event_outcomes`. |
| `research_flow_1m` | flujo agregado (delta_ratio, compra/venta) | 14 | 1 927 | 2026-10-07 → 2026-10-16 | 1m | Reciente, no resuelto. |
| `flow_buckets` (microprobe) | buckets de flujo agresor | 14 | 8 204 | 2026-10-07 → 2026-10-16 | 10s/30s/1m/5m | Reciente, no resuelto. |
| book depth en T (ventana resuelta) | **profundidad/libro en instante T** | **0** | **0** | — | — | **0 filas en Sep 8 – Oct 7.** `research_book_1m` empieza 2026-10-07 22:43 (sin resolver). **Liquidez en T no disponible para outcomes resueltos.** Véase §4 (matriz de aprovechamiento por observación). |

Tabla completa: `docs/evidence/research/universe_liquidity_v1/coverage.json`.

### Procedencia y límites
- Datos reales de SQLite (no fixtures), salvo las celdas vacías (book depth en ventana resuelta = 0).
- El censo `event_instances` es **same-grid**: los eventos ya se detectaron porque movieron (sesgo de selección). Denominadores y descartados reportados.
- No se reconstruye libro histórico a partir de OHLC ni se usa libro actual para explicar decisión pasada.
- book.py trabaja con top-20 y bandas 5/10/25 bps: no se asume cobertura de ±1 % (100 bps); si una banda no está cubierta, UNKNOWN.

---

## 4. Resultado computado (acotado, reproducible)

Solo los datos aptos permiten un análisis de **nivel A (asociación descriptiva)** sobre los 6 símbolos con forward outcome resuelto (BTC/ETH/SOL/MINAU/NMR/ORCA), ventana 2026-09-08 a 2026-10-07. **No es predicción (nivel B) ni resultado operativo tras costes (nivel C).**

Resultado: `docs/evidence/research/universe_liquidity_v1/descriptive.json`.

| Métrica | Valor |
|---|---|
| Eventos totales (`data_quality='OK'`) | 2 761 |
| Con proxy de flujo en T (`taker_buy_proxy`) | 2 761 |
| Con retorno forward 1h usable | 2 758 |
| Símbolos evaluados | BTC, ETH, SOL, MINAU, ORCA, NMR |
| Participación sobre universo elegible (522) | 1,15% |
| `label` de `event_outcomes` | siempre NULL (sin etiquetar) |

Retorno forward medio a 1h por símbolo (sobre eventos con flujo + outcome):

| Símbolo | n | mean ret 1h | median ret 1h | % positivo | n tbp≥0.5 | mean ret (tbp≥0.5) | n tbp<0.5 | mean ret (tbp<0.5) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 463 | +0,000043 | −0,000066 | 48,8% | 219 | +0,000029 | 244 | +0,000056 |
| ETHUSDT | 484 | −0,000011 | +0,000042 | 50,6% | 237 | −0,000174 | 247 | +0,000145 |
| SOLUSDT | 569 | +0,000383 | −0,000099 | 48,2% | 266 | +0,000335 | 303 | +0,000425 |
| MINAUSDT | 613 | +0,001021 | +0,000620 | 50,9% | 282 | +0,002945 | 331 | −0,000619 |
| ORCAUSDT | 587 | +0,001026 | 0,000000 | 49,9% | 262 | +0,000634 | 325 | +0,001341 |
| NMRUSDT | 42 | +0,005747 | +0,001925 | 50,0% | 25 | −0,000935 | 17 | +0,015575 |

### Hallazgos (nivel A, descriptivo)

1. **BTC/ETH/SOL (los más poblados):** retorno forward medio a 1h ≈ 0 (4,3e-05, −1,1e-05, 3,8e-04) y % positivo ≈ 48–51%. Es decir, **cara/cruz**: sin borde direccional claro en este censo. Coherente con OFFLINE_EVAL_CENSUS_V2 (H1/H3 rechazadas).
2. **MINAU/ORCA/NMR:** medias más altas pero con n menor y sin consistencia entre tbp≥0.5 y tbp<0.5 (ej. NMR: tbp≥0.5 → −0,0009 vs tbp<0.5 → +0,0156, n=17/25). No es evidencia.
3. **El split por flujo agresor (`taker_buy_proxy`) no muestra un borde consistente**: en varios símbolos el lado con flujo agresor menor tiene retorno medio similar o mayor.
4. **La hipótesis objetivo (liquidez vs flujo agresor) NO es testeable hoy**: no existe profundidad/libro en el instante T para la ventana de outcomes resueltos (0 filas). Solo hay proxy de flujo, no liquidez en T.
5. **Universo resuelto no representativo:** 6 símbolos = 1,15% de los 522 elegibles. No se puede generalizar al universo.

**Veredicto del bloque:** diagnóstico computado de **insuficiencia**. Con los datos actuales no se puede medir la hipótesis liquidez-vs-flujo sobre un universo representativo. No se entrega otro simulador.

---

## 5. Plan mínimo de adquisición (propuesta, NO ejecutar en este bloque)

Tal como exige el punto 7, solo se propone la adquisición mínima; no se ejecuta.

| Capacidad que falta | Adquisición mínima | Fuente existente a reutilizar | Frecuencia / duración / retención | Presupuesto |
|---|---|---|---|---|
| Universo elegible en T | Snapshots periódicos de `exchangeInfo` (símbolos activos + filtros) con `available_at` | `src/microstructure_probe/universe.py`, `universe_manager.py` | Periódico (ej. cada 15–60 min); historia ≥ 30–90 d | bajo |
| Serie rolling-24h por símbolo (precio/volumen) para ranking causal | recolectar klines 1m/15m con `available_at` | `historical_klines`, `market_klines` | 1m; cobertura del universo elegible | medio |
| Liquidez en T (spread/profundidad) | snapshots de order book top-20 para el universo candidato | `book.py`, `research_book_1m` | 100 ms sobre candidatos (no todos los contratos) | medio (no conectar todos los contratos a la vez) |
| Flujo agresor en T | taker buy/sell por barra o aggTrade agregado | `flow.py`, `historical_klines.taker_buy_*` | por barra | bajo |
| Funding calendario más allá de BTC/ETH/SOL | `scripts/build_funding_calendar.py` extendido | ya existe | por contrato | bajo |

**Criterio de suficiencia:** tener (a) snapshot de universo en T, (b) rolling-24h, (c) liquidez en T y (d) flujo en T para un conjunto representativo (≥ decenas de símbolos, no solo el trio), con resultados forward resueltos. Sin eso, la estrategia completa de extremos sobre universo y liquidez permanece NO EVALUADA.

**Criterio de interrupción:** si tras la adquisición mínima el retorno forward condicionado sigue ≈ 0 tras costes en el universo representativo, no escalar.

**Qué NO se propone:** colección indefinida, todas las fuentes externas a la vez, declarar un proveedor "gratis/disponible/suficiente" sin verificar condiciones, capturar en este bloque.

---

## 4. Matriz de aprovechamiento de datos existentes

Generada por `scripts/research_universe_liquidity_inventory.py` (salida:
`joint_coverage.json`). Evalúa cobertura conjunta: símbolo × ventana de libro/
flujo × cobertura de precio posterior × horizontes computables × motivos de
exclusión.

| Símbolo | Ventana libro/flujo | Precio posterior | Horizontes computables | Adecuado para outcomes | Motivos de exclusión |
|---|---|---|---|---|---|
| BTCUSDT | 2026-10-07 22:43 → 2026-10-16 03:46 | market_klines 1h (2026-10-08 → 2026-11-03) | 1h | SÍ | 1m: primera vela 1m (2026-10-22) tras fin de ventana |
| AIOTUSDT | ... | ninguno | — | NO | sin precio posterior |
| (12 símbolos más) | ... | ninguno | — | NO | sin precio posterior |

**Resultado:** cobertura útil para liquidez + flujo + resultado posterior =
**1 de 14 símbolos research** (BTCUSDT), y 0 de los 13 restantes. Incluso para
BTCUSDT solo el horizonte 1h es computable (1m no, por falta de velas 1m
posteriores dentro de la ventana).

Esto confirma el diagnóstico de §4: no hay cobertura suficiente para medir la
hipótesis liquidez-vs-flujo sobre un universo representativo. Se detiene antes
de adquirir datos nuevos; se entrega el plan de adquisición en §5.

---

## 5. Autoselección de candidatos para investigación

**Política versionada:** `research-selector-v1` (archivo:
`scripts/research_selector.py`, pruebas: `tests/test_research_selector.py`).

La autoselección de investigación **NO equivale a autorización para operar**.
Es un protocolo reproducible que elige qué estudiar sin selección manual
posterior de monedas ganadoras.

### 5.1 Política (fijada antes de resultados nuevos)

| Ítem | Definición |
|---|---|
| Universo | Contratos Binance USD-M Futures elegibles: status=TRADING, contractType=PERPETUAL, quoteAsset=USDT (desde `contract_catalog`, referencia estática; universo en T = UNKNOWN). |
| Exploración | Amplia: todos los elegibles del catálogo son considerados inicialmente; no se eligen seis monedas porque tengan datos ni los ganadores finales de un período. |
| Selección acotada | Conjunto bounded para análisis profundo (`max_deep_analysis_total=20`, `max_per_side=10`). Techo total para la unión candidatos + comparadores. |
| Lados | Ambos lados del movimiento (UP si cambio_24h ≥ +0.02; DOWN si ≤ −0.02). `cambio_24h_pct` se interpreta en **puntos porcentuales** (convención Binance priceChangePercent: 5.0 = 5%); 0.02 = 0,02 puntos porcentuales (hipótesis no validada, ambigüedad previa documentada). |
| Criterios en T | Movimiento (cambio_24h_pct), volumen (quote_volume_24h), cobertura (ticker 24h). Aceleración (1h), percentil de volumen vs propia historia y liquidez NO disponibles en discovery → marcados como UNKNOWN, nunca fabricados. |
| Límites | max_candidates_total=500 (tope de recursos de descubrimiento, NO recorte del universo: todos los elegibles se consideran), max_deep_analysis_total=20 (estudio profundo), max_per_side=10 (techo por lado). |
| Rotación | min_dwell_cycles=1, max_cycles_per_symbol=5 — **diferidos**: no existe gestor de rotación en este prototipo; no se aplican. |
| Comparador | Muestreo con semilla fijada (`comparator_seed=42`, share=0.25) del mismo universo disponible en T; registra probabilidad y mecanismo de muestreo. |

### 5.2 Comparador reproducible

Además de candidatos, se conserva un comparador de selección sencilla con
semilla fijada del mismo universo disponible en T, en condiciones de
observación comparables. Se registra la probabilidad de muestreo y el
mecanismo. No se afirma representatividad por observar "decenas de símbolos";
se publica cobertura, concentración por símbolo y dependencia entre eventos.

### 5.3 Trazabilidad por ciclo

Cada ciclo produce: `cycle_id`, instante de referencia, versión de política,
universo observado y procedencia, candidatos seleccionados y comparadores,
variables disponibles, motivos de elección/exclusión y datos faltantes,
timestamps de disponibilidad, estado: `pendiente / evaluable / insuficiente /
error`.

**Ningún resultado forward se usa para seleccionar.** La selección se basa
únicamente en datos disponibles en T (movimiento 24h, volumen 24h, cobertura).
Los tests de mecanismo verifican: mismos datos en T → misma selección; datos
posteriores no alteran la selección hasta T; símbolo inelegible → exclusión
explícita; ganadores y perdedores por la política declarada; límites
respetados; comparador reproducible; no seleccionados registrados con motivos;
cero red pública; cero escrituras en DBs canonicas.

### 5.4 Qué hace efectivamente el selector / qué permanece diferido

**Qué hace el selector (implementado y probado):**
- Construye el universo observado desde `contract_catalog` (referencia estática; universo en T = UNKNOWN).
- Filtra símbolos elegibles (PERPETUAL/TRADING/USDT) y marca los no elegibles con motivo.
- Para cada elegible con datos en T (movimiento 24h, volumen 24h, cobertura), asigna lado (UP/DOWN) si `cambio_24h` supera el umbral (0,02 puntos porcentuales).
- Rankea por prioridad de estudio (movimiento, volumen) y selecciona hasta `max_deep_analysis_total` (20) en total, respetando `max_per_side` (10) por lado.
- Construye un comparador de selección sencilla con semilla fijada sobre el resto del universo, dentro del mismo techo total, deduplicando símbolos ya seleccionados y reportando probabilidad efectiva de muestreo.
- Produce trazabilidad completa por ciclo (cycle_id, instante, política, universo, candidatos, comparador, exclusiones, estado).

**Qué permanece diferido (no implementado en este bloque):**
- Gestor de rotación / permanencia (`min_dwell_cycles`, `max_cycles_per_symbol`): no existe gestor de rotación; no se construye uno solo para justificarlos.
- Liquidez en T real (profundidad/spread): no disponible para la ventana resuelta (0 filas de libro en T).
- Percentil de volumen vs propia historia y aceleración 1h: no disponibles en `discovery.Candidate`.
- Ejecución, paper trading, órdenes, cambios de reglas operativas.

**Cuántas observaciones son utilizables de verdad (matriz de aprovechamiento, §4):**
- Solo **BTCUSDT** tiene precio posterior compatible para la ventana de libro/flujo research (2026-10-07 22:43 → 2026-10-16).
- De las 1081 observaciones de libro/flujo de BTCUSDT, **253 están emparejadas** con un precio objetivo en T+h (horizonte 1h); 828 excluidas (falta precio posterior compatible).
- Los otros 13 símbolos research tienen **0 observaciones emparejadas** (no tienen precio posterior en `market_klines`).
- Conclusión: cobertura útil = 1 símbolo de 14 research (≈ 0,2% de los 522 elegibles), solo horizonte 1h. No hay cobertura suficiente para medir la hipótesis liquidez-vs-flujo sobre un universo representativo.

**Captura mínima que faltaría (no ejecutar en este bloque):**
- Liquidez en el instante T (order book top-20 con `available_at`) para el universo candidato, al menos los símbolos con resolución histórica (BTCUSDT y los de `historical_klines`).
- Serie rolling-24h por símbolo para ranking causal.
- Universo elegible en T (snapshots periódicos de `exchangeInfo`).

---

## 6. Trabajo congelado y componentes reutilizados

**Congelado (punto 1):** no añadir controles, pantallas, indicadores, IA, conectores ni otro supervisor. No tocar 3020/8792/opencode.json ni archivos ajenos. La integración visual del libro deja de ser requisito previo para investigarlo.

**Componentes reutilizados (sin crear reemplazos paralelos):**
- `src/microstructure_probe/universe.py`, `universe_manager.py` — universo y selección (límites: universo estático, no snapshot en T).
- `src/microstructure_probe/book.py` — profundidad (top-20, bandas 5/10/25 bps; sin asumir ±1 %).
- `src/microstructure_probe/flow.py` — flujo agresor (taker buy/sell, delta_ratio).
- `src/microstructure_probe/discovery.py` — descubrimiento.
- `src/microstructure_probe/backtest_offline.py` — motor offline (v4.2), reutilizado sin cambios salvo flag del harness.
- `scripts/build_funding_calendar.py` — calendario de funding (BTC/ETH/SOL; fuera de ellos UNKNOWN).
- `docs/EXTREMES_EVALUABILITY_MATRIX.md`, `OFFLINE_EVAL_CENSUS_V2.md`, `EXTREME_MOVERS_OBJECTIVE.md`, `STRATEGY_THESIS.md`, `PRODUCT_GOAL.md`.

**Nuevo código:** solo `scripts/research_universe_liquidity_inventory.py` (extracción/inventario read-only) y este documento. Sin pruebas decorativas.

---

## 7. Siguiente paso (el que más reduce incertidumbre económica)

El mecanismo de autoselección ya está implementado y probado
(`scripts/research_selector.py` + `tests/test_research_selector.py`). El
siguiente paso que más reduce incertidumbre económica sigue siendo **adquirir
liquidez en el instante T** (profundidad/order book top-20 con `available_at`)
para el universo candidato, de modo que se pueda unir
(símbolo × instante T) liquidez + flujo agresor + retorno forward resuelto y
probar la hipótesis líquido-vs-flujo con denominadores. Sin ese dato, la
hipótesis permanece no testeable y cualquier "selector" sería un simulador
sin soporte.

**Criterio de interrupción:** si tras la adquisición mínima el retorno
forward condicionado sigue ≈ 0 tras costes en un universo representativo, no
escalar.

---

## 8. Publicación y trazabilidad

- Protocolo: este documento (§2 y §5).
- Resultado reproducible: `coverage.json` + `descriptive.json` +
  `joint_coverage.json` + scripts `research_universe_liquidity_inventory.py`
  y `research_selector.py`.
- Pruebas del mecanismo: `tests/test_research_inventory.py` +
  `tests/test_research_selector.py`.
- Cambios de prioridad registrados en `docs/CURRENT_STATE.md`,
  `docs/TASK_QUEUE.md`, `docs/DECISIONS.md` (append-only), con enlace desde
  `docs/FEATURE_BACKLOG.md`.
- No se declara "listo para operación"; no se aprueban umbrales ni mapping;
  SUCCESS_GATES no se altera por este documento.
