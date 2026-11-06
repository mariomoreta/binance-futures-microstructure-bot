# Informe rectificado — universo-liquidez-v1 (captura pública public-pilot-1h-20261106a), análisis v2

run_id: `public-pilot-1h-20261106a` · commit base: `046f69f1d21ea46ab14b6f262471d4de4d943689` (HEAD verificado, coincide con base esperada) · código de salida del proceso: `UNKNOWN` (no recuperable retrospectivamente).

Script: `scripts/analisis_universo_liquidez_v2.py` (versión identificable v2, argumentos explícitos `--jsonl / --out-derivados / --out-tablas / --run_id`). Pruebas: `tests/test_analisis_universo_liquidez_v2.py` (6 passed, incl. invocación del CLI real sobre JSONL temporales). Muestra del dataset externo validada independientemente (100 % de retornos recalculados coinciden con los persistidos). Dataset y derivados voluminosos fuera de Git; solo script, pruebas, informe y tablas pequeñas se publican. `neto_estado=UNKNOWN` donde no existan costes ni ejecución acreditados.

## 1. Verificación de fuentes y conservación de resultados originales

Hashes del dataset original verificados contra el manifiesto publicado en `docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/`. Dataset y derivados anteriores (v1) no se modificaron ni sobrescribieron: el análisis v2 genera derivados en un directorio nuevo (`...\derivados\analisis_universo_liquidez_v2\`) y tablas en un archivo nuevo (`resumen_analisis_universo_liquidez_v2.json`).

Conteos comprobados desde registros (valores esperados confirmados):

| Métrica | Valor |
|---|---|
| Observaciones emitidas | 216 |
| Observaciones aptas | 168 |
| Observaciones descartadas | 48 |
| Resultados | 504 (168 × 5m, 15m, 60m) |
| Resultados pendientes | 0 |
| Duplicados `observation_id` | 0 |
| Pares `(observation_id, horizon)` duplicados | 0 |
| Resultados huérfanos | 0 (504/504 con padre apto) |
| `neto_estado` | UNKNOWN (504/504) |

## 2. Embudo reconstruido desde registros de selección (corrección principal)

El análisis v1 contaba `kind="observacion"` y llamaba «seleccionadas» a esas filas. El v2 separa la selección (registros de ciclo, campos `selected` y `comparator`) de las observaciones emitidas (`kind="observacion"`), distinguiendo ciclo de selección (`reference_ms`) y ciclo de decisión (`decision_ms`).

### Selección desde registros de ciclo

| Rol | Seleccionados | Observaciones emitidas | Selecciones sin observación | Aptas | Descartadas |
|---|---|---|---|---|---|
| candidate | 144 | 136 | 8 | 126 | 10 |
| comparator | 96 | 80 | 16 | 42 | 38 |
| Total | 240 | 216 | 24 | 168 | 48 |

- 24 selecciones no tuvieron observación emitida (8 candidate, 16 comparator). Estas no se cuentan como observaciones ni como aptas/descartadas.
- Los 216 observados, 168 aptos y 48 descartados se mantienen como comprobaciones esperadas, pero **no equivalen al denominador inicial de selección** (240).

### Ciclo de selección vs ciclo de decisión

Cada ciclo de selección (`reference_ms`) se empareja con un ciclo de decisión (`decision_ms`) por orden cronológico (12 de cada uno). `decision_ms` es aproximadamente `reference_ms + ~85 s` (tiempo entre selección y evaluación).

### Incorporación al seguimiento (solo cuando la secuencia persistida lo permite)

Se reconstruye por símbolo a partir del ciclo de primera aparición (`reference_ms` del ciclo donde el símbolo se selecciona por primera vez):
- **Primera incorporación**: ciclo donde el símbolo aparece por primera vez.
- **Permanencia**: símbolo aparece en el ciclo de decisión inmediato anterior.
- **Reincorporación**: símbolo apareció antes pero no en el ciclo anterior inmediato.

Esta clasificación es aplicable a las 216 observaciones emitidas (todas tienen `symbol` y `decision_ms` vinculables a un ciclo de selección). 28 símbolos únicos aparecen a lo largo de los 12 ciclos; 12 símbolos están en todos los ciclos, 16 en menos ciclos (rotación, n_rotaciones_salida = 25).

### Comparadores aptos por ciclo

| Ciclo (idx) | Comparadores aptos |
|---|---|
| 0 | 8 |
| 1 | 1 |
| 2 | 4 |
| 3 | 2 |
| 4 | 7 |
| 5 | 3 |
| 6 | 3 |
| 7 | 1 |
| 8 | 5 |
| 9 | 1 |
| 10 | 6 |
| 11 | 1 |

Cuatro ciclos (1, 7, 9, 11) tienen **un solo comparador apto**. Esto limita la solidez de la comparación en esos ciclos y se debe al descarte concentrado de comparadores por `dato_obsoleto_flujo` (38 de 38 descartes de comparator).

## 3. Disponibilidad para la asociación (derivada de la entrada, no fija)

Se eliminó la afirmación literal «168/168 aptas con campo completo». Ahora se calcula desde la entrada:

| Métrica | Valor |
|---|---|
| Filas para asociación (observación × horizonte) | 504 |
| Campos ausentes o no finitos | 0 |
| Profundidad cero o inválida | 0 |
| Ventana de flujo incompleta | 0 |
| Parejas válidas por horizonte (5m / 15m / 60m) | 168 / 168 / 168 |

Regla de denominador: si `bid_notional_top20 + ask_notional_top20` es 0 o None → ratio `None` (nunca se convierte en cero). En este dataset el denominador nunca es cero.

Identidad de corrida: todos los registros pertenecen a `public-pilot-1h-20261106a`; no se detectó mezcla de corridas.

## 4. Comparación candidatos vs comparadores (5m / 15m / 60m)

Retornos en fracción (0.01 = 1 %). Precio inicial = `libro_mid`, precio posterior = `klines_apertura_1m` (proxy de fuentes mixtas, no mark-to-mid, no P&L). `neto_estado=UNKNOWN`.

### 5m
- Candidatos: n=126, media +0,305 %, mediana +0,116 %, desv 1,50 %, mín −4,05 %, máx +8,28 %, 61 % positivos. Media por símbolo (igual peso): +0,248 %.
- Comparadores: n=42, media −0,023 %, mediana −0,069 %, desv 0,24 %, mín −0,47 %, máx +0,58 %, 38 % positivos. Media por símbolo: −0,026 %.
- Diferencia medias agrupada: +0,328 pp. Media de diferencias por ciclo: +0,309 pp. Diferencia por símbolo (igual peso): +0,274 pp.

### 15m
- Candidatos: n=126, media +1,016 %, mediana +0,134 %, desv 2,97 %, mín −4,14 %, máx +11,22 %, 55 % positivos. Media por símbolo: +0,934 %.
- Comparadores: n=42, media +0,095 %, mediana +0,107 %, desv 0,37 %, mín −0,71 %, máx +0,83 %, 60 % positivos. Media por símbolo: +0,123 %.
- Diferencia medias agrupada: +0,921 pp. Media de diferencias por ciclo: +0,857 pp. Diferencia por símbolo: +0,811 pp.

### 60m (corrección)
- Candidatos: n=126, media +3,93 %, mediana **0,56 %**, desv 7,43 %, mín −5,29 %, máx +27,01 %, 57 % positivos. Media por símbolo: +3,01 %.
- Comparadores: n=42, media +0,70 %, mediana **0,61 %**, desv 0,62 %, mín −0,31 %, máx +2,66 %, 83 % positivos. Media por símbolo: +0,81 %.
- Diferencia medias agrupada: +3,23 pp. Media de diferencias por ciclo: +3,25 pp. Diferencia por símbolo: +2,20 pp.

**Corrección vs informe v1:** a 60m la mediana de candidatos (0,56 %) **no supera** la de comparadores (0,61 %). La diferencia favorable a 60m se sostiene en la media (agrupada, por ciclo y por símbolo) y en UP/DOWN por separado, pero no en la mediana.

### UP / DOWN por separado (candidatos, clasificación `side` real)
| Horizonte | UP media | DOWN media |
|---|---|---|
| 5m | +0,337 % (n=49) | +0,284 % (n=77) |
| 15m | +1,222 % (n=49) | +0,886 % (n=77) |
| 60m | +6,35 % (n=49) | +2,39 % (n=77) |

Los resultados de tres horizontes sobre una misma observación no son independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son automáticamente.

## 5. Sensibilidad al excluir cada símbolo (uno por uno)

La diferencia candidatos menos comparadores conserva signo positivo al excluir cualquier símbolo, pero su magnitud cambia notablemente:

| Símbolo excluido | 5m diff (pp) | 15m diff (pp) | 60m diff (pp) | Efecto |
|---|---|---|---|---|
| Base (ninguno) | +0,328 | +0,921 | +3,226 | — |
| AKEUSDT | +0,175 (−47 %) | +0,376 (−59 %) | +2,091 (−35 %) | concentra resultado positivo |
| JCTUSDT | +0,239 (−27 %) | +0,683 (−26 %) | +2,565 (−20 %) | concentra resultado positivo |
| CYBERUSDT | +0,345 (+5 %) | +0,973 (+6 %) | +3,611 (+12 %) | compensa (al excluirse sube) |
| BIRBUSDT | +0,393 (+20 %) | +1,111 (+21 %) | +3,776 (+17 %) | compensa (al excluirse sube) |

Conclusión: el resultado no depende de un único símbolo, pero AKEUSDT y JCTUSDT aportan una parte sustancial de la diferencia positiva. La diferencia mantiene signo positivo en todas las exclusiones.

Las ventanas solapadas no se tratan como observaciones independientes; la cobertura desigual (126 aptas candidate vs 42 aptas comparator) no se interpreta como un sesgo de dirección ya demostrado.

## 6. Asociación exploratoria: flujo relativo a profundidad

Una única definición principal (no se probaron múltiples fórmulas):

`(buy_notional − sell_notional) / (bid_notional_top20 + ask_notional_top20)`

- Flujo agresor neto en USDT sobre profundidad notional top-20. Ventana de flujo 60 000 ms. Ratio adimensional.
- Umbral numérico (corte fijo) obtenido del dataset (tercil superior de |ratio|): **no es un umbral operativo validado**.
- Distinción explícita: ratio firmado vs retorno firmado; magnitud absoluta del ratio vs magnitud absoluta del retorno.
- Denominadores efectivos: 0 campos ausentes, 0 profundidad cero, 168/168 parejas válidas por horizonte.

| Horizonte | Pearson (ratio firmado vs retorno firmado) | Grupo |ratio| alto (n=56) media retorno | Grupo |ratio| bajo (n=112) media retorno |
|---|---|---|---|---|---|
| 5m | +0,037 | +0,51 % | +0,08 % |
| 15m | +0,112 | +1,56 % | +0,40 % |
| 60m | +0,144 | +3,90 % | +2,73 % |

Asociación exploratoria débil-positiva: el ratio flujo/profundidad muestra correlación positiva pequeña con el retorno posterior, y el tercil superior de |ratio| tiende a retornos medios superiores, más marcado a 60 m. **Esto es exploratorio sobre una sola captura de una hora; no es una hipótesis prerregistrada ni confirmación independiente.**

Limitación: la comparación mezcla símbolos con distinta composición por ciclo; la cobertura desigual entre roles expone esa limitación.

## 7. Interpretación de precios y costes

- Precio inicial del libro (`libro_mid`) frente a precio posterior de klines (`klines_apertura_1m`), con desfase por horizonte (horizonte efectivo = nominal + desfase de publicación). Proxy de fuentes mixtas, no mark-to-mid, no P&L ejecutable.
- `neto_estado=UNKNOWN` en los 504 resultados: no existen costes, comisiones, funding ni fills acreditados. No se inventan fills, comisiones, funding ni P&L.

## 8. Respuestas a las preguntas de entrega

1. **¿La autoselección distinguió comportamientos posteriores respecto a sus comparadores?**
   Sí, descriptivamente: en los tres horizontes los candidatos mostraron retornos medios superiores a los comparadores (+0,33 pp a 5m, +0,92 pp a 15m, +3,23 pp a 60m), consistente entre ponderación agrupada, por ciclo e igual por símbolo, y en UP y DOWN por separado. A 60m, sin embargo, la mediana de candidatos (0,56 %) no supera la de comparadores (0,61 %). No es prueba de capacidad predictiva ni de rentabilidad (neto=UNKNOWN; sin costes).

2. **¿La cobertura permite una comparación razonable?**
   Parcialmente. Todos los ciclos tienen ambos grupos, sin ciclos excluidos ni resultados huérfanos. Pero la cobertura de aptas es asimétrica (126 candidate vs 42 comparator), con 38 comparadores descartados (todos por `dato_obsoleto_flujo`) vs 10 candidatos. Cuatro ciclos tienen un solo comparador apto. No se pueden atribuir diferencias de retorno al selector ignorando esa diferencia de cobertura.

3. **¿Existe alguna asociación exploratoria entre flujo relativo a profundidad y movimiento posterior?**
   Sí, débil y positiva (Pearson +0,037 / +0,112 / +0,144 en 5m/15m/60m; tercil superior de |ratio| con retornos medios superiores). Exploratorio, no prerregistrado, una sola hora, denominador siempre disponible en este dataset.

4. **¿Qué incertidumbre económica debe resolverse después?**
   - `neto_estado=UNKNOWN`: faltan costes, comisiones, funding, slippage y fills acreditados para convertir retornos brutos en P&L ejecutable. Añadir comisiones **no basta** por sí solo para acreditar rentabilidad.
   - Precio mixto (`libro_mid` → `klines_apertura_1m` con desfase); no es mark-to-mid.
   - Una sola hora: sin representatividad del universo ni estabilidad entre regímenes.
   - Cobertura asimétrica de comparadores: descartes concentrados en `dato_obsoleto_flujo`; cuatro ciclos con un solo comparador apto.
   - Concentración en símbolos: AKEUSDT y JCTUSDT aportan gran parte de la diferencia positiva.

## Archivos publicados en Git
- `scripts/analisis_universo_liquidez_v2.py` (script v2, argumentos explícitos).
- `tests/test_analisis_universo_liquidez_v2.py` (6 pruebas focalizadas).
- `docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/resumen_analisis_universo_liquidez_v2.json` (tabla pequeña).
- Este informe.

Fuera de Git: `C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\` (dataset original) y `...\derivados\analisis_universo_liquidez_v2\analisis_completo_v2.json` (derivado detallado).

## Referencia en estado y cola
Análisis offline autorizado completado (bloque research/universe-liquidez-v1, análisis v2). No se abrió Binance ni se propuso otra captura automáticamente. El siguiente paso, solo tras revisar estos resultados y con autorización explícita del presupuesto, sería repetir la captura con cierre acreditado y settle completado para 60m, e incorporar costes/ejecución para poder declarar rentabilidad.
