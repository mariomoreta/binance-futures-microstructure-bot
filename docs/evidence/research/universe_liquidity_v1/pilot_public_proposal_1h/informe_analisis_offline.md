# Informe de análisis offline — captura pública public-pilot-1h-20261105a

**run_id:** `public-pilot-1h-20261105a`
**Rama / base:** `research/universe-liquidity-v1` en `f6eb22afa3e35f7e1ed0305e184bec81881b7991`
**Estado de la corrida:** `corrida_interrumpida_o_cierre_no_acreditado` (causa de parada: `UNKNOWN`)
**Análisis:** solo lectura, offline, sin conexión a Binance, sin adquisición de datos nuevos.
**Script:** `scripts/analisis_offline_captura_publica.py`
**Pruebas:** `tests/test_analisis_offline_captura_publica.py` (5 passed)
**Tablas pequeñas (Git):** `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline.json`
**Derivados detallados (fuera de Git):** `C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\analisis_completo.json`

---

## A. Calidad y sesgos del dataset

| Ítem | Valor |
| --- | --- |
| Ciclos de selección completados | 12 / 12 |
| Observaciones totales | 240 |
| Observaciones aptas | 128 |
| Observaciones descartadas | 112 |
| Resultados totales | 206 |
| Resultados 5m | 115 |
| Resultados 15m | 91 |
| Resultados 60m | 0 (NO EVALUADO) |
| Resultados faltantes (aptas × 3 − generados) | 178 (causa UNKNOWN) |
| Símbolos observados | 44 (repetidos entre ciclos) |
| Roles | candidate 144, comparator 96 |
| Versión de política | research-selector-v2 (12 ciclos) |

**Descartes por motivo (pueden solaparse; no suman obligatoriamente 112):**
- `sin_libro`: 66
- `sin_flujo`: 66
- `dato_obsoleto_flujo`: 37
- `dato_obsoleto_libro`: 15

Los descartes se distribuyen a lo largo de los 12 ciclos (no se concentran solo en el primero) y afectan a candidatos y comparadores (comparator: sin_libro 44 / sin_flujo 44; candidate: sin_libro 22 / sin_flujo 22). No hay evidencia para atribuir la causa a rotación, baja liquidez o fallo de transporte.

**Sesgos conocidos:**
- Las 178 observaciones aptas sin resultado no se tratan como cero; su causa es UNKNOWN.
- El horizonte 60m tiene 0 resultados resueltos: queda sin evaluar.
- Los símbolos se repiten entre ciclos y una observación puede aportar dos horizontes, por lo que los 206 resultados no son 206 muestras independientes.
- La corrida cerró sin acreditar causa (no hay código de salida ni logs de consumo); no se puede afirmar que completó el settle.

**Precios y costes:** el piloto usa `libro_mid` como precio inicial y `klines_apertura_1m` como precio posterior. Es un **proxy de fuentes mixtas**, no un retorno mid-to-mid ni P&L. `neto_estado = UNKNOWN` en todos los resultados; no se introdujeron costes arbitrarios.

---

## B. Candidatos frente a comparadores

Analizados 5m y 15m por separado. La comparación solo representa al subconjunto con resultado observado (no a las 128 aptas completas). Se prioriza la comparación dentro del mismo ciclo: 9 ciclos tienen ambos grupos a 5m y 7 a 15m.

### 5 minutos

| Métrica | Candidatos | Comparadores |
| --- | --- | --- |
| n resultados | 97 | 18 |
| n observaciones originales | 97 | 18 |
| n símbolos | 15 | 8 |
| n ciclos | 9 | 9 |
| Media | −0,00340 | −0,00054 |
| Mediana | −0,00150 | −0,00021 |
| Desv. estándar | 0,01263 | 0,00527 |
| Mínimo | −0,05290 | −0,01829 |
| Máximo | 0,02084 | 0,00669 |
| Proporción positivos | 0,402 | 0,500 |
| Diferencia de medias descriptiva (cand − comp) | \multicolumn{2}{c}{−0,00286} |

### 15 minutos

| Métrica | Candidatos | Comparadores |
| --- | --- | --- |
| n resultados | 76 | 15 |
| n observaciones originales | 76 | 15 |
| n símbolos | 14 | 8 |
| n ciclos | 7 | 7 |
| Media | −0,01225 | −0,00117 |
| Mediana | −0,00724 | −0,00245 |
| Desv. estándar | 0,02220 | 0,00578 |
| Mínimo | −0,08582 | −0,01427 |
| Máximo | 0,01880 | 0,01030 |
| Proporción positivos | 0,303 | 0,333 |
| Diferencia de medias descriptiva (cand − comp) | \multicolumn{2}{c}{−0,01108} |

### Dirección de selección (proxy: `move_24h_pct`)

Las observaciones individuales no traen campo `side`; se usa el signo de `move_24h_pct` como proxy de la dirección que motivó la selección (`UP_like` si > 0, `DOWN_like` si < 0).

**5m:** `UP_like` n=31, media −0,0071, positivos 0,323; `DOWN_like` n=66, media −0,0017, positivos 0,439.
**15m:** `UP_like` n=27, media −0,0240, positivos 0,259; `DOWN_like` n=49, media −0,0058, positivos 0,327.

No hay agrupación que oculte signos; UP_like y DOWN_like se reportan por separado. Esto **no** es una orden de compra ni de venta.

**Lectura descriptiva:** en ambos horizontes la media de candidatos es más negativa que la de comparadores, pero el número de comparadores es pequeño (18 y 15), las dispersiones son altas y las muestras no son independientes. No se interpreta como efecto causal, alpha ni rentabilidad.

---

## C. Liquidez / flujo frente a movimiento posterior

Se fijaron de antemano dos métricas exploratorias, calculadas solo con variables disponibles al decidir (libro y flujo en T), sin usar resultados posteriores para elegirlas:

1. `delta_ratio` (sesgo agresor de la ventana de decisión).
2. `profundidad_notional_top20` = `bid_notional_top20 + ask_notional_top20` (USDT).

Cobertura: 206 filas con ambas métricas presentes (denominador completo para los resultados disponibles).

| Horizonte | Pearson `delta_ratio` vs retorno | Pearson profundidad vs retorno | n |
| --- | --- | --- | --- |
| 5m | −0,052 | 0,133 | 115 |
| 15m | 0,034 | 0,265 | 91 |

**Retorno medio por tercil de `delta_ratio`:**
- 5m: bajo −0,0019; medio −0,0032; alto −0,0038 (sin patrón monotónico claro).
- 15m: bajo −0,0082; medio −0,0127; alto −0,0104 (sin patrón monotónico claro).

**Lectura descriptiva:** las correlaciones son débiles y la muestra es pequeña y no independiente. La profundidad muestra una correlación descriptiva más marcada a 15m (0,265), pero no es estadísticamente concluyente ni implica causalidad. No se optimizan umbrales ni se propone estrategia.

---

## D. Qué está respaldado y qué sigue indeterminado

**Respaldado:**
- El transporte, la selección automática (`research-selector-v2`), el universo real (942 símbolos, 465 elegibles) y la generación de observaciones funcionaron en 12 ciclos.
- El dataset persistido es reproducible: hashes verificados contra el manifiesto publicado.
- Las pruebas focalizadas pasan (denominadores, faltantes no-cero, separación de horizontes/roles, símbolos repetidos, ciclo sin grupo comparable).

**Indeterminado:**
- Causa de parada de la corrida: UNKNOWN (sin código de salida, sin logs de consumo, archivos de control de fin ausentes).
- Si el settle completó los 60m: hay 0 resultados a 60m, por lo que queda NO EVALUADO.
- Si existe una ventaja real de candidatos sobre comparadores: las diferencias descriptivas son pequeñas, con comparadores escasos y alta dispersión.
- Cualquier asociación entre liquidez/flujo y retorno posterior: correlaciones débiles, muestra pequeña, no independiente.
- Rentabilidad, alpha, P&L o efecto causal: no se pueden afirmar.

---

## E. El único siguiente paso que más reduciría incertidumbre

Repetir la captura con un **cierre acreditado** (código de salida, logs de consumo, archivos de control de fin) y permitir que el **settle complete los 60m** antes de calcular retornos, sin cambiar reglas, tolerancias ni estrategia. Solo entonces la comparación candidatos vs comparadores y el horizonte 60m tendrían denominadores completos para una lectura descriptiva fiable.

No se propone otra captura automáticamente ni se modifica la política según este resultado.

---

**Descargo:** este es un informe descriptivo de una única captura limitada (44 símbolos, una hora, cierre no acreditado). Una captura con poca cobertura útil acredita transporte, no suficiencia del dataset. Cero datos válidos exigiría diagnóstico, no cambiar tolerancias. No se presentan retornos brutos como P&L.
