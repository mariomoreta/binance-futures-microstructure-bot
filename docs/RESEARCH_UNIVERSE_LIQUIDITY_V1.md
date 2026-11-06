# Investigación: universo y selección por liquidez/flujo — v1

**Rama:** `research/universe-liquidity-v1` (desde `dash-v2-05-public-acceptance` @ `78371aa`)
**Estado:** investigación en curso (solo lectura de datos locales; sin conexión pública; sin órdenes; sin cambios de reglas operativas)
**Fecha:** 2026-11-03 (actualizado 2026-11-04: corrida final de observaciones y reconciliación de disponibilidad)
**Evidencia:** `docs/evidence/research/universe_liquidity_v1/` —
`coverage.json`, `descriptive.json`, `joint_coverage.json` (inventario),
`observaciones.jsonl` + `observaciones_resumen.json` (corrida final),
`disponibilidad_as_of.json` (consulta de `as_of_ms`), `validacion_muestra.json`
(validación contra fuente), `run_final_stdout.txt` y `run_final_hashes.json`
(prueba de solo lectura).

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
| Selección acotada | Conjunto bounded para análisis profundo (`max_candidatos=12`, `max_comparadores=8`, `max_deep_analysis_total=20`, `max_per_side=10`). Techo total para la unión candidatos + comparadores. |
| Lados | Ambos lados del movimiento (UP si cambio_24h ≥ +0.02; DOWN si ≤ −0.02). `cambio_24h_pct` se interpreta en **puntos porcentuales** (convención Binance priceChangePercent: 5.0 = 5%); 0.02 = 0,02 puntos porcentuales (hipótesis no validada, ambigüedad previa documentada). |
| Criterios en T | Movimiento (cambio_24h_pct), volumen (quote_volume_24h), cobertura (ticker 24h). Aceleración (1h), percentil de volumen vs propia historia y liquidez NO disponibles en discovery → marcados como UNKNOWN, nunca fabricados. |
| Límites | max_candidatos=12 (candidatos seleccionados para estudio profundo), max_comparadores=8 (reserva para el comparador), max_deep_analysis_total=20 (techo total unión candidatos+comparadores), max_per_side=10 (techo por lado). |
| Rotación | min_dwell_cycles=1, max_cycles_per_symbol=5 — **diferidos**: no existe gestor de rotación en este prototipo; no se aplican. |
| Comparador | Muestreo con semilla fijada (`comparator_seed=42`, `comparator_share=0.25`) del mismo universo disponible en T; registra probabilidad de muestreo efectiva y mecanismo. |

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
- Rankea por prioridad de estudio (movimiento, volumen) y selecciona hasta `max_candidatos` (12) en total, respetando `max_per_side` (10) por lado y el techo total `max_deep_analysis_total` (20).
- Construye un comparador de selección sencilla con semilla fijada sobre el resto del universo, dentro del mismo techo total (reserva explícita de `max_comparadores=8`), deduplicando símbolos ya seleccionados y reportando probabilidad efectiva de muestreo.
- Produce trazabilidad completa por ciclo (cycle_id, instante, política, universo, candidatos, comparador, exclusiones, estado).

**Qué permanece diferido (no implementado en este bloque):**
- Gestor de rotación / permanencia (`min_dwell_cycles`, `max_cycles_per_symbol`): no existe gestor de rotación; no se construye uno solo para justificarlos.
- Liquidez en T real (profundidad/spread): no disponible para la ventana resuelta (0 filas de libro en T).
- Percentil de volumen vs propia historia y aceleración 1h: no disponibles en `discovery.Candidate`.
- Ejecución, paper trading, órdenes, cambios de reglas operativas.

**Cuántas observaciones son utilizables de verdad (corregido 2026-11-04, §5.5):**
- **0 observaciones causalmente evaluables.** Ninguna de las 1827 parejas libro+flujo
  tiene `as_of_ms <= bucket_end` en AMBAS fuentes.
- **121 parejas son descriptivas, no evaluables:** tienen precio en T y en T+h
  (todas de **BTCUSDT**, horizonte 1h) pero su disponibilidad publicada en T no
  está acreditada (103 con `as_of_ms` NULL en ambas fuentes, 18 con `as_of_ms`
  posterior al bucket en ambas). Su retorno 1h se conserva como descripción y
  **no sostiene ninguna conclusión causal**.
- **1809 observaciones descartadas:** 1706 parejas sin precio en T o en T+h, más
  103 filas sin contraparte (3 de libro, 100 de flujo).
- Los otros 13 símbolos research tienen 0 parejas con precio posterior en
  `market_klines`.
- Conclusión: cobertura útil para evaluación causal = **0 observaciones**;
  cobertura descriptiva = **121 parejas** (todas BTCUSDT, 1h). La corrección de
  la causa (antes atribuida a publicación posterior a T en *todos* los buckets)
  está en §5.5.3.

**Captura mínima que faltaría (no ejecutar en este bloque):**
- Liquidez en el instante T (order book top-20 con `available_at`) para el universo candidato, al menos los símbolos con resolución histórica (BTCUSDT y los de `historical_klines`).
- Serie rolling-24h por símbolo para ranking causal.
- Universo elegible en T (snapshots periódicos de `exchangeInfo`).

---

## 5.5 Corrida final sobre DBs reales y reconciliación de disponibilidad (2026-11-04)

Generador: `scripts/research_observations_table.py` (procedimiento
`observaciones_libro_flujo_precio_v2`). **Una sola corrida final**, solo lectura
(`mode=ro`) sobre `data/historical/historical.db` y
`data/market-cache/market_cache.db`. SHA-256 idéntico antes y después
(`run_final_hashes.json`: `sin_cambios=true`). Sin Binance, sin escrituras en
DBs canónicas, sin tocar 3020/8792/`opencode.json`.

Artefactos: `observaciones.jsonl` (1930 filas), `observaciones_resumen.json`,
`observaciones_muestra_validacion.json`, `run_final_stdout.txt`,
`run_final_hashes.json`, `disponibilidad_as_of.json`, `validacion_muestra.json`.

### 5.5.1 Consulta de disponibilidad publicada, por fuente

Consulta ejecutada tal cual (también en `disponibilidad_as_of.json`):

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN as_of_ms IS NULL THEN 1 ELSE 0 END) AS as_of_null,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms <= bucket_end
           THEN 1 ELSE 0 END) AS as_of_presente_en_o_antes_del_bucket,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms > bucket_end
           THEN 1 ELSE 0 END) AS as_of_posterior_al_bucket,
  MIN(as_of_ms) AS as_of_min,
  MAX(as_of_ms) AS as_of_max
FROM research_book_1m;   -- idéntica sobre research_flow_1m
```

Resultados medidos:

| Fuente | Total | `as_of_ms` NULL | Presente (`<= bucket_end`) | Posterior (`> bucket_end`) |
|---|---:|---:|---:|---:|
| `research_book_1m` | 1 830 | **1 776** | **0** | **54** |
| `research_flow_1m` | 1 927 | **1 855** | **15** | **57** |

Dos matices medidos, no inferidos:

1. Los 54 `as_of_ms` de libro posteriores al bucket están entre **+365 ms y
   +1 354 ms** (mediana +474 ms); los 57 de flujo, entre **+380 ms y +4 210 ms**.
   Son marcas de *flush* posteriores al cierre, no horas de retraso.
2. Las 15 filas de flujo con `as_of_ms <= bucket_end` son el **último bucket de
   cada corrida**, persistido antes del cierre nominal (entre 6,3 s y 58,3 s
   antes). Son buckets en curso/parciales: "presente" **no** certifica que el
   minuto estuviera completo. No forman pareja evaluable (libro no tiene
   ninguna fila con `as_of_ms <= bucket_end`).

### 5.5.2 Tabla única de la corrida final

| Nivel | Concepto | n |
|---|---|---:|
| Libro (1 830 filas) | `as_of_ms` NULL (procedencia desconocida) | 1 776 |
| Libro | `as_of_ms <= bucket_end` | 0 |
| Libro | `as_of_ms > bucket_end` | 54 |
| Flujo (1 927 filas) | `as_of_ms` NULL (procedencia desconocida) | 1 855 |
| Flujo | `as_of_ms <= bucket_end` (todos parciales, ver §5.5.1) | 15 |
| Flujo | `as_of_ms > bucket_end` | 57 |
| Parejas (1 827) | Ambas fuentes publicadas en T | **0** |
| Parejas | Alguna fuente con `as_of_ms` NULL | 1 773 |
| Parejas | Alguna fuente posterior al bucket | 54 |
| Observaciones (1 930) | Descartadas (sin pareja o sin precio) | 1 809 |
| Observaciones | Descriptivas, **no** evaluables causalmente | 121 |
| Observaciones | **Causalmente evaluables** | **0** |
| Retorno 1h descriptivo (n=121) | media / mediana / mín / máx | +6,60e-05 / +3,04e-04 / −2,77e-03 / +1,96e-03 |

Las 121 descriptivas se reparten en 103 con `as_of_ms` NULL en ambas fuentes y
18 con `as_of_ms` posterior al bucket en ambas. Las 54 parejas posteriores se
reparten en 18 descriptivas y 36 sin precio. Las 1 773 parejas con alguna fuente
NULL se reparten en 103 descriptivas y 1 670 sin precio.

### 5.5.3 Reconciliación: «publicación posterior a T» frente a «disponibilidad desconocida»

La afirmación anterior («el `as_of_ms` de **todos** los buckets es posterior a
`bucket_end`») **no se sostiene** con los datos y queda corregida:

- El artefacto previo (`65d73ff`) ya mostraba el reparto real de motivos:
  **1 773** observaciones con `disponibilidad_publicada_desconocida` (1 670 + 103)
  frente a **54** con `disponibilidad_publicada_despues_de_T` (36 + 18). La
  afirmación generalizó el motivo minoritario (2,96 % de las parejas).
- La causa dominante de exclusión causal es **falta de trazabilidad**
  (`as_of_ms` NULL: 1 776/1 830 en libro, 1 855/1 927 en flujo), no publicación
  tardía. `as_of_ms` es la marca de persistencia en el *flush*
  (`history_store._ensure_v3`), no una prueba de cuándo estuvo disponible el
  dato.
- **No se inventa ningún timestamp**: NULL permanece NULL; `last_event_ms` NO se
  usa como sustituto de disponibilidad publicada. Tampoco se rellena el hueco con
  el `as_of_ms` de la otra fuente (el código anterior lo hacía; ahora cada fuente
  se clasifica por separado y se exige que **ambas** cumplan).
- **Reconciliación del 253**: el «253» previo no eran parejas. Era la suma de
  **121 filas de libro + 132 filas de flujo** de BTCUSDT contadas por separado
  por la matriz de cobertura (unidad = fila). La corrida actual exige pareja
  libro+flujo en el mismo bucket y ambos precios: **121 parejas**. Verificado
  por consulta independiente: libro 121, flujo 132, parejas 121. En este dataset
  el criterio «vela que contiene T+h» y el criterio estricto
  (`close_time <= T+h`) seleccionan exactamente las mismas filas, así que la
  diferencia 253→121 es de **unidad de conteo**, no de lookahead.

### 5.5.4 Validación de la muestra contra registros fuente

`scripts/research_observations_validate_sample.py` recalcula con SQL
independiente (sin helpers del generador) sobre ambas DBs en solo lectura.
Conjunto: la muestra determinista del generador **más** un suplemento que cubre
todas las combinaciones (estado × clase de libro × clase de flujo) presentes,
para no dejar `publicada_despues_de_T` sin comprobar.

| Resultado | Valor |
|---|---:|
| Observaciones validadas | 26 |
| Con al menos un valor no nulo comparado | 26 |
| Comprobaciones comparables | **529** |
| Pares null-null (no acreditados) | 105 |
| Discrepancias | **0** |
| Combinaciones estado/clase cubiertas | 8 |
| DBs modificadas | 0 (`db_sin_cambios=true`) |

Ejemplos (registrado = fuente, cálculo independiente = mismo valor):

| Observación | Estado | `precio_T` | `precio_T+h` | retorno 1h | `as_of` libro/flujo |
|---|---|---|---:|---:|---|
| `BTCUSDT\|1791604560000\|1791604620000` | descriptiva (desconocida) | 82 590,3 | 82 559,9 | −3,6808196604e-04 | NULL / NULL |
| `BTCUSDT\|1791889800000\|1791889860000` | descriptiva (posterior) | 83 310,1 | 83 325,2 | +1,8125053265e-04 | 1791889861250 / 1791889861204 |
| `LUMIAUSDT\|1791632160000\|1791632220000` | descartada | — | — | — | NULL / NULL |

En la segunda fila el `as_of` es +250 ms y +204 ms posterior al bucket: la clase
`publicada_despues_de_T` se comprobó contra la fuente, no se dedujo. En la
tercera no hay precio; su fila de flujo sí se validó (delta = buy − sell,
delta_ratio = delta/(buy+sell), base_volume = buy_base + sell_base): comparar
null con null no se usa como acreditación.

### 5.5.5 Separación descriptivo/causal y límites

- **Descriptivo (121):** spread, desequilibrio, microprice, delta y retorno 1h
  existen y son verificables. Sirven para describir el tramo, no para afirmar
  asociación causal con el retorno.
- **Causalmente evaluable (0):** ninguna observación acredita que libro y flujo
  estuvieran publicados en T.
- **La falta de trazabilidad no es una conclusión económica.** Que 1 773 parejas
  tengan `as_of_ms` NULL significa «no se registró cuándo se publicó», no «no
  había relación entre liquidez y flujo». La hipótesis sigue **NO TESTEABLE** con
  los datos actuales; no queda refutada.
- No se declara fill, coste, rentabilidad operable ni cobertura representativa.
  El retorno descriptivo no está ajustado por costes y no es una señal.

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

**Nuevo código:** `scripts/research_universe_liquidity_inventory.py`
(extracción/inventario read-only), `scripts/research_observations_table.py`
(tabla de observaciones, solo lectura), `scripts/research_availability_counts.py`
(consulta de disponibilidad) y `scripts/research_observations_validate_sample.py`
(validación contra fuente). Sin pruebas decorativas.

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
  `joint_coverage.json` + `observaciones.jsonl` + `observaciones_resumen.json` +
  `disponibilidad_as_of.json` + `validacion_muestra.json` + scripts
  `research_universe_liquidity_inventory.py`, `research_selector.py`,
  `research_observations_table.py`, `research_availability_counts.py` y
  `research_observations_validate_sample.py`.
- Pruebas del mecanismo: `tests/test_research_inventory.py` +
  `tests/test_research_selector.py` + `tests/test_research_joint_coverage.py`
  (incluye integración que ejecuta `main()` completo contra SQLite temporal).
  Subconjunto research: 49 passed (`pytest_research.txt`). Suite completa:
  1661 passed, 2 skipped, 12 failed PREEXISTENTES y ajenos a este bloque
  (`pytest_full.txt`; fixture desfasada de `test_engineering_live_window_local.py`,
  FAIL/UNKNOWN de `test_market_stream_window.py` y vela futura fija en
  `test_session_new_public_market.py`; ninguno importa el código modificado).
- Cambios de prioridad registrados en `docs/CURRENT_STATE.md`,
  `docs/TASK_QUEUE.md`, `docs/DECISIONS.md` (append-only), con enlace desde
  `docs/FEATURE_BACKLOG.md`.
- No se declara "listo para operación"; no se aprueban umbrales ni mapping;
  SUCCESS_GATES no se altera por este documento.

## 9. Piloto prospectivo v1 (protocolo fijado 2026-11-04)

Este bloque añade un **piloto prospectivo local y reproducible** que ejecuta la
cadena completa sin órdenes ni endpoints privados:

```
universo elegible → autoselección (research-selector-v2) → captura de libro y
flujo → precios posteriores (5m/15m/60m) → evaluación reproducible.
```

### 9.1 Protocolo (fijado antes de capturar; no optimizado por resultados)

- **Universo y elegibilidad:** catálogo público USD-M (PERPETUAL / TRADING /
  USDT) + tickers 24h; snapshot con `as_of_ms` y procedencia. El catálogo es un
  snapshot, no acredita universo histórico.
- **Selección:** `research-selector-v2` (umbral 0,02 pp como hipótesis NO
  validada, no se ajusta en el piloto). Hasta 12 candidatos y hasta 8
  comparadores, unión ≤ 20 símbolos simultáneos. Comparadores del mismo
  universo excluyendo candidatos, muestreo con semilla y probabilidad de
  inclusión registrada. Sin resultados futuros para seleccionar.
- **Frecuencia:** selección cada ciclo de selección; decisiones cada ciclo de
  captura. Rotación con observaciones y resultados pendientes conservados
  (nunca se borran ni se abandonan silenciosamente).
- **Permanencia/datos ausentes:** ausencia de datos no es cero; huecos,
  desconexiones y buckets parciales se registran con causa y cobertura
  explícitas (`motivos`). `last_event_ms` no se usa como sustituto de
  publicación; no se rellenan timestamps desconocidos.
- **Horizontes de resultado:** 5m, 15m y 60m desde el instante de decisión.
- **Métricas:** libro (spread bps, imbalance base/notional, desplazamiento de
  microprice, profundidad top-20 base y notional, bandas realmente cubiertas)
  y flujo agresor (delta, delta_ratio, volumen base/notional, trades en
  ventana), con distinción profundidad base vs notional USDT.
- **Regla de precios:** precio de decisión = mid del libro (mark-to-mid, no P&L
  ejecutable); precio posterior = apertura de la vela 1m alineada al alza
  (>= objetivo), con timestamp real, antigüedad, desfase y horizonte efectivo.
  Si excede tolerancia → NO_EVALUABLE. El retorno es variación mark-to-mid
  (fracción); sin supuestos de ejecución/costes, el neto queda UNKNOWN.
- **Instante de decisión:** `max(disponibilidad de todos los datos usados)`;
  nunca `bucket_end`. Debe ser >= disponibilidad de libro y flujo. Una
  publicación posterior al cierre del minuto se usa para una decisión
  posterior, nunca se retrodata.
- **Suficiencia e interrupción:** parada por duración, max observaciones, max
  bytes o max mensajes; limpieza (cerrar feeds WS, drenar buckets abiertos
  como PARTIAL, pendientes como PENDING con motivo, escribir manifiesto y
  resumen desde lo persistido). Ningún proceso persistente al finalizar.
- **Política de pendientes y settle:** al terminar la captura se deja de
  seleccionar/capturar y el settle acotado solo madura resultados ya
  programados, manteniendo presupuesto, plazo y cancelación. Al agotarse el
  settle lo no resuelto se persiste como `pendiente` con causa
  (`ventana_de_settle_agotada`); no se inventan precios ni se prorroga. Una
  parada explícita del operador detiene la adquisición y no realiza más
  consultas de precio, conservando observaciones y pendientes con causa. El
  presupuesto agotado bloquea el siguiente envío antes del transporte y
  persiste pendientes con causa. El settle no devuelve cupos, no crea otro
  `run_id` y no abre prórroga ilimitada.

### 9.2 Ejecución local reproducible (comando productivo)

```
python scripts/research_pilot.py \
  --run-id piloto-local --out-dir data/research_pilot/piloto-local \
  --duration-seconds 14400 --settle-seconds 4200 \
  --cycle-seconds 60 --selection-seconds 300 \
  --max-symbols 20 --max-candidates 12 --max-comparators 8 \
  --horizons "5m=300000,15m=900000,60m=3600000" \
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000
```

Contra proveedores públicos reales esto usaría:
`--rest-base https://fapi.binance.com --ws-public-base
wss://fstream.binance.com/public --ws-market-base
wss://fstream.binance.com/market`. En este bloque **no se ejecuta contra
Binance** (cero conexiones públicas de mercado).

La prueba de cadena completa se ejecuta contra proveedores HTTP/WS loopback y
SQLite temporal con reloj de prueba (`tests/test_research_pilot.py`):
`pytest tests/test_research_pilot.py -v` (28 passed). El test **no duerme para
avanzar el reloj**: fija el instante, ordena al proveedor publicar el burst,
espera confirmación por `--status-file` (contadores aceptados por fuente y
última disponibilidad) y solo entonces autoriza la evaluación con
`--decision-gate-file`; después avanza al siguiente instante. Ambos flags solo
se aceptan con `--clock manual`. Verifica frescura independiente por fuente
(libro obsoleto / flujo obsoleto), ventana incompleta con motivo, `decision_ms`
no retrotraído, unión ≤ 20, duplicados sin multiplicación, rotación conservando
el resultado del símbolo retirado, horizontes 5m/15m/60m con `desfase_ms=0`,
manifiesto con hashes, resumen regenerado desde lo persistido y contabilidad
de aperturas WS (2 por rotación, más reaperturas no deliberadas). También cubre
la política de pendientes: fin normal → settle madura; fin de settle →
`pendiente` con causa; parada explícita (`--stop-file`, solo con reloj manual)
→ ninguna consulta de precio adicional; presupuesto agotado → siguiente envío
bloqueado antes del transporte y pendientes con causa.
`max_data_age_ms` permanece en 5000. Evidencia:
`docs/evidence/research/universe_liquidity_v1/pilot_sync/`.

### 9.3 Propuesta pública vigente: 1 h + 70 min (NO ejecutada)

> Estado 2026-11-05: **propuesta no ejecutada**. No se abrió ningún endpoint
> de mercado. Esta propuesta sustituye a la de 4 h + 70 min (§9.3.1), que queda
> conservada solo como antecedente histórico y no debe usarse como presupuesto
> vigente.

**Comando único propuesto (PowerShell; requiere autorización separada):**

```powershell
Set-Location "C:\proyectos\binance-futures-microstructure-bot"
python scripts/research_pilot.py `
  --run-id "public-pilot-1h-20261105a" `
  --out-dir "C:\proyectos\binance-futures-data\public-pilot-1h-20261105a" `
  --mode public --activar-publico `
  --rest-base "https://fapi.binance.com" `
  --ws-public-base "wss://fstream.binance.com/public" `
  --ws-market-base "wss://fstream.binance.com/market" `
  --duration-seconds 3600 --settle-seconds 4200 `
  --cycle-seconds 300 --selection-seconds 300 `
  --decision-delay-seconds 5 --tick-ms 500 `
  --max-symbols 20 --max-candidates 12 --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons "5m=300000,15m=900000,60m=3600000" `
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 `
  --max-data-age-ms 5000 --max-observations 20000 `
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 `
  --max-ws-reconnects 20 --max-messages 5000000 --max-bytes 134217728
```

No se ha lanzado. El directorio de datos es propio y persistente, fuera de Git;
`--budget-only` se usó solo para generar el presupuesto publicado en evidencia.
El comando usa `research-selector-v2` sin cambios y mantiene
`max_data_age_ms=5000`.

**Presupuesto generado sin red**

`--budget-only` con esa configuración produjo
`docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/presupuesto.json`.
El hash SHA-256 de la configuración efectiva (incluye `run_id` y `out_dir`) es
`2538ac09409b93ba9943323d0ce6c8ece7adce00c0dbf09ab2f8ae4d1891522c`,
calculado sobre el JSON canónico (`sort_keys=True`, UTF-8, separadores `,`/`:`) de
`config_efectiva.json` (incluye `run_id` y `out_dir`; conserva los valores
numéricos tal como los serializa el CLI, p. ej. `3600.0`).
SHA del código base verificado: `68c0520de6354775b9a6148ed629047f562ce212`.
El commit de esta propuesta se publica en la rama; su SHA es el de
`git rev-parse HEAD`.

- 12 selecciones y 12 ciclos de decisión; 240 observaciones máximas; 720
  consultas de klines base (20 símbolos × 3 horizontes × 12 ciclos).
- 24 consultas de catálogo/ticker + 720 de klines = **744 intentos HTTP base**;
  **1.212 de peso base** (12×1 + 12×40 + 720×1).
- Reserva de 50 reintentos: 794 intentos; peor caso de peso 3.212 si los 50
  reintentos fueran tickers de peso 40. La puerta efectiva es 2.000 intentos /
  5.000 de peso; no se presupuesta `/time` porque el programa no la llama.
- El límite de reintentos es posterior al envío: el evento 51 marca bloqueo,
  pero intentos y peso siguen acotados antes del transporte por
  `max_http_attempts` y `max_http_weight`.

**Verificación oficial (consultada 2026-11-05)**

| Comprobación | Fuente oficial |
| --- | --- |
| Pesos REST: klines `limit=1` → 1; ticker sin `symbol` → 40; exchangeInfo → 1 | [Market Data, USDⓈ-M](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) |
| Cabecera `X-MBX-USED-WEIGHT-1M`; 429/418; límites por IP | [General Info, LIMITS](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info#limits) |
| 2.400/min por IP; UM y CM comparten el mismo pool | [Aviso de integración CM/UM](https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/Important-CM-UM-Integration-Notice) |
| Rutas `/public` y `/market`; 24 h; ping/pong; 10 mensajes entrantes/s; 1.024 streams/conexión | [Websocket Market Streams, Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect) |
| `depth<levels>@100ms` en `/public`; `aggTrade` en `/market` | [Important WebSocket Change Notice](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice) |

El límite de 300 intentos de conexión cada 5 minutos no aparece en las páginas
UM vigentes consultadas; el «300» de WebSocket API General Info es un límite de
órdenes (`ORDERS/10s`), no de conexiones. El plan no depende de esa cota; aun si
aplicara, 46 intentos de apertura máximos quedarían por debajo de 300.

El limitador de ventana de `HistoryClient` usa pesos conservadores propios
(klines 10, exchangeInfo 20, ticker 40) y 1.200/min; no consume el pool oficial
de 2.400/min, solo espacia. Por ciclo de 5 min el plan usa 660 de ese peso
conservador (20×3×10 + 20 + 40), por debajo de 1.200. El presupuesto de 1.212
usa los pesos oficiales del gate, no los conservadores del limitador.

**Contabilidad WS (aperturas, rotaciones y reconexiones)**

| Concepto | Cálculo | Total |
| --- | --- | --- |
| Conexiones simultáneas | `/public` (depth) + `/market` (aggTrade) | 2 |
| Aperturas iniciales | primera selección | 2 |
| Rotaciones | 12 selecciones − 1 = 11; 2 feeds reabiertos por cambio | 22 |
| Reaperturas tras desconexión/fallo (incluye cierre normal) | `max_ws_reconnects` | 20 |
| Sobregiro entre comprobaciones | hasta 2 feeds cruzan el umbral en un tick | 2 |
| Intentos de apertura máximos | 2 + 22 + 20 + 2 | **46** |

`max_ws_reconnects` cuenta `StreamFeed.reconnects`: reaperturas o intentos de
reconexión después de una desconexión o fallo, **incluidos los cierres normales
del servidor y los fallos antes de la primera conexión**. No cuenta la primera
apertura exitosa ni las rotaciones deliberadas. Un intento fallido incrementa
`errors`/`reconnects`, no `connections`; `connections` solo sube tras conectar.
El tope se comprueba por tick, de ahí el sobregiro acotado de 2. El pico es 20 streams por conexión
(40 totales), muy por debajo de 1.024. Los 10 mensajes/s son «incoming» hacia el
servidor (el cliente solo envía pong; no suscribe por mensaje), no un tope de
datos servidor→cliente. `max_messages=5.000.000` cuenta solo mensajes de datos;
los ping/pong de control no se contabilizan. La validez de 24 h supera las
2 h 10 min de la corrida.

**Almacenamiento previsto**

| Componente | Cálculo | Bytes |
| --- | --- | --- |
| JSONL | 240 observaciones × 1.600 + 720 resultados × 500 | 744.000 |
| SQLite | 7.200 filas 10 s + 2.400 filas 1 m (libro+flujo), 200 B/fila | 1.920.000 |
| Auxiliares WAL/SHM | 2 × 65.536 | 131.072 |
| **Total** | | **2.795.072** (2,67 MiB) |
| Tope | `max_bytes` | 134.217.728 |
| Margen | | **131.422.656** (97,92 %) |

La comprobación de total es previa a cada escritura y el JSONL tiene su propio
tope; la cola del recorder (2.000 filas por defecto) puede sobregirar como máximo
esas filas en vuelo, no un múltiplo del tope. Con 2,8 MB previstos frente a
128 MiB el margen es suficiente para esta corrida.

**Aceptación previa a la captura**

| Recurso | Base | Máximo permitido | Mecanismo | Compatible |
| --- | --- | --- | --- | --- |
| Intentos HTTP | 744 | 2.000 | `RunBudget.before_send` antes del transporte | Sí |
| Peso HTTP | 1.212 | 5.000 | `RunBudget.before_send` | Sí |
| Reintentos | 0 | 50 (+1 en vuelo) | `after_send` | Sí; reserva 3.212 |
| Peso/min cliente | 660 por ciclo de 5 min | 1.200/min | `HistoryClient._admit` | Sí |
| Peso/min oficial | ~101 por ciclo | 2.400/min UM+CM | pool por IP | Sí |
| Conexiones WS simultáneas | 2 | 2 | diseño `/public`+`/market` | Sí |
| Intentos de apertura WS | 24 exitosos planificados (2+22) | 46 (20+2 no deliberadas) | rotación + `max_ws_reconnects` | Sí |
| Streams por conexión | 20 | 1.024 | servidor | Sí |
| Mensajes de datos | no estimado | 5.000.000 | comprobación por tick | Blando; puede parar antes |
| Almacenamiento | 2,80 MB | 128 MiB | total + tope JSONL | Sí; 97,9 % de margen |
| Observaciones | 240 | 20.000 | `take_decisions` | Sí |
| Settle | 4.200 s | 4.200 s | bucle de settle | Sí; último 60m en 6.905 s, margen 895 s |

**Hallazgos concretos y riesgos**

- La base de 720 klines **no es un máximo**: si falta la vela, `resolve_due`
  reintenta cada tick (500 ms) hasta la ventana de tolerancia. Esos intentos
  repetidos solo quedan acotados por la puerta de 2.000 intentos/5.000 de peso.
  Si se agota, la corrida para con `presupuesto_agotado` y deja pendientes con
  causa; puede truncar el settle. No se aumenta el límite ni se cambia el
  comportamiento en este bloque.
- `max_messages` se comprueba por tick, no por mensaje: es un tope blando. Solo
  cuenta datos; a 20 símbolos, `depth20@100ms` aporta ~720.000 mensajes/hora y
  deja ~4,28 M para `aggTrade`. No hay garantía de que el flujo agresor quepa en
  el tope; si se alcanza, la corrida para y no se resuelven más precios.
- `max_ws_reconnects` cuenta reaperturas tras desconexión o fallo (incluye
  cierres normales, no solo errores) y se comprueba por tick;
  `max_http_retries` también es posterior al evento (sobregiro acotado). Los
  topes estrictos de intentos y peso son previos al transporte.
- El límite de 300 conexiones/5 min de USD-M no consta en la documentación UM
  vigente consultada; no se usa como cota. El total de 46 intentos de apertura
  es una cota conservadora calculada, no una medida.

Esta propuesta **no declara el piloto listo**: requiere autorización humana
explícita y aceptar el riesgo de repetición por velas ausentes. No incluye
backfill, order book histórico ni endpoints privados/órdenes.

#### 9.3.1 Propuesta histórica 4 h + 70 min (sustituida)

La propuesta anterior usaba captura 14.400 s + settle 4.200 s, decisión cada
60 s, 20 símbolos y un peso REST aproximado de 16.374 (≈17.193 con 5 % de
reintentos). Su presupuesto está en
`docs/evidence/research/universe_liquidity_v1/pilot_local/presupuesto.json`.
Queda **sustituida** por §9.3; se conserva solo como antecedente y sus cifras no
deben presentarse como vigentes.

### 9.4 Evidencia publicada (muestra pequeña, dataset fuera de Git)

- `docs/evidence/research/universe_liquidity_v1/pilot_local/manifiesto.json`
  (run, versiones, config, hashes, git HEAD).
- `docs/evidence/research/universe_liquidity_v1/pilot_local/resumen.json`
  (resumen regenerado desde lo persistido).
- `docs/evidence/research/universe_liquidity_v1/pilot_local/observaciones_muestra.jsonl`
  (12 filas de muestra).
- `docs/evidence/research/universe_liquidity_v1/pilot_local/presupuesto.json`
  (presupuesto histórico de 4 h, **sustituido**; no vigente).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/`
  (`presupuesto.json` vigente de 1 h + 70 min, `config_efectiva.json`,
  `config_sha256.txt`, `verificacion.txt`, `comando_propuesto.txt`; generado con
  `--budget-only`, no ejecutado).
- Dataset completo (observaciones.jsonl, research.db) fuera de Git; se
  publica solo manifiesto, hashes y muestra pequeña.

### 9.5 Límites del bloque

- Cero conexiones públicas de mercado; cero escrituras en DBs canónicas; sin
  dashboard nuevo, Paper Lab, IA, órdenes, pagos ni móvil; sin integración de
  ramas ni procesos persistentes al finalizar.
- No se declara ventaja, rentabilidad, representatividad estadística ni bot
  listo para operar. El piloto produce observaciones aptas para estudio y un
  presupuesto público revisable; nada más.

### 9.6 Resultados descriptivos de la captura pública ejecutada (offline)

**run_id:** `public-pilot-1h-20261105a`. **Estado:** `corrida_interrumpida_o_cierre_no_acreditado`
(causa de parada `UNKNOWN`; no hay código de salida ni logs de consumo).
**Análisis:** solo lectura, offline, sin conexión a Binance, sin adquisición de datos nuevos.

| Ítem | Valor |
| --- | --- |
| Ciclos de selección | 12 / 12 |
| Observaciones totales | 240 (aptas 128, descartadas 112) |
| Resultados totales | 206 (5m: 115, 15m: 91, 60m: 0) |
| Resultados faltantes (aptas × 3 − generados) | 178, causa UNKNOWN |
| Símbolos observados | 44, repetidos entre ciclos |
| Roles | candidate 144, comparator 96 |
| Precios | libro_mid (inicial) → klines_apertura_1m (posterior; proxy fuentes mixtas) |

**Descartes por motivo (pueden solaparse):** `sin_libro` 66, `sin_flujo` 66,
`dato_obsoleto_flujo` 37, `dato_obsoleto_libro` 15. Distribuidos en los 12
ciclos y en ambos roles; no se concentra solo en el primero.

**Candidatos vs comparadores (solo subconjunto con resultado observado):**

- 5m: candidatos n=97, media −0,0034, mediana −0,0015, desv 0,0126, min −0,0529,
  max 0,0208, positivos 0,402. Comparadores n=18, media −0,0005, mediana −0,0002,
  desv 0,0053, positivos 0,500. Diferencia de medias descriptiva −0,0029. 9
  ciclos con ambos grupos.
- 15m: candidatos n=76, media −0,0123, mediana −0,0072, desv 0,0222, min −0,0858,
  max 0,0188, positivos 0,303. Comparadores n=15, media −0,0012, mediana −0,0024,
  desv 0,0058, positivos 0,333. Diferencia de medias descriptiva −0,0111. 7
  ciclos con ambos grupos.

**Dirección de selección (proxy `move_24h_pct`, no es orden):** a 5m `UP_like`
media −0,0071 (n=31), `DOWN_like` media −0,0017 (n=66); a 15m `UP_like` media
−0,0240 (n=27), `DOWN_like` media −0,0058 (n=49).

**Liquidez/flujo vs retorno (descriptivo, variables al decidir):** correlación
Pearson débil. 5m: delta_ratio −0,052, profundidad 0,133. 15m: delta_ratio 0,034,
profundidad 0,265. Sin patrón monotónico claro por terciles de delta_ratio.

**Veredicto por dimensión:**
- A. Integración técnica: transporte y selección funcionaron; cierre no acreditado.
- B. Calidad/cobertura: 206 resultados resueltos, 60m sin evaluar, suficiencia limitada.
- C. Resultados descriptivos: neto_estado UNKNOWN; no se presentan como P&L.

**Conclusión:** no hay datos suficientes para afirmar una ventaja, alpha o
rentabilidad. Insuficiencia no es ausencia de ventaja. El siguiente paso que más
reduciría incertidumbre es repetir la captura con cierre acreditado y settle
completado para 60m, sin cambiar reglas ni tolerancias.

### 9.7 Embudo corregido y diagnóstico de incorporación (rectificación)

**Estado:** `corrida_interrumpida_o_cierre_no_acreditado` (causa de parada `UNKNOWN`).

**Embudo corregido (verificado contra el dataset original):** los conteos por
rol **no se solapan** (candidate y comparator son mutuamente excluyentes).

| Rol | Seleccionadas | Aptas | Descartadas | Resultados 5m | Resultados 15m | Resultados 60m |
| --- | --- | --- | --- | --- | --- | --- |
| candidate | 144 | 109 | 35 | 97 | 76 | 0 |
| comparator | 96 | 19 | 77 | 18 | 15 | 0 |
| **Total** | **240** | **128** | **112** | **115** | **91** | **0** |

**Tasas de cobertura (sobre aptas / sobre seleccionadas):**
- candidate 5m: 97/109 = 89,0 % / 97/144 = 67,4 %.
- candidate 15m: 76/109 = 69,7 % / 76/144 = 52,8 %.
- comparator 5m: 18/19 = 94,7 % / 18/96 = 18,8 %.
- comparator 15m: 15/19 = 78,9 % / 15/96 = 15,6 %.

**Diagnóstico de incorporación:** los comparadores acumulan descartes porque
se eligen con muestreo aleatorio sin reemplazo (`rng.sample`, seed 42) de
~465 elegibles, con solo 8 por ciclo; la mayoría son `primera_vez` o
`reincorpora` y no tienen libro ni flujo cuando se evalúan (feeds recién
abiertos). Los candidatos son top-12 por prioridad determinista que se repiten
(`permanece` = 122 de 144) y son mayoritariamente aptos.

| Origen de descartes de comparadores (77) | Cantidad | Motivo principal |
| --- | --- | --- |
| `primera_vez` + `reincorpora` (sin libro/flujo) | 44 | carrera de feeds al entrar al seguimiento |
| `permanece` descartados | 33 | dato_obsoleto_flujo (32), dato_obsoleto_libro (5) |

**Corrección de coordinación implementada y verificada (actualizada
2026-11-05):**
el orden del código es `run_cycle()` (selección) → `_restart_feeds()` (abrir
feeds) → corte de evaluación → `take_decisions()`. El calentamiento ya no se
mide con `selection_seconds`: `symbol_warmup_ms = FLOW_HORIZONS_MS["1m"]` = 60 s
(`DECISION_FLOW_HORIZON = "1m"`), es decir, la ventana de flujo que la decisión
necesita, independiente de la cadencia de selección. Cada símbolo nuevo o
reincorporado renueva `symbol_first_seen_ms` al suscribirse y un símbolo que
continúa conserva el suyo.

El bucle automático (`ProductRun`/CLI, sin barrera manual) corta en
`max(corte_actual, min(first_seen) + warmup)` y después avanza `cycle_seconds`;
si tras un corte no se escribió ninguna observación, se reprograma al
`siguiente_calentamiento` pendiente (`_earliest_ready_ms`). Un símbolo que
alcanza la readiness a mitad de ciclo se evalúa antes de la siguiente selección,
y `_symbols_evaluated_this_cycle` garantiza como máximo una observación por
símbolo y ciclo. `decision-gate-file` queda solo como control explícito de las
pruebas de cadena; la ruta productiva no usa barrera.

La corrección se verificó con `tests/test_recorrido_productivo.py` (6 pruebas)
y `tests/test_research_pilot.py` (28 pruebas, 7 de ellas de cadena
sincronizada): selección real con candidatos y comparadores, suscripción de
feeds, recepción confirmada antes del corte, evaluación automática tras el
calentamiento de 60 s, símbolos nuevos/reincorporados sin cobertura ficticia y
con nuevo periodo y nueva oportunidad de evaluación, fuente ausente con motivo
explícito, y una observación por símbolo y ciclo. Evidencia:
`docs/evidence/coordinacion-20261105/`.

**Qué queda UNKNOWN:** 33 descartes de comparadores `permanece` (mayoritariamente
`dato_obsoleto_flujo`); no se atribuye a baja liquidez, rotación o transporte
sin demostrar la secuencia de disponibilidad por símbolo.

**Evidencia publicada (muestra pequeña, dataset fuera de Git):**
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/rectificacion_embudo_publica.md` (rectificación identificable del embudo: conteos por rol, diagnóstico de incorporación, reproducción del recorrido productivo y decisión de no modificar el código productivo; sustituye las cifras de embudo del informe inicial).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/embudo_publica.json` (tabla pequeña del embudo).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/informe_analisis_offline.md` (informe inicial, conservado como antecedente).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/rectificacion_analisis_offline_v2.md` (rectificación v2: unidades, comparación por ciclo y símbolo, asociaciones reproducibles).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline_v2.json` (tablas pequeñas v2).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline.json` (tablas v1, conservadas como antecedente).
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/manifiesto_corrida_publica_1h.json`
- `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/diagnostico_corrida_publica_1h.md`
- Scripts: `scripts/analisis_offline_captura_publica.py`, `scripts/diagnostico_embudo_publica.py`
- Pruebas: `tests/test_analisis_offline_captura_publica.py` (9 passed),
  `tests/test_embudo_publica.py` (7 passed),
  `tests/test_recorrido_productivo.py` (recorrido productivo con proveedores loopback y CLI del piloto).
- Dataset completo y derivados detallados fuera de Git; solo manifiesto, hashes y muestra se publican.
