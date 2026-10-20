# Backtest V2 — evidencia e2e en navegador (cinco defectos corregidos)

Fecha: 2026-10-20 · Rama: `review/o1-funcional-v2-observacion`
Build servido: Next.js `next build` + `next start -p 3020 -H 127.0.0.1` (frontend)
URL base: `http://127.0.0.1:3020`

## 1. Ejecución real (flujo completo)

| Paso | Acción | Resultado |
|---|---|---|
| 1 | `GET /backtest` | HTTP 200, estado inicial `Tarea: SIN EJECUTAR` |
| 2 | Click en `Ejecutar backtest` | `POST /api/v1/backtest/run` → `started: true` |
| 3 | Sondeo `/api/v1/backtest/status` | `EJECUTANDO` → `COMPLETADO` (~16 s, ejecutor Python real) |
| 4 | Sección «3. Resultados del experimento» | Renderizada con agregados @1x, hipótesis y placebo separados |
| 5 | Click en `Ejecutar backtest` (segunda vez) | Nueva ejecución con identidad nueva, sin duplicados |
| 6 | Espera a `COMPLETADO` | Resultados del segundo run servidos y enlazados al run nuevo |
| 7 | Click en `Abrir replay` (fila 817:H1) | `GET /api/v1/backtest/replay?...&run=<run2>` → 200, Paper Lab carga el artefacto |

Run ids reales observados:

- Run 1: `bt-eval-census-v2-trio-20261020213213876-614cf8ad`
- Run 2: `bt-eval-census-v2-trio-20261020213645692-d701b7ef`

Valores servidos (idénticos en ambos runs, motor determinista):

- Operaciones @1x: 5255 (5248 realizadas + 7 abiertas)
- Resultado REALIZADO @1x — hipótesis: `-5011.37`
- Resultado REALIZADO @1x — placebo (referencia): `-3826.43`
- Marcas de abiertas @1x: `-7.04`
- Suma aritmética de ledgers @1x (control): `-8837.79` (etiquetada «NO es cartera ni beneficio de una estrategia»)
- Reconciliación con el motor: `OK` (56 celdas de resultado + 14 auxiliares)
- Operaciones totales (1x+2x+3x): 15765 (mismo conjunto bajo tres escenarios de coste)

## 2. Contratos de error observados (sin sustitutos)

| Petición | Estado | Cuerpo |
|---|---|---|
| `GET /api/v1/backtest/replay?...&run=<run2>` | 200 | `run_id` = run2, `artifact.provenance.backtest_run_id` = run2, `replay_id` = `PLR-BTCUSDT-LONG-1788817500000-baseline-1.0x` |
| `GET /api/v1/backtest/replay?...event_id=NOPE` | 422 | `{"error":"TARGET_NOT_IN_RUN","detail":"La operacion no pertenece a los resultados de esta ejecucion.","run_id":<run2>}` |
| `GET /api/v1/backtest/results?run=bt-eval-census-v2-trio-20990101000000000-deadbeef` | 409 | `{"available":false,"status":"sin_ejecutar","error":"RESULT_NOT_READY","run_id":"...deadbeef"}` |
| `GET /api/v1/backtest/results?experiment=no-existe` | 400 | `{"error":"EXPERIMENT_NOT_ALLOWED"}` |

Paper Lab con identidad inexistente muestra: «No se pudo cargar la operación enlazada desde Backtest
(TARGET_NOT_IN_RUN). La operación sigue disponible en la tabla de Backtest; no se fabrica un replay alternativo.»

Consola del navegador durante el recorrido: 0 errores de ejecución; los únicos `error` registrados son
los `4xx` intencionales de las pruebas negativas anteriores. 36 advertencias (preexistentes, configuración de Vite).

## 3. Evidencia visual (escritorio)

Alcance vigente: `docs/DESKTOP_FIRST_SCOPE_20261020.md` (SCOPE-DESKTOP-FIRST-20261020).
La QA, las capturas y los criterios de aceptación móviles están aplazados, así que
esta entrega publica solo capturas de escritorio; no se añadió trabajo móvil.

Capturas (publicadas, generadas desde el build servido, 1440×900):

- `BACKTEST_V2_FIX_DESKTOP_RESULTS.png` (página completa)
- `BACKTEST_V2_FIX_DESKTOP_RESULTS_METRICS.png` (recorte del panel de métricas, escala de dispositivo)
- `BACKTEST_V2_FIX_DESKTOP_LINKED_REPLAY.png` (Paper Lab con replay enlazado, página completa)

**Separación de evidencia:**

- Verificación **DOM/árbol de accesibilidad** (automática): textos, estados, enlaces, respuestas de red y
  códigos de estado de la tabla anterior. No sustituye la inspección visual.
- Inspección **visual real** (lectura directa de la captura por el modelo): en
  `..._DESKTOP_RESULTS_METRICS.png` se confirma que «Resultado REALIZADO @1x — hipótesis» y
  «Resultado REALIZADO @1x — placebo (referencia)» son tarjetas distintas y que
  «Suma aritmética de ledgers @1x (control)» lleva el aviso «suma técnica de dos ledgers distintos;
  NO es cartera ni beneficio de una estrategia», sin solapes ni recortes.

Limitaciones declaradas: la inspección visual se hizo sobre las capturas publicadas; no se auditaron colores
exactos ni contraste WCAG (no forma parte de los cinco defectos). La captura de página completa se entrega a
escala CSS reducida por el visor y en ella el texto pequeño no es legible: por eso se añadió el recorte.
