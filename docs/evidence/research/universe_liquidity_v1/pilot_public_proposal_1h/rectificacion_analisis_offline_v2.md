# Rectificación del análisis offline — captura pública public-pilot-1h-20261105a

**run_id:** `public-pilot-1h-20261105a`
**Rama / base:** `research/universe-liquidity-v1` en `5a404219d45d1584e085ac2208718bccdcb269fe`
**Estado de la corrida:** `corrida_interrumpida_o_cierre_no_acreditado` (causa de parada `UNKNOWN`)
**Análisis:** solo lectura, offline, sin conexión a Binance, sin adquisición de datos nuevos.
**Script:** `scripts/analisis_offline_captura_publica.py` (v2)
**Pruebas:** `tests/test_analisis_offline_captura_publica.py` (9 passed)
**Tablas pequeñas (Git):** `docs/evidence/research/universe_liquidity_v1/pilot_public_proposal_1h/tablas/resumen_analisis_offline_v2.json`
**Derivados detallados (fuera de Git):** `C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\derivados\analisis_v2\analisis_completo_v2.json`

Esta rectificación **no sobrescribe** el informe anterior (`informe_analisis_offline.md`). Corrige unidades, añade comparación por ciclo y por símbolo, explica la cobertura desigual y hace reproducibles las asociaciones. Las cifras anteriores se declaran sustituidas por el cálculo ahora reproducible; no se ajustaron cortes para recuperar sus valores.

---

## A. Embudo de cobertura por rol

| Rol | Seleccionadas | Aptas | Descartadas | Resultados 5m | Resultados 15m | Resultados 60m |
| --- | --- | --- | --- | --- | --- | --- |
| candidate | 144 | 128 | 112 (solapados con comparator) | 97 | 76 | 0 |
| comparator | 96 | — | — | 18 | 15 | 0 |

Nota: los descartes por motivo pueden solaparse (una observación descartada puede tener varios motivos); sus conteos no suman obligatoriamente al total de descartes.

**Tasas de cobertura (5m):**
- Candidatos: 97/144 seleccionadas = 67,4 %; 97/128 aptas = 75,8 %.
- Comparadores: 18/96 seleccionadas = 18,8 %.

**Tasas de cobertura (15m):**
- Candidatos: 76/144 seleccionadas = 52,8 %; 76/128 aptas = 59,4 %.
- Comparadores: 15/96 seleccionadas = 15,6 %.

**Resultado faltante (nunca cero):** 178 = aptas (128) × 3 horizontes (384) − generados (206). Causa: UNKNOWN (cierre no acreditado).

**60m:** NO EVALUADO (0 resultados).

**Descartes por motivo (pueden solaparse):** `sin_libro` 66, `sin_flujo` 66, `dato_obsoleto_flujo` 37, `dato_obsoleto_libro` 15. Distribuidos en los 12 ciclos y en ambos roles; no se concentra solo en el primer ciclo.

---

## B. Comparación global, por ciclo y por símbolo

### Global (agrupada, no ajustada por ciclo)

| Horizonte | Grupo | n | Media fraccional | Media % | Mediana % | Desv. % | Mín % | Máx % | % positivos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | Candidatos | 97 | −0,003398 | −0,340 | −0,150 | 1,263 | −5,290 | 2,084 | 0,402 |
| 5m | Comparadores | 18 | −0,000535 | −0,054 | −0,021 | 0,527 | −1,829 | 0,669 | 0,500 |
| 15m | Candidatos | 76 | −0,012251 | −1,225 | −0,724 | 2,220 | −8,582 | 1,880 | 0,303 |
| 15m | Comparadores | 15 | −0,001166 | −0,117 | −0,245 | 0,578 | −1,427 | 1,030 | 0,333 |

**Diferencia de medias agrupada (cand − comp):**
- 5m: −0,286 puntos porcentuales.
- 15m: −1,108 puntos porcentuales.

### Por ciclo (mismo peso a cada ciclo con ambos grupos)

Solo ciclos con resultados utilizables de candidatos y comparadores:

**5m (9 ciclos):**
- Media de diferencias por ciclo: −0,325 puntos porcentuales.
- Rango de diferencias por ciclo: −1,166 a +0,376 puntos porcentuales.
- La diferencia de medias agrupada (−0,286 pp) **no es igual** a la media de diferencias por ciclo (−0,325 pp): son estadísticas distintas, claramente separadas.

**15m (7 ciclos):**
- Media de diferencias por ciclo: −1,223 puntos porcentuales.
- Rango de diferencias por ciclo: −2,234 a −0,390 puntos porcentuales.
- La diferencia de medias agrupada (−1,108 pp) **no es igual** a la media de diferencias por ciclo (−1,223 pp).

Los tamaños de grupo por ciclo varían mucho (candidatos 9–12, comparadores 1–4), por lo que la media agrupada da más peso a ciclos con más observaciones; la media de diferencias por ciclo da igual peso a cada ciclo.

### Por símbolo (media y mediana por símbolo, horizonte, rol)

Se publica el resumen por símbolo en las tablas pequeñas. Ningún símbolo cambia de rol entre ciclos en este dataset (cada símbolo mantiene un solo rol por ciclo observado, aunque un símbolo puede aparecer en varios ciclos con el mismo rol).

**Ponderación igual por símbolo (promedio de las medias de cada símbolo):**
- 5m candidate: −0,362 % (15 símbolos).
- 5m comparator: −0,260 % (8 símbolos).
- 15m candidate: −1,353 % (14 símbolos).
- 15m comparator: −0,312 % (8 símbolos).

Regla de ponderación: igual peso por símbolo (promedio de medias por símbolo), no promedio de todos los retornos. Esto no garantiza independencia estadística.

---

## C. Asociaciones reproducibles

Métricas fijadas de antemano (solo variables al decidir): `delta_ratio` (flujo) y `profundidad_notional_top20` (libro, USDT).

| Horizonte | Métrica | n pares válidos | Pearson | Símbolos | Ciclos | Excluidos (métrica None) | Excluidos (retorno None) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | delta_ratio | 115 | −0,052 | 24 | 1,3,4,5,6,7,8,9,10 | 0 | 0 |
| 5m | profundidad_notional_top20 | 115 | 0,133 | 24 | 1,3,4,5,6,7,8,9,10 | 0 | 0 |
| 15m | delta_ratio | 91 | 0,034 | 24 | 1,3,4,5,6,7,8 | 0 | 0 |
| 15m | profundidad_notional_top20 | 91 | 0,265 | 24 | 1,3,4,5,6,7,8 | 0 | 0 |

**Terciles de delta_ratio (corte por posición ordenada; empates por posición estable):**
- 5m: bajo (n=39, media −0,191 %), medio (n=38, media −0,319 %), alto (n=38, media −0,378 %). Sin patrón monotónico claro.
- 15m: bajo (n=31, media −0,816 %), medio (n=30, media −1,274 %), alto (n=30, media −1,045 %). Sin patrón monotónico claro.

**Método:** Pearson sobre pares válidos (ambas variables finitas y no None). Varianza cero o muestra < 2 → Pearson indefinido con motivo, nunca cero inventado. Terciles con n < 3 → motivo, sin valores inventados.

---

## D. Rectificación de las afirmaciones anteriores

Se eliminan expresiones como "ligeramente" o "pequeño" que no estaban justificadas. La magnitud observada (diferencias de −0,286 pp a 5m y −1,108 pp a 15m en la media agrupada) **no demuestra rentabilidad ni una oportunidad operable en corto**. Las dispersiones son altas, los comparadores son escasos, las muestras no son independientes y el cierre de la corrida no está acreditado.

Las dos asociaciones marginales (delta_ratio y profundidad vs retorno) **no prueban directamente** "flujo agresor relativo a liquidez". Son correlaciones marginales débiles, exploratorias y posteriores a observar los datos.

**Variables ya capturadas que permitirían evaluar posteriormente esa relación (con limitaciones):**
- Magnitud del flujo (no solo su desequilibrio `delta_ratio`): disponible en `flujo.base_volume`, `buy_notional`, `sell_notional`.
- Profundidad y unidades: `bid_notional_top20` / `ask_notional_top20` (USDT), pero top-20 no representa una banda fija de ±1 % y la cobertura de precios puede diferir entre símbolos.
- Ventana del flujo: `flujo.window_ms` y `flujo.ventana_completa`.
- Cobertura variable del top-20 entre símbolos.

Cualquier análisis adicional sobre estos mismos resultados sería exploratorio y posterior a haberlos observado. No se optimizan umbrales ni se propone una operación.

---

## E. Recomendación concreta sustentada

**No repetir la captura simplemente porque falta 60m.** El problema que resolvería la siguiente adquisición es permitir que el **settle complete los 60m** con un **cierre acreditado** (código de salida, logs de consumo, archivos de control de fin). Solo entonces:
- el horizonte 60m tendría denominador completo;
- la comparación candidatos vs comparadores usaría todas las aptas (no solo las con resultado observado);
- se podría distinguir si la diferencia negativa observada es estable o artefacto de cobertura desigual.

Condición: sin cambiar reglas, tolerancias ni estrategia; sin crear otro `run_id`.

---

**Descargo:** lectura descriptiva de una única captura limitada (44 símbolos, una hora, cierre no acreditado). No se presentan retornos brutos como P&L. `neto_estado = UNKNOWN` en todos los resultados. Insuficiencia de datos no es ausencia de ventaja.
