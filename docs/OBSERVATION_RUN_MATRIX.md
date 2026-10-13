# Matriz de funcionalidades — corridas de observacion con Dashboard V2 principal

Base: backend revision `3cbbb1c`; V2 checkpoint `27b7af5`
(`dash-v2-03-token-detail`, rama a continuar; no modificarla desde aqui).
Verificacion de lectores V2 por `git show 27b7af5:...` (sin checkout).
Backend verificado en este arbol. Leyenda: DISPONIBLE / PARCIAL /
AUSENTE. Incompatibilidad v10/v3: los gates del frontend citado exigen
historico-2 (`UNSUPPORTED_HISTORICAL_SCHEMA`) y operacional-9
(`UNSUPPORTED_SYSTEM_SCHEMA`); el backend actual es historico-v3 +
operacional-v10 (fail-closed en ambas hasta un SHA que declare v10/v3).

| # | Funcion | Backend disponible | Lector V2 @27b7af5 | Incompatibilidad | Pendiente | Aceptacion |
|---|---|---|---|---|---|---|
| 1 | Captura del bot (observaciones crudas) | `probe.py` -> `market_observations` / `rejected_observations` (v10) | AUSENTE (V2 lee features derivadas, no crudo) | ninguna (fuera de V2 por diseno) | contrato o exclusion explicita | corrida escribe observaciones; V2 no las reclama |
| 2 | Estado y salud | `/api/health`, `/system`, `system-evidence` (tablas + spans) | `system-evidence/route.ts` + paneles System (V2-71) | gate operacional-9 vs backend v10 => 503 fail-closed | SHA frontend que declare v10 | 503 con `SYSTEM_EVIDENCE_UNAVAILABLE` en v10; 200 solo en v9 |
| 3 | Movers | `/movers`, `/api/discovery`, velocity/ranks | `live-movers/route.ts` + `/movers` (alignment/freshness UNVERIFIED) | etiquetas v9 hardcodeadas; tablas v10 compatibles en lectura | declarar v10 + superficie run_id/as_of | categorias con fuentes declaradas; sin orden LONG/SHORT |
| 4 | Detalle del token | `/symbol/:symbol`, chart/CSV `/api/symbol/` | `/symbol/[symbol]` (dash-v2-03) | misma familia de etiquetas v9 | declarar v10; cobertura historica por `historical-coverage` | paneles con DISCOVERY ONLY honesto; CSV acotado |
| 5 | Indicadores y procedencia | motores returns/flow/book/OI/structure + linkage v3 (run_id/as_of/fuente) | lectores de `*_features` (sin run_id en view-model) | procedencia v3 no superficie en V2 | extender view-model con `as_of`/fuente/version | cada indicador muestra ancla/horizonte/frescura o UNKNOWN |
| 6 | Oportunidades | `/api/opportunities` (v0.1.0, lifecycle) | `opportunities/route.ts` (STALE/UNKNOWN, `recordedOpportunities`) | etiquetas v9; sin probabilidad (por diseno) | declarar v10 | lifecycle + RESEARCH ONLY sin P&L |
| 7 | Prospectivos | `/api/prospective` (schema v9, tablas v10-compatibles) | `prospective/route.ts` (`schema_version:9`) | etiqueta 9 vs tablas v10 (lectura OK, etiqueta pendiente) | declarar v10 | COMPLETE/PENDING/INSUFFICIENT sin fabricar |
| 8 | Historico | `/api/history/*` (historical.db v3) | `historical-coverage` + `/historical-research/*` (lectura REAL readOnly) | gate historico-2 vs backend v3 => `UNSUPPORTED_HISTORICAL_SCHEMA` | SHA frontend que declare v3 | 503 fail-closed en v3; datos solo en v2 |
| 9 | Calidad de datos | rechazos/skew/gaps (SYSTEM), `historical_gaps`, diagnosticos V2-70 (streams, parse, clock) | diagnosticos grabados + `historical_gaps` via coverage | mismos gates 2/9 | declarar v10/v3 | gaps/UNKNOWN visibles; cobertura nunca inferida |
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
4. Preflight de almacenamiento (contrato `docs/STORAGE_PREFLIGHT_CONTRACT.md`).
5. Ciclo de uso y lista de aceptacion (`docs/OBSERVATION_RUN_CYCLE.md`).
Nada de esto autoriza operacion, paper, ejecucion ni gates.
