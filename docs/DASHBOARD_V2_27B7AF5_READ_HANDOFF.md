# Handoff de lectura — frontend exacto `27b7af59cb1e313169f49655161d66e043b5412d`

Status: READ-ONLY HANDOFF (research/prep). Revisado desde Git
(`git show 27b7af5:...`); `frontend/` NO modificado en esta tarea.
Nada aqui autoriza operacion, paper, ejecucion ni avance de gates.

## Que es este SHA

Commit `27b7af5` ("Integrate recorded System panels and flag unverified
source rows", rama `dash-v2-03-token-detail`). Contiene rutas BFF bajo
`frontend/src/app/api/v1/` (live-movers, market-snapshot, opportunities,
price-series/[symbol], prospective, historical-coverage,
historical-research, runtime, runtime/start, runtime/stop,
runtime/readiness, system-evidence) y adapters de lectura
(`frontend/src/lib/canonical-market.ts`, `historical-db.ts`,
`persisted-market.ts`, `live-movers.ts`). Integracion PARCIALMENTE
implementada (ruta de lectura existe); feed live/operacion NO
verificados (las rutas declaran alignment/freshness UNVERIFIED).

## Que lee (verificado en el arbol del SHA)

- `historical-db.ts`: abre `data/microprobe.db` en modo readOnly con
  `node:sqlite` (`DatabaseSync(path, {readOnly: true})`).
- `canonical-market.ts`: `historicalRead` con BEGIN/COMMIT (+ROLLBACK en
  error) sobre tablas `discovery_snapshots`, `return/flow/book/oi/
  structure/state_features`, `price_samples`, `prospective_setups`,
  `prospective_outcomes`, `opportunity_candidates`; fallback
  `available:false` ante cualquier error.
- `historicalSnapshot` etiqueta `schema_version:9` (hardcodeado) y lee
  tablas de la era v9 (`prospective_*`, `price_samples`).
- Las rutas BFF advierten: "Read time is not observation time",
  "Retained coverage and captured freshness do not certify present feed
  liveness".

## Incompatibilidad explicita operacional-v10 / historico-v3

- El backend operacional (`data/microprobe.db`) es schema v10: tablas v9
  + columnas de linkage run_id/rules_version/as_of/dataset (migraciones
  v1..v10 en una init, error explicito ante tablas ausentes — R6).
- El store historico (`data/historical/historical.db`) es schema v3 y es
  OTRO archivo: klines/mark-klines/OI/coverage/gaps/runs de ingesta,
  event studies y research buckets. El frontend 27b7af5 NO lo lee.
- Consecuencia: consumir 27b7af5 contra un backend v10 exige verificar
  presencia de tablas por contrato versionado (nunca asumir); el
  `schema_version:9` hardcodeado del frontend NO certifica el backend.
  H2/H3/funding dependen de calendarios y linkage que este SHA no conoce.

## Reglas de consumo (binding)

1. Solo lectura readOnly sobre copias o el canonico declarado; ningun
   test/fixture escribe en `data/` (barrera
   `scripts/audit_test_isolation.py`).
2. Tablas ausentes => error explicito nombrando la tabla (R6); jamas skip
   silencioso ni fallback inventado.
3. `run_id`/versiones/`as_of`/fuente/dataset se propagan sin backfill de
   historicos NULL (= UNKNOWN).
4. La fundacion antigua de `frontend/` no se edita como sustituto de este
   handoff: cualquier cambio necesita revision del SHA exacto nuevo.

## Pendiente para el frontend exacto

Revision del SHA que consuma: contratos v10/v3 declarados aqui,
calendarios de funding versionados, y linkage research (run_id) antes de
cualquier integracion viva. Sin paper/ejecucion.
