# Informe rectificado — universo-liquidez-v1 (captura pública public-pilot-1h-20261106a), análisis v4

run_id: `public-pilot-1h-20261106a` · commit base: `fc057dc4f0a740959dca3571363e6aff65a0c273` (HEAD verificado, coincide con base esperada) · código de salida del proceso: `UNKNOWN` (no recuperable retrospectivamente).

Script: `scripts/analisis_universo_liquidez_v2.py` (versión identificable v4, argumentos explícitos `--jsonl / --out-derivados / --out-tablas / --run_id`). Pruebas: `tests/test_analisis_universo_liquidez_v2.py` (16 passed, incl. invocación del CLI real sobre JSONL temporales). Dataset y derivados voluminosos fuera de Git; solo script, pruebas, informe y tablas pequeñas se publican. `neto_estado=UNKNOWN` en los 504 resultados (sin costes ni ejecución acreditados).

## 1. Conservación de fuentes

Hashes del dataset original verificados contra el manifiesto publicado en `docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/`. Lectura exclusiva del dataset; no se modificó ni se sobrescribieron derivados anteriores (v2/v3 conservados). El análisis v4 genera derivados en directorio nuevo (`...\derivados\analisis_universo_liquidez_v4\`) y tabla en archivo existente (`resumen_analisis_universo_liquidez_v2.json`, versión v4).

## 2. Reconciliación de las tres observaciones excluidas de la asociación flujo/profundidad

La tabla v2/v3 declaraba erróneamente cero importes negativos y 168 parejas válidas por horizonte. La corrección v4 detecta 3 observaciones con un importe bruto (buy_notional o sell_notional) ligeramente negativo por error de punto flotante (~1e-14). Estas se excluyen de la asociación flujo/profundidad (regla estricta: buy y sell deben ser >= 0), pero **no** por flujo neto negativo (su diferencia es legítima). Parejas válidas pasan de 168 a **165 por horizonte**.

Tabla compacta publicada en `tablas/excluidas_asociacion_flujo.json`. Resumen:

| observation_id | Símbolo | Rol | decision_ms | buy_notional | sell_notional | Flujo neto | Profundidad top-20 | Motivo de exclusión |
|---|---|---|---|---|---|---|---|---|
| CGPTUSDT\|1793942927179 | CGPTUSDT | comparator | 1793942927179 | −9.59e-14 | 190.34 | −190.34 | 66 614.16 | buy_notional negativo (punto flotante ~1e-14) |
| HANAUSDT\|1793944127943 | HANAUSDT | candidate | 1793944127943 | 470.12 | −1.15e-12 | +470.12 | 63 160.74 | sell_notional negativo (punto flotante ~1e-14) |
| CHILLGUYUSDT\|1793945328322 | CHILLGUYUSDT | comparator | 1793945328322 | 38.28 | −5.42e-14 | +38.28 | 10 992.21 | sell_notional negativo (punto flotante ~1e-14) |

### Distinción importe bruto vs flujo neto
- **Importe bruto negativo** (buy < 0 o sell < 0): excluye de la asociación. Aquí son errores de punto flotante (~1e-14), no valores económicos negativos.
- **Flujo neto negativo** (buy − sell < 0): es legítimo y **no** excluye. En el dataset hay 234 filas observación×horizonte con flujo neto negativo legítimo (comprador neto vendedor), todas admitidas en la asociación.

### Denominadores efectivos (con unidades claras)
| Denominador | Valor |
|---|---|
| Observaciones únicas aptas | 168 |
| Filas observación×horizonte (para la asociación) | 504 |
| Observaciones excluidas de la asociación | 3 (todas por importe bruto negativo ~1e-14) |
| Parejas válidas por horizonte (5m / 15m / 60m) | 165 / 165 / 165 |
| Filas con flujo neto negativo legítimo | 234 |

### Causa de exclusión
Las 3 observaciones tienen buy_notional o sell_notional ligeramente negativo (−9.59e-14, −1.15e-12, −5.42e-14), profundidad válida y positiva, ventana de flujo completa (60 000 ms), y cobertura completa. La causa es error de punto flotante en el importe bruto, no baja liquidez ni transporte. No se aplicó valor absoluto, recorte a cero ni tolerancias nuevas para recuperar estas observaciones.

### Los resultados forward de las 3 observaciones excluidas se conservan
Una observación inválida para la asociación de flujo no desaparece de la comparación de retornos. Los 3 símbolos excluidos (CGPTUSDT, HANAUSDT, CHILLGUYUSDT) siguen presentes en la comparación candidatos-vs-comparadores con sus 3 retornos forward cada uno (9 retornos en total), porque esa comparación no usa la asociación flujo/profundidad.

## 3. Identidad de corrida separada de duplicados

| Control | Resultado |
|---|---|
| Duplicados de observation_id (observaciones) | Ninguno (216 únicos) |
| Duplicados de pares observation_id×horizonte (resultados) | Ninguno (504 únicos) |
| Campo run_id en los registros | Ausente (no existe en ningún registro JSONL) |
| run_id en registros | UNKNOWN |
| run_id coincide con CLI --run_id | None (no determinable) |
| Mezcla de corridas detectada | None (no determinable sin campo run_id) |

**Identidad de corrida y duplicados son controles distintos.** Un duplicado de observation_id dentro de una misma corrida no demuestra mezcla de corridas. Una mezcla con identificadores únicos sí sería detectada si los registros tuvieran campo run_id (dos valores distintos → contradicción). Como los registros no contienen run_id, la identidad es `UNKNOWN` (no `false`, no «mezcla descartada»). La identidad de corrida se acredita mediante el manifiesto publicado y el hash SHA-256 del archivo observaciones.jsonl, no por el argumento CLI ni el nombre del directorio.

## 4. Asociación flujo/profundidad regenerada (filas admitidas: 165 por horizonte)

Una única definición principal (sin cambios):

`(buy_notional − sell_notional) / (bid_notional_top20 + ask_notional_top20)`

Reglas de validez: importes finitos y no negativos; profundidad finita y estrictamente positiva; ventana completa (`ventana_completa=true` y `window_ms=60000`). El flujo neto firmado puede ser negativo; no es dato inválido.

| Horizonte | Filas | Pares válidos | Pearson (ratio firmado vs retorno firmado) | Corte fijo \|ratio\| | Grupo alto media retorno | Grupo bajo media retorno |
|---|---|---|---|---|---|---|
| 5m | 168 | 165 | +0,037 | 0,256 | +0,51 % | +0,08 % |
| 15m | 168 | 165 | +0,112 | 0,256 | +1,56 % | +0,40 % |
| 60m | 168 | 165 | +0,144 | 0,256 | +3,90 % | +2,73 % |

Asociación débil-positiva, exploratoria sobre una sola captura de una hora. El corte fijo (tercil superior de \|ratio\| del dataset) **no es un umbral operativo validado**. No se probaron múltiples fórmulas ni cortes para obtener resultados favorables.

## 5. Qué cambia y qué permanece vs informe v3

**Cambian:**
- Parejas válidas por horizonte: 168 → 165 (3 observaciones excluidas por importe bruto negativo ~1e-14).
- Correlaciones Pearson: +0,037 / +0,112 / +0,144 (mínimo cambio por la exclusión de 3 filas de 504).
- `mezcla_run_id_detectada`: `false` → `None` (no determinable sin campo run_id en registros).
- `run_id_en_registros`: ausente → `UNKNOWN`.
- Separación explícita de duplicados vs identidad de corrida.

**Permanecen:**
- Conteo global: 216 observaciones, 168 aptas, 48 descartadas, 504 resultados (168 × 3 horizontes).
- Embudo: 240 seleccionados (144 candidate, 96 comparator), 24 sin observación emitida.
- Comparación candidatos vs comparadores (sin cambios: no usa la asociación flujo/profundidad).
- Mediana candidatos inferior a comparadores a 60m (0,56 % vs 0,61 %).
- Sensibilidad por símbolo (AKEUSDT y JCTUSDT concentran parte del resultado; diferencia conserva signo al excluir cualquier símbolo).
- `neto_estado=UNKNOWN` en los 504 resultados. Añadir comisiones no acredita rentabilidad.
- Los 168 resultados de 60m ya existen; no se recomienda repetir la captura solo para completarlos.

## 6. Conclusión económica permitida

Ninguna conclusión de rentabilidad. Los retornos son proxies descriptivos sin costes ni ejecución (`neto_estado=UNKNOWN`). Una sola hora no acredita representatividad del universo ni estabilidad entre regímenes. La cobertura asimétrica de comparadores (42 aptas vs 126 candidate; 4 ciclos con un solo comparador apto) y la concentración en símbolos (AKEUSDT, JCTUSDT) limitan la generalización. La asociación flujo/profundidad es débil-positiva y exploratoria, no prerregistrada.

## Archivos publicados en Git
- `scripts/analisis_universo_liquidez_v2.py` (script v4, argumentos explícitos).
- `tests/test_analisis_universo_liquidez_v2.py` (16 pruebas focalizadas).
- `docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/resumen_analisis_universo_liquidez_v2.json` (tabla pequeña, versión v4).
- `docs/evidence/research/universe_liquidity_v1/public-pilot-1h-20261106a/tablas/excluidas_asociacion_flujo.json` (tabla compacta de las 3 observaciones excluidas).
- Este informe.

Fuera de Git: `C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\` (dataset original) y `...\derivados\analisis_universo_liquidez_v4\analisis_completo_v2.json` (derivado detallado).

## Referencia en estado y cola
Análisis offline autorizado completado (bloque research/universe-liquidez-v1, análisis v4). No se abrió Binance ni se propuso otra captura. Los 168 resultados de 60m ya existen; no se recomienda repetir la captura solo para completarlos. Cualquier nueva captura requiere definición del problema que resolvería y autorización explícita del presupuesto.
