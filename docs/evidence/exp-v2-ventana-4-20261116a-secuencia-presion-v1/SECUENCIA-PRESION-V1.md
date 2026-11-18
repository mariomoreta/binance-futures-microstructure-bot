# DETECTOR EXPERIMENTAL SECUENCIA-PRESION-V1 — documentación de implementación

Contexto: bloque de investigación offline autorizado el 2026-11-16
("PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS, LOCAL Y SIN MERCADO").
Sin Binance, consultas públicas, capturas, órdenes, relanzamientos, cambios en
la estrategia productiva, dashboard, servicios, supervisores ni dependencias
nuevas.

Este detector es EXPERIMENTAL, sin validación económica. No conecta al camino
productivo ni recibe autorización para operar. La regla operativa actual
permanece congelada como referencia.

> **Rectificación 2026-11-17 (base `619d357`).** Este documento declaraba que un
> corte con ventanas válidas separadas por huecos dejaba el archivo sin decisión
> (`r is None`) y que la ventana 4 tenía "0 ternas evaluables". Ambas
> afirmaciones se corrigen sin borrar el antecedente: ahora el corte persiste
> `DATOS_INSUFICIENTES` y la cobertura de los agregados de un minuto devuelve
> **501 ternas acreditadas** (sección 5.2). Evidencia reproducible en
> `docs/evidence/secuencia-presion-v1-correcciones-20261117/`.

## 1. Qué reconoce exactamente el detector

El detector SECUENCIA-PRESION-V1 reconoce una secuencia temporal de tres
ventanas consecutivas y completas de UN MINUTO en las que simultáneamente:

1. La presión agresora neta (`buy_notional − sell_notional`, USDT) es a favor
   de la dirección candidata y creciente en magnitud relativa a la profundidad;
2. La profundidad contraria (libro del lado opuesto a la posición) disminuye;
3. El precio de cierre conocido de cada ventana avanza en la dirección candidata.

### Definición mecánica (fijada antes de cualquier evaluación económica)

Para cada ventana k (1 minuto completa):

- `F_k = compras_agresoras_k − ventas_agresoras_k` (USDT,
  de `flujo.buy_notional − flujo.sell_notional`)
- `D_k = profundidad contraria` (USDT):
  - LONG → `ask_notional_top20` (profundidad de venta)
  - SHORT → `bid_notional_top20` (profundidad de compra)
- `Q_k = s × F_k / D_k`, con `s = +1` (LONG) / `−1` (SHORT)

Primera definición mecánica:
- `0 < Q_1 < Q_2 < Q_3`
- `D_1 > D_2 > D_3 > 0`
- los cierres conocidos de las tres ventanas avanzan en la dirección candidata
  (LONG: `precio_1 < precio_2 < precio_3`; SHORT: `precio_1 > precio_2 > precio_3`)

### Salidas del detector

| Salida | Significado |
| --- | --- |
| `LONG_EXPERIMENTAL` | Secuencia cumple el patrón para LONG |
| `SHORT_EXPERIMENTAL` | Secuencia cumple el patrón para SHORT |
| `SIN_PATRON` | Hay una terna de 3 ventanas válidas **contiguas** que no cumple el patrón |
| `DATOS_INSUFICIENTES` | El corte no alcanza una terna contigua (menos de 3 ventanas válidas, huecos o solapamientos); **se persiste** una fila con símbolo, corte, ventanas examinadas y motivo |

Cada salida incluye: condiciones cumplidas/faltantes, las ventanas usadas (o las
examinadas, con su motivo de exclusión), F_k, D_k, Q_k, precios, timestamps,
procedencia, versión y hash de configuración, motivo explícito. Las filas
`DATOS_INSUFICIENTES` identifican el corte (`<symbol>|corte:<corte_ms>`) y las
ternas se identifican por la `observation_id` de su tercera ventana.

Ausentes, no finitos, importes inválidos, profundidad no positiva, ventanas
incompletas o huecos impiden acreditar el patrón. Nunca UNKNOWN → cero.
No se mezclan "no se cumple el patrón" con "no podemos evaluarlo", y un corte
sin terna nunca deja el archivo sin decisión.

### Reglas temporales (acreditadas en esta corrección)

- Las ventanas deben ser **realmente contiguas**: `ventana_inicio_ms[k+1] ==
  ventana_fin_ms[k]`, mismo símbolo, misma `ventana_ms` (60s). Un hueco rompe
  la secuencia; una nueva secuencia comienza después.
- Se evalúan **ternas contiguas sucesivas** (1-2-3, luego 2-3-4, 3-4-5, …) a
  medida que llegan los datos. Una decisión emitida se **conserva**
  (inmutabilidad); repetir el mismo corte no duplica. Una entrada contradictoria
  con la misma identidad produce conflicto explícito, no sustitución silenciosa.
- El **instante de detección** es el máximo de las disponibilidades de las tres
  ventanas (incluidos precios). Nunca es anterior a la finalización de las tres
  ventanas ni a la disponibilidad acreditada de cualquier componente.

### Precio e integridad

- El `stop_px`/`precio_cierre` es el `precio_base` (mid del libro) en
  `decision_ms`, no se asume como cierre OHLC de un minuto sin verificarlo.
- Se verifican todos los importes indispensables: ausentes, no finitos o
  inválidos no equivalen a SIN_PATRON ni a cero.
- La integridad se acredita por ventana cuando las fuentes lo permiten;
  de lo contrario se conserva la limitación.

## 2. Código y comando local reproducible

Archivo: `scripts/secuencia_presion_v1.py`

CLI:
```powershell
python scripts/secuencia_presion_v1.py --fuente <observaciones.jsonl> --salida <decisiones.jsonl>
```

- `--fuente`: ruta al JSONL de observaciones (formato del piloto,
  `kind: observacion`)
- `--salida`: ruta al JSONL de salida con una fila por terna contigua
  evaluada (LONG/SHORT/SIN_PATRON) y una fila `DATOS_INSUFICIENTES` por corte
  sin terna contigua
- Trabaja sin red, genera decisiones reconstruibles desde lo persistido
- No crea motor de trading, framework de aprendizaje ni servicio

### Estructura de la configuración congelada

```json
{
  "version": "SECUENCIA-PRESION-V1",
  "ventana_ms": 60000,
  "num_ventanas": 3,
  "profundidad_niveles": 20,
  "profundidad_lado_contrario": true,
  "requiere_ventana_completa": true,
  "requiere_integridad_valida": true,
  "requiere_ventanas_contiguas": true,
  "condiciones": {
    "q_positivo_creciente": true,
    "profundidad_contraria_decreciente": true,
    "precio_avanza_en_direccion": true
  },
  "flujo_fuente": "aggTrade",
  "profundidad_fuente": "depth20@100ms"
}
```

SHA-256 de la configuración: calculado sobre el JSON serializado con
`sort_keys=True`.

## 3. Traza LONG y SHORT (datos sintéticos de prueba)

### Traza LONG (3 ventanas contiguas, capacidad 1 aislada)

| Ventana | decision_ms | buy_notional | sell_notional | F_k | ask_notional_top20 (D_k) | Q_k | precio_cierre |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | T0+0 | 100.0 | 20.0 | +80.0 | 1000.0 | +0.080 | 100.00 |
| 2 | T0+60s | 150.0 | 20.0 | +130.0 | 900.0 | +0.144 | 100.50 |
| 3 | T0+120s | 200.0 | 20.0 | +180.0 | 800.0 | +0.225 | 101.00 |

Comprobaciones:
- Q: 0.080 < 0.144 < 0.225 ✓ (positivo y creciente)
- D: 1000 > 900 > 800 ✓ (decreciente y positivo)
- precio: 100.00 < 100.50 < 101.00 ✓ (avanza en LONG)
→ **LONG_EXPERIMENTAL**

### Traza SHORT (3 ventanas contiguas, capacidad 1 aislada)

| Ventana | decision_ms | buy_notional | sell_notional | F_k | bid_notional_top20 (D_k) | Q_k | precio_cierre |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | T0+0 | 20.0 | 100.0 | −80.0 | 1000.0 | +0.080 | 100.00 |
| 2 | T0+60s | 20.0 | 150.0 | −130.0 | 900.0 | +0.144 | 99.50 |
| 3 | T0+120s | 20.0 | 200.0 | −180.0 | 800.0 | +0.225 | 99.00 |

Comprobaciones:
- Q: 0.080 < 0.144 < 0.225 ✓ (positivo y creciente)
- D: 1000 > 900 > 800 ✓ (decreciente y positivo)
- precio: 100.00 > 99.50 > 99.00 ✓ (avanza en SHORT)
→ **SHORT_EXPERIMENTAL**

## 4. Pruebas, resultados y códigos observados

Archivo: `tests/test_secuencia_presion_v1.py` — **24 pruebas pasando**
(rectificado el 2026-11-17; la versión publicada declaraba 18 y exigía
`r is None` para ventanas no contiguas, que era el defecto corregido en el
bloque de correcciones).

| Prueba | Resultado |
| --- | --- |
| secuencia LONG válida | PASSED → LONG_EXPERIMENTAL |
| secuencia SHORT válida | PASSED → SHORT_EXPERIMENTAL |
| presión creciente, profundidad no disminuye | PASSED → SIN_PATRON |
| profundidad decreciente, sin presión alineada | PASSED → SIN_PATRON |
| precio sin confirmación direccional | PASSED → SIN_PATRON |
| ventana incompleta | PASSED → DATOS_INSUFICIENTES |
| dato inválido (profundidad no positiva) | PASSED → DATOS_INSUFICIENTES |
| ventanas no contiguas (huecos) | PASSED → DATOS_INSUFICIENTES persistido (antes: None) |
| ventanas solapadas | PASSED → DATOS_INSUFICIENTES con solapamiento diagnosticado |
| terna contigua válida que no cumple el patrón | PASSED → SIN_PATRON (no DATOS_INSUFICIENTES) |
| ternas sucesivas detectan posterior | PASSED → LONG en terna 3-5 |
| datos futuros no cambian decisión emitida | PASSED → decisión conservada |
| símbolos distintos no comparten historia | PASSED → LONG y SHORT independientes |
| repetir mismo corte no duplica | PASSED → misma decisión |
| disponibilidad tardía de ventana anterior | PASSED → detección fechada con disp de la terna |
| precio no disponible → DATOS_INSUFICIENTES | PASSED → DATOS_INSUFICIENTES |
| conflicto de identidad explícito | PASSED → no sustitución silenciosa |
| CLI real con JSONL sintético → LONG | PASSED → exit_code 0 |
| CLI real con 2 ventanas → DATOS_INSUFICIENTES | PASSED → exit_code 0 |
| CLI real con ternas sucesivas | PASSED → detecta terna posterior |
| CLI real con huecos → persiste DATOS_INSUFICIENTES | PASSED → archivo con 1 fila (antes: 0 bytes) |
| CLI real repetir el mismo corte | PASSED → sin fila nueva ni cambio de bytes |
| CLI real con un corte nuevo posterior | PASSED → añade fila sin alterar la anterior |

Todas las pruebas ejecutan el código productivo del detector (no fórmulas
aisladas). Códigos de salida observados: 0 (éxito), 3 (conflicto de identidad).

La evidencia de la corrección (comandos, códigos de salida y hashes) está en
`docs/evidence/secuencia-presion-v1-correcciones-20261117/`.

## 5. Cobertura real y faltantes exactos

Se inspeccionó el dataset de la ventana 4
(`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a`) en modo solo
lectura. Hay **dos poblaciones distintas** y no se suman:

- **Población A — observaciones del piloto** (`observaciones.jsonl`): 196
  observaciones de decisión. Miden si el piloto pudo observar el minuto, no si
  existe una terna.
- **Población B — agregados de un minuto** (`research_flow_1m`,
  `research_book_1m`): filas por `(symbol, bucket_start)` que, emparejadas y
  acreditadas, forman las ternas evaluables.

La sección 5.1 conserva la medición publicada de la población A. La sección 5.2
es la medición rectificada de la población B (2026-11-17).

### 5.1 Población A — observaciones del piloto

| Métrica | Valor |
| --- | --- |
| Observaciones totales | 196 |
| Observaciones aptas (`apto_para_evaluacion=True`) | 161 |
| Observaciones descartadas | 35 |
| Símbolos únicos | 34 |
| Observaciones con flujo (buy/sell notional) | 196 / 196 |
| Observaciones con libro (bid/ask top-20) | 196 / 196 |
| Observaciones con precio base | 196 / 196 |
| Observaciones con ventana de flujo completa | 183 / 196 |
| Observaciones con integridad válida | 33 / 196 |
| Observaciones que cumplen TODOS los requisitos | **20 / 196** |
| Motivos de descarte (solapables) | `dato_obsoleto_flujo` 28, `flujo_ventana_incompleta` 13, `dato_obsoleto_libro` 1 |

### 5.2 Población B — agregados de un minuto (rectificado 2026-11-17)

Requisito que limita al resto: **integridad por intervalo**.

| Etapa | Valor |
| --- | --- |
| Parejas iniciales `(symbol, bucket_start)` en ambas tablas | 1190 |
| Claves de flujo sin contraparte de libro | 75 |
| Claves de libro sin contraparte de flujo | 7 |
| Ternas sobre ventanas de flujo (referencia, sin contraparte) | 1107 |
| Ternas sobre parejas | 1032 |
| Ventanas acreditadas tras completitud | 1190 (0 excluidas) |
| Ventanas acreditadas tras integridad por intervalo | 1005 (185 excluidas) |
| Ventanas acreditadas tras valores válidos | 1005 (0 excluidas) |
| Ventanas acreditadas tras precio | 1005 (0 excluidas) |
| Ventanas acreditadas tras disponibilidad | 1005 (0 excluidas) |
| **Ternas acreditadas finales** | **501** |
| **Símbolos con al menos una terna** | **43** |

Motivos de exclusión de las 185 ventanas (solapables):

- 183 con `libro_degradado` y `libro_huecos_profundidad` (los mismos 183
  intervalos; dos motivos cada uno),
- 2 con `flujo_data_quality_no_ok` (`PARTIAL_OK`).

Los 29 intervalos con un lado en cero **registrado** son admisibles y no se
excluyen. El precio acreditado es `price_close` de `research_flow_1m`, cierre
del agregado de operaciones `aggTrade`; no es `libro_mid` ni precio ejecutable.
La disponibilidad acreditada es el máximo de `as_of_ms` de flujo y libro con
ambos presentes; no es `bucket_end` ni el instante efectivo de detección.

### 5.3 Por qué se rectifica la conclusión publicada

La publicación del 2026-11-16 declaró "0 ternas evaluables" y "0 símbolos con
≥3 ventanas válidas". Esa conclusión mezclaba la población A (20/196
observaciones con todos los campos del streaming) con la población B, y
contradecía su propia cadena `1107 → 1032 → 501 → 501`: no existía ningún
requisito posterior a precio que eliminara esas 501 ternas. La regeneración con
el extractor corregido reproduce la cadena exacta y devuelve **501 ternas
acreditadas** sobre 1005 ventanas. Terna acreditada no es patrón detectado ni
rentabilidad: este documento no ejecuta el detector sobre esas ternas ni calcula
retornos.

### 5.4 Listado mínimo de campos, resolución e historia previa para futura adquisición

Para ejecutar el detector en una captura futura se requiere, por símbolo y
ventana de 1 minuto:

| Campo | Origen | Unidades | Resolución | Nota |
| --- | --- | --- | --- | --- |
| `buy_notional` | flujo (aggTrade) | USDT | 1 min | Compras agresoras en la ventana |
| `sell_notional` | flujo (aggTrade) | USDT | 1 min | Ventas agresoras en la ventana |
| `bid_notional_top20` | libro (depth20@100ms) | USDT | 1 min | Profundidad de compra top-20 |
| `ask_notional_top20` | libro (depth20@100ms) | USDT | 1 min | Profundidad de venta top-20 |
| `precio_base` | ver definición | precio | 1 min | **Observación del piloto:** mid del libro. **Agregado `research_flow_1m`:** `price_close`, cierre del agregado `aggTrade`. No son intercambiables ni es un precio ejecutable |
| `ventana_completa` | flujo | booleano | 1 min | La ventana de 1 min está completa |
| `integridad` (sin huecos, sin invalidos, sin cruce) | flujo/libro | booleano | 1 min | Integridad del streaming |
| `disponibilidad.max_ms` | disponibilidad | ms | 1 min | Instante en que toda la evidencia estaba disponible |
| `decision_ms` | observación | ms | 1 min | Instante real de evaluación (reloj del piloto) |
| `symbol` | observación | ticker | — | Identidad del contrato |
| `observation_id` | observación | id | — | Identificador único de la ventana |

**Historia previa necesaria:** al menos 3 ventanas consecutivas por símbolo
(orden cronológico por `decision_ms`), cada una con los campos anteriores
completos y sin huecos en el feed.

**No se deben reconstruir ventanas de 30 segundos desde agregados de 1
minuto.** Cada ventana debe ser una ventana de 1 minuto completa e
independiente, con su propio flujo, libro y precio.

## 6. Qué queda preparado para la siguiente validación

Se deja una ficha breve para la prueba independiente posterior:

- **Observación de un minuto:** cada ventana representa 1 minuto de datos de
  flujo agresor y profundidad top-20, capturada en un ciclo de decisión.
- **Horizonte principal propuesto (rectificado 2026-11-17):** **5 minutos**
  para la futura evaluación del detector. La hipótesis de magnitud a **60
  minutos** queda **diferida**: no se evalúa en este bloque, no se usa para
  aceptar ni descartar el detector y no se declara como horizonte vigente.
- **Precio y momento de entrada causal:** `precio_base` (libro_mid) en
  `decision_ms`, el instante real de evaluación del piloto. No se usa
  `bucket_end` ni precios retrotrados.
- **Tratamiento de alertas repetidas del mismo episodio:** una vez emitida una
  decisión (LONG_EXPERIMENTAL o SHORT_EXPERIMENTAL) sobre una secuencia de 3
  ventanas, datos futuros no la cambian. El detector emite una decisión por
  símbolo basada en las primeras 3 ventanas válidas que cumplan (o las
  primeras 3 válidas si ninguna cumple → SIN_PATRON).
- **Comparación con referencia sencilla:** comparar contra una regla de
  dirección por signo de `move_24h_pct` (sin confirmación de flujo), con
  controles del mismo universo (mismos símbolos, mismos ciclos).
- **Costes, pérdidas, movimiento adverso y abstenciones:** no aplicable en
  esta fase (no hay entradas, posiciones ni P&L). El detector solo emite
  detecciones mecánicas.
- **Criterio económico para continuar, descartar o declarar insuficiencia:**
  si una captura futura acredita ≥3 ventanas contiguas por símbolo con patrones
  detectables, proceder a la evaluación del detector con horizonte de 5 min. La
  magnitud a 60 min queda diferida a un bloque posterior con autorización
  propia. Si no hay cobertura suficiente (como en la población A de esta
  captura), declarar insuficiencia y no operar.

**Distingue reconocimiento mecánico de utilidad predictiva y operativa:** el
detector reconoce un patrón mecánico (presión creciente, profundidad
decreciente, precio avance). Esto no implica utilidad predictiva ni
rentabilidad. La validación económica requiere una captura nueva con su propia
autorización.

## 7. Lo que NO acredita

Rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja de
candidato sobre comparador, generalización (una hora de captura,
dependencia temporal, símbolos repetidos). El detector no se conecta al
camino productivo. No se presentan detecciones sintéticas como oportunidades
reales.

## 8. Artefactos

- Código: `scripts/secuencia_presion_v1.py`
- Pruebas: `tests/test_secuencia_presion_v1.py` (24 passed)
- Extractor de cobertura: `scripts/extraer_cobertura_research_db.py`
- Pruebas del extractor: `tests/test_extraer_cobertura_research_db.py`
  (7 passed)
- Regresiones: `test_analisis_contrafactual_ventana4.py` (16 passed),
  `test_operativo_replay_offline.py` (7 passed)
- Evidencia de cobertura: sección 5 de este documento (poblaciones A y B) y
  `docs/evidence/secuencia-presion-v1-correcciones-20261117/` (evidencias A, B
  y C con comandos, códigos de salida, hashes y JSON regenerado) — basado en
  `observaciones.jsonl` y `research.db` de la ventana 4, leído en modo solo
  lectura
- SHA base del detector: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`
- SHA base de las correcciones: `619d357443ace0aa7c0b939f07b6a1457265adfd`
- SHA del análisis original: commit `4a7df47` (detector SECUENCIA-PRESION-V1)
- SHA del bloque de correcciones: `11c7af7bc04c99faf20de85300590121dfbc9742`
  (`research/universe-liquidez-v1`, mensaje "Corrige caso sin terna y
  extractor de cobertura (SECUENCIA-PRESION-V1)")

## 9. Lo que NO se hizo

No se creó motor de trading, framework de aprendizaje, servicio, supervisor,
dashboard ni dependencias nuevas. No se conectó a Binance. No se hicieron
capturas. No se cambiaron entradas, stops, notional ni capacidad del
experimento vigente. No se calculó rentabilidad ni se exploraron umbrales
sobre esta captura.
