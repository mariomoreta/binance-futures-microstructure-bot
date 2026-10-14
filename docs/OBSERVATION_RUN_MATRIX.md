# Matriz de funcionalidades — corridas de observacion con Dashboard V2 principal

Base: backend revision `3cbbb1c`; V2 checkpoint `27b7af5`
(`dash-v2-03-token-detail`, rama a continuar; no modificarla desde aqui).
Verificacion de lectores V2 por `git show 27b7af5:...` (sin checkout).
Backend verificado en este arbol. Leyenda: DISPONIBLE / PARCIAL /
AUSENTE.

Correccion 2026-10-14 (revision independiente, verificada en este
arbol): las restricciones historico-2 / operacional-9 pertenecen al
SHA 27b7af5, NO a esta rama. Los lectores publicados aqui SI admiten
operacional 9/10 (`system-evidence.ts`: `schemaValue==="9"||"10"`,
probado `accepts schema 10`, `system-evidence.test.ts:65`) e
historico 2/3 (`historical-coverage.ts`, probado `accepts schema 3`,
`historical-coverage.test.ts:32`). Verificado vivo 2026-10-14 por
copia-temp read-only: operacional `data/microprobe.db` = v10 (22
tablas), historico `data/historical/historical.db` = v3 (16 tablas);
ambos dentro de contrato. Compatibilidad implementada != consumo vivo
comprobado: ningun consumo extremo a extremo con servicios se ha
verificado aun (ver fila 2/8, Pendiente). Ruta historica correcta:
`data/historical/historical.db` (NO `data/historical.db`). Base
historica = base main preexistente (ingestas research previas, v3,
14 coberturas, 2831 eventos; `data/` git-ignored, solo lectura en
esta tarea); base incremental de esta tarea = 0 filas (cero corridas
lanzadas, cero escrituras).

| # | Funcion | Backend disponible | Lector V2 @27b7af5 | Incompatibilidad | Pendiente | Aceptacion |
|---|---|---|---|---|---|---|
| 1 | Captura del bot (observaciones crudas) | `probe.py` -> `market_observations` / `rejected_observations` (v10) | AUSENTE (V2 lee features derivadas, no crudo) | ninguna (fuera de V2 por diseno) | contrato o exclusion explicita | corrida escribe observaciones; V2 no las reclama |
| 2 | Estado y salud | `/api/health`, `/system`, `system-evidence` (tablas + spans) | `system-evidence/route.ts` + paneles System (V2-71) | gate admite 9/10 (compat implementada); consumo vivo sin comprobar | verificacion viva con servicios + screenshots | 200 en v10/v3 actuales tras lectura viva; 503 solo ante schema fuera de 9/10 (`SYSTEM_EVIDENCE_UNAVAILABLE`) |
| 3 | Movers | `/movers`, `/api/discovery`, velocity/ranks | `live-movers/route.ts` + `/movers` (alignment/freshness UNVERIFIED) | etiquetas v9 hardcodeadas; tablas v10 compatibles en lectura | declarar v10 + superficie run_id/as_of | categorias con fuentes declaradas; sin orden LONG/SHORT |
| 4 | Detalle del token | `/symbol/:symbol`, chart/CSV `/api/symbol/` | `/symbol/[symbol]` (dash-v2-03) | misma familia de etiquetas v9 | declarar v10; cobertura historica por `historical-coverage` | paneles con DISCOVERY ONLY honesto; CSV acotado |
| 5 | Indicadores y procedencia | motores returns/flow/book/OI/structure + linkage v3 (run_id/as_of/fuente) | lectores de `*_features` (sin run_id en view-model) | procedencia v3 no superficie en V2 | extender view-model con `as_of`/fuente/version | cada indicador muestra ancla/horizonte/frescura o UNKNOWN |
| 6 | Oportunidades | `/api/opportunities` (v0.1.0, lifecycle) | `opportunities/route.ts` (STALE/UNKNOWN, `recordedOpportunities`) | etiquetas v9; sin probabilidad (por diseno) | declarar v10 | lifecycle + RESEARCH ONLY sin P&L |
| 7 | Prospectivos | `/api/prospective` (tablas v10, lectura OK) | `prospective/route.ts` (reporta `schema_version` real 9/10 desde `persistence_meta`, correccion 2026-10-14) | ninguna (etiqueta fija 9 eliminada) | consumo vivo sin comprobar | COMPLETE/PENDING/INSUFFICIENT sin fabricar |
| 8 | Historico | `data/historical/historical.db` v3 (base main preexistente; incremental de esta tarea 0 filas) | `historical-coverage` + `/historical-research/*` (lectura REAL readOnly) | gate admite 2/3 (compat implementada); consumo vivo sin comprobar | verificacion viva con servicios + screenshots | 200 en v3 actual tras lectura viva; 503 solo ante schema fuera de 2/3 |
| 9 | Calidad de datos | rechazos/skew/gaps (SYSTEM), `historical_gaps`, diagnosticos V2-70 (streams, parse, clock) | diagnosticos grabados + `historical_gaps` via coverage | gates 9/10 + 2/3 admitidos (ver correccion arriba) | consumo vivo sin comprobar | gaps/UNKNOWN visibles; cobertura nunca inferida |
| 10 | Supervision de corridas | `control supervise`/sentinel/`launch_supervised_transaction` (DISABLED) + `status_readonly` | `runtime/*`, `launch-readiness.ts`, `runtime-control.ts` (DASH-V2-45/46/47; bloquea starts no supervisados) | Start habilitado pendiente de autorizacion + revision SHA | autorizacion explicita + revision exacta antes de habilitar | Start rechaza sin requisitos; UI != arranque del bot |

## Funding: tres niveles separados (sin mezclar)

- **Cotizado** (contexto): `funding_snapshot` (dashboard legado) y
  `funding_estimated_bps` (motor): tasa proxima citada + `fundingTime`;
  jamas entra en contabilidad.
- **Calendario realizado**: `FundingCalendar` versionado por contrato
  (timestamp + tasa liquidadas, identidad, dedup, gaps, completitud);
  fuente/ recepcion explicitas.
- **Contabilidad de replay**: `run_backtest` (qty x mark causal,
  realizado vs hipotetico, `funding_events[]` con basis). Reglas de
  presentacion: lo cotizado se rotula FUTURO-ESTIMADO; lo realizado cita
  calendario+version; el replay cita dataset+config+segmento. Ningun
  nivel sustituye a otro.

## Integracion pertinente en V2 (contratos explicitos, sin codigo UI aqui)

1. View-model de estado/features con `as_of`/fuente/version (linkage v3).
2. Declaracion v10/v3 en un SHA frontend revisado (gates actualizados).
3. Superficie de funding en tres niveles (reglas de arriba).
4. Preflight de almacenamiento (contrato: docstring + umbrales en
   `scripts/storage_preflight.py` — `WARN_FREE_BYTES=1_000_000_000`
   avisos, salida exit 0/2 — integrados como requisito de readiness en
   `frontend/src/lib/launch-readiness.ts`: BLOQUEO sin DB operacional
   legible, sin disco medible o bajo `STORAGE_BLOCK_FLOOR_BYTES`
   (256MB); ADVERTENCIA sin bloqueo bajo el piso de aviso 1GB, sin
   snapshot, o sin historico — cobertura research UNKNOWN).
5. Ciclo de uso y lista de aceptacion (`docs/OBSERVATION_RUN_CYCLE.md`).
Nada de esto autoriza operacion, paper, ejecucion ni gates.
