# Informe rectificado — universo-liquidez-v1 (captura pública public-pilot-1h-20261106a), análisis v3

run_id: `public-pilot-1h-20261106a` · commit base: `30c0bdcf6a9f2e4ac1f8b216ea609876a64f1d1e` (HEAD verificado, coincide con base esperada) · código de salida del proceso: `UNKNOWN` (no recuperable retrospectivamente).

Script: `scripts/analisis_universo_liquidez_v2.py` (versión identificable v3, argumentos explícitos `--jsonl / --out-derivados / --out-tablas / --run_id`). Pruebas: `tests/test_analisis_universo_liquidez_v2.py` (12 passed, incl. invocación del CLI real sobre JSONL temporales). Dataset y derivados voluminosos fuera de Git; solo script, pruebas, informe y tablas pequeñas se publican. `neto_estado=UNKNOWN` en los 504 resultados (sin costes ni ejecución acreditados).

## 1. Conservación de fuentes

Hashes del dataset original verificados contra el manifiesto publicado en `docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/`. Lectura exclusiva del dataset; no se modificó ni se sobrescribieron derivados anteriores. El análisis v3 genera derivados en directorio nuevo (`...\derivados\analisis_universo_liquidez_v3\`) y tabla en archivo nuevo (`resumen_analisis_universo_liquidez_v2.json`).

## 2. Embudo reconstruido desde registros de selección (vínculo selección→decisión corregido)

El análisis v2 emparejaba selección y decisión por posición cronológica (reference_ms ordenado ↔ decision_ms ordenado). El v3 utiliza el identificador persistido real: `observacion.disponibilidad.seleccion_ms == ciclo.reference_ms`. Nunca se usa orden cronológico, proximidad temporal ni igualdad de cantidades.

### Verificación de pertenencia y vínculos

Desde los 216 registros de observación:
- **Observación con selección acreditada**: 216/216 (todas vinculan vía `seleccion_ms` a un ciclo de referencia, y su símbolo/rol pertenecen a la selección de ese ciclo).
- **Observación sin vínculo acreditable**: 0.
- **Vínculos contradictorios o ambiguos**: 0.
- **Mezcla de corridas detectada**: No (`mezcla_run_id_detectada=false`; observation_id únicos en observaciones, pares `(observation_id, horizon)` únicos en resultados).

### Embudo (selección vs observación emitida)

| Rol | Seleccionados | Observaciones emitidas | Selecciones sin observación | Aptas | Descartadas |
|---|---|---|---|---|---|
| candidate | 144 | 136 | 8 | 126 | 10 |
| comparator | 96 | 80 | 16 | 42 | 38 |
| Total | 240 | 216 | 24 | 168 | 48 |

Los conteos conocidos (216 observaciones, 168 aptas, 48 descartadas, 504 resultados) se mantienen como comprobaciones, pero **no equivalen al denominador inicial de selección** (240). Las 24 selecciones sin observación emitida (8 candidate, 16 comparator) no se cuentan como aptas ni descartadas.

### Ciclo de selección vs ciclo de decisión

Cada ciclo de selección (`reference_ms`) se empareja con un ciclo de decisión (`decision_ms`) por el vínculo persistido `seleccion_ms == reference_ms` (12 de cada uno). `decision_ms` es aproximadamente `reference_ms + ~85 s`.

### Incorporación al seguimiento

Clasificada por ciclo de primera aparición (`reference_ms` donde el símbolo se selecciona por primera vez): 28 símbolos únicos, 12 en todos los 12 ciclos, 16 en menos ciclos (rotación, n_rotaciones_salida = 25). Primera incorporación / permanencia / reincorporación identificables para las 216 observaciones emitidas.

### Comparadores aptos por ciclo

Ciclos 1, 7, 9 y 11 tienen **un solo comparador apto**. Los demás tienen entre 2 y 8. Esto limita la solidez de la comparación en esos ciclos y se debe al descarte concentrado de comparadores por `dato_obsoleto_flujo` (38 de 38 descartes de comparator).

## 3. Comparación candidatos vs comparadores (5m / 15m / 60m)

Retornos en fracción (0.01 = 1 %). Precio inicial = `libro_mid`, precio posterior = `klines_apertura_1m` (proxy de fuentes mixtas, no mark-to-mid, no P&L). `neto_estado=UNKNOWN`.

### 5m
- Candidatos: n=126, media +0,305 %, mediana +0,116 %, desv 1,50 %, mín −4,05 %, máx +8,28 %, 61 % positivos. Media por símbolo (igual peso): +0,248 %.
- Comparadores: n=42, media −0,023 %, mediana −0,069 %, desv 0,24 %, mín −0,47 %, máx +0,58 %, 38 % positivos. Media por símbolo: −0,026 %.
- Diferencia medias agrupada: +0,328 pp. Media de diferencias por ciclo: +0,309 pp. Diferencia por símbolo (igual peso): +0,274 pp.

### 15m
- Candidatos: n=126, media +1,016 %, mediana +0,134 %, desv 2,97 %, mín −4,14 %, máx +11,22 %, 55 % positivos. Media por símbolo: +0,934 %.
- Comparadores: n=42, media +0,095 %, mediana +0,107 %, desv 0,37 %, mín −0,71 %, máx +0,83 %, 60 % positivos. Media por símbolo: +0,123 %.
- Diferencia medias agrupada: +0,921 pp. Media de diferencias por ciclo: +0,857 pp. Diferencia por símbolo: +0,811 pp.

### 60m (rectificación vs informe v2)
- Candidatos: n=126, media +3,93 %, mediana **0,56 %**, desv 7,43 %, mín −5,29 %, máx +27,01 %, 57 % positivos. Media por símbolo: +3,01 %.
- Comparadores: n=42, media +0,70 %, mediana **0,61 %**, desv 0,62 %, mín −0,31 %, máx +2,66 %, 83 % positivos. Media por símbolo: +0,81 %.
- Diferencia medias agrupada: +3,23 pp. Media de diferencias por ciclo: +3,25 pp. Diferencia por símbolo: +2,20 pp.

**Rectificación:** a 60m la mediana de candidatos (0,56 %) **no supera** la de comparadores (0,61 %). La diferencia favorable se sostiene en la media (agrupada, por ciclo y por símbolo) y en UP/DOWN por separado, pero no en la mediana.

### UP / DOWN por separado (candidatos, clasificación `side` real)
| Horizonte | UP media | DOWN media |
|---|---|---|
| 5m | +0,337 % (n=49) | +0,284 % (n=77) |
| 15m | +1,222 % (n=49) | +0,886 % (n=77) |
| 60m | +6,35 % (n=49) | +2,39 % (n=77) |

Los resultados de tres horizontes sobre una misma observación no son independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son automáticamente.

## 4. Sensibilidad reproducible por símbolo (desde código ejecutable)

La exclusión de cada símbolo, uno por uno, retirando todas sus observaciones de ambos roles. La diferencia base se conserva en el informe como resultado principal; las exclusiones son diagnóstico de concentración.

| Símbolo excluido | 5m diff (pp) | 15m diff (pp) | 60m diff (pp) | Cambio vs base 60m | Signo |
|---|---|---|---|---|---|
| Base (ninguno) | +0,328 | +0,921 | +3,226 | — | + |
| AKEUSDT | +0,175 | +0,376 | +2,091 | −1,13 pp | + |
| JCTUSDT | +0,239 | +0,683 | +2,565 | −0,66 pp | + |
| CYBERUSDT | +0,345 | +0,973 | +3,611 | +0,39 pp | + |
| BIRBUSDT | +0,393 | +1,111 | +3,776 | +0,55 pp | + |
| (28 símbolos en la tabla publicada) | | | | | |

La diferencia **conserva signo positivo** al excluir cualquier símbolo (ningún cambio de signo). Sin embargo, su magnitud depende de símbolos concretos: AKEUSDT y JCTUSDT aportan una parte sustancial de la diferencia positiva (excluirlos la reduce ~20–35 % a 60m), mientras CYBERUSDT y BIRBUSDT la compensan (excluirlos la aumenta). La tabla completa se publica en `tablas/resumen_analisis_universo_liquidez_v2.json` (`sensibilidad_por_simbolo`), no solo ejemplos favorables.

## 5. Asociación flujo/profundidad: entradas validadas

Una única definición principal (no se probaron múltiples fórmulas ni cortes):

`(buy_notional − sell_notional) / (bid_notional_top20 + ask_notional_top20)`

Reglas de validez aplicadas a cada fila (observación × horizonte):
- Importes de compra y venta finitos y no negativos.
- Profundidad total finita y estrictamente positiva (denominador > 0).
- Ventana de flujo completa acreditada (`ventana_completa=true` y `window_ms=60000`).
- El flujo neto firmado puede ser negativo; eso no es un dato inválido.

Resultados de validación (dataset original):

| Métrica | Valor |
|---|---|
| Filas para asociación | 504 (168 × 3 horizontes) |
| Campos ausentes o no finitos | 0 |
| Valor negativo en flujo | 0 |
| Valor negativo en profundidad | 0 |
| Profundidad cero o inválida | 0 |
| Ventana incompleta | 0 |
| Filas inválidas para asociación | 0 |
| Parejas válidas por horizonte | 168 / 168 / 168 |
| Mezcla de corridas detectada | No |

Asociación exploratoria (corte fijo = tercil superior de |ratio| del dataset, **no umbral operativo validado**):

| Horizonte | Pearson (ratio firmado vs retorno firmado) | Grupo \|ratio\| alto media retorno | Grupo \|ratio\| bajo media retorno |
|---|---|---|---|
| 5m | +0,037 | +0,51 % | +0,08 % |
| 15m | +0,112 | +1,56 % | +0,40 % |
| 60m | +0,144 | +3,90 % | +2,73 % |

Asociación débil-positiva, exploratoria sobre una sola captura de una hora. No es una hipótesis prerregistrada ni confirmación independiente. La comparación mezcla símbolos con distinta composición por ciclo; la cobertura desigual entre roles expone esa limitación.

## 6. Precios y costes

- Precio inicial del libro (`libro_mid`) frente a precio posterior de klines (`klines_apertura_1m`), con desfase por horizonte. Proxy de fuentes mixtas, no mark-to-mid, no P&L ejecutable.
- `neto_estado=UNKNOWN` en los 504 resultados: no existen costes, comisiones, funding ni fills acreditados. No se inventan fills, comisiones, funding ni P&L. **Añadir comisiones no basta por sí solo para acreditar rentabilidad.**

## 7. Respuestas a las preguntas de entrega

1. **¿La autoselección distinguió comportamientos posteriores respecto a sus comparadores?**
   Sí, descriptivamente: candidatos mostraron retornos medios superiores en los 3 horizontes (+0,33 pp a 5m, +0,92 pp a 15m, +3,23 pp a 60m), consistente entre ponderación agrupada, por ciclo e igual por símbolo, y en UP y DOWN por separado. A 60m, la mediana de candidatos (0,56 %) no supera la de comparadores (0,61 %). No es prueba de capacidad predictiva ni de rentabilidad (neto=UNKNOWN).

2. **¿La cobertura permite una comparación razonable?**
   Parcialmente. Todos los ciclos tienen ambos grupos, sin resultados huérfanos. Pero la cobertura de aptas es asimétrica (126 candidate vs 42 comparator), con 38 comparadores descartados (todos por `dato_obsoleto_flujo`) vs 10 candidatos, y 4 ciclos con un solo comparador apto. No se pueden atribuir diferencias de retorno al selector ignorando esa diferencia de cobertura.

3. **¿Existe asociación exploratoria entre flujo relativo a profundidad y movimiento posterior?**
   Sí, débil y positiva (Pearson +0,037 / +0,112 / +0,144 en 5m/15m/60m). Exploratorio, no prerregistrado, una sola hora, denominador siempre disponible y validado en este dataset.

4. **¿Qué conclusión económica permite la evidencia?**
   Ninguna conclusión de rentabilidad. Los retornos son proxies descriptivos sin costes ni ejecución (`neto_estado=UNKNOWN`). Una sola hora no acredita representatividad del universo ni estabilidad entre regímenes. La cobertura asimétrica de comparadores y la concentración en símbolos (AKEUSDT, JCTUSDT) limitan la generalización. No se declara rentabilidad por añadir comisiones.

## 8. Qué se mantiene y qué cambia vs informe v2

**Se mantienen:** conteos globales (216/168/48/504), comparación agrupada y por ciclo, UP/DOWN por `side`, métrica flujo/profundidad, Pearson por horizonte, `neto_estado=UNKNOWN`.

**Cambian:**
- Vínculo selección→decisión: ahora usa `seleccion_ms == reference_ms` (identificador persistido), no orden cronológico.
- Sensibilidad por símbolo: ahora reproducible desde el código ejecutable, tabla completa publicada (28 símbolos).
- A 60m: mediana de candidatos (0,56 %) **inferior** a comparadores (0,61 %) — corregido.
- Validación de entradas: profundidad > 0, ventana completa, importes finitos y no negativos, pares `(observation_id, horizon)` únicos para detección de mezcla de corridas.
- Se elimina la recomendación de repetir la captura para completar 60m: ya existen sus 168 resultados.

## Archivos publicados en Git
- `scripts/analisis_universo_liquidez_v2.py` (script v3, argumentos explícitos).
- `tests/test_analisis_universo_liquidez_v2.py` (12 pruebas focalizadas).
- `docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/resumen_analisis_universo_liquidez_v2.json` (tabla pequeña).
- Este informe.

Fuera de Git: `C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\` (dataset original) y `...\derivados\analisis_universo_liquidez_v3\analisis_completo_v2.json` (derivado detallado).

## Referencia en estado y cola
Análisis offline autorizado completado (bloque research/universe-liquidez-v1, análisis v3). No se abrió Binance ni se propuso otra captura automáticamente. Los 168 resultados de 60m ya existen; no se recomienda repetir la captura solo para completarlos. Cualquier nueva captura requiere definición del problema que resolvería y autorización explícita del presupuesto.
