# Rectificación del embudo de cobertura — captura pública public-pilot-1h-20261105a

**run_id:** `public-pilot-1h-20261105a`
**Rama / base:** `research/universe-liquidity-v1` en `640973b652e414a5baf16f2cbadbb1a97224341c`
**Estado de la corrida:** `corrida_interrumpida_o_cierre_no_acreditado` (causa de parada `UNKNOWN`)
**Análisis:** solo lectura, offline, sin conexión a Binance, sin adquisición de datos nuevos.
**Script:** `scripts/diagnostico_embudo_publica.py`
**Pruebas:** `tests/test_embudo_publica.py` (6 passed)
**Tablas pequeñas (Git):** `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/embudo_publica.json`
**Derivados detallados (fuera de Git):** `C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\embudo\diagnostico_embudo.json`

Esta rectificación **no sobrescribe** el análisis offline v2 (`rectificacion_analisis_offline_v2.md`). Corrije el embudo documental: el informe anterior atribuía incorrectamente las 128 aptas totales a candidatos. Los conteos reales por rol, verificados contra el dataset original, son los que se publican aquí. Los informes anteriores se conservan como históricos.

---

## A. Embudo corregido (verificado contra el dataset original)

Los conteos por rol **no se solapan**: candidate y comparator son mutuamente excluyentes por observación. Los motivos de descarte **pueden solaparse** dentro de una misma observación (una observación descartada puede tener varios motivos), por eso la suma de motivos no tiene por qué igualar el total de descartes.

| Rol | Seleccionadas | Aptas | Descartadas | Resultados 5m | Resultados 15m | Resultados 60m |
| --- | --- | --- | --- | --- | --- | --- |
| candidate | 144 | 109 | 35 | 97 | 76 | 0 |
| comparator | 96 | 19 | 77 | 18 | 15 | 0 |
| **Total** | **240** | **128** | **112** | **115** | **91** | **0** |

**Comprobación de consistencia (pasada):** `candidate + comparator == total` en seleccionadas (240), aptas (128) y descartadas (112). `aptas + descartadas == seleccionadas` (240).

### Tasas de cobertura

| Rol | Horizonte | Resultados | Aptas | Tasa sobre aptas | Seleccionadas | Tasa sobre seleccionadas |
| --- | --- | --- | --- | --- | --- | --- |
| candidate | 5m | 97 | 109 | **89,0 %** | 144 | 67,4 % |
| candidate | 15m | 76 | 109 | **69,7 %** | 144 | 52,8 % |
| comparator | 5m | 18 | 19 | **94,7 %** | 96 | 18,8 % |
| comparator | 15m | 15 | 19 | **78,9 %** | 96 | 15,6 % |

**Lectura clave:** los comparadores tienen muy pocas seleccionadas (96) porque solo 19 son aptas; de esas 19 aptas, la mayoría consiguen resultado (94,7 % a 5m, 78,9 % a 15m). El problema de los comparadores no es que fallen tras ser aptas, es que **pocas son aptas** (solo 19 de 96 seleccionadas, el 19,8 %).

### Descartes por motivo (pueden solaparse; no suman obligatoriamente al total)

| Rol | sin_libro | sin_flujo | dato_obsoleto_libro | dato_obsoleto_flujo | Total descartes |
| --- | --- | --- | --- | --- | --- |
| candidate | 22 | 22 | 10 | 5 | 35 |
| comparator | 44 | 44 | 5 | 32 | 77 |

---

## B. Diagnóstico de incorporación al seguimiento

Cada observación se clasifica por condición de incorporación del símbolo en su ciclo:

| Rol | Condición | Seleccionadas | Aptas | Descartadas | sin_libro | sin_flujo | obsoleto_libro | obsoleto_flujo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| candidate | permanece | 122 | 109 | 13 | 0 | 0 | 10 | 5 |
| candidate | primera_vez | 17 | 0 | 17 | 17 | 17 | 0 | 0 |
| candidate | reincorpora | 5 | 0 | 5 | 5 | 5 | 0 | 0 |
| comparator | permanece | 52 | 19 | 33 | 0 | 0 | 5 | 32 |
| comparator | primera_vez | 27 | 0 | 27 | 27 | 27 | 0 | 0 |
| comparator | reincorpora | 17 | 0 | 17 | 17 | 17 | 0 | 0 |

**Hallazgos:**

1. **Todas las "primera_vez" y "reincorpora" están descartadas** (0 aptas en ambos roles). Todas tienen `sin_libro` y `sin_flujo` (100 %) y `ventana_incompleta` (100 %).
2. Solo las que "permanecen" tienen aptas: candidate 109/122, comparator 19/52.
3. De los 77 descartes de comparadores:
   - 44 (57 %) son `primera_vez` (27) o `reincorpora` (17): símbolos que entran al seguimiento y no tienen libro ni flujo aún.
   - 33 (43 %) son `permanece`: de estos, 32 por `dato_obsoleto_flujo` y 5 por `dato_obsoleto_libro`.
4. De los 35 descartes de candidates:
   - 22 (63 %) son `primera_vez` (17) o `reincorpora` (5).
   - 13 (37 %) son `permanece`: 10 por `dato_obsoleto_libro`, 5 por `dato_obsoleto_flujo`.

### ¿Por qué los comparadores acumulan tantos descartes?

El comparador se construye con `build_comparator`: **muestreo aleatorio sin reemplazo (`rng.sample`) del universo elegible excluyendo candidatos**, con semilla fija (42) y techo conjunto candidatos + comparadores (≤ 20). Con ~465 símbolos elegibles y solo 8 comparadores por ciclo, la probabilidad de que un símbolo repita como comparador en ciclos consecutivos es muy baja (~1,7 % por ciclo). Por eso la mayoría de comparadores son `primera_vez` o `reincorpora` en cada ciclo, y al ser evaluados inmediatamente después de abrirse los feeds, no tienen libro ni flujo acumulados.

Los candidatos, en cambio, son un **top-12 por prioridad determinista** (movimiento + volumen), que se repiten entre ciclos (`permanece` = 122 de 144), por lo que acumulan datos de libro/flujo y son mayoritariamente aptos (109 de 144).

### Carrera reproducible demostrada

El orden del código en el piloto ejecutado (commit `7916c49`, base actual) es:

1. `run_cycle()`: selección de candidatos y comparadores (research-selector-v2), actualización de `self.roles`, `self.selection_meta`, `self.followed`.
2. `_restart_feeds()`: apertura/suscripción de feeds `/public` y `/market` para el nuevo set.
3. `take_decisions()`: evaluación e generación de observaciones a partir de los datos acumulados en los engines.

Un símbolo que entra por primera vez o se reincorpora tiene su feed abierto en el paso 2 y es evaluado en el paso 3 sin haber acumulado ventana de libro/flujo. Por eso `primera_vez` y `reincorpora` tienen `sin_libro`/`sin_flujo` y `ventana_incompleta`.

**Esta es una carrera reproducible del camino productivo**, demostrada con una prueba focalizada loopback (`tests/test_embudo_publica.py::test_carrera_simbolo_nuevo_sin_datos_se_descarta`). No sustituye la evidencia histórica: una reproducción local demuestra que el camino existe, no que fuera la causa exclusiva de todos los descartes de la corrida.

### ¿Qué queda explicado y qué queda UNKNOWN?

| Pregunta | Respuesta |
| --- | --- |
| ¿El embudo ya es consistente? | **Sí.** `candidate + comparator == total` en seleccionadas, aptas y descartadas; comprobado contra el JSONL original. |
| ¿Qué parte de los 77 descartes de comparadores queda explicada? | **44 (57 %)**: `primera_vez` + `reincorpora` sin libro ni flujo (carrera de feeds al entrar al seguimiento). |
| ¿Qué parte queda UNKNOWN? | **33 (43 %)**: `permanece` descartados, mayoritariamente por `dato_obsoleto_flujo` (32). No se puede atribuir a baja liquidez, rotación o transporte sin demostrar la secuencia de disponibilidad por símbolo. |
| ¿Hace falta una corrección técnica concreta antes de otra captura? | **No se recomienda cambiar la lógica productiva todavía.** La carrera es inherente al diseño (símbolos nuevos sin datos al entrar). Se puede mitigar con calentamiento de feeds antes de la primera evaluación, pero eso requiere cambiar tolerancias/lógica, fuera de este bloque. |
| ¿Qué incertidumbre resolvería una nueva adquisición? | Si el patrón de descartes de comparadores por "primera_vez" persiste con cierre acreditado y settle completo, confirmaría que es estructural (muestreo aleatorio sin reemplazo + símbolos nuevos sin datos) y no un artefacto de la corrida interrumpida. Una nueva adquisición requeriría autorización y run_id propios. |

---

## Limitaciones

- No se puede afirmar que el 100 % de los descartes de `primera_vez` se deba exclusivamente a la carrera de feeds; también podría ser que el símbolo no tuviera datos en el mercado en ese instante. `sin_libro`/`sin_flujo` sugiere falta de datos del feed, pero no lo prueba de forma exclusiva.
- Los 32 descartes de `permanece` comparadores por `dato_obsoleto_flujo` no implican necesariamente baja liquidez; pueden deberse a que el flujo no cubrió la ventana completa en el instante de decisión.
- No se presentan retornos brutos como P&L. `neto_estado = UNKNOWN` en todos los resultados.
- 60m queda NO EVALUADO (0 resultados).
- No se autoriza ni ejecuta otra captura. Una futura adquisición requeriría autorización y run_id propios.

---

## Pruebas (6 passed)

`tests/test_embudo_publica.py`:
1. `test_totales_por_rol_y_suma_global` — totales por rol y suma global (no solapamiento).
2. `test_tasas_denominadores_correctos` — tasas con denominadores correctos (sobre aptas y seleccionadas).
3. `test_condicion_incorporacion` — entrada, permanencia y reincorporación.
4. `test_timestamp_ausente_unknown` — timestamp ausente tratado como UNKNOWN.
5. `test_motivos_solapados_sin_duplicar_observaciones` — motivos solapados sin duplicar observaciones.
6. `test_carrera_simbolo_nuevo_sin_datos_se_descarta` — carrera reproducible (símbolo nuevo sin datos se descarta).
