# Informe — universo-liquidez-v1 (captura pública public-pilot-1h-20261106a)

run_id: `public-pilot-1h-20261106a` · commit base: `dc1367c9a9e6fe1c5e670753b8be0dbf441b5b1c` (HEAD == base; hashes del manifiesto verificados contra origen) · código de salida del proceso: `UNKNOWN` (no recuperable retrospectivamente).

Script: `scripts/analisis_universo_liquidez_v1.py` (argumentos explícitos `--jsonl / --out-derivados / --out-tablas / --run_id`; sin dependencia implícita de la captura 20261105a). Pruebas: `tests/test_analisis_universo_liquidez_v1.py` (10 passed). Muestra validada independientemente contra registros fuente (100 % de retornos recalculados coinciden). Dataset y derivados voluminosos fuera de Git; solo script, pruebas, informe, tablas pequeñas y manifiestos se publican.

## 1. Verificación de fuentes (desde registros)

| Métrica | Valor | Fuente |
|---|---|---|
| Observaciones | 216 | `observaciones.jsonl` |
| Aptas | 168 | `estado=observada` |
| Descartadas | 48 | `estado=descartada` |
| Resultados | 504 | 168 × 3 horizontes (5m, 15m, 60m) |
| Duplicados `observation_id` | 0 | |
| Pares `(observation_id, horizon)` duplicados | 0 | |
| Resultados huérfanos | 0 | 504/504 con padre apto |
| 60m pendientes | 0 | todos resueltos |

Roles (mutuamente excluyentes, no se solapan): candidate 136 seleccionadas (126 aptas, 10 descartadas), comparator 80 seleccionadas (42 aptas, 38 descartadas). Suma = 216.
Motivos de descarte (pueden solaparse dentro de una observación): candidate `{dato_obsoleto_flujo: 9, flujo_ventana_incompleta: 1}`, comparator `{dato_obsoleto_flujo: 38, dato_obsoleto_libro: 4}`. Suma de conteos de motivos (52) > descartadas (48) por solapamiento (4 observaciones comparator con dos motivos).

Símbolos únicos: 28; distribución por ciclo desigual (rotación; n_rotaciones_salida = 25). 12 símbolos en todos los 12 ciclos; 16 en menos ciclos. Primera incorporación / permanencia / reincorporación identificables por ciclo de primera aparición (registros lo permiten).

## 2. Compara el comportamiento posterior (5m / 15m / 60m)

Retornos en fracción (0.01 = 1 %). Precio inicial = `libro_mid`; precio posterior = `klines_apertura_1m` (proxy de fuentes mixtas, no mark-to-mid, no P&L). `neto_estado=UNKNOWN` en los 504 (sin costes ni ejecución acreditados).

### 5m
- Candidatos: n=126, media +0,305 %, mediana +0,116 %, desv 1,50 %, mín −4,05 %, máx +8,28 %, 61 % positivos. Media por símbolo (igual peso): +0,248 %.
- Comparadores: n=42, media −0,023 %, mediana −0,069 %, desv 0,24 %, mín −0,47 %, máx +0,58 %, 38 % positivos. Media por símbolo: −0,026 %.
- Diferencia medias agrupada: +0,328 pp. Media de diferencias por ciclo (12 ciclos con ambos grupos): +0,309 pp. Diferencia por símbolo (igual peso): +0,274 pp.
- UP (n=49): media +0,337 %. DOWN (n=77): media +0,284 %.

### 15m
- Candidatos: n=126, media +1,016 %, mediana +0,134 %, desv 2,97 %, mín −4,14 %, máx +11,22 %, 55 % positivos. Media por símbolo: +0,934 %.
- Comparadores: n=42, media +0,095 %, mediana +0,107 %, desv 0,37 %, mín −0,71 %, máx +0,83 %, 60 % positivos. Media por símbolo: +0,123 %.
- Diferencia medias agrupada: +0,921 pp. Media de diferencias por ciclo: +0,857 pp. Diferencia por símbolo: +0,811 pp.
- UP (n=49): media +1,222 %. DOWN (n=77): media +0,886 %.

### 60m
- Candidatos: n=126, media +3,93 %, mediana +0,56 %, desv 7,43 %, mín −5,29 %, máx +27,01 %, 57 % positivos. Media por símbolo: +3,01 %.
- Comparadores: n=42, media +0,70 %, mediana +0,61 %, desv 0,62 %, mín −0,31 %, máx +2,66 %, 83 % positivos. Media por símbolo: +0,81 %.
- Diferencia medias agrupada: +3,23 pp. Media de diferencias por ciclo: +3,25 pp. Diferencia por símbolo: +2,20 pp.
- UP (n=49): media +6,35 %. DOWN (n=77): media +2,39 %.

### Interpretación de la comparación
Los 12 ciclos tienen ambos grupos, por lo que no hay ciclos excluidos por falta de comparador. La cobertura de aptas es asimétrica entre roles (126 candidate vs 42 comparator), aunque dentro de cada ciclo ambos grupos están representados. La diferencia favorable de candidatos no puede atribuirse al selector sin considerar que la cobertura de comparadores es menor (38 descartados vs 10 candidatos), concentrada en `dato_obsoleto_flujo`.

Los retornos de tres horizontes sobre una misma observación no son independientes; los símbolos repetidos y las ventanas solapadas tampoco lo son. Una media favorable no demuestra capacidad predictiva.

## 3. Asociación exploratoria: flujo relativo a profundidad

Métrica principal (una sola definición, corte fijo): `(buy_notional − sell_notional) / (bid_notional_top20 + ask_notional_top20)`, flujo agresor neto en USDT sobre profundidad notional top-20, ventana de flujo 60 000 ms, ratio adimensional. Disponible en 168/168 aptas; denominador nunca cero (regla: si profundidad == 0 o None → ratio None, no se convierte en cero). No se sustituyó volumen nocional por `delta_ratio` ni se inventaron bandas.

| Horizonte | Pearson (ratio vs retorno) | Corte fijo | Ratio alto (n=56) media retorno | Ratio bajo (n=112) media retorno |
|---|---|---|---|---|
| 5m | +0,037 | 0,256 | +0,51 % | +0,08 % |
| 15m | +0,112 | 0,256 | +1,56 % | +0,40 % |
| 60m | +0,144 | 0,256 | +3,90 % | +2,73 % |

Asociación exploratoria débil-positive: el ratio flujo/profundidad muestra una correlación positiva pequeña con el retorno posterior, y el tercil superior de |ratio| tiende a retornos medios mayores, más marcado a 60 m. **Esto es exploratorio sobre una sola captura de una hora; no es una hipótesis prerregistrada ni confirmación independiente.** Las correlaciones separadas de profundidad y desequilibrio no evalúan por sí solas la hipótesis conjunta, y una sola hora no acredita estabilidad entre regímenes.

## 4. Respuestas a las preguntas de entrega

1. **¿La autoselección distinguió comportamientos posteriores respecto a sus comparadores?**
   Sí, descriptivamente: en los tres horizontes los candidatos mostraron retornos medios y medianos superiores a los comparadores (diferencia de ~+0,3 pp a 5m, ~+0,9 pp a 15m, ~+3,2 pp a 60m), consistente entre ponderación agrupada, por ciclo e igual por símbolo, y en UP y DOWN por separado. No es prueba de capacidad predictiva ni de rentabilidad (neto=UNKNOWN; sin costes).

2. **¿La cobertura permite una comparación razonable?**
   Parcialmente. Todos los 12 ciclos tienen ambos grupos, sin ciclos excluidos ni resultados huérfanos. Pero la cobertura de aptas es asimétrica: 126 candidate vs 42 comparator, con 38 comparadores descartados (36 por `dato_obsoleto_flujo`) vs 10 candidatos. No se pueden atribuir diferencias de retorno al selector ignorando esa diferencia de cobertura.

3. **¿Existe alguna asociación exploratoria entre flujo relativo a profundidad y movimiento posterior?**
   Sí, débil y positiva: Pearson +0,037 / +0,112 / +0,144 en 5m/15m/60m; el grupo de ratio alto muestra retornos medios superiores. Exploratorio, no prerregistrado, una sola hora, denominador siempre disponible en este dataset.

4. **¿Qué incertidumbre económica debe resolverse después?**
   - `neto_estado=UNKNOWN`: faltan costes, comisiones, funding, slippage y fills acreditados para convertir retornos brutos en P&L ejecutable.
   - Precio mixto (`libro_mid` → `klines_apertura_1m` con desfase); no es mark-to-mid.
   - Una sola hora: sin representatividad del universo ni estabilidad entre regímenes.
   - Cobertura asimétrica de comparadores: descartes concentrados en `dato_obsoleto_flujo`.
   - Siguiente paso (solo tras ver estos resultados): repetir la captura con cierre acreditado y settle completado para 60m, y añadir costes/ejecución para poder declarar rentabilidad. No se propone otra captura automáticamente.

## Archivos publicados en Git
- `scripts/analisis_universo_liquidez_v1.py` (script, argumentos explícitos).
- `tests/test_analisis_universo_liquidez_v1.py` (10 pruebas focalizadas).
- `docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/resumen_analisis_universo_liquidez_v1.json` (tabla pequeña).
- Este informe.

Fuera de Git: `C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\` (dataset original) y `...\derivados\analisis_universo_liquidez_v1\analisis_completo.json` (derivado detallado).
