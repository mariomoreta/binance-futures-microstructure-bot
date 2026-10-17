# Addendum de corrección — EVAL-CENSUS-V2 / artefacto 1385927

**SHA del commit publicado:** `13859277b7baa8b029d385c41bd3cb60c7cd4b13` (prefijo `1385927`).
**Rama:** `review/o1-funcional-v2-observacion`.
**Artefacto en Git:** `frontend/src/data/census-eval-v2.json` (sha256 `2b74a841…d37060`, 73051 B).

Este addendum corrige la declaración histórica del commit `1385927` sin borrarla. Se añade por addendum, sin reescribir el commit ni el doc base.

---

## 1. Identificación de 1385927

`1385927` NO es un run_id ni un ID de sesión. Es el prefijo de 7 caracteres de un objeto SHA válido en el repositorio:

```
git rev-parse --verify 1385927   ->   13859277b7baa8b029d385c41bd3cb60c7cd4b13
git show 1385927 --stat          ->   commit EVAL-CENSUS-V2 (censo causal exhaustivo + evaluacion same-grid)
```

Verificación de remoto:
```
git remote -v                    ->   origin https://github.com/mariomoreta/binance-futures-microstructure-bot.git (fetch/push)
git rev-parse HEAD               ->   13859277b7baa8b029d385c41bd3cb60c7cd4b13
git branch --show-current        ->   review/o1-funcional-v2-observacion
git fetch origin                 ->   FETCH OK
```

El objeto `1385927` existe localmente y en remoto. El árbol del commit contiene `frontend/src/data/census-eval-v2.json`.

**Declaración histórica conservada:** el commit `1385927` se refería al SHA final publicado de EVAL-CENSUS-V2, no a una sesión. Esta discrepancia queda documentada en este addendum.

---

## 2. Recalculo de celdas 1x (sin mezclar placebo)

Comando reproducible:
```
python scripts/verify_census_eval_v1.py
```

Resultado por símbolo / resolución / familia / segmento / coste 1x:

| Symbol | Res | Familia | Segmento | Events | Trades | Open | Skipped | Cells | NegCells |
|--------|-----|---------|----------|--------|--------|------|---------|-------|----------|
| BTCUSDT | 15m | H1/H3 direccional | dev | 757 | 286 | 0 | 471 | 2 | 2 |
| BTCUSDT | 15m | H1/H3 direccional | oos | 966 | 367 | 1 | 599 | 2 | 2 |
| BTCUSDT | 15m | H2 fade | dev | 60 | 37 | 0 | 23 | 2 | 2 |
| BTCUSDT | 15m | H2 fade | oos | 79 | 48 | 0 | 31 | 2 | 2 |
| BTCUSDT | 15m | baseline/placebo | dev | 842 | 269 | 0 | 573 | 1 | 1 |
| BTCUSDT | 15m | baseline/placebo | oos | 1020 | 309 | 0 | 711 | 1 | 1 |
| ETHUSDT | 15m | H1/H3 direccional | dev | 822 | 316 | 0 | 506 | 2 | 2 |
| ETHUSDT | 15m | H1/H3 direccional | oos | 987 | 379 | 1 | 608 | 2 | 2 |
| ETHUSDT | 15m | H2 fade | dev | 20 | 18 | 0 | 2 | 2 | 2 |
| ETHUSDT | 15m | H2 fade | oos | 63 | 37 | 0 | 26 | 2 | 2 |
| ETHUSDT | 15m | baseline/placebo | dev | 854 | 278 | 0 | 576 | 1 | 1 |
| ETHUSDT | 15m | baseline/placebo | oos | 1040 | 322 | 0 | 718 | 1 | 1 |
| SOLUSDT | 15m | H1/H3 direccional | dev | 887 | 331 | 0 | 556 | 2 | 2 |
| SOLUSDT | 15m | H1/H3 direccional | oos | 1076 | 396 | 1 | 680 | 2 | 2 |
| SOLUSDT | 15m | H2 fade | dev | 30 | 27 | 0 | 3 | 2 | 2 |
| SOLUSDT | 15m | H2 fade | oos | 37 | 26 | 0 | 11 | 2 | 1 |
| SOLUSDT | 15m | baseline/placebo | dev | 913 | 283 | 0 | 630 | 1 | 1 |
| SOLUSDT | 15m | baseline/placebo | oos | 1117 | 326 | 0 | 791 | 1 | 1 |
| (1h filas omitidas por brevedad; idénticas al artefacto) | | | | | | | | | |

### Conteo H1/H3 direccionales 15m @1x (SIN baseline)

| Métrica | Valor |
|---------|-------|
| Celdas H1/H3 direccionales 15m | 12 |
| Celdas negativas @1x | 12 |
| Eventos H1/H3 15m | 5495 |
| Trades H1/H3 15m | 2075 |
| Abiertas H1/H3 15m | 3 |
| Skipped overlap H1/H3 15m | 3420 |

**Corrección de 12/12 vs 18/18:** El commit `1385927` declara "H1/H3 RECHAZADAS (18/18 15m + 6/6 1h negativas @1x)". Ese 18/18 mezcla las 6 celdas baseline/comparator (3 símbolos × 2 segmentos = 6), que NO son direccionales H1/H3. Contando solo celdas direccionales H1/H3 15m @1x, son **12/12** y todas 12 son negativas. El doc base (`docs/OFFLINE_EVAL_CENSUS_V2.md`, §6) ya declara correctamente 12/12; el mensaje de commit declara incorrectamente 18/18. Este addendum subsana la discrepancia.

---

## 3. Conteos separados (verificados desde el artefacto)

| Conjunto | Eventos | Trades | Abiertas | Skipped overlap | Realizadas (trades − abiertas) |
|----------|---------|--------|----------|-----------------|-------------------------------|
| Hipótesis (1x, excluye baseline) | 7152 | 2991 | 5 | 4161 | 2986 |
| Placebo/baseline (1x) | 7152 | 2264 | 2 | 4888 | 2262 |
| **Total combinado** | **14304** | **5255** | **7** | **9049** | **5248** |

Contrato: `realizadas = trades − abiertas`. Verificado: 2991−5=2986 (hipótesis), 2264−2=2262 (placebo), 5255−7=5248 (total).

---

## 4. Reconstrucción numérica 9320 → 7152

| Etapa | Entradas | Exclusiones / motivo | Salidas |
|-------|----------|----------------------|---------|
| Detecciones admitidas (censo) | 9320 | — | 9320 |
| entry >= available | 9320 | 6 tail-edge sin entry (honesto) | 9314 con entry |
| Exclusiones por símbolo/intervalo/gap/cola/confirmación H2 / purga | 9314 | 2162 (motivo individual no desglosado en artefacto publicado) | 7152 entradas de hipótesis |
| Trades tras purga de solapes intra-celda | 7152 | 4161 skipped_overlap | 2991 trades |
| Abiertas (`open_at_end`) | 2991 | — | 5 abiertas; 2986 realizadas |

**Declaración de alcance:** Las etapas de exclusión intermedia (símbolo/intervalo/gap/cola/confirmación H2 / purga) suman 2162 exclusiones (9314 − 7152) pero el desglose por motivo individual **NO está explícito en el artefacto publicado** `census-eval-v2.json`. Los manifiestos temporales con los event_ids de cada etapa están en `temp/opencode/eval*_*/`, fuera de Git. Por tanto, la reconciliación etapa-a-etapa con motivo granular es **UNKNOWN** desde el artefacto publicado; solo es verificable el resultado final (9320 → 7152 → 2991).

---

## 5. Trazabilidad e independencia

### Trazabilidad detección → operación
El vínculo completo `detección original → definition/formation/available_at → mapping → evento exportado → operación o descarte` **NO está publicado en GitHub**. Los manifiestos con `event_ids` (p. ej. `BTCUSDT:1789741800000:LONG:H1:H1-v1:0`) residen en `temp/opencode/eval15_btc/manifest_BTCUSDT_15m.json` y hermanos, fuera de Git. Por tanto:

- Vínculo completo detección → operación: **UNKNOWN** (no publicado en Git)
- Campos `event_id/definition/formation/confirmation/availability` conservados en manifiestos temporales: **VERIFICABLE en temp, no en Git**
- `census-eval-v2.json` publicado en Git conserva conteos agregados pero no event_ids individuales.

### 594 grupos duplicados / 616 filas extra
- 594 grupos de duplicados contados, 616 filas extra. Nunca tratados como independientes.
- Regla que evita duplicación en cada métrica: agrupación por `event_id` en manifiestos; `originals_matched: 2831/2831`; `duplicate_extra_rows: 616` excluidas del conteo de independientes.
- `max_concurrent=1` es INTRA-celda (hasta 65% skips en SOL cont-dev). **NO prueba independencia estadística entre familias o celdas**; cross-celda no modelada, no reclamada.
- Independencia entre familias/celdas: **UNKNOWN** (no modelada en el censo).

---

## 6. Funding

### Separación: aplicaciones por operación vs liquidaciones únicas
- Liquidaciones únicas del calendario (símbolo + timestamp): 90 por símbolo (BTC, ETH, SOL) = **270 únicas** (ver `temp/opencode/funding_*.json`, `n: 90` por símbolo, `rateType: Regular`, `fundingTime` único por fila).
- Aplicaciones por operación: **741** (declaradas en commit `1385927`; no desglosadas por operación en el artefacto publicado).
- No son la misma métrica: 741 aplicaciones ≠ 270 liquidaciones únicas.

### unknown-excluded vs uncovered
- `0 unknown-excluded en las 60 celdas` (declarado): indica que no se excluyó ninguna celda por falta de mark de settlement.
- `24/60 celdas con holdings de cola fuera del calendario = uncovered/UNKNOWN`: holdings fuera del calendario de funding, no liquidaciones excluidas.
- **No son lo mismo:** unknown-excluded = falta de mark para aplicar funding; uncovered = posición de cola sin cobertura en el calendario. Presentar `0 unknown-excluded` como "cobertura completa" es incorrecto; las 24/60 celdas uncovered permanecen.

### Reconciliación 24/60 celdas
- 60 celdas totales (3 símbolos × 2 resoluciones × 2 segmentos × 5 familias... estructura de celdas del artefacto).
- 24 celdas con uncovered/UNKNOWN (holdings de cola fuera de calendario).
- 36 celdas con cobertura completa en ventana.
- Esto es **consistente** con la declaración del commit; no hay contradicción numérica, solo conceptual entre unknown-excluded (0) y uncovered (24/60).

---

## 7. Contradicciones del informe

| Contradicción | Resolución |
|---------------|------------|
| H1/H3 12/12 frente a 18/18 celdas 15m | 18/18 mezcla baseline. Contando solo direccionales: **12/12**, todas negativas @1x. Corregido en este addendum. |
| MFE/MAE reportados frente a "no capturados" | MFE 0.18–0.66% / MAE 0.10–0.42% existen como excursión; la **captura** es pregunta de regla de salida no respondida en este informe. No hay contradicción: los valores son excursión, no captura realizada. |

Ambas resoluciones usan los resultados fuente del artefacto, no estimaciones.

---

## 8. Verificabilidad y estado de entrega

- Artefacto en Git: `frontend/src/data/census-eval-v2.json` (en commit `1385927`).
- Script de verificación: `scripts/verify_census_eval_v1.py` (nuevo en este commit).
- Manifiestos con event_ids: en `temp/opencode/`, **fuera de Git** — no parte de la entrega publicada.
- Sin corridas Binance, sin forward, sin paper, sin órdenes, sin optimización de umbrales.
- V2 disponible en 3020; monitor detenido.

**Pendientes para entrega completa en GitHub:**
- Los manifiestos temporales (`eval*_*/manifest_*.json`) necesitan ser publicados o declarados formalmente fuera de alcance.
- El vínculo completo de trazabilidad (event_id → operación) queda como UNKNOWN hasta que los manifiestos estén en Git.

---

## 9. Comandos ejecutados y resultados

```
git rev-parse --verify 1385927          -> 13859277b7baa8b029d385c41bd3cb60c7cd4b13 (VALID)
git show 1385927 --stat                  -> commit EVAL-CENSUS-V2 (HEAD de review/o1-funcional-v2-observacion)
git remote -v                            -> origin https://github.com/mariomoreta/binance-futures-microstructure-bot.git
git fetch origin                         -> FETCH OK
python scripts/verify_census_eval_v1.py  -> 7152/2991/5/4161 (hipótesis), 7152/2264/2/4888 (placebo), 14304/5255/7/9049 (total)
```

---

## 10. Pendientes

1. Publicar manifiestos de `temp/opencode/eval*_*/` en Git o declarar formalmente fuera de alcance.
2. Completar trazabilidad event_id → operación (actualmente UNKNOWN).
3. Commit selectivo y push de este addendum + script de verificación (pendiente al momento de este documento).
4. No declarar "flujo publicado/verificado" hasta que la evidencia esté efectivamente en GitHub.
