## Visibilidad global de corridas V2 (2026-10-16, sobre 5d4fef6, sin push aun)
Barra global en todas las pantallas (estado, origen, run_id, inicio,
duracion prevista y restante vivo; feed/supervisor/sentinel por
separado con frescura; en terminal motivo, hora de cierre y duracion
congelada; registrado vs verificado). Stop con confirmacion para
cualquier corrida verificada del proyecto (dashboard/agent/direct),
backend verifica identidad/propiedad sin ampliar permisos. Tests:
backend 10 + frontend 63 dirigidos verdes; fixtures y procesos
aislados, cero corridas Binance. Reconciliacion: 123.957s vs 133s
sin contradiccion, 9 funding artefacto sin valor de senal, aborto
previo con retraso observado pero origen no aislado (correccion).
Contratos y docs actualizados. Resta: barrera completa, commit
selectivo, push, entrega con SHA/pruebas/capturas. V2 abierto,
monitor detenido (COMPLETED, PIDs muertos).

## Piloto brief COMPLETADO 20261015T102519Z (2026-10-15, autorizado, sin push aun)
Arranque V2 confirmado (492/12980/20736); 123.96s, 82161 msgs,
0 rechazos, lags sanos, dispatch p50 ~0.001ms (primera medicion),
yield combinado p50 ~0.6s; watchers 6+6 sin abortos; cierre natural
code 0, PIDs muertos, COMPLETED congelado 133s; sin hot journal;
V2 lee todo (price 12->51). Evidencia PILOT_BRIEF_20261015_COMPLETED
+ copia RECOVERY_CANONICAL aplicada. Dashboard abierto.

## Mantenimiento recovery APLICADO (2026-10-15, autorizado, sin push aun)
Pre verificado (SHA e773e51, cero escritores, V2 propio detenido por
identidad, registry ABORTED, hashes sin deriva, destino fuera del
repo). Apply PASS: backup real + restore + integrity ok + schema 10 +
conteos iguales + journal consumido. Hash resultante byte-identico
(rollback limpio). V2 reiniciado (PID 25684): readiness 6/6,
5 rutas 200. Monitor NO arrancado. Evidencia
DB_MAINTENANCE_APPLIED_20261015.txt.

## Ventana por registry + fixture hot real (2026-10-16, sin push aun)
Sonda lock eliminada (recuperaba el original pre-backup: forense).
Ventana = registry no-ACTIVO + re-hash pre-write (sin exclusion
sostenida declarada). Fixture hot REAL (magia valida, bloquea ro).
Spy: 1 sola apertura rw en origen (la _recover final). Barrera
pendiente. Sin aplicar, sin corridas. V2 abierto.

## Mantenimiento aplicable + deriva/discrepancia (2026-10-16, sin push aun)
--apply con backup real + re-verificacion pre-write + exclusion de
escritores + aplicado-vs-restaurado; backup verificado fuera del
repo e inexistente; regresiones de deriva/discrepancia (22 tests).
Barrera 1108 exit 0. Sin aplicar, sin corridas. V2 abierto.

## Correccion revision 2026-10-16 — metricas honestas + apply/backup (sin push aun)
dispatchDelayMs/yieldLagMs (nombres honestos) + test ruta real con
delay 300ms (3/3 estable); --apply con backup fuera de git +
protecciones realpath + fallos limpios (14 tests); informe
RECOVERY_REHEARSAL publicado (hot-rollback, intacto). Barrera 1100
exit 0. Sin aplicar al original, sin corridas. V2 abierto.

## Journal-recovery ensayado + atribucion queue/transit (2026-10-15, sin push aun)
Bloqueo resuelto por procedimiento propuesto (DB_MAINTENANCE_RECOVERY,
NO aplicado al original): ensayo en copia ok, diff 0, canonico
intacto. Instrumentacion arrival/queue/transit + 5 tests (umbral
intacto, sin corridas). V2 abierto (nuevo PID), cero auto-corridas.

## Post-mortem piloto brief 20261015T000730Z — ABORTED sano (2026-10-15, sin push aun)
Lanzado por V2 fuera de autorizacion registrada (agente no emitio).
Aborto timestamp-reject-rate 0.146136>0.05 a 00:08:34Z; PIDs muertos
verificados, seguridad 0/0/0. Rechazos = skew-guard bookTicker,
reloj sano, entrega degradada; umbral intacto. SQLite 503 por journal
caliente (error exacto preservado; journal intacto). Correcciones:
contador terminal congelado + readiness ABORTED terminal. Evidencia
PILOT_BRIEF_20261015_ABORT.txt. V2 abierto, cero auto-corridas.

## Cierre defectos pre-piloto 202/identidad/migracion (2026-10-14, review/o1-funcional-v2-observacion, sin push aun)
BotControl: 202 pendiente + reconcile (exito solo con confirmacion
explicita; 3 tests). host_process: `_run_text` (None/decode/ausente →
UNKNOWN) + expected-sin-real → False (15 tests, 7 fail-before; 8E+1F
previos verdes por la causa). Migracion en fixtures v9/v2 temporales
(cero contacto canonico). Barrera 1077 OK exit 0; frontend 255/255.
Piloto brief 120s pendiente de autorizacion, no iniciado.

## Revision pre-piloto sobre e887287 (2026-10-14, review/o1-funcional-v2-observacion, sin push aun)
Presupuestos separados (status 4200 / stop 8000 / start 65000ms) con
reconciliacion START_TIMEOUT_UNCERTAIN (202) + pre-check ALREADY_RUNNING
(sin segundo spawn); readiness por capability habilitada (no callable)
+ storage (bloqueo sin DB/disco<256MB; aviso 1GB/historico); presets
own-keys (prototipos rechazados); compat corregida (lectores admiten
9/10 y 2/3; prospective reporta schema real; ruta
data/historical/historical.db; base main v10/v3 verificada por
copia-temp, incremental 0 filas). Compat implementada != consumo vivo
(pendiente barrera final + QA visual + piloto brief autorizado).

## Bot + V2 observacion (2026-10-13, review/bot-dashboard-v2-observacion, sin push aun)
V2 checkpoint 27b7af5 (mas reciente; contiene DASH-V2-47) como interfaz
principal; Python SSR a LEGADO (sin semanticas contradictorias).
Matriz 10 funciones + funding en 3 niveles + ciclo/aceptacion + preflight
medido (docs/OBSERVATION_RUN_MATRIX|CYCLE|STORAGE_PREFLIGHT_CONTRACT).
Kronos/IA diferidos (F-KRONOS-01). V2 SELECT-only verificado; gates 2/9
vs backend v10/v3 (fail-closed). Vitest local 24/24; visual 27b7af5
PENDIENTE (sin servicios). Sin corridas reales, paper, ordenes ni gates.

## Entrega nueve archivos 6fd6091-base (2026-10-13; push review/entrega-nueve-archivos-6fd6091 completado en 3cbbb1c)
Base 6fd6091 (= remoto). Nueve archivos tecnicos: comparador+M6-M8 auto (10/10),
motor (cap uncovered al holding, calendario monocontrato, mark stale excluido,
fees salida a exit value; 1 assert legacy corregido y documentado), runner
(symbol preservado + manifiesto), tests R1-R7 (9/9), handoff 27b7af5 corregido
(lee historical.db real; gates historico-2/operacional-9 vs backend v10/v3).
Dirigidas 68/68 OK; barrera 1029 con 1F+8E preexistentes contrastados en
worktree de14ac1 (misma firma); aislamiento OK (0/0/0, hashes iguales).
Logs completos en docs/evidence/BARRIER_ENTREGA_NUEVE_*. Sin merge, sesiones,
paper, ordenes ni gates.

## Correccion tecnica de14ac1-base (2026-10-13, review/correccion-tecnica-de14ac1, sin push aun)
Base de14ac1 (= remote review/w-lumia-correccion-bc327f1; phase1 remote=local en
bc327f1; main intacto). Comparador: signo/posicion de inf + CSV vacio/ilegible
(INCOMPLETE exit 2), regresiones M1-M8 + SELF automatizadas
(scripts/regress_compare_cases.py, 10/10). Motor v4 aditivo: realizados vs
abiertas vs marcas, open_at_end fuera de metricas realizadas, costes de
salida hipoteticos separados, curva realizada por cierre efectivo; funding
qty x mark con identidad, dedup/rechazo duplicados, cobertura acotada,
gaps detectados, faltantes/fallback explicitos (contrato v4.1). Runner por
familia/ version (H3 ya no descartado), identidad por indice, demo H1/H2/H3.
Aislamiento: incidente v2->v3 reconciliado (aditivo, verificado read-only;
canonico intacto); incompatibilidad v10/v3 explicita + handoff 27b7af5
(docs/DASHBOARD_V2_27B7AF5_READ_HANDOFF.md; frontend/ intacto). Pendientes
que siguen: despliegue/operacion de lo corregido, OOS/calibracion/
rentabilidad, gates. Sin merge, sesiones, paper, ordenes.

## Cierre W/LUMIA documental — reproduccion aislada (2026-10-13; push phase1 bc327f1 completado)
Reproduccion de caso (DESCRIPTIVE/IN-SAMPLE): paquete en
`binance_case_study/` (12/12 hashes OK), re-ejecutado en copia temporal
(analyze 0, finish 0); coincidencia numerica parsed 0 diffs, bytes
difieren por serializacion; PNG NO inspeccionado (equivalencia visual no
declarada). Evidencia: `docs/evidence/CASE_STUDY_WUSDT_LUMIA_*` + script
de comparacion. Distincion: reproduccion de casos != integracion
dashboard (campos/versionado/funding-calendario pendientes) !=
validacion financiera (sin OOS/calibracion/rentabilidad; gates intactos).
V2 exacto `27b7af59cb1e313169f49655161d66e043b5412d` = checkpoint
estatico frontend `dash-v2-03-token-detail` (Next.js bajo `frontend/`,
sin BFF/datos vivos); no confundir con el dashboard Python SSR del
backend (`dashboard.py`). Pendientes explicitos del prompt correctivo
anterior (NO resueltos por este cierre): funding, posiciones abiertas,
runner, incidente de aislamiento, schemas V2. Sin ordenes/paper/servicios.

## Correccion V2 + comparador (2026-10-13, review/w-lumia-correccion-bc327f1; push de14ac1 completado)
Addendum sobre el bloque anterior (historia preservada). V2 exacto
`27b7af59cb1e313169f49655161d66e043b5412d` (rama `dash-v2-03-token-detail`,
revisado con `git show`, sin tocar el checkout) SI tiene rutas BFF
(`frontend/src/app/api/v1/live-movers/route.ts` y hermanas) y adapters de
lectura SQLite (`frontend/src/lib/canonical-market.ts`, `historicalRead`
con BEGIN/COMMIT/ROLLBACK y fallback `available:false`): el "sin
BFF/datos vivos" del bloque anterior era erroneo. Integracion
PARCIALMENTE implementada (ruta de lectura existe) != feed
live/operacion verificados (la ruta declara alignment/freshness
UNVERIFIED y advierte que cobertura retenida no certifica liveness
presente). Comparador fortalecido (missing-masks primero, tipos y
especiales, sin omisiones silenciosas, exit 1/2, JSON UTF-8) con 5
regresiones en copias temporales. Reconciliacion: phase1 avanzo
bdc9ef2->bc327f1 con 21 commits (esta correccion anadio solo sus
propios); publicar no equivale a aceptar las correcciones anteriores.
Pendientes: funding, realizados/marcas, runner, aislamiento, schemas V2.
Sin merge/force-push, despliegues, sesiones, paper, ordenes ni gates.

## Mejoras funding/trazabilidad/dashboard/casos/evaluacion (2026-10-13, sin push aun)
Funding v4 por liquidaciones + linkage research v3 + dashboard con
semantica honesta + protocolo de casos (paquete ausente) + runner de
evaluacion por familias. INCIDENTE: historico canonico v2->v3 por
side-effect de test (aditivo, verificado intacto); corregido y con
barrera. Sin ordenes/paper/servicios; sin rentabilidad ni gates.

## Cierre correctivo R1-R7 (2026-10-13, rama review, sin push aun)
R1-R5 motor v3 (conocimiento estricto, marcas vs ejecuciones, gap-first,
orden stop-antes-fills, metricas demostradas); garantias v2 retiradas,
motor NO verificado causalmente. R6 cadenas v1-v8 a v10 en una init
(pins actualizados, error explicito en tablas ausentes). R7 resolver
HistoryStore unico en status/worker/retention. run_id UUID32 con garantia
probabilistica precisa. Suite 972/972 en sitio + barrera exit 0 (0/0/1RO,
hashes limpios); canonico intacto (schema v9, 221b33/ca6479/45c6a3,
375/225). Copia aislada pendiente. Sin rentabilidad/V2/Paper/ejecucion.

## Verificacion final (2026-10-12, sin push)
In-place: barrera P2 exit 0 sobre 950 tests (0 bloqueados, 0 efectivos,
1 RO mode=ro de supervision registrado aparte, hashes/inventarios
iguales). Copia aislada (git archive HEAD, sin data//logs/untracked):
Windows win32, Python 3.14.3, websockets 15.0.1, discovery unittest
canonico 950 ejecutados, 0 fallos, 1 skip esperado (migracion v9 sobre
copia canonica ausente), exit 0, sin crear data/ ni logs/. Plataforma
Linux no reproducida aqui (pendiente si se requiere). Evidencia:
docs/evidence/ISOLATED_RUN_950.txt. Commits locales (sin push):
motor, aislamiento, trazabilidad, documentacion + 2 fallouts de
verificacion (ruta absoluta en test, mkdir diferido). Trabajo ajeno y
untracked preexistentes intactos.

## Cierre correctivo P1-P4 (2026-10-12, sin push)
P1 motor offline v2 (7 defectos causales/contables corregidos; 10
regresiones fail-before 8F+2E sobre bdc9ef2, 26/26 pass-after; contrato
de lectura v2 sin cablear). P2 inyeccion minima Rutas B/C con defaults
intactos (barrera con buckets: 946 verdes, 0 bloqueados, 0 efectivos,
1 RO mode=ro separado, hashes/inventarios limpios). P3 linkage run_id
(schema v10; migracion probada en copia temporal v9 real; historicos
NULL=UNKNOWN sin backfill). P4 docs reconciliados (README/EVENT_LABELING/
ARCHITECTURE/TASK_QUEUE/PAPER_LAB/V2-addendum/cobertura BTC 1h). Suite
950/950 en sitio; copia aislada pendiente de corrida final. Sin
rentabilidad, V2, Paper Lab ni ejecucion. Veredicto final abajo.

## ETAPA 5 Paper Lab plan — DONE (2026-10-12, design only)
Six build items + entry gates specified; nothing implemented or started.
Plan: docs/PAPER_LAB_PLAN_ETAPA5.md. Canonical 932/932 OK with stable
hashes (221b33/ca6479/45c6a3).

## ETAPA 4 offline backtest prep — DONE (2026-10-12, prep only)
Isolated engine + 16 tests green + UNWIRED V2 read contract. Mechanics
smoke on fixtures executes (dev/OOS x 1x/2x/3x, monotone costs, counted
skips); no performance claim, no validation. Engine:
src/microstructure_probe/backtest_offline.py. Contract:
docs/BACKTEST_READ_CONTRACT_V1.md.

## ETAPA 3 research/backtest contract — DONE (2026-10-12, contract only)
H1/H2/H3 study contracts with per-family universe/confirmation/timing/
invalidation/no-trade/params/evidence blocks + versioned cost model +
replay limits + in-sample labeling mandate. No engine, no runs, no claims.
Report: docs/RESEARCH_BACKTEST_CONTRACT_ETAPA3.md.

## ETAPA 2 dataset readiness — DONE (2026-10-12)
Pure-read provenance (hashes unchanged): 225 fixture rows confirmed
(DOGEUSDT hot lifecycle detail=test) retained + explicit filter rule; 150
operational-probable with unknown per-row runs; prospective 66/228 clean of
markers; event studies 2831x6 exact with FORMATION_GAP usability correct by
design. Verdict: descriptive exploration only; no validation/trading claim.
Evidence: docs/evidence/DATASET_PROVENANCE_ETAPA2.json, report
docs/DATASET_READINESS_ETAPA2.md.

## ETAPA 1 test isolation — DONE (2026-10-12)
Barrier scripts/audit_test_isolation.py over the full suite: PREFIX 911/911
green WITH 61 swallowed default-factory attempts (test_probe x5,
test_host_telemetry x2, test_p14b_3 x4 methods) + 97 residual canonical
connects classified (rehydration/HistoryStore-reads/RO-URI) + 0-byte
logs/probe-runs sidecars from three test-side routes. Repro on temp:
10 bodies -> 4 obs + 54 rej rows, canonical untouched. Fixes are test-only
(isolated-probe helpers, evidence_dir, pc.repo_root patch; 5 new regression
tests, no production change). POSTFIX: 916/916 OK, zero prohibited hits,
zero file/registry writes, clean inventories, exit 0. Canonical
run_tests.py -q: 916/916 OK (162.068s), microprobe.db SHA256 stable
(221b33..fb86), historical.db + registry unchanged. Pure re-read: 375
universe rows, 225 detail='test', retained as-is. Complete-purity (zero
connects) NOT claimed: Routes B/C need production injection points
(deferred). Full evidence: docs/TEST_ISOLATION_ETAPA1_REPORT.md.

## Final proof and fixture-isolation checkpoint (2026-10-11)
Original proof correction: focused 1/1 and canonical 910/910 exit0 (184.479s).
A subsequent System read found 375 universe rows, 225 tagged detail='test',
rather than the earlier read of 366/222. Earlier canonical-suite preservation
claims do NOT hold across those test runs. Readonly GET hashes are a separate,
bounded check and remain equal.

Root route proven without touching the canonical DB: original HotSyncTest
calls the default persistence factory twice and writes three DOGEUSDT lifecycle
rows to an intercepted temporary store. test_universe_probe.make_probe now
injects a real initialized temporary PersistenceStore with cleanup per testcase.
All 11 module tests pass with the default factory forbidden, zero calls.
One added regression prevents fallback. No application source changes.
This establishes a test contamination route; it does not attribute every
historical tagged row. Existing canonical rows were retained without cleanup.

Final canonical: 911/911 application tests exit0. The preservation wrapper
exits1: microprobe.db SHA256 changed; historical.db and registry hashes equal.
Universe rows stayed375/225: HOT leakage fixed, whole-suite preservation FAILED.
A guarded subset audit (729 tests) records default-store accesses in test_probe,
test_host_telemetry and test_p14b_3_transport_freshness (six errors with factory
forbidden, swallowed persistence errors also observed). These remaining fixtures
are a BLOCKER for whole-suite isolation; no claim of complete purity is made.
See backend-isolated-final.json and default-store-audit.json.
Source notice remains until historical provenance is reviewed.
The 496-test frontend Python snapshot is historical validation, not the
current backend. Its old HOT fixtures must not be rerun against the canonical
store; reconcile the fixture isolation or run it in a fully isolated checkout.
FEATURES_IMPLEMENTED adds temporary HOT fixtures and fallback regression.
FEATURES_VERIFIED final 911 plus isolated original/after negative control.
DEFERRED_FEATURES retains remaining default-store test isolation, historical lineage and complete cutover.
No runs, traffic, orders, Start, retirement, main merge or gate advancement.


# CURRENT_STATE

## DASH-V2-71B reviewer correction — 2026-10-11
89232f7 independently reviewed: discovery/canonical 910, exit0. Strengthened
existing purity test (missing historical-byte assertion, no new logs, env
restoration); historical-tempfile mutation passed old proof and fails new.
No application source change. Final bytes do not certify readonly mode;
four HistoryStore init calls observed. See DASH_V2_71B_REVIEW_CORRECTIONS.md.
Full cutover/Start/gates unchanged; universe detail=test provenance pending.


## DASH-V2-69 — 2026-10-11 — extraction proof review
Exact c59c5ec extraction reviewed independently. Five helper bodies match; original Python 3.14 find_module blocker was ineffective despite four green tests. Existing H2 strengthened with find_spec plus deliberate negative control; four focused tests pass. No application source edits. V1 contract retirement section now closes extraction prerequisite while retaining parity/review/authorization requirements; no retirement performed. See DASH_V2_69_EXTRACTION_PROOF_REVIEW.md; canonical verification recorded there. Full cutover and operational readiness remain PARTIAL; Start/gates/main/DB/registry preserved.



## DASH-V2-62 - 2026-10-11 - disabled transactional launch corrected

User authorized the V2 reviewer to correct the backend branch directly, in an isolated checkout based on da231b9. R1-R5 and C1/C2 from frontend f63dd16 corrected: direct captured child identity, one lease evaluation, canonical supervise argv, strict finite verification/deadline, owned/gone/replaced/unknown rollback with final pure assessment, strict non-future freshness and explicit lock/evidence preflight effects. Added 29 tests; canonical 902/902 OK, 160.768s, exit 0; focused 52/52 OK. Fail-before: 15 of 18 initial methods failed (25 assertions/subtests). See DASH_V2_62_SUPERVISED_LAUNCH_CORRECTIONS.md and docs/evidence/DASH_V2_62_LAUNCH_VERIFICATION.json. DONE bounded disabled preparation; no general operational PASS. Start/launch flag remain disabled; no new HTTP/CLI operation, market probes, longevity, SUCCESS_GATES or main merge. Original agent checkout/evidence preserved; backend remote will advance by normal fast-forward push. Next exact-SHA V2 checkpoint, enablement/real watcher startup association and runs remain separate.

Factual state as of 2026-10-06 (order refinement). Historical evidence:
`docs/PHASE_1_REPORT.md` (do not rewrite).

## Baseline (audited, preserved)

- Codebase: `src/microstructure_probe/` — `probe.py`, `detectors.py`, `metrics.py`,
  `telemetry.py`, `clock.py`, `config.py`, `models.py`, `__main__.py`.
  Plus root `run_tests.py` (P1-00; test tooling only, no app behavior change).
- Version: 0.2.0 (`pyproject.toml`). History: `157e85e` baseline + `d6801a5`
  brain checkpoint, branch `phase1/market-intelligence-dashboard`, published to
  private `mariomoreta/binance-futures-microstructure-bot` (origin/main +
  origin/phase1 in sync). Repo-local git identity configured per operator
  authorization; nothing global was changed.
- Mode: OBSERVE ONLY. `BOT_MODE=observe` enforced in code; any other value aborts.
  No authenticated clients, no order paths (covered by static test).
- Feeds (public, routed endpoints): `/public` (bookTicker, depth20@100ms),
  `/market` (aggTrade, `!markPrice@arr@1s`, `!forceOrder@arr`).
  Symbols: BTCUSDT, ETHUSDT, SOLUSDT (`config/probe.json`).
- Implemented: clock sync (5-sample midpoint median, ~10 min), gap/staleness
  detection (staleness only on cadenced streams; event-driven silence ≠ stale),
  raw/corrected event+transaction latency per stream/symbol, monotonic processing
  latency split (parse/metrics/detector), liquidation individual+10s-window
  detectors, funding percentile extremes with warm-up + non-independence note,
  10s-bucket volume z-score with warm-up + near-miss, telemetry
  (quantiles over last 20k samples; exact count/min/max/mean), JSON logs +
  `final_summary`.
- Phase 1B semantics: `E` = event time; `T` = trade/transaction time except
  markPrice where `T` = next funding time (NOT latency). Legacy global clamped
  lag kept labeled as legacy, not a gate metric.

## Verification (2026-10-06)

- Canonical: `python run_tests.py` from repo root → **144/144 PASS** (28 baseline
  + 32 persistence/sampling/v2 + 22 universe/returns + 24 dashboard + 38 P1-05).
- `--show-streams` → correct routed `/public` + `/market` URLs.
- Port candidates 8091/8092/8093/18091/18765 probed FREE on 127.0.0.1
  (dashboard port-policy evidence; selection happens at P1-03 startup).

## P1-01 short transport validation — RESULT: PARTIAL (2026-10-06)

Run: `python -m microstructure_probe --duration 1800`, BOT_MODE=observe,
`runtimeSeconds: 1804.969`, exit 0. Evidence log (local, git-ignored):
`logs/p1-01/probe-1800s.log`. No keys, no orders, no capital, no private APIs.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`.
- Uptime: market 98.51% (1773.3s/1800.1s), public 95.05% (1711.0s).
  Attempts 60 (public 46, market 14), all succeeded.
- Reconnects: 58 total (public 45, market 13) — every one
  `ConnectionClosedError: no close frame received or sent`, retry 1s
  (backoff resets on success, so it never grew). ~1 drop per 31s average.
- Messages: 172,906 total. bookTicker 32.2/31.5/17.9 msg/s (BTC/ETH/SOL);
  depth ~2/s per symbol (cadence allows ~10/s); markPrice arrays 1563 of ~1800
  expected; forceOrder 421; aggTrade 5466/4709/3205.
- Delivery lag (corrected event lag): bookTicker p50 14.8–19.2s / p95
  45.6–53.8s; depth p50 ~14.7s / p95 ~50.4s; aggTrade p50 31.6–38.1s / p95
  73.5–75.6s; markPrice p50 35.0s / p95 75.9s; forceOrder p50 38.5s / p95 69.0s;
  max ~127s. Exchange-side E−T deltas are milliseconds (bookTicker p50 0ms),
  so the delay is entirely in the delivery path to this host, not Binance.
  Clock sync 3/3 ok (15/15 samples); offset drifted −231ms → −475ms; RTT
  610–943ms — slow/lossy path confirmed.
- Skew guard: `timestampRejected: 147417` (~85% of messages, |received−E| >
  5000ms, degraded from the first 30s summary onward). Rejected messages skip
  metrics+detectors, so detectors operated on survivors only.
- Gaps/silence: depth sequence gaps 50/49/49 (reconnect-driven, expected).
  Max observed silence: depth ≤28s, bookTicker ≤21.5s, aggTrade ≤16s,
  markPrice 12s. forceOrder silent up to 111s — event-driven, correctly NOT
  reported stale (Phase 1B fix works in practice).
- Errors: parse 0, payload 0, websocket errors = reconnects (58).
  Processing latency sub-ms (p50 ≤0.17ms) — probe CPU is fine.
- Detectors: 26 `extreme_funding_rate`, 0 liquidation, 0 volume. The 26 funding
  events are sampling artifacts (near-constant series ±1e-7…1e-5 evaluated on
  sparse post-rejection arrivals, first firing at the 30-sample warm-up edge),
  NOT signal validation. No threshold conclusion may be drawn from this run.
- Safety block in every summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.

Verdict reasoning: P1-01 as a measurement exercise succeeded (full
characterization obtained), but transport in THIS environment is unhealthy
(reconnect storm + 15–75s delivery lags + 85% skew-rejection). Therefore
PARTIAL: evidence recorded, P1-02/P1-03 (local builds) may proceed, but gates
G2–G4 cannot pass on this evidence and P1-10/P1-14 require re-validation in a
healthy network (tracked as `P1-01R` in `docs/TASK_QUEUE.md`).
`docs/PHASE_1_REPORT.md` historical evidence untouched.

## Phase 1 execution order (binding, refined 2026-10-06)

`P1-00` tooling ✅ → `P1-01` short transport validation (30–60 min, NOT 6h) →
`P1-02` persistence foundation → `P1-03` minimal dashboard (`/overview`,
`/system`) → `P1-04` universe+returns → `P1-05` velocity/rank → `P1-06`
volume/flow → `P1-07` book/OI → `P1-08` VWAP/vol/structure → `P1-09`
intelligence dashboard (`/movers`, `/symbol/:symbol`, raw features first) →
`P1-10` ≥6h soak with dashboard live → `P1-11` raw feature validation →
`P1-12` classifier v0 (BLOCKED until P1-11) → `P1-13` signal/extreme-move UI →
`P1-14` 24h calibration + gate evaluation. Full detail: `docs/TASK_QUEUE.md`.

Superseded: the earlier "soak first, persist nothing in Phase 1" sketch.
Persistence foundation is now explicitly a Phase 1 task (local, observe-only,
dashboard-feeding) — see `docs/DECISIONS.md`.

## P1-02 persistence foundation — RESULT: PASS (2026-10-06)

- Tech: stdlib SQLite (`sqlite3`), no new dependencies. Store:
  `data/microprobe.db` (project-local, git-ignored via `data/` + `*.db`).
- Schema v1 + version gate + column migration: `persistence_meta`,
  `telemetry_snapshots` (periodic `build_summary` output for the P1-03
  dashboard), `market_observations` (valid only, `is_valid` + symbol/stream
  indexes), `rejected_observations` (skew/parse rejects, reason + stream
  indexes). 9 indexes total.
- Write path (probe.py, all fire-and-forget with `persistence_error` logging,
  never breaking the probe): valid dict payloads → observations with
  normalized price/qty/E/T; markPrice arrays → single `MULTI` record (no
  longer dropped); skew-rejected payloads (dict or list) → rejections only;
  every summary (30s + final) → snapshot row.
- Invalid-data guarantee: the skew guard returns before the valid-write code,
  so rejected messages can only reach `rejected_observations`;
  `latest_observations()` hard-filters `is_valid = 1` (both proven by tests,
  including a probe-level skew test).
- Retention: snapshots ≤1000, observations ≤10000, rejections ≤1000 rows
  (instance-overridable); steady-state storage bounded (~10–20MB worst case).
- Non-blocking: writes run via `asyncio.to_thread` under a lock (single
  shared connection); smoke (2000 mixed msgs): schedule p50/p95
  0.021/0.039ms, full drain 9.2s off-loop. Per-insert retention DELETE is the
  dominant cost (~4.6ms) — fine at current rates; see risks.
- Restart: close() is idempotent; reopen replays schema gate and all rows
  survive (tested).
- Found and fixed during verification (were failing, 5 errors): missing
  `spread_bps_json` column + 19-vs-18 INSERT mismatch; `store_rejection_record`
  crashed with no running loop; real-summary legacy-lag dict vs REAL column;
  markPrice arrays never persisted; snapshots never wired to the probe.
- Known risks: (1) no write backpressure — sustained rates far above ~200/s
  queue tasks in memory (dashboard freshness lags, WS never blocks); P1-04
  sampling/aggregation is the planned remedy. (2) At full healthy-network
  bookTicker rates the 10k observation cap retains only recent minutes —
  sufficient for dashboard/P1-04 bootstrap, not archival history (Phase 2
  owns that).

## Project brain

- Live corrigendum (found during P1-03): snapshot writes starved behind bulk
  observation traffic on the shared executor (0 snapshot rows vs 9260
  observations in a live run). Fixed with a dedicated single-thread snapshot
  writer + regression test; 2 snapshots landed on the very next live run.
  See `docs/DECISIONS.md`.

## P1-03 minimal live dashboard — RESULT: PASS (2026-10-06)

- Stack: stdlib only (`src/microstructure_probe/dashboard.py`,
  `ThreadingHTTPServer`, server-rendered dark HTML, no new dependencies,
  version 0.3.0). Data only via P1-02 reads (`latest_telemetry`,
  `latest_observations`, `get_rejection_stats`, `storage_info`).
- Routes live: `/overview` (safety banner, connections, uptime, message
  activity, stale/silent, reconnects, gaps, rejections, snapshot age,
  detector counts labeled NOT trade signals), `/system` (per-stream table,
  rates, raw/corrected p50/p95, processing latency, clock, rejections,
  persistence, safety), `/api/health` (status/version/uptime/reachability/
  snapshot time/streams/BOT_MODE/safety/reasons), `/api/snapshot`.
  No buttons, no trading controls, no private-account data.
- Live instance: http://127.0.0.1:8091 (first candidate, was free),
  PID 10796, `logs/dashboard.pid`, health `ok` at startup, all routes
  HTTP 200, unknown route 404. Started via
  `python -m microstructure_probe.dashboard start`; left running (read-only,
  localhost — safe).
- Seed: 40s observe-only probe (exit 0) wrote 10k observations + 2 snapshots
  of real market data — no mock data anywhere. Seed window itself was healthy
  (0 reconnects, 0 skew-rejections), so the pages currently show HEALTHY;
  the model reports DEGRADED/STALE/UNKNOWN from persisted evidence when
  present (proven by tests, and P1-01-style degradation would surface the
  same way). Snapshot ages without a running probe — STALE chip after 120s
  is honest; continuous freshness arrives with the P1-10 soak feed.
- Found and fixed live: snapshot executor starvation (see DECISIONS).
- Tests: 66/66 (18 dashboard: health ok/degraded/stale/unknown, routes,
  empty-DB, banner values, no-controls, port skip/busy, PID live/dead/stale).

## P1-04 symbol universe + multi-timeframe returns — RESULT: PASS (2026-10-06)

- Universe: `universe.py`, active trio preserved (BTC/ETH/SOLUSDT, explicit
  enabled/source/reason/activated_at metadata); no expansion, no ranking.
  No new REST endpoint introduced (static-config source; exchangeInfo remains
  future work) — no Binance-docs verification owed.
- Engine: `returns.py` — mark-price log returns, 7 TFs, 10s buckets (≤9180),
  tolerance max(60s, tf/20), UNKNOWN never 0, no lookahead, late/invalid
  refused. Valid-path-only ingestion (rejected messages return before it).
- Backpressure: sampling gate (bookTicker/aggTrade/depth ≤1/s per symbol;
  markPrice/forceOrder ungated; counts in `sample_stats()`); dedicated
  snapshot writer kept; schema v2 (`price_samples`, `return_features`,
  migration tested). 106/106 tests.
- Live 360s attempt: harness session-end killed the detached probe at ~330s
  (11 periodic summaries, no final) — lesson: detached children die with the
  tool session; reran 240s blocking → clean exit 0 + `final_summary`.
  Mid-run API: all 3 symbols with real prices, 1m warmed first, longer
  horizons honestly unavailable; dashboard `ok` while fed, STALE/DEGRADED
  honestly after (DEGRADED currently live from persisted reconnects +
  rejection rate — P1-01 degradation surfacing as required).
- Clean-run evidence (244s, 11/11 streams, 0 stale, safety 0/0/0):
  5 reconnects, 11448 skew-rejects (~93%, lags p50 22–85s — degraded env);
  engine 46 samples/symbol over 25-min restored+live span, 0 invalid, 0 late,
  0 unknown-symbol; sampling accepted 36/dropped 858 counted;
  inflight high-water 345, drained to 0 — no unbounded queue growth.
  Rejects went to `rejected_observations` only (cap 1000); returns contain
  no rejected input by construction + unit test.
- Dashboard: Symbol Returns on `/overview` + `/api/features/returns` live;
  partial warmup renders values + "—", no movers/rank/states/controls.

## P1-05 dynamic discovery + velocity/acceleration/ranking — RESULT: PASS (2026-10-06)

- Discovery (`discovery.py`, public REST only, no keys): exchangeInfo +
  24hr tickers on `fapi.binance.com` (docs site unfetchable — behavior
  verified live instead). Live scan: 924 seen → 449 eligible → 475 filtered
  (PERPETUAL + TRADING + USDT + ≥1M quote-vol floor). Core trio preserved.
- HOT: 6 dynamic (USUSDT +41%, 龙虾USDT +35%, BR/ORCA/NMR/GRIFFAIN +31–41% —
  small sharp movers, not large caps) promoted after 2 votes, stable after;
  losers LYN −25%, MINA −24%; most-active BTC/ETH/SOL by volume (movement ≠
  volume demonstrated). No WS subscription changes (trio only); HOT proposed
  via API/dashboard/logs; dynamic resubscribe is a documented next step.
- Momentum (`momentum.py` on P1-04 series, `feature()` untouched): velocity =
  return-change per second (flat trends ≈ 0 — not renamed returns),
  timestamp-aware acceleration, None until warmed; live velocity_1m values
  (e.g. ETH +3.2e-6/s) with accel honestly None until 3 evaluations;
  ranks ±/ties/change/velocity/accel across the trio (ETH #1 climbing).
- Dashboard: three separated health blocks, Symbol Returns kept, new
  intelligence area (tiers, live momentum, discovery movers, event history),
  `/api/discovery` + `/api/features/momentum`; forceOrder never missing;
  reject labels split run-vs-retained; no movers route, no states, no controls.
- Persistence v3 (discovery snapshot REPLACE, universe_events ≤500, rank
  vectors REPLACE-per-metric; tested v1→v3 and v2→v3 migrations).
- Live windows: 360s detached run killed by tool-session end (~330s, lesson
  recorded — detached children die with the harness session) + clean 240s
  blocking run (exit 0, final_summary): 11/11 streams, 0 reconnects,
  0 skew-rejects (healthy window!), 143659 msgs, engine 91 samples/symbol
  over 89-min span, sampling accepted 1888/dropped 141k counted, inflight
  high-water 6 → 0, safety 0/0/0. Dashboard `ok` while fed, STALE/DEGRADED
  honestly after. 30 funding crossings judged non-signal artifacts as before.
- Tests: 144/144 (38 new). Unicode HOT symbol (龙虾USDT) flows through
  JSON/DB/HTML correctly; only legacy Windows-console display needed UTF-8.

- `AGENTS.md` + 20 docs under `docs/`. No strategy, engine, or safety code
  touched. `docs/PHASE_1_REPORT.md` preserved as-is.

## P1-06 volume + aggressive trade flow — RESULT: PASS (2026-10-07)

- Semantics verified against CURRENT official USD-M docs + live payloads:
  same-price/same-side 100ms aggregation (insurance/ADL excluded), `m`
  (true→aggressive SELL, false→aggressive BUY), `q` RPI-inclusive vs `nq`
  normal, `E` ordering key, `st: 1` live. Recorded in `docs/MARKET_DATA.md`.
- Engine (`flow.py`, NEW): every valid aggTrade ingested pre-sampling;
  trailing windows 10s/30s/1m/3m/5m/15m with exact per-horizon expiry;
  baselines 10s/30s/1m/5m on completed buckets (skips counted, z null on
  thin/zero-variance history); 1m-referenced acceleration; same-E accepted
  in arrival order (first live run proved `<=` undercounts ~35% BTC flow —
  fixed, re-validated to 4027/4027 accepted, 0 late, 0 invalid).
- Persistence v4 (additive, tested v1/v2/v3→v4): `flow_features` per symbol
  + bounded `flow_buckets` (168 rows/run); restarts restore closed buckets
  only — returns span grew across runs (9340s → 9970s), no double-count.
- Live windows (blocking, BOT_MODE=observe, exit 0, dashboard live):
  (a) 363s degraded-transport lesson run (2403 processed, 35% same-E lesson);
  (b) 363s HEALTHY run — 11/11 streams, 0 reconnects, 0 skew-rejects,
  clock 5/5: 4027/4027 valid aggTrades into the engine (BTC 2035 / ETH 1317
  / SOL 675), raw persistence kept 746 aggTrade (3281 sampled away — flow
  totals provably unaffected), 168/168 buckets persisted, engine latency
  p50 0.030ms / p95 0.069 / max 0.19, queue 0/0, inflight 6→0, safety 0/0/0.
  Snapshot BTC 1m: 408 trades, $2.61M notional, 85.9% aggressive buy,
  delta +$1.88M, ratio +0.72 (raw feature, no conclusion). Baselines
  honestly warming (6/30 samples → z null). HOT [] (one scan < 600s
  interval → votes 1/2, hysteresis honest). 37 funding crossings — same
  hypothesis-artifact class as before, no threshold conclusions (P1-11).
- Dashboard v0.5.0 live at http://127.0.0.1:8091 (restarted, PID 31436):
  flow table + BUY/SELL bars on /overview, DISCOVERY ONLY labels,
  `/api/features/flow` + `/api/features/volume` live (200), health `ok`
  while fed; no buttons/controls/signals.
- Tests: 190/190 (46 new: 44 flow + v3→v4 migration + same-E arrival).
  Two pre-existing version-3 assertions updated to v4 (migration, expected).

## P1-07 order book + open interest — RESULT: PASS (2026-10-08)

- Docs verified (current USD-M pages + live payloads): depth20@100ms = FULL
  top-20 snapshots (`U`/`u`/`pu` chain, `st: 1`, `ps` live); OI = public
  `GET /fapi/v1/openInterest` (`{symbol, openInterest base, time}` live);
  `openInterestHist` evaluated + deferred (single provenance). In MARKET_DATA.
- Book (`book.py`, NEW): every valid depth snapshot pre-sampling; best/mid/
  spread, top-1/5/10/20 sums, imbalances, microprice + displacement,
  LS-origin slopes + asymmetry, 5/10/25bps concentration (null when
  unspanned), crossed kept+counted, gap→DEGRADED-until-chained, no score.
- OI (`open_interest.py`, NEW): 60s bounded poller (worker thread, failures
  counted, WS untouched) + tracker (2000/symbol; 1m/5m/15m deltas+rug rates,
  1m accel, descriptive price/OI contexts, staleness honest).
- Persistence v5 (additive, tested v1/v2/v3/v4→v5): `book_features` latest
  only (never restored live), `oi_samples` + `oi_features`.
- Live 363s blocking run (exit 0, dashboard live): 11/11 streams, 1 public
  reconnect, 15992 skew-rejects (degraded bookTicker window — recorded
  honestly). BOOK 7309/7309 valid processed (0 invalid/late), latency p50
  0.15ms/p95 0.30/max 1.07, 1 gap/symbol all recovered, queue 0/0.
  OI 18/18 polls ok (0 failures, p50 380ms/max 7.6s absorbed). FLOW intact
  (5684 processed — P1-06 regression green). Sampling lossless to engines
  (depth persisted 739 vs 7309). Safety 0/0/0. Live book: spreads
  0.012/0.037/0.834bps, ask-heavy imbalances, micro ~0, SOL 55% conc@10bps
  (BTC/ETH honestly null — band unspanned). Live OI: BTC 96105.2 (+9.4/1m,
  +69.7/5m), ETH 2323727.6, SOL 8287311.7 with descriptive contexts only.
  99 funding crossings — same hypothesis-artifact class, no conclusions.
- Dashboard v0.6.0 at http://127.0.0.1:8091 (restarted, PID 27296): book +
  OI tables, NO LIVE FLOW/BOOK labels, `/api/features/book` +
  `/api/features/open-interest` live (200), health DEGRADED honestly
  (reconnect + retained rejects); no buttons/controls/signals.
- Tests: 239/239 (49 new: 48 book/OI + v4→v5 migration). Five v4
  assertions updated to v5 (migration, expected).

## P1-08 VWAP + volatility + structure — RESULT: PASS (2026-10-09)

- Zero new sources: VWAP from flow aggregates, vol/range/structure from
  persisted 10s mark buckets, mark reference (MARKET_DATA §P1-08).
- Engine (`market_structure.py`, NEW, stateless over peer state): VWAP
  1m/3m/5m/15m + displacement; raw `sqrt(sum(r²))` vol 1m/5m/15m/1h
  (≥5 returns + window−10s span, grid-coverage `warmed`); range + position
  + median/z expansion over completed blocks; confirmed pivots (30s delay),
  HH/LH/HL/LL, swing distances, prior-15m-block breakout tags. Resilience
  deferred (DECISIONS).
- Persistence v6 (additive, tested v1..v5→v6): `structure_features`
  REPLACE-per-symbol; continuity inherited, never fabricated.
- Live 372s blocking run (exit 0, dashboard live): 11/11 streams, 2 public
  reconnects, 57954 skew-rejects (degraded bookTicker window — honest).
  STRUCT 27 evals (9 summaries × 3), latency p50 0.84ms/p95 1.26, queue
  0/0. FLOW 4111 + BOOK 1737 + OI 15/15 intact (peer regressions green).
  Sampling lossless (aggTrade 172 vs 4111). Safety 0/0/0. Live: VWAP disp
  +0.7..+1.1bps (raw only); 1m vol UNKNOWN — fresh mark buckets starved
  by rejects, reported honestly; swings (incl. ETH HH) from restored
  history proving continuity; breakouts UNKNOWN (thin prior block).
  11 funding crossings — same hypothesis class, no conclusions.
- Dashboard v0.7.0 at http://127.0.0.1:8091 (restarted, PID 30344):
  structure table + `/api/features/vwap|volatility|structure` live (200),
  health DEGRADED honestly; no buttons/controls/signals.
- Tests: 277/277 (38 new: 37 structure + v5→v6 migration). Five v5
  assertions updated to v6 (migration, expected).

## P1-09 market-intelligence terminal — RESULT: PASS (2026-10-09)

- IA: `OVERVIEW` (market summary cards, top activity, compact live-core
  rows linking to token pages) → `MOVERS` (market table + 8 categories:
  24h gainers/losers/most-active, HOT, live velocity ±, acceleration,
  volume expansion, aggressive-flow leaders) → `/symbol/:symbol`
  (header + mark-price SVG chart + momentum/flow/book/OI/VWAP-vol-
  structure panels) → `SYSTEM` (all P1-03…P1-08 diagnostics + API index).
  Search (`/search` + `/api/search`, case-insensitive partial over the
  persisted universe, escaped, deterministic). Capability vocabulary
  LIVE/WARMING/DISCOVERY ONLY/STALE/DEGRADED/UNKNOWN UI-wide, tier
  orthogonal (neutral chips). No signals, no controls, no private data.
- Code: `dashboard.py` (routing/health/lifecycle, v0.8.0) +
  `dashboard_data.py` + `dashboard_components.py` + `dashboard_views.py`.
  Chart/CSV: `GET /api/symbol/:symbol/price[?range][.csv]` over P1-04
  `price_samples` (5m/15m/1h/4h/24h, ≤1000 pts, oldest-first, no futures,
  400/404 semantics). Book integrity copy: HEALTHY / Recovered N gaps /
  DEGRADED — gap active (no more `OK (1 gaps)`).
- Tests: 312/312 (35 new P1-09: routing/search/movers/token/chart-CSV/
  UI-regressions/unicode/escaping; 3 old overview-table assertions moved
  to `/symbol/:symbol` as intentional IA evolution; P1-04…P1-08 APIs green).
- Live 360s blocking run (exit 0, dashboard live, BOT_MODE=observe):
  11/11 streams, 0 reconnects, 0 skew-rejects (healthy window), uptime
  99.7%, corrected lags p50 ~180–260ms, clock 1/1 ok (−137ms/356ms RTT).
  FLOW 11086 events p50 0.03ms; BOOK 10274, 0 gaps; OI 18/18 polls ok;
  STRUCT 33 evals p50 ~1.05ms; returns 236 samples/symbol over 18.38M ms
  span, 0 invalid/late; discovery 924→481 eligible, HOT [] (one interval,
  votes 1/2 — honest); 140 funding crossings (same hypothesis-artifact
  class, no conclusions); safety 0/0/0. Evidence: `logs/p1-09/`
  (local, git-ignored).
- Dashboard live at http://127.0.0.1:8091 (restarted, PID 7564, v0.8.0):
  health `ok` while fed; all 22 routes 200 (pages 9–49ms, APIs 2–30ms);
  BTC chart 1h=44pts/5m=26pts; search `btc`→BTCUSDT; discovery-only
  龙虾USDT (+54.08%) page 200 with DISCOVERY ONLY — NO LIVE DEEP FEATURES
  and no fake panels; BTC page WARMING + HEALTHY integrity; CSV
  `text/csv timestamp,price`; forbidden-language scan clean on
  overview/movers/token pages. P1-01R transport re-validation still owed
  before P1-10 (this window was healthy but is not the gated 30–60 min
  P1-01R run).

## P1-01R transport re-validation — RESULT: PASS (2026-10-07)

Run: `python -m microstructure_probe --duration 2700`, BOT_MODE=observe,
`runtimeSeconds: 2702.262`, exit 0, attached blocking (no detached child).
Evidence (local, git-ignored): `logs/p1-01r/probe-2700s.log` (4.5MB raw
console) + `logs/p1-01r/transport-summary.json` (extracted final_summary)
+ `logs/p1-01r/dashboard-health.json`. No keys, no orders, no capital, no
private APIs. No application-code changes in this phase.

Measured (from `final_summary`):

- Coverage: 11/11 streams active, `missingStreams: []`, `staleStreams: []`,
  `silentStreams: ["!forceOrder@arr"]` only (event-driven, correctly
  not-stale).
- Uptime: market 99.964765% (2699.097s), public 99.965575% (2699.119s).
  Attempts 1/1 per endpoint, 0 failures.
- Reconnects: 0 total (market 0, public 0); websocket errors 0.
- Messages: 2,259,664 total. bookTicker 958k/773k/375k (BTC/ETH/SOL);
  depth ~26k/symbol; markPrice 2699 updates; forceOrder 519; aggTrade
  30457/31289/9179.
- Delivery lag (corrected event lag): p50 171–251ms across all streams
  (aggTrade ~171–174ms, bookTicker 175–216ms, depth ~175ms, forceOrder
  174ms, markPrice 251ms); p95 199–390ms; max ~3.2–3.4s rare outliers
  simultaneous across streams (one transient ~3.3s stall, auto-recovered,
  no reconnect). Exchange-side E−T is milliseconds (bookTicker p50 0ms,
  depth p50 1–4ms), so the sub-second path delay is the delivery path to
  this host, not Binance.
- Skew guard: `timestampRejected: 0` (0.0% — vs 85% in P1-01).
- Gaps/silence: depth sequence gaps 0/0/0. Max cadenced silence 2.85s;
  forceOrder silent up to 66.9s — event-driven, correctly NOT stale.
- Errors: parse 0, payload 0. Processing p50 sub-ms (parse/metrics/
  detector); full-processing p50 ≤2.4ms, p95 ≤22ms; isolated max spikes
  (one 464ms aggTrade) with all queues 0/0 — no backlog, probe CPU fine.
- Clock sync 5/5 ok (25/25 samples); offset −254ms; RTT 340ms.
- Engines (regression watch only, no semantic changes): returns 507
  samples/symbol over 21.58M ms span, 0 invalid, 0 late; FLOW 70925
  events p50 0.043ms queue 0/0; BOOK 77081 msgs 0 gaps 0 crossed p50
  0.19ms; OI 132/132 polls ok 0 failures; STRUCT 267 evals p50 1.93ms
  queue 0/0; persistence inflight high-water 43, drained to 0.
- Discovery: 924 seen → 482 eligible; HOT 6 promoted over multiple scans
  with votes (multi-scan hysteresis working as designed).
- Detectors: 3701 `extreme_funding_rate` (same hypothesis-artifact class
  as P1-01/P1-05 — near-constant series, NOT signal validation),
  2 `large_liquidation_individual` (ETH SELL, real counted observations),
  22 `volume_spike` (real hypothesis-threshold crossings). No threshold
  conclusion drawn from any of these.
- Safety block in final summary: observe, 0 keys, 0 orders, 0 capital,
  no authenticated clients, no order paths.
- Dashboard (v0.8.0, PID 7564, left running): `ok` while fed (53.7s
  snapshot age at check); post-run `/overview`, `/movers`, `/system`,
  `/symbol/BTCUSDT`, `/api/health` all 200 (20–51ms); health transitioned
  honestly to `stale` 134s after probe exit (snapshot age >120s chip).

Verdict reasoning: every P1-01R gate passes on the full 45-minute window
— full coverage, 0 reconnects, sub-second p50/p95 delivery lag, 0%
rejections, sub-ms-typical processing with drained queues, 5/5 clock sync.
The single ~3.3s transient stall is rare-outlier grade (p99 ≤1.1s worst
stream), not P1-01-grade degradation. Therefore PASS: transport is healthy
enough for the P1-10 ≥6h soak. `docs/PHASE_1_REPORT.md` untouched.

## P1-10 prolonged soak — RESULT: FAIL, truncated at 4.91h (2026-10-07)

Run: `python -u -m microstructure_probe --duration 21600` (requested
21600s), BOT_MODE=observe, started 2026-10-07 05:15:41 local. Evidence
(local, git-ignored): `logs/p1-10/probe-21600s.log` (52MB, UTF-16 —
PowerShell stdout-redirect capture, long JSON lines wrapped; reconstructed
by rejoining wrapped fragments, proven by 0 runtime drops). No
checkpoint/final-summary sidecar files were written; all metrics below come
from the 554 periodic summaries (every ~30–32s) parsed out of the raw log.

Continuity: ONE process (`startup` × 1, no restart). Last periodic summary
`runtimeSeconds: 17677.917` (81.8% of 21600); log wall span 05:15:41 →
10:10:37 (~17696s); NO `final_summary`; tail ends mid-stream on detector
lines with no shutdown/traceback and the process is gone — externally
killed between summaries, exit code UNKNOWN. Max inter-summary gap 62s, no
gap >120s: no evidence gap *within* the run, but the run itself is
truncated. Duration gate (≥21600s continuous) NOT met → FAIL per
docs/SUCCESS_GATES procedure (duration invalid). Dashboard was NOT
restarted (PID 7564, v0.8.0, uptime 63283s spanning the whole run).

Full-window (END, rt=17677.9s) transport:
- Coverage 11/11, missing [], stale [], silent `!forceOrder@arr` only
  (event-driven, correct). Uptime market 99.65% (17613.6s), public 97.08%.
- Reconnects 43 total (public 38, market 5); attempts 45 (public 39,
  market 6); websocket errors 43 (= reconnects). Jump +29 reconnects in the
  final 55 min (14 → 43) — closing-phase reconnect storm, nearly all public.
- Messages 15,341,473. bookTicker p50 ~190–200ms / p95 ~321–465ms
  (HEALTHY, P1-01R-grade); depth p50 ~182ms but p95 ~45–47s; aggTrade SPLIT:
  BTC p50 214ms vs ETH p50 152s / SOL p50 90s (P1-01-grade); markPrice p50
  253ms but p95 132s; forceOrder p50 205ms–1.2s, p95 ~158–159s; max ~265s.
  Exchange-side E−T stays milliseconds (bookTicker p50 0–1ms), so the delay
  is delivery-path, not Binance. Mixed verdict: bookTicker core stayed
  P1-01R-grade while aggTrade (ETH/SOL), depth-tail, markPrice-tail and the
  final hour regressed to P1-01-grade. Prolonged stalls: max observed
  silence 51–133s incl. 132.5s on cadenced bookTicker/depth — real stall
  episodes, not sampling noise.
- Skew guard: `timestampRejected: 742182` (~4.8% of messages; rejects by
  stream worst on bookTicker/aggTrade). Far better than P1-01's 85%, worse
  than P1-01R's 0%. +366k rejects landed in the final 55 min (376k → 742k).
- Depth gaps 33/32/32 (reconnect-driven, all recovered, `degraded: false`
  at END, crossed books 0 — final book integrity HEALTHY).
- Clock 30/30 syncs ok (150/150 samples), offset −413ms at END, RTT
  338ms; full-run offsets min −1001.6 / max +47.1 / median −241.6ms, RTT
  319.6–376.2ms (median 336.3). One ~1050ms offset discontinuity between
  sync 6 (−1001.6) and sync 7 (+47.1), then steady drift to −413 — sync
  never failed, recorded as drift, not a gate break.
- Processing sub-ms typical (parse/detector/metrics p50 ≤0.03ms); isolated
  max spikes (941ms bookTicker metrics, 1660ms SOL aggTrade processing,
  1098ms markPrice) with all engine queues 0/0 — absorbed, no backlog.

Engines (all alive at END, 0 invalid / 0 late everywhere):
- Returns: 1867 samples/symbol over 58,830,000ms span (16.34h incl.
  restored history), 0 invalid, 0 late. 1m/3m/5m/15m/1h/4h mature; 24h
  partial (16.34h/24h, honest).
- Flow: 502,191 events (BTC 222513 / ETH 228183 / SOL 51495 trades),
  latency p50 0.017ms / p95 0.085 / max 64.6, queue 0/0, 2103 completed
  10s-buckets/symbol (~5.8h live) — 15m maturity + volume baselines mature.
- Book: 388,570 msgs (130853/131465/126252), p50 0.19ms / p95 0.33,
  gaps 33/32/32 all recovered, crossed 0, integrity HEALTHY.
- OI: 813/813 polls ok (0 failures), latency p50 341ms / p95 3028 /
  max 10190 (slow polls absorbed); tracker 332 samples/symbol (271 total);
  1m/5m/15m + acceleration mature.
- Structure: 1659 evals, p50 5.9ms / p95 10.2, queue 0/0; pivots/HH-LH/
  HL-LL/breakout/range all evaluating (maturity inherited from 16.34h span).
- VWAP 1m/3m/5m/15m + volatility 1m/5m/15m/1h available (zero stays 0.0,
  distinct from unknown, per P1-08 contract).

Discovery/HOT (proposal/discovery only — no WS resubscribe, trio intact):
30 scans (600s cadence × 4.91h), seen 924 constant, eligible 486 → 496.
HOT 6-slot rotation with vote/dwell hysteresis working (26 promote/demote
events embedded in scan records; END set: AIN/MINA/AIOT/RLC/CAP/龙虾USDT;
earlier windows held NMR/GRIFFAIN/LYN/PHA — rotation, not flapping).

Dashboard long-run: all routes 200 during post-mortem
(`/overview` 49.6ms, `/movers` 12ms, `/system` 6.4ms, token pages 9–22ms,
`/api/health` 21.5ms, `/api/snapshot` 3.7ms, search 7.2ms). Health `stale`
honestly (snapshot 22520s old — probe dead, expected); was `ok`-while-fed
per 749 persisted snapshots. 9/9 movers categories render; discovery-only
honesty holds (AINUSDT page: DISCOVERY ONLY + NO LIVE DEEP FEATURES).
Chart: 4h MATURED during soak (16.34h span); 24h PARTIAL (16.34h/24h,
capped 1000 pts, restored-history dependent). Post-mortem trailing-4h
query returns 0 pts — honest staleness artifact (feed 6.25h old), not a bug.
Movers anomaly CONFIRMED by code inspection (`dashboard_views.py`
movers section: shared per-row `_v` overwritten by each later category
loop, so a symbol in several categories shows the last-assigned value in
every table — velocity/accel/vol-z/flow scales mixed). Recorded as a
P1-11A audit item; NOT fixed during closure.

Persistence (DB `data/microprobe.db`, schema v6, ~197MB at END; start size
not captured — unavailable, not guessed): snapshots 749 (cap 1000, holds;
min rt 32.19 / max rt 17677.917 — this run's 554 + prior runs retained),
observations 10000 (cap holds), rejections 1000 (cap holds), price_samples
5601 (16.34h span), flow_buckets 4710 bounded (600/597/304/69 per
size/symbol), oi_samples 996, return/flow/book/OI/structure features 3
each (REPLACE latest-only), discovery snapshot 1 (REPLACE), universe_events
46 (cap 500), rank snapshots 3. Write errors 0, lock errors 0, no snapshot
starvation (dedicated writer held), persistence inflight high-water 5063 →
final 0, drained to 0. Sampling gate intact (accepted 34k/40k/39k vs
dropped 468k/13.6M/349k aggTrade/bookTicker/depth; markPrice/forceOrder
ungated and fully ingested).

Resources: RSS/CPU NOT captured by the probe (UNAVAILABLE — do not infer
from DB size). Backpressure bounded everywhere (engine queues 0/0,
inflight 0, dashboard ms-grade post-mortem).

Errors (full 4.91h): websocket 43 (38 public + 5 market) CONCERNING in the
final hour (storm) / RECOVERED earlier; parse 0, payload 0, invalid engine
events 0, late events 0; timestamp rejects 742182 (~4.8%) CONCERNING
(final-hour concentration); persistence errors 0; SQLite errors 0; OI REST
failures 0/813; depth gaps 97 total, all recovered (RECOVERED); dashboard
HTTP errors 0 (post-mortem 200s); reconnects 43 CONCERNING. None BLOCKING
except the duration gate itself.

Detectors (telemetry only, NOT signals): `extreme_funding_rate` 16512 log
lines (crossings BTC 5417 / ETH 4960 / SOL 6095 — near-constant series:
175–176 valueChanges over 13519 samples; same hypothesis-artifact class,
no conclusions); `large_liquidation_individual` 25 (all SELL: 8/12/5);
`large_liquidation_window` 8 (1/4/3); `volume_spike` 102 (36/35/31). No
threshold tuned.

Safety: BOT_MODE=observe in startup + all 554 summaries; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, cancels 0, leverage changes
0, private/account endpoints 0, capital at risk 0, order paths absent
(static test green). NO VIOLATION.

Checkpoints (reconnects / rejects / msgs / gaps / flow / HOT):
START rt32: 0 / 0 / 16k / 0s / 349 / [] → T+1h: 6 / 125k / 3.07M / 3s /
108895 / 5 HOT → T+2h: 10 / 231k / 5.90M / 7s / 192706 / 6 HOT → T+3h:
10 / 231k (flat — healthy middle third) / 9.20M / 7s / 292131 → T+4h:
14 / 376k / 12.51M / 11s / 409250 → END rt17678: 43 / 742k / 15.34M /
33s / 502191. Drift story: healthy middle (T+2h→T+3h: 0 new reconnects,
0 new rejects over 3600s), degraded bookends, collapsing final hour.

Verdict reasoning: gate A (one continuous run ≥21600s) fails — 17677.9s
is the proven maximum, no final_summary, unclean externally-killed exit.
Per the closure rubric FAIL is forced ("duration invalid"); PARTIAL does
not apply (the run did not complete). Safety is clean, engines/persistence
/dashboard all behaved, but transport showed sustained P1-01-grade episodes
(aggTrade ETH/SOL p50 90–152s, final-hour storm). The 4.91h of evidence is
VALID for P1-11 raw-feature auditing (monotonic, gap-free summaries), but
P1-10 itself must be re-run (P1-10R) with a survivable launch before any
gate may pass. `docs/PHASE_1_REPORT.md` untouched.

## P1-11A raw feature + Movers integrity audit — RESULT: PASS (2026-10-07)

Used the valid P1-10 4.91h evidence (554 gap-free summaries, 15.34M msgs;
P1-10 stays FAIL on duration — not marked PASS). Baseline before work:
312/312 PASS. No strategy/backfill/classifier/subscription/signal/paper
work started.

Movers bug — FOUND, ROOT-CAUSED, FIXED NARROWLY: `render_movers`
(`dashboard_views.py`) shared one per-row `_v` across all 9 category loops
(last write won: symbols in several tables showed e.g. the flow value in
the gainers table). Source→render audited per category (DISCOVERY: 24h
gainers/losers → `change_24h_pct` sorted by signed 24h %, shown `+%.2f%%`;
quote-volume leaders → `quote_volume_24h`; HOT → "proposed". LIVE,
subscribed-only: velocity ± → `velocity_1m` (`%.3g/s`); acceleration →
`accel_1m` (`%.3g/s²`, sorted by |accel|); volume expansion →
`vol_z_1m` (`%+.2f z`); aggressive-flow → `flow_delta` (`%+.2f`, sorted by
|delta|)). Fix: per-category display keys passed to the renderer; sources,
sorts, units, formatters unchanged. Proven: new `MoversIntegrityTest`
(5 tests, unique fixtures) fails 4/5 on old code, passes 5/5 fixed.

Feature verdicts (END-state rows + START/END summaries; full scales in
`docs/FEATURE_MODEL.md`): returns 1m/3m/5m/4h live with sane log scales
(15m/1h/24h honestly UNKNOWN after the degraded finale); velocity/accel
scales 1e-6–1e-5 /s and 1e-7–1e-8 /s² with correct warming gates; flow all
6 horizons + baselines + accel present (ratios in [−1,+1], units USD
notional, BTC>ETH>SOL ordering); book spreads 0.012–0.86bps, imbalances in
[−1,+1], 0 crossed, gaps recovered; OI base-unit units verified with mixed
horizon signs and coherent anchors; VWAP ±4.6bps; vol warmed flags honest
(UNKNOWN ≠ 0); range positions in [0,1]; structure evaluating on 16.34h
span. No impossible values, no unit mismatches, no malformed transitions.
Funding crossings re-confirmed artifact-class (near-constant series).

Transport impact (healthy T+2h→T+3h vs degraded T+4h→END): 918 msg/s 0%
rejects 0 reconnects 0 gaps vs 867 msg/s 12.9% rejects 29 reconnects 64
gaps. Feature effect: returns span still grew (+360 vs +129 samples); flow
−6.5%; book ingest −64% (depth starved, integrity HEALTHY); structure
−19%; OI ISOLATED (0 failures both). Degradation starves honestly, never
corrupts — classifiers must take UNKNOWN/staleness as first-class input.

Design-only plans added (nothing implemented): BTC context + relative/
correlation/beta/lead-lag, exhaustion/absorption research, opportunity
lifecycle, backtest/paper sim costs (`docs/SIGNAL_RESEARCH_PLAN.md`);
P1-11B resolutions + P1-11C event studies with MFE/MAE/no-lookahead
(`docs/HISTORICAL_RESEARCH_PLAN.md`); roadmap P1-11A→…→P1-16 in TASK_QUEUE.
Tests after: 317/317 (312 + 5 new). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B historical data foundation — RESULT: PASS (2026-10-07)

Official docs first: developers.binance.com unfetchable here (empty
responses, same as P1-05) → all seven contracts verified LIVE against
fapi.binance.com (public, no keys, ~35 tiny requests) + OpenAPI enum
cross-check; recorded exactly in `docs/MARKET_DATA.md` (params, limits
1500/500/1000, weights measured ~1/1/20, intervals, startTime/endTime
edge behavior, 2400/min pool).

Built (stdlib only): `history_client.py` (conservative weights + adaptive
weight-header hard pause 2000/2400; retries budget 5 exp-backoff+jitter;
429 honors Retry-After budget 2 then abort; 418 aborts; forward pagination
with overlap-raise + skip-record; OI timestamp pagination; aggTrades fromId
helper) + `history_store.py` (separate `data/historical/historical.db`,
schema v1: klines WITH volume / mark klines WITHOUT volume columns /
OI as-served / coverage / run ledger / gaps) + `history.py` CLI (status /
fetch / verify; explicit symbols, 7d/25 defaults, no bulk mode).
Listing-aware (geneses recorded: BTC Sep-2019, MINA Feb-2023, ORCA
Dec-2024); CLOSED candles only; gaps stay UNKNOWN/GAP (no fill).

Pilot (bounded): 1h×30d klines ×5 syms (719 each), 15m×30d ×3 (2879),
1m×3d BTC (4319), 1h×30d mark ×3 (719) — all ratio 1.0, 0 gaps, 0 malformed;
5m×7d OI BTC hit the 500-row availability cap (~41.6h — documented
limitation); aggTrades confirmed recent-only (0.1 min). Resume re-run: 0
rows, 1 request (idempotent). 13 series stored. No backfill beyond pilot.

Minimal exposure: `/api/history/status` + `/api/history/:symbol`
(404-empty/unknown, 400-malformed) + HISTORICAL COVERAGE token card; no
Opportunities/Signals/Paper/Backtest UI. Storage tiers + prospective
flow/book retention + fidelity contract in HISTORICAL_RESEARCH_PLAN.md /
FEATURE_MODEL.md. Tests after: 353/353 (322 + 31 new mocked-HTTP history
tests). `docs/PHASE_1_REPORT.md` untouched.

## P1-11B.1 probe lifecycle + dashboard run control — RESULT: PASS (2026-10-07)

Canonical manager `control.py` (registry `logs/probe_runtime.json` with
pid/ctime/started/mode/duration/expected-end/launcher/preset/evidence/
last-exit; CLI status/start/stop). Probe self-registers on EVERY direct
launch (`__main__`; refuses with exit 2 when another probe holds the
registry; COMPLETED/FAILED/STOPPED marked on exit; registry failures never
break collection). Single-instance refusal; stale-PID recovery to FAILED;
stop kills only the verified PID (bounded 10s wait). All control-started
probes get merged UTF-8 file logs (`logs/probe-runs/`, validation preset
`logs/p1-10r/`). Dashboard: `GET /api/control/probe/status` (process +
feed separated) + POST-only start/stop (localhost Host + local Origin +
per-process nonce; GET mutations 405; fixed argv, BOT_MODE forced observe,
no shell) + MARKET ENGINE header block on all pages (no `<button>`, 4s
polling, green/gray/amber/red). Modes: Continuous, 6 Hours, 6H Validation
(evidence mechanics — NOT an automatic P1-10R PASS).

Live-verified (short bounded only, no 6h started): dashboard START →
RUNNING PID 16336 (tasklist-confirmed) → feed STALE→ok honestly →
dashboard STOP killed only the probe (dashboard survived); external CLI
start (--duration 90/75) auto-discovered as RUNNING/launcher=agent in UI;
90s run self-marked COMPLETED duration-reached; CLI stop → STOPPED.
Tests after: 376/376 (353 + 23 new mocked lifecycle/API tests).
`docs/PHASE_1_REPORT.md` untouched.

## P1-11C historical event studies + prospective capture — RESULT: PASS (2026-10-07)

- Engine (`events.py`, NEW, research-only, no signals): formation uses
  bars with open_time <= T only; outcomes use open_time > T only (proven
  by no-lookahead tests incl. poisoned-future reruns). Reference price =
  closed bar close at/preceding T, labeled mark_close vs regular_close
  (never silently mixed). Fixed horizons 1m/3m/5m/15m/30m/1h; LONG-up
  MFE/MAE + SHORT-down mirror; time_to_MFE/MAE; predeclared invalidation
  only; path COMPLETE/PARTIAL/INVALID_GAP/INSUFFICIENT_HISTORY (never
  filled); formation/outcome gap exclusions; BTC synchronized lookup +
  relative_return = token − BTC; 30d as-of levels; HISTORICAL_TAKER_BUY_
  PROXY + ABSORPTION_PROXY labels; sample tiers
  INSUFFICIENT/EXPLORATORY/PRELIMINARY/LARGER_SAMPLE (quantity only).
- Definitions: 6 versioned HYPOTHESIS families (EXTENDED_GAINER/LOSER,
  MOMENTUM_ACCELERATION_UP/DOWN as HISTORICAL_MOMENTUM_PROXY, FAILED_
  HIGH/LOW_CANDIDATE); changing a threshold creates a new version; runs
  recorded with params/symbols/ranges/sources (deterministic reruns).
- Storage: historical DB schema v2 (additive over v1): event_definitions,
  event_study_runs, event_instances, event_feature_snapshots,
  event_outcomes + research_flow_10s/1m + research_book_1m (idempotent
  keys; retention cleanup batched/hourly, never per-tick).
- Recorder (`research_recorder.py`, NEW, probe-owned): starts with
  MarketProbe, drains (partials marked) on exit; same process/registry/
  launcher — no second manager. Bounded queue (drops counted, engine
  never stalls); DB failures degrade the recorder only (probe survives,
  tested). Flow semantics reuse validated P1-06 m-mapping read-only.
  Retention 7d/90d/90d configurable; measured estimate ~200B/row →
  ~66KB/day/symbol flow-10s + ~288KB/day/symbol each 1m table (~35MB for
  15 symbols at full retention).
- Live verification (canonical control plane, 150s → COMPLETED
  duration-reached, evidence `logs/probe-runs/probe-20261007T224304Z.log`):
  runtime 153.15s, flow 1722 events, book 4042 msgs, research writes 60
  (flow_10s 45 + flow_1m 9 + book_1m 6 rows), drops 0, errors 0,
  inflight 0, high_water 2, final_summary present. Dashboard restarted
  (PID 30984): /api/research/status + /api/events/studies +
  /api/events/studies/:def + /api/events/symbol/:sym all 200; control
  status/start/stop/external-detection intact; 6H-Validation preset
  verified compatible (forces 21600s, same registry/evidence path —
  NOT started).
- Pilot (bounded, stored bars only): 38 runs — 1h × (BTC/ETH/SOL/MINA/
  ORCA/NMR) × 6 families + 15m × trio GAINER/LOSER. NMR added by a
  justified 2-request extension (719 bars, ratio 1.0, ~144KB). Counts:
  GAINER 168 usable (mean fwd −0.04bps), LOSER 67 (−25.8bps), ACCEL_UP
  1170/1203 (+8.7bps), ACCEL_DOWN 1147/1184 (+4.4bps), FAILED_HIGH 18/19,
  FAILED_LOW 8/10. Sub-1h horizons on 1h bars share the next-bar outcome
  (resolution limitation, documented). No profitability/edge claim; small
  samples flagged INSUFFICIENT/EXPLORATORY.
- Tests: 408/408 (376 + 32 new: 18 events incl. no-lookahead/MFE-MAE/
  gaps/BTC/relativity/as-of/proxy/versioning/idempotency/no-autotune +
  14 recorder incl. buckets/quality/retention/queue-drops/isolation/
  lifecycle/no-second-process). `docs/PHASE_1_REPORT.md` untouched.

## P1-10R formal ≥6h soak re-run — RESULT: PASS (2026-10-08)

Run: ONE continuous WMI-detached process (PID 19084; parent chain
python → cmd → WmiPrvSE Session 0, independent of all agent shells),
`--duration 21600`, preset validation-6h, launcher
scheduler-6h-validation, BOT_MODE=observe. Started 2026-10-08T00:48:20Z,
final summary 2026-10-08T06:48:23Z: **21603.9s ≥ 21600s**. Registry
COMPLETED + duration-reached + exit 0; process exited (no orphan); 1
startup; 699 periodic summaries, max inter-summary gap 49.7s, 0 gaps
>120s. Evidence (local, git-ignored):
`logs/p1-10r/probe-20261008T0048Z.log` (33.3MB merged UTF-8) +
`logs/p1-10r/P1-10R_HANDOFF.md`. No app-code changes during the run
(proven: empty `git log` on src/tests/config since launch baseline).

Transport (vs P1-01R healthy precedent and P1-10 degraded finale):
- Coverage 11/11 all 6h, missing [], stale []. 19,004,903 messages
  (bookTicker 17.77M, depth 590k, aggTrade 595k, markPrice 42k,
  forceOrder 8.8k).
- Reconnects 10 total (public 4 × ConnectionClosed, market 6: 1
  ConnectionClosed + 5 opening-handshake TimeoutErrors with 2→30s
  backoff); attempts 12, parse 0, payload 0.
- Skew-rejects 143,624 (0.76%); uptime market 99.10% (21406s),
  public 99.95%.
- Corrected delivery lag p50 ~170–250ms every stream (P1-01R-grade);
  p95 sub-second except sparse forceOrder; p99 ≤0.66s (forceOrder
  excluded: event-driven). Rare single-message max outliers (~311–510s)
  with steady neighboring throughput — isolated, not episodes.
- Episodes (all auto-recovered, none hidden in averages): ~01:29–01:32Z
  (public reconnect, ~24k rejects); ~02:31–02:35Z (public reconnect,
  ~37k rejects); ~04:20–04:29Z (~9.5min: market handshake timeouts,
  6 market + 1 public reconnects, ~82k rejects, market-stream silence
  ≤192s). Final hour rt 18007→21590: 0 reconnects, 0 rejects, 3.07M
  msgs — NO P1-10-style final-hour collapse.
- Depth gaps 5/5/5 total (reconnect-driven), all recovered
  (degraded=false, crossed 0 at END). Clock 36/36 syncs ok, 0 failures
  (offset −582ms → −208ms, RTT ~343ms).

Engines (all monotonic, 0 invalid / 0 late everywhere): returns 3886
samples/symbol over 31.5h span (restored + live); flow 566,244 events;
book 587,330 msgs; OI 1029/1029 polls ok (p50 347ms, slow polls
absorbed); discovery 36 scans (924 seen → 467 eligible, HOT 6 with
hysteresis); structure evaluating (symbols_evaluated). Detectors are
telemetry only: 22622 funding crossings (same hypothesis-artifact
class), 11 individual + 1 window liquidations, 181 volume spikes — no
threshold conclusions.

Research recorder (P1-11C validation): RUNNING all 6h → drained STOPPED;
writes 8273, drops 0, errors 0, inflight 0, high-water 6. Rows added:
flow_10s +6191 (vs ~6480 est, 95.5%), flow_1m +1041 (~96%), book_1m
+1041 (~96%) — shortfall is the documented stall episode plus edge
partials, no unexplained loss. Historical DB +1.58MB (16.47 → 18.05MB),
integrity ok; operational DB 206.9 → 238.9MB (retention caps hold:
snapshots at 1000), integrity ok; persistence errors 0, locks 0.

Dashboard: alive throughout and after (PID 30984); feed/health states
independent and truthful (STALE chip after completion is honest — last
snapshot is the 06:48:23Z final). No phantom RUNNING. The known
tasklist/wmic popup defect (P1-10R-FIX-01) stayed cosmetic: 2 spawns
per 4s poll, negligible overhead, no evidence impact; fix deferred to a
separate post-soak change (CREATE_NO_WINDOW), NOT applied here.

Safety: BOT_MODE=observe in startup + final; apiKeysUsed 0,
authenticated clients false, realOrdersSent 0, capital 0, no order
paths (static tests green). NO VIOLATION.

P1-10 failure mode eliminated: the old run died externally at 4.91h
with an unhealthy finale; P1-10R survived its full window in a
session-independent process AND its worst transport episode (~9.5min)
self-recovered with 3.5 clean hours after it.

## P1-10R-FIX-01 console-popup fix — APPLIED (2026-10-08, post-PASS)

Root cause (confirmed earlier): every 4s browser poll of
`/api/control/probe/status` ran `dashboard.process_info()` →
`subprocess.run(tasklist)` + `subprocess.run(wmic)` with no
`CREATE_NO_WINDOW`, flashing visible consoles; probe launches via
`control.start_probe` had the same gap. Fix: new
`dashboard.no_window_flags()` helper (CREATE_NO_WINDOW on Windows, 0
elsewhere — POSIX unchanged) applied to both `process_info` calls and
the `start_probe` Popen. Identity semantics untouched (image +
creation-time checks, honest UNKNOWN on failure). Verified: 420/420
tests (12 new, mocked — no real consoles opened); dashboard restarted
(PID 30984 → 28440, no probe active at the time); 75s observe-only
lifecycle via the canonical plane went STARTING → RUNNING (feed
HEALTHY) → COMPLETED naturally; /overview /movers /system 200;
Next.js :3000 unaffected. Popup suppression is proven at code level
(flags asserted in tests); headless agents cannot visually confirm
flash absence — user-side confirmation still welcome. P1-10R PASS and
P1-12 READINESS unchanged.

## P1-12A market state classifier v0 — RESULT: PASS (2026-10-08)

Deterministic explainable classifier (`classifier.py`, rules v0.1.0,
all-HYPOTHESIS): NORMAL / IGNITION / EXPANSION / EXHAUSTION / REVERSAL +
UNKNOWN (missing/stale/discovery-only), directions UP/DOWN/NONE/UNKNOWN.
Every record carries symbol, state, direction, observed_at_ms,
features_used, evidence_for/against, missing_features, validity,
rules_version, and transition {previous, changed, since, duration,
reasons}. No probabilities, no LONG/SHORT wording, no entries — observed
states only. Priority REVERSAL > EXHAUSTION > EXPANSION > IGNITION >
NORMAL with contradictions stored, never hidden; hysteresis holds
energetic states 2 evals (UNKNOWN exits at once); REVERSAL needs 2
consecutive confirmations; no forced sequence; memory restarts cold and
says so. Inputs are the already-built peer-engine rows (returns +
momentum, 1m flow, book imbalance, 1m OI, 15m range/structure/vol) —
no new ingest/endpoint, no lookahead possible by construction.

Persistence schema v7 (additive, tested v1..v6→v7 with rows preserved):
`state_features` REPLACE/symbol + `state_transitions` append ≤500.
Probe evaluates once per ~30s summary (measured 0.16–0.20ms/batch —
negligible) and logs real transitions; summary carries a `states`
census block. Dashboard: token-page "Market state v0" panel
(state/direction/as-of/rules/previous/reasons/features/missing/validity)
with honest discovery-only/warming notes — no new HTTP contract, no
Next.js changes.

Validation: 25 deterministic fixture tests (all states × directions,
UNKNOWN paths, contradictions, transitions, hysteresis, gaps, cold
restart, no-lookahead incl. future-key injection, timestamps,
discovery-only, serialization, determinism). Controlled 120s
observe-only run via canonical plane COMPLETED naturally: 9 evaluations
(3 symbols × 3 summaries), states + 4 transitions persisted (incl.
BTC NORMAL→REVERSAL with flip evidence), token pages render the panel,
0 rejects, 0 reconnects, 0 orders, both frontends 200. No predictive
accuracy claimed (prospective evaluation is P1-14 territory).

## P1-12B dynamic live universe v0 — RESULT: PASS (2026-10-08)

Bounded HOT selection + lifecycle (`universe_manager.py`, v0, pure
deterministic logic): DISCOVERY_ONLY → PROMOTION_PENDING → SUBSCRIBING →
WARMING → LIVE (DEGRADED on silent streams) with DEMOTION_PENDING →
UNSUBSCRIBING → UNKNOWN + cooldowns. Ranked proposals from existing
`select_hot` votes (no classifier input — no circularity); eligibility +
ticker freshness + slot/stream budgets + transport health gate every
promotion; 1800s LIVE dwell, 3600s demotion cooldown, 2-missed-scan rank
decay, ineligibility bypasses dwell (proven breach), CORE never evicted
or shadowed. Budgets (fail-closed, conservative local policy — official
WS docs unfetchable here, all caps UNVERIFIED): 3 HOT slots, 60 total
streams, 50/connection, 6 connections; actual footprint 4 connections /
≤26 streams. HOT rides `hot-public` (bookTicker+depth) + `hot-market`
(aggTrade); global markPrice/forceOrder arrays never duplicated.
`_connection_loop` accepts a URL callable so reconnects restore exactly
the desired set; resync (cancel exactly the 2 managed tasks + respawn)
fires only on desired-set change with a 60s anti-flap guard; canonical
pair never touched. Engines gained allow/forget (flow/book/returns/
structure/classifier/OI tracker) + OI poller HOT list (≤8 polls/round);
recorder finalizes demoted symbols as explicit PARTIAL (idempotent keys);
markPrice returns ingest extends to subscribed HOT (funding detector
stays CORE-configured). Dashboard overview distinguishes proposals
(`HOT dynamic`) from subscriptions (`HOT subscribed (deep)`) + lifecycle
table + hot_* events; Token Detail opens HOT symbols via live sets.
No schema migration (discovery snapshot blob extended in place).

Validation: 31 tests (manager + probe sync + recorder + classifier +
config + safety surface); full suite 478/478. Controlled 300s
observe-only run (temp 60s-scan config, repo config untouched)
COMPLETED naturally: 465 eligible → 6 proposals → 3 promotions
(OGNUSDT/METUSDT/GRIFFAINUSDT), both HOT connections up, all 3 LIVE
(mark+trade+depth), 0 demotions/failures/refusals, 0 reconnects,
0 rejects, 259k msgs, HOT research buckets 24/4/3 per symbol,
6 symbols classified, safety 0/0/0. Dashboard verified live
(subscribed row, lifecycle table, OGN token panel).

## P1-12B.1 dynamic universe integrity audit — RESULT: PASS (2026-10-08)

Independent review of P1-12B raised two concerns; both reproduced, both
fixed minimally with no architecture change:

A. Candidate freshness (CONFIRMED): `ticker_close_ms=None` promoted,
future timestamps passed the one-sided comparison, and malformed values
aborted the whole update. Fix: per-candidate fail-closed
`check_timestamp_fresh()` (missing/malformed/implausible-unit/too-old/
too-future reject with reasons; ≤60s future skew tolerated and
documented). Upstream passes None through, so the manager gate is the
enforcement point; trusted clock is local wall time.

B. Stream accounting (CONFIRMED, conservative direction): `+2`
connections leaked into a stream total, and reports claimed `17
canonical` vs measured **11** (9 per-symbol + 2 global arrays). Fix:
single authoritative `account_streams()` shared by enforcement and
telemetry (connections and streams separate units; globals counted
once). No over-budget promotion ever occurred (errors over-counted).

Provider docs re-fetched 2026-10-08: empty again — all caps stay
UNVERIFIED/LOCAL_POLICY, nothing raised. Validation: 18 new tests;
full suite 496/496; 240s observe run COMPLETED (3 promotions AIOT/MET/
OGNUSDT all LIVE, 0 staleness skips — real closeTime is fresh ms,
400k msgs, 0 reconnects/rejects, 6 symbols classified, safety clean);
dashboard shows subscribed row + lifecycle + token panels; Next.js
unaffected. P1-12B PASS record stands (append-only correction).

## Known gaps (Phase 1 work ahead, in order)

Minimal dashboard: DONE (P1-03 PASS) → terminal DONE (P1-09 PASS,
v0.8.0 live at http://127.0.0.1:8091).
Returns engine: DONE (P1-04 PASS — universe + 7-TF mark-price log returns).
Discovery + velocity/acceleration/ranking: DONE (P1-05 PASS — 449-eligible
scan, 6-HOT proposal, live momentum + ranks, intel UI + APIs).
Movers integrity + raw-feature validation: DONE (P1-11A PASS — per-category
display keys, 5 regression tests, all families measured trustworthy).
Volume + aggressive flow: DONE (P1-06 PASS — 6-horizon flow, baselines,
acceleration, v0.5.0 dashboard + APIs, healthy 363s validation).
Order book + open interest: DONE (P1-07 PASS — snapshot book intel, OI
polls/deltas/contexts, v0.6.0 dashboard + APIs, 363s validation).
VWAP + volatility + structure: DONE (P1-08 PASS — flow-VWAP, raw vol,
range expansion, confirmed pivots, v0.7.0 dashboard + APIs, 372s run).
Transport re-validation: DONE (P1-01R PASS — 45min healthy window, soak
gate unblocked).
Remaining: P1-13A opportunity/setup engine (NEXT candidate — needs explicit
instruction), then P1-13B UX, calibration (P1-14).
Decision/feature traceability for these lives in `docs/FEATURE_BACKLOG.md`
(F-UNI-01, F-OPP-01/UI-01, F-BT-01, F-PAPER-01, F-PORT-01). P1-11 raw-feature validation may use the valid
4.91h P1-10 evidence; the Movers shared-`_v` category-value anomaly is a
recorded P1-11A audit item (not fixed).

## Blockers / issues

- P1-10 FAIL (2026-10-07): soak killed externally at 4.91h/6h (17677.9s),
  no final_summary, exit unknown. P1-10R re-run required before any soak
  gate passes; launch must survive the full window (see DECISIONS) and
  capture merged stdout+stderr as UTF-8 (the P1-10 UTF-16 PowerShell `>`
  capture wrapped every long JSON line and had to be reconstructed).
- Transport was flaky in this environment (P1-01 PARTIAL: 58 reconnects,
  85% rejects), but P1-01R (45min, 0 reconnects, 0% rejects, sub-second
  lags) now PASSES the soak gate. If a future run shows P1-01-grade
  degradation again, re-validate before trusting soak/calibration gates.
- Detached probe processes die with the harness tool session (observed twice):
  use blocking bounded runs for evidence windows.
- Dashboard RUNNING at http://127.0.0.1:8091 (PID 7564, v0.8.0; read-only,
  localhost — safe to keep). Snapshot goes STALE without a running probe
  feed (honest chip); continuous freshness arrives with the P1-10 soak.
- No secrets, keys, or account access exist or are needed.

## P1-14A prospective setup evaluation V0 — RESULT: PASS (2026-10-08)

Forward outcome observation for P1-13A setups. Registers candidates at first DETECTED
and evaluates mark-price returns at versioned horizons (1m/5m/15m/1h/4h).
Research only — no P&L, no lookahead, no probabilities.

- Module: `src/microstructure_probe/prospective.py` (`ProspectiveRecorder`).
  Idempotent, restart-safe, bounded queue (default 1000), drops telemetry.
- Horizons: 1m/5m/15m/1h/4h (ms). Maturity checked strictly after
  `detected_at_ms + horizon_ms` — no lookahead.
- Outcome states: COMPLETE / PENDING / INSUFFICIENT_HISTORY /
  INVALID_GAP / PARTIAL. Missing ≠ zero; incomplete never forced COMPLETE.
- Persistence schema v9 (additive): `prospective_setups` (REPLACE per key)
  + `prospective_outcomes` (append-only, unique (key, horizon, observed_at_ms),
  rolling 500 per setup). Migration chains v1–v9 all upgraded.
- Retention cleanup: `research_retention_cleanup(days)` — hourly max,
  default 90 days for both tables.
- Probe integration: registers in opportunity cycle (DETECTED + evals<=1),
  observes with current mark_price at summary tick. State exposed in
  `snapshot()["prospective"]`.
- Dashboard: `/api/prospective` (schema_version 9, RESEARCH ONLY banner,
  live status + latest 10 outcomes).
- Fabrication guards: no MFE/MAE, no win-rate, no "X% probability"
  patterns; interpretation says "research priority only — NOT expected profit".
- Tests: 35 tests in `tests/test_prospective.py` — all pass.
  Full suite: 554/554 OK (519 baseline + 35 new).

## P1-14B prospective integrity validation (recovery) — RESULT: PASS (2026-10-09)

Recovery of the interrupted P1-14B session on branch
`phase1/market-intelligence-dashboard` at SHA `e727e54`; workspace recovered,
evidence preserved, no data loss. Validation of P1-14A prospective evaluation
integrity against deterministic tests and real persisted evidence:
event-time maturity, no-lookahead, dedup, restart idempotency, v8→v9 migration,
90-day retention + bounded 500-outcome log, quality flags without fabrication,
dashboard `/api/prospective` parity, observe-only safety. Full suite **593/593**
OK (519 + 35 + 39 `tests/test_p14b_validation.py`).

- Two session fixes accepted into the working tree:
  `prospective.py:106` rehydrates `setup.get("setup_json", {})` so restarted
  registries carry `detected_mark_price` (recompute COMPLETE, not
  INSUFFICIENT_HISTORY); `dashboard.py:403` reads the injected shared store
  so `/api/prospective` mirrors the recorder (parity).
- Real evidence in `data/microprobe.db` (schema v9): 7 unique registered setups
  (event time 2026-10-08 23:42:04 → 24:06:30), 1 observed outcome
  (`REVERSAL_WATCH:ETHUSDT:UP` → 1m, COMPLETE, mark_return_pct=-0.037134,
  detected 2477.50 → current 2476.58). Event-time audit PASS on every record;
  zero duplicates; zero PENDING/INVALID/INSUFFICIENT rows (unobserved horizons
  are absent, never fabricated).
- Pilot preserved: `p14b_pilot_monitor.py` (+`logs/p14b_pilot.log`) — 150s
  observe-only run with DB polling and event-time vs wall-clock audit;
  `p14b_dashboard_readtest.py` — dashboard read-path validation;
  `.firecrawl/*.json` market-data dumps preserved.
- API verified locally: `/api/prospective` returns schema_version 9,
  RESEARCH ONLY banner, setup_count=7, outcome_count=1, full denominator in
  latest_outcomes; `state` = UNKNOWN honestly reflects no live probe.
- Limitations (honest): single outcome is descriptive only (-0.037134%);
  6/7 setups lack observed horizons because the pilot window's event time did
  not reach their 5m/15m/1h/4h maturities — absent, not forced. The pilot
  suffered host clock anomalies (ms/s epoch mismatch in the monitor log) which
  limited coverage; the event-time design tolerates host skew by firing only at
  `detected_at_ms + horizon_ms` and never looking ahead.
- No active run; `BOT_MODE=observe` preserved; zero orders, zero capital;
  Dashboard V2 worktree untouched. P1-14C not started.
- Full report: `docs/P1_14B_VALIDATION_REPORT.md`.

## P1-13A research opportunity/setup engine V0 — RESULT: PASS (2026-10-08)

Observe-only engine that identifies market setups worthy of further
research. Consumes existing P1-12A classifier output + P1-12B universe +
all feature rows — never recalculates states, never generates orders.

- Module: `src/microstructure_probe/opportunity.py`
  (`OpportunityEngine`, `evaluate_symbol`, `historical_reference`,
  `rank_candidates`). Rules version `v0.1.0`.
- 5 setup families: MOMENTUM_CONTINUATION, IGNITION_WATCH,
  EXHAUSTION_WATCH, REVERSAL_WATCH, EXTREME_MOVE_RESEARCH.
- Lifecycle: DETECTED → WATCHING → ACTIVE_RESEARCH → INVALIDATED/EXPIRED
  → UNKNOWN. Cooldown 60 min (code 3_600_000 ms), TTL 24h, max 200 candidates / 500 events.
- Persistence schema v8: `opportunity_candidates` (REPLACE per key) +
  `opportunity_events` (append-only, rolling 500). All upgrade chains
  migrated through v8.
- Probe integration: `opportunity()` property, demotion `forget()`,
  promotion `allow()`, summary stats + event logging.
- Dashboard: `/opportunities` page + `/api/opportunities` JSON endpoint
  (v0.1.0 candidate view-model, RESEARCH ONLY banner).
- Fabrication guards: no confidence/win-rate/expected-return/MFE/MAE;
  no "X% probability" patterns; interpretation says
  "research priority only — NOT expected profit".
- Tests: 58 tests in `tests/test_opportunity.py` — all pass.
  Full suite: 554 tests OK (553 baseline + 1 new).
- Validation run (120s, observe): 3 REVERSAL_WATCH candidates stored
  (DETECTED), 4 lifecycle events, 7 state rows, safety clean
  (BOT_MODE=observe, 0 keys, 0 orders, 11/11 streams).

## P1-14B.1 time integrity, data quality & prospective readiness — RESULT: PASS (2026-10-09)

Audit → reproduce → correct → test → validate → document. Starting SHA
`18c639b`; no other agent changes; safety preserved throughout.

- **Anomaly A (monitor-side, confirmed):** pilot `elapsed=-1789712305900s`
  is `time.time()[s] − t0[ms]` in the executed (unpreserved) monitor
  version — magnitude, +10 s/poll tick, and exact constant all reproduced
  (`t0_ms=1791503809710`, poll-1 wall `1791503809.713313`). The bug also
  defeated the monitor's 200 s timeout (hence the killed session). Core
  engine clean (zero `time.time()` in `prospective.py`; all-ms paths in
  `probe.py`/`clock.py`). Preserved `p14b_pilot_monitor.py` (Run B) is
  unit-clean; kept byte-identical as evidence with hygiene notes.
- **Defect B (core, fixed):** restart rehydration dead on the production
  path — `config/probe.json` has no `db_path`, so `_load_from_db`
  early-returned and restarts orphaned all setups (Run B: `registered_setups=0`
  with 6 DB rows). Fix: default-store rehydration + seen-set rebuild from
  stored outcomes + load-failure warning. Post-fix run: `registered_setups=7`
  from summary #1.
- **Defect C (core, fixed):** `store_prospective_outcome`'s 500-row bounding
  DELETE lacked a key filter — every store wiped all other setups' outcome
  rows (scratch-proven: A×2 then B×1 → total=1, A=0). This artifact shaped
  the P1-14B "single outcome" evidence. Fix: scoped per-key bound. Post-fix
  run: 28 coexisting rows (4/key × 7), 0 dupes, all COMPLETE.
- **Change D (core, fixed):** `observe()` ran only inside the matched-
  candidate loop, so quiet ticks never matured setups (run #1: 7 setups,
  4 summaries, 0 calls — against the spec's per-cycle mandate). Fix:
  per-symbol observation over `opp_bundles` each summary (same mark source).
- **Corrected denominators:** 7 setups cumulative across ≥4 runs (5 pre-pilot
  + 1 Run-A-window + 2 Run-B @00:06:30); 28/28 matured cells COMPLETE
  (4h: 0/7 matured — genuinely future); 0 PENDING/INSUFFICIENT rows;
  no-lookahead PASS all rows; Defect-C losses unrecoverable (documented,
  not reconstructed). The original UP-1m outcome predates the pilots.
- **Host clock:** `w32tm` unsynchronized flag + 9 s dispersion, but live
  offsets sub-second (−120 ms → +448 ms); design correctly avoids depending
  on it (exchange E for ordering; host wall only as self-consistent anchor).
- **Tests:** 609/609 OK (593 + 16 new `test_p14b_1_time_integrity.py`;
  1 P1-14B restart test hardened). Three controlled 120 s observe-only runs
  (exit 0) prove each fix live. P1-12A/B, P1-13A untouched.
- **Readiness:** prolonged-run criteria + blockers recorded (needs 30+ min
  healthy window, pre-run clock resync note, log-capture hygiene). NO long
  run started. V2 worktree/ports untouched.
- Full report: `docs/P1_14B_1_TIME_INTEGRITY_AUDIT.md`.

## P1-14B.2 prospective operational stability gate — RESULT: PARTIAL (2026-10-09)

Preflight PASS (0 processes, port free, registry COMPLETED, SQLite ok, disk
163.6 GB, baseline identical: v9 / 7 setups / 28 COMPLETE). Clock audit PASS
(+517 ms worst case vs 60 s tolerance; 3/3 syncs ok; deliberate no-resync).
35-min observation via canonical plane (`control start --duration 2100`,
PID 32532, UTF-8 log `logs/probe-runs/probe-20261009T015411Z.log`) ABORTED
by controlled stop at 23.4 min (1401.7 s, exit 0, `stopped-by-agent`) when
the cumulative reject rate crossed 5.15 % (episode marginal rate ~100 % since
rt≈983, 3 market reconnects, markPrice stale, throughput collapse ~7×).
Per §6 the <30 min window is INSUFFICIENT — duration objective not met.

- Pristine first 15.8 min (0 rejects/reconnects); HOT promotions (JCT/OGN/RLC)
  grew streams 11→20 honestly; prospective layer error-free throughout
  (rehydration + per-cycle observe live: 17 new setups incl. first
  EXHAUSTION_WATCH/MOMENTUM_CONTINUATION, 40 new outcomes).
- Post-run read-only audit: 24 unique setups, 68/68 COMPLETE, 0 dupes
  (restart idempotency holds live), no-lookahead + math PASS, 68/68 matured
  cells covered (52 unmatured absent honestly), max lateness 6732.6 s
  recorded not backdated. DB file +0.0 MB; disk 163.5 GB. CPU/mem per-process
  not captured (stated, not inferred).
- Tests 609/609 OK (no new tests — no confirmed defect; episode is
  environmental). Gates: CLOCK/PERSISTENCE/PROSPECTIVE/RESOURCE/SAFETY PASS
  (resource with capture note); TRANSPORT PARTIAL (limiting gate).
- No 4–6 h run authorized. V2/main untouched. Full report:
  `docs/P1_14B_2_OPERATIONAL_STABILITY_REPORT.md`.

## P1-14B.3 transport freshness & prospective outcome validity — RESULT: PARTIAL (2026-10-09)

P1-14B.2's episode root-caused from per-summary corrected-lag series
(bookTicker p95 0.4 s → 375 s; processing sub-ms frozen; rate collapse without
drain spike; syncs stable; worst stall on zero-reconnect `public`): host-external
delivery stall, then path outage. Local backlog, clock skew, and HOT logic discarded
with evidence; provider-vs-ISP left unseparated (no vantage point).
Open-but-stale never triggers error retries (gap), and `last_seen` updates on receipt,
so flowing-stale traffic looked healthy — receipt ≠ acceptance.

- 68 historical outcomes classified read-only (rows preserved): 19 VALID_FRESH,
  28 VALID_BUT_DELAYED (honest-late), 21 INSUFFICIENT_FRESHNESS_EVIDENCE
  (degraded-window, math/lookahead still verified), 0 STALE_OR_INVALID.
  Detection-time marks were fresh everywhere (1–17 s); only observation-time age
  was unknowable in v9 columns.
- Fixes (minimal, no new motor states): stale-mark gate (age >120 s known →
  PENDING with explicit reason; unknown fail-open) with `sample_age_ms`
  pass-through; freshness watchdog (accepted-traffic accounting per stream,
  pure stream→connection mapping, 90 s / 300 s budgets, 120 s grace + cooldown,
  one-shot consume → existing retry path); additive summary `freshness` block.
- Tests: 629/629 OK (609 + 20 new `test_p14b_3_transport_freshness.py`).
- Controlled validation (single authorized ≤35 min run, PID 34040, UTF-8 log
  `logs/probe-runs/probe-20261009T100545Z.log`): 10-min pre-window committed
  (6 min pristine); watchdog fired market+public → both reconnected in ~12 s →
  5 min zero rejects (recovery PROVEN live); second episode + path outage
  (handshake timeouts, 10 error-reconnects) → controlled stop at 17.1 min
  (exit 0). Window <30 min = INSUFFICIENT. Post-run: 24 setups, 99 outcomes
  (68+31) all COMPLETE, 0 dupes; 21 missing cells fully explained (OGN/RLC
  15m/1h/4h: never simultaneously matured+observed+marked — unsubscribed +
  CORE-only restore, no defect). No PENDING fired live (marks absent-not-stale).
- Gates: CLOCK/PROSPECTIVE/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL.
  No 4–6 h run authorized; P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_3_TRANSPORT_FRESHNESS_AUDIT.md`.

## P1-14B.4 prospective freshness & PENDING lifecycle integrity — RESULT: PASS (2026-10-09)

UNKNOWN-freshness audit: via the probe, mark present implies age present/finite/>=0
(`returns.feature` atomicity) — UNKNOWN arose only from direct callers; `nan`
slips comparisons and negative age signals clock pathology (both closed).
Precedent: classifier/opportunity engines already gate at 300 s; detections
always had fresh marks (1–17 s). Policy: strict classification
(ok/unknown/nonfinite/future; sub-ms negatives clamped, documented).

- PENDING lifecycle decision (documented vs alternatives): grace-deferred, then
  terminal. Failed evaluations retry silently while `now − first ≤ horizon_ms`
  (recovery window = one horizon past maturity = pre-existing det+2H audit bound,
  now enforced); then terminal PENDING with explicit reason. INSUFFICIENT stays
  immediate+terminal. Upgrade-to-COMPLETE rejected (schema cannot express it without
  backdating or dupe rows). No schema change (v9), no new states, no rewrites;
  restart restarts grace (bounded, documented).
- Outcome Contract v1.1 (`PROSPECTIVE_CONTRACT_VERSION`): decision table + additive
  telemetry (`completed/pending/insufficient/in_grace`, dashboard-compatible).
- Tests: 683/683 OK (648 + 19 new `test_p14b_4_lifecycle.py` + 16 net from converting
  `test_prospective.py`'s 35 pytest-style functions — AUDIT FINDING: unittest discovery
  silently ran 0 of them; now all execute). Legacy suites updated intent-preserving
  to v1.1 (fresh ages; grace patterns; strict-unknown rename). Market/opportunity
  rules untouched.
- Validation: 120 s controlled run COMPLETED naturally (11/11, 0/0, reg=24 from
  summary 1, 0 writes/errors, DB byte-identical 24/99, new telemetry live). No
  stale-mark occasion live (marks fresh-or-absent; Fix A unit-proven). No 35-min,
  4–6-h, or paper runs. All 99 historical rows preserved byte-identical.
- Gates: prospective/persistence/safety PASS (no transport re-rating — no long run).
  Verdict PASS. P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_4_PROSPECTIVE_LIFECYCLE_AUDIT.md`.

## P1-14B.5 transport resilience & independent network diagnostics — RESULT: PASS (operational, 2026-10-10)

Attribution resolved as far as evidence allows: with identical code/config/host, NO episode
reproduced — persistent host or bot defects DISCARDED; episodes are intermittent path/provider
instability (which of the two still UNKNOWN — stated, not forced).

- Independent probe (`netprobe.py`, stdlib + existing websockets dep): single reference connection
  (host-pinned, private streams refused, params mirrored, read-only), bookTicker + markPrice-array
  streams, per-message E/lag/reorder/gap tracking, DNS/handshake/error classes, UTF-8 JSONL, bounded
  duration. 17 deterministic tests (faked transports/clocks). Limitation (honest): the bare
  `/stream` path served zero markPrice-array messages in 40 min while bookTicker flowed — tool-side
  path limitation, not a health signal; reference coverage is bookTicker-only for now.
- Coincident 35+40 min windows AGREE: bot bookTicker p50 ~175 ms / p95 ~390 ms vs reference p50
  ~340 ms / p95 ~370 ms (same sub-second regime); bot markPrice healthy (p50 ~243 ms); rejects 0;
  reconnects 0/0; E-reorders 0; reference attempts 1, errors {}. DNS 8.3 ms.
- Health classifier (pure, shared): raw socket vs FLOWING_FRESH/FLOWING_STALE/SILENT/RECONNECTING/
  UNAVAILABLE + evidence, missing-is-None; summary `connectionHealth` additive; netprobe reuses it.
  8 tests. Watchdog 10/10 re-verified (code + live log: cooldowns 292 s apart, recoveries, no loops).
- Layered diagnosis: host (w32tm self-syncing, +322 ms, no resync; CPU/NIC per-process still
  uncaptured — stated gap), transport (handshake timeouts = post-TCP path slowness, non-DNS),
  engine (sub-ms, queues empty), data (all feeds fresh).
- Controlled validation: preflight PASS + 10-min diagnostic gate → single ≤35 min run (PID 32940)
  COMPLETED naturally: 2102.5 s, 20/20, 0 reconnects, 0 rejects, exit 0 — **≥30-min healthy window
  DEMONSTRATED** (P1-14B.1 blocker #1 satisfied as far as one window can). Post-run: 49 setups
  (+25), 150 outcomes (+51) all COMPLETE, 0 dupes, 0 anomalies; contract v1.1 + v9 intact.
- Tests 708/708 OK (683 + 17 + 8). Gates: TRANSPORT/FRESHNESS/PERSISTENCE/SAFETY PASS.
  Verdict PASS (operational). Still NO 4–6 h authorization (recurrence risk — repeat advisable);
  P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_5_TRANSPORT_RESILIENCE_REPORT.md`.

## P1-14B.6 reproducibility & operational readiness — RESULT: PARTIAL (2026-10-10)

Second window reproduced BOTH regimes: ~22.6 min pristine, then delivery episode (rejects → 8.83%,
error reconnects 1+3, watchdog fired 3 cycles, handshake timeouts). Abort rule breached UNACTED —
live supervision lost to a harness timeout at launch (demerit recorded; no safety rule breached).

- netprobe markPrice placement verified 2×2 live (arrays ONLY on `/market/stream`; per-symbol on
  `/stream`+`/public/stream — mirrors the bot's own routing): `--base-path` allowlist + placement
  warning + two-instance operational reference. Official docs unfetchable (recorded); vendor
  incident reports TODAY corroborate provider-side instability (Sierra Chart feed stops;
  connector ACK-but-no-data issue) — kept as context, not proof.
- Fixes: netprobe heartbeat summaries (total silence now observable) + host telemetry
  (`os.times` CPU%, psapi RSS with real-handle fix, per-stream exact bytes, UNKNOWN-safe) in
  bot summary `host` block + netprobe records; shared health classifier + `connectionHealth`.
- Discriminating evidence: bot CPU flat 3–6% + 30.5 s summary cadence through the episode
  (local compute/loop-blockage DISCARDED); references on the same host stayed healthy
  (bookTicker p95 ≤581 ms bump coinciding with bot collapse = shared wobble, ~100× milder);
  per-connection selective degradation → server-side edge attribution refined (reconnect
  recovery works until handshake-refusal stage). Provider-vs-ISP residual UNKNOWN (stated).
- Tests 726/726 OK (708 + 4 path + 1 warning + 1 flag-off + 12 host + heartbeat). Post-run:
  57 setups (+8), 202 outcomes (+52) all COMPLETE, 0 dupes, 0 anomalies; v1.1 + v9 intact.
- Gates: CLOCK/PERSISTENCE/SAFETY PASS; TRANSPORT/FRESHNESS PARTIAL. Verdict PARTIAL
  (duration + abort-supervision failed; fixes validated). Still NO 4–6 h authorization
  (repeat advisable); P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_6_REPRODUCIBILITY_READINESS_REPORT.md`.

## P1-14B.7 persistent supervision & enforced abort gates — RESULT: PASS (2026-10-10)

P1-14B.6's abort breach happened because evaluation lived in the agent session. Fix by
architecture: `control supervise` — a detached, registry-leased watcher evaluating documented
abort rules every cycle from probe evidence, enforcing one-shot verified-PID stops with persisted
reasons. Never starts/restarts runs, never touches foreign PIDs, never acts on UNKNOWN.

- Rules (exact, LOCAL_POLICY except cumulative 5% rejects): safety immediate; rejects >5%;
  >5 reconnects/10 min sliding; persistence ≥2 events/10 min ×2 checks (or recorder DEGRADED);
  clock >30 s ×3; DB unreadable ×6; watchdog-overwhelm compound (forced≥3 + errors≥3 + rising).
  Freshness-absence reduces to these (documented). Streaks persist in the lease (restart-safe).
- Lease serializes supervisors (live→refuse, stale/corrupt→recorded takeover); failure budget
  (5×) marks FAILED and exits without touching the probe; terminal ABORTED + reason/threshold/
  observed persisted; second cycle no-op; launchers preserved.
- Identity: PID + image + creation-time; wmic absent on this host class (verified) → ctypes
  GetProcessTimes fallback restores full identity (proven live with ISO stamps).
- Validation: 34 supervisor tests (decision matrix, lease/races, stale/reuse no-touch, terminal
  no-ops, V2 contract keys, no-start assertion, store isolation) + REAL-PID integration (breach
  evidence → sleeper killed, foreign sleeper alive, ABORTED persisted, no re-fire). Suite 760/760.
  Brief live run (150 s probe + 12-cycle supervisor): claimed, heartbeated, clean exit, zero false
  aborts; probe 11/11, 0/0, reg=57, DB identical. Found+fixed: self-registration wiped evidence
  paths (same-PID preservation now).
- V2 contract additive (`supervisor` block in control status → API; mapping table; UI renders via
  existing opaque strings). No frontend changes. All 202 rows / 57 setups preserved byte-identical.
- Gates: prospective/persistence/safety PASS (mechanism + validation, no long run). Verdict PASS.
  Still NO 4–6 h authorization; P1-14C not started; V2/main untouched. Full report:
  `docs/P1_14B_7_PERSISTENT_SUPERVISION_AUDIT.md`.

## P1-14B.8 supervised maiden voyage & abort enforcement — RESULT: PASS (2026-10-10)

Agent-independence demonstrated in execution, not assertion. Probe PID 33292 ran 2102.147 s
per final_summary (13:12:44 → 13:47:55Z, exit 0) while supervisor PID 25800 ran 70 cycles 13:13:35 → 13:48:24Z
and exited cleanly — zero agent contact after launch. Post-hoc log audit (68 summary + one
final_summary): 0.00% rejects,
0 reconnects, 20/20 streams, reg 57→66 (+9 setups), 35 writes, 0 errors — nothing breached,
correctly nothing aborted. The long window ran supervisor-only: a concurrently launched sentinel died silently in ~30 s (no cycles,
no output); root-cause class: silent early death under buffering (observability gap, not a
proven cause — `-u`/flush improve diagnostics, they do not fix process lifetime) — encoded fixes: flushed
startup prints in both mains, `-u` in detached launches, lease-presence launch verification.

- Sentinel layer completed: claim/takeover/no-op semantics, stale/FAILED-lease abort via
  canonical `enforce_abort`, own failure budget, additive status block + CLI, no-start guarantee.
- Brief three-layer validation (150 s probe + 14-cycle supervisor + 12-cycle sentinel, verified
  leases; brief-run preflight was 66/228): claimed, heartbeated to natural COMPLETED, zero false
  aborts, zero orphans; probe
  11/11, 0/0/0, reg=66, DB byte-identical (66/228/0 dupes, unchanged by the brief run).
- Tests 775/775 OK (760 + 15 sentinel). Post-run: 66 setups (+9), 228 outcomes (+26) all COMPLETE,
  0 dupes, 0 anomalies; v1.1 + v9 intact; 202 prior rows preserved.
- Gates: CLOCK/TRANSPORT/FRESHNESS/SUPERVISION/PERSISTENCE/SAFETY PASS. Verdict PASS.
  Still NO 4–6 h authorization (recurrence risk); P1-14C not started; V2/main untouched.
  Full report: `docs/P1_14B_8_SUPERVISED_RUN_REPORT.md`.

## P1-14B.8 follow-up — enforce fencing (bounded correction, 2026-10-11)

Frontend review `d80fb9b:docs/DASHBOARD_V2_50_CORRECTIONS_REVIEW.md` (backend
`8648366`) left HIGH findings: `enforce_abort` terminated before fencing,
terminal marks ignored run replacement, `aborted_by` hardcoded, heartbeat
regression no-op'd. Fixed deterministically, no market runs launched:

- `enforce_abort`: STOPPING via locked `update_registry`; pre-terminate gate
  re-verifies eligible state, run PID+ctime, canonical liveness, owner lease
  and foreign STOPPING marker (`already-stopping` refusal). Failed/refused
  marker never reaches termination. ABORTED/FAILED marks recheck run
  identity, own marker and lease; `aborted_by` persists the real owner
  (`supervisor`/`sentinel`/`direct`). `sentinel_once` heartbeat is now
  locked+fenced (replaced sentinel no-ops; no clobber of supervisor block).
  Cleanup: single JSON parse in `update_registry`; unreachable abort-field
  block removed.
- Regressions `tests/test_enforce_abort_fencing.py` (13): foreign owner never
  terminates (x2); COMPLETED+takeover between read and STOPPING preserved
  (x2); STOPPING write failure never terminates (x2); PID/ctime + foreign
  marker fenced on ABORT and timeout paths (x4); real owner persisted (x2);
  foreign STOPPING acquisition refused. On `8648366` 8/13 fail (termination
  invoked, COMPLETED overwritten, `sentinel` mis-marked as `supervisor`);
  on corrected code 13/13 pass.
- Heartbeat `test_concurrent_heartbeats_keep_both_fields` now uses owned
  leases (`os.getpid()`): 4 threads x25 locked heartbeats advance both
  `last_check_at`, retain distinctive `11`/`22` + streaks/action, preserve
  the run, exit cleanly with zero hidden errors. Old fixture (PIDs
  424244/424245) left a byte-equivalent record. Added
  `test_racing_sentinel_claims_single_winner`: exactly one winner (supervisor
  race already covered).
- Suite: `python run_tests.py` → 808/808 OK (794 + 13 fencing + 1 sentinel
  race). No probes, P1-14C, long runs or paper trading started. DB/logs
  preserved. V2 transactional supervised start stays PENDING and separate.
  SUCCESS_GATES not advanced.
- Window scope: historical >=30-min healthy windows (P1-14B.5 2102.5 s;
  P1-14B.8 2102.147 s supervisor-only + brief three-layer run) are historical
  evidence only. No new supervised window was run on this corrected SHA (per
  task bounds); corrected-code longevity remains UNDEMONSTRATED.

## P1-14B.8 V2-51 fencing (bounded correction, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `35401f9:docs/DASHBOARD_V2_51_FENCING_REVIEW.md` (backend
`0786617`) left HIGH findings with mocked reproductions
(`scripts/review-p1-14b8-final-fencing.py`,
`design/qa/v2-51/backend-reproductions.json`): post-claim takeover still
reached termination, owned lease need not cover the run, `status()` overwrote
terminals, no `status_readonly()`, thread-only concurrency. Fixed
deterministically, no market runs launched:

- Operation boundary through termination: STOPPING acquisition AND a final
  locked verify-and-kill (same lock held across re-verification and the
  kill, via `update_registry` transform). Post-claim owner/run/marker changes
  refuse with `takeover-after-claim`/`run-replaced`/`replaced-owner` and leave
  the mocked termination uncalled. `_terminate_verified_pid(pid, ctime)` now
  verifies on the real OS handle (Windows: one handle reads GetProcessTimes
  and terminates; POSIX: `pid_is_ours` immediately before `os.kill`) and
  returns False on identity failure. `stop_probe` carries the same
  verify-while-locked discipline with its own `stop:` marker.
- Lease-vs-run: `_owner_lease_valid` (ACTIVE + owned + `watched_pid` == run
  PID + ctime when determinable on both sides) replaces pid-only checks at
  acquisition, pre-kill and terminal marking, for supervisor and sentinel.
  Wrong-run (`wrong-run-lease`), foreign (`replaced-owner`), inactive
  (`owner-lease-invalid`) leases never terminate. Heartbeats keep pid-only
  `_owns_lease` (non-replacement proof) by design.
- `control.status_readonly()`: pure projection shared with `status()` via
  `_status_view` (identical shape/nullability). No writes, no reconciliation,
  no log-handle mutation, no process action. Missing → STOPPED shape without
  creating a file; dead/reused PID, STOPPING and ABORTED preserved
  byte-for-byte. Mutating reconciliation is separated into fenced
  `_reconcile_stale_record` (locked; never touches terminal states nor a
  held enforcement STOPPING) and `dashboard.probe_status()` (browser-polled
  GET path) now reads purely. `try_register`/`start_probe`/`_mark_terminal`
  moved to locked fenced commits (refuse live runs and held STOPPING
  markers; never overwrite terminals).
- Concurrency between processes: `tests/test_process_concurrency.py` (3)
  with spawned owners (distinct PIDs, barrier rendezvous so winners stay
  alive during the race): supervisor+sentinel claim then 10 counted
  heartbeats each (bool returns; every call wrote, both final timestamps
  fall inside the overlapped window, 11/22 + streaks/action survive);
  4-process supervisor and sentinel claim
  races elect exactly one winner; all workers exit 0 with zero hidden
  errors. Without the rendezvous, late starters legitimately take over
  exited winners' leases (documented takeover, not a lock failure).
- Fail-before: 15 new boundary/readonly tests fail on `0786617`
  (termination reached, `status_readonly` missing, ABORTED overwritten with
  FAILED); corrected code passes all. Heartbeat counting fails before the
  bool-return change (returns None). Prior 808 green preserved.
- Suite: `python run_tests.py` → 826/826 OK (808 + 8 boundary + 7 readonly
  + 3 multiprocess). No probes, P1-14C, long runs, paper trading or Start
  enablement. SQLite/logs/evidence preserved. V2/main untouched.
  SUCCESS_GATES not advanced. Transactional supervised start stays PENDING
  and separate.
- Guarantee: with the lock held across final verification and the
  handle-bound kill, a registry takeover cannot interleave at the boundary
  and a reused PID cannot be hit (Windows: same-handle check+kill).
  Residuals (explicit): POSIX has no handle API (microsecond recheck
  window); ctime comparison skipped when indeterminable either side;
  `_owns_lease` stays pid-only for heartbeats; `status()` CLI/`stop_probe`
  stale paths still mutate by design (fenced). No complete-protection claim
  beyond the audited writers.
- Window scope: no new supervised window on this corrected SHA (per bounds);
  historical windows stay historical; corrected-code longevity UNDEMONSTRATED.

## P1-14B.8 V2-52 integration (bounded correction, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `066577e:docs/DASHBOARD_V2_52_INTEGRATION_REVIEW.md` (backend
`55efaa2`) with mocked reproductions (`scripts/review-p1-14b8-v2-52.py`,
`design/qa/v2-52/backend-reproductions.json`). H1+H2 fixed with
failing-first hermetic regressions; `status_readonly()` and contracts kept:

- H1 native Windows termination: `TerminateProcess`/`CloseHandle` now carry
  explicit HANDLE-width (`c_void_p`) argtypes/restype with BOOL checked; a
  `0`/exception returns False with a bounded GetLastError record
  (`_LAST_NATIVE_ERROR`, code + timestamp, single overwritten entry) --
  never reported as success. Handle closed on success, refusal and
  exception paths alike; creation verification and termination stay on the
  same handle inside the registry lock. Missing ctime falls back to
  handle-liveness only (open + queryable times terminate; unqueryable
  refuses) -- PID-reuse NOT excluded there, documented residual.
  Precision: the finding never proved a live process falsely marked
  ABORTED (callers verify disappearance + 10s wait); the demonstrated fault
  was accepting native refusal as success. Tests
  `tests/test_native_terminate.py` (9: matching/mismatched ctime,
  GetProcessTimes refusal, TerminateProcess=0, exception, open failure,
  >32-bit handle intact `0x100000123`, missing-ctime fallback, 2 POSIX).
  Fail-before on `55efaa2`: signatures unconfigured, `0` returned True.
- H2 parent/child start race: `_commit_start` recognizes the own
  just-spawned child by PID + creation-time (captured once) and adopts its
  RUNNING/STARTING record verbatim -- no kill, no STARTING overwrite,
  evidence preserved (byte-preserving: adoption writes nothing). Held
  enforcement markers are never adopted. Genuinely foreign runs and reused
  PIDs (same PID, different ctime) are still refused with exactly one
  orphan-cleanup kill; write failures kill once. Tests
  `tests/test_start_race.py` (5: parent-first, child-first, foreign-winner
  via preflight→commit injection, reused-PID, write failure; response +
  final record + kill count asserted). Fail-before: child-first killed its
  own child and returned started=False. Not extended to the V2 supervised
  transactional launch (separate).
- C1 concurrency precision (corrected V2-54): M1 heartbeat workers
  rendezvous on a shared start barrier with ten effective writes per owner
  and both final timestamps inside the window [t0, t1] (2s tolerance for
  ISO-second truncation). This does NOT prove strict advancement versus the
  claim timestamps, forced per-write interleaving, or longevity.
- Suite: `python run_tests.py` → 840/840 OK (826 + 9 native + 5 start-race;
  M1 strengthened in place). No probes, P1-14C, long runs, paper, trading
  or Start enablement. SQLite/logs/evidence preserved. V2/main and
  SUCCESS_GATES intact. `status_readonly()` kept in all GET paths.
  Transactional supervised start stays separate.
- Residuals (explicit): POSIX pre-kill recheck window (no handle API);
  ctime-None fallback excludes PID-reuse proof; `_owns_lease` pid-only kept
  for heartbeats; `status()` CLI/`stop_probe` stale paths mutate by design
  (fenced). No general PASS, no demonstrated longevity, no authorization
  for new runs.

## P1-14B.8 V2-54 corrections (bounded, 2026-10-11) — RESULT: DONE (acotado)

Frontend review `d4d82c9:docs/DASHBOARD_V2_54_BACKEND_CORRECTIONS_REVIEW.md`
(backend `b801ab0`) with mocked reproductions
(`scripts/review-p1-14b8-v2-54.py`,
`design/qa/v2-54/backend-reproductions.json`). R1+R2 fixed with
failing-first hermetic regressions; `status_readonly()` and contracts kept:

- R1 exact Win32 BOOL: native signatures now use 32-bit
  `ctypes.wintypes.BOOL` (`c_long`; `c_bool` is 1 byte and misreads native
  returns such as 256 as falsy) for TerminateProcess/CloseHandle/
  GetProcessTimes results, the OpenProcess inherit flag, and HANDLE-width
  (`c_void_p`) arguments -- bound once in `_configure_kernel_signatures`
  (no silent setup), verified on the same handle inside the registry lock.
  Refusal/exception propagation, bounded `_LAST_NATIVE_ERROR` and guaranteed
  close preserved. Tests `tests/test_win32_bool.py` (7: 32-bit width +
  exact type identity, ABI 0/1/256 through real WINFUNCTYPE callbacks --
  256 truthy under BOOL and falsy under `c_bool` -- plus end-to-end helper
  acceptance of a 256 native success). Fail-before on `b801ab0`: width 1,
  no exact-type helper, 256 returned False. No real termination failure or
  false ABORTED is claimed (out of scope by review precision).
- R2 child-first log association: adoption with absent evidence now performs
  a conditional locked handoff binding the parent-created log to the same
  PID+ctime run (revalidating state, no enforcement hold, no valid log
  present). Valid pre-existing evidence is preserved verbatim (no write);
  foreign/terminal/enforcement races refuse without touching; handoff
  OSError keeps the verified live child running with the association
  explicitly unconfirmed (`evidence_associated: False` -- never declared
  confirmed when not established); no log is invented for direct launches
  (handoff only binds the log this start created). Tests rewritten onto the
  REAL `try_register()` child-first flow (evidence None) plus existing
  evidence, interleaved STOPPING, and handoff write failure; parent-first,
  foreign, reused-PID and commit-failure cases kept with response + record +
  kill-count assertions. Fail-before: association stayed None.
- C1 precision corrected in test wording and here: M1 is a shared start
  barrier with ten effective writes per owner and final timestamps inside
  [t0, t1] -- NOT strict advancement versus claim timestamps, NOT forced
  per-write interleaving, NOT longevity. Earlier "advance" phrasing above
  is superseded by this scope.
- Suite: `python run_tests.py` → 850/850 OK (840 + 7 win32-bool + 3
  start-race delta: 8 cases = 4 kept + 4 handoff/real-registration cases
  replacing 1 artificial). No probes, backfills, P1-14C, long windows,
  paper, trading or Start. SQLite/logs/evidence preserved. V2/main/
  SUCCESS_GATES intact. Supervised transactional start stays separate.
- Residuals (explicit): POSIX recheck window; ctime-None fallback;
  pid-only heartbeat ownership; mutating CLI/stop paths by design (fenced);
  pure status certifies no OS liveness. No general PASS, no longevity, no
  authorization for new runs.

## Supervised transactional launch — preparation DISABLED (2026-10-11) — RESULT: DONE (acotado)

Contract first: `docs/SUPERVISED_LAUNCH_CONTRACT.md` (preconditions +
capacity, per-process identity/association, sequence, watcher confirmation
criteria, finite budget, partial failure/cancellation/rollback, confirmed/
rejected/uncertain outcomes, backend/BFF responsibilities + field compat).
R1/R2 accepted as closed; not reopened.

- Implementation: `control.launch_supervised_transaction` (public, refuses
  with `supervised-launch-disabled` and zero side effects) +
  `_launch_supervised_impl` (tested engine reusing `start_probe`, leases,
  identity, verified termination, registry lock; pure-read verification,
  kill-only rollback). No HTTP route, CLI subcommand, Start enablement or
  contract change ships with this preparation.
- Confirmation rule: Popen/ACTIVE lease/heartbeat alone never confirms.
  Both watchers must verify ACTIVE + owned PID/ctime + watched==run +
  alive + parseable fresh non-future heartbeat on ONE fresh read inside the
  budget. Confirmation is point-in-time, never future protection.
- Rollback: reverse order, spawn-captured identity only, verified kills;
  already-dead counts as cleaned; foreign/terminal records never written
  or killed. Unverifiable cleanup → UNCERTAIN with pending evidence (never
  declared completed).
- Failure matrix (`tests/test_supervised_launch.py`, 23): full path;
  foreign pre-seed / probe / supervisor / sentinel spawn-register failures;
  absent / stale / future / malformed / wrong-run leases; dead watcher;
  reused watcher PID; timeout; unreadable verification; takeover/STOPPING
  and terminal interleaves (records preserved); refused/stuck kills
  (uncertain); concurrent launches elect one confirmation (single
  parent-held Popen patch -- per-thread global patches leak process-wide);
  repeated launch rejected; verification+rollback issue zero registry
  writes under strict no-write mocks. Fail-before: 23/23 missing API.
- Suite: `python run_tests.py` → 873/873 OK (850 + 23). No real probes,
  market traffic, P1-14C, long runs, paper, orders or Start. SQLite/logs/
  evidence preserved. V2/main/SUCCESS_GATES intact. `status_readonly()` in
  GETs. No phase advanced.
- Residuals (explicit): default Popen spawners dormant (untested against
  live OS); POSIX/no-handle and ctime-None limits inherited; heartbeat
  ownership pid-only; CLI/stop mutations by design (fenced); pure status
  proves no liveness. No general PASS, no longevity, no operational
  authorization.

## DASH-V2-64 backend reconciliation + read contracts (2026-10-11) — RESULT: DONE (acotado)

Frontend checkpoints read from Git only (`dash-v2-03-token-detail`
`8780da2`: cutover audit, backend handoff, V2-63 data contract). No V2,
main, SQLite, log, or evidence mutation; no collector/formula duplication.

- Preflight/reconciliation: branch `phase1/market-intelligence-dashboard`,
  local `da231b9` vs remote `c635938` (owner fix "fence disabled launch
  ownership and uncertainty", +29 tests). Worktree clean (tracked),
  zero Python processes, COMPLETED terminal registry, unheld sidecar lock,
  stale dashboard pidfile only → fast-forward `da231b9..c635938` executed
  with no reset/clean/kill. No conflict or active-process blocker existed.
- Deployed identity (verified post-FF): V2 `runtime-control.ts` spawns
  Python with cwd+PYTHONPATH = this workspace (`/src`) calling
  `control.status_readonly()` (fallback READ_ONLY_STATUS_REQUIRED), and
  reads canonical `data/microprobe.db` via DatabaseSync readOnly. V2
  imports NOTHING else from backend Python. Deployed source == accepted
  `c635938`; the audit's da231b9-vs-remote split is closed on this
  checkout (V2 re-verifies the exact SHA before consuming).
- Inventory: `docs/DASHBOARD_V1_READ_CONTRACTS.md` — all legacy GET pages
  + 25 JSON APIs (fields, units, nullability, response-time `generated_at`,
  empty→404 semantics), universe/search (persisted-only universe, exact/
  prefix/substring order, limit 25; `normalize_symbol` accepts unicode
  alnum — STRICTER-than-Python V2 parser is a V2-side boundary for
  DASH-V2-65), historical coverage + event studies (separate historical
  DB, fixed columns, limits 20/50), price ranges 5m–24h anchored at
  REQUEST time (vs V2-63 LAST_RETAINED_SAMPLE ≤600 buckets + >60s gap
  segments — never silently substituted) + CSV/JSON export metadata.
- Diagnostics: `status_readonly()` purity re-pinned by new
  `tests/test_dashboard_get_purity.py` (G1–G3: stale RUNNING never
  reconciled, absent never created, process/feed reported separately,
  zero writes/handles/actions; mutation check restoring legacy `status()`
  fails G1/G3). Recency never proves identity/liveness/protection;
  unverified reads UNKNOWN. Future authorized runs must produce the
  evidence list in §5 of the inventory doc — no standing authorization.
- Retirement: reversible old-UI plan PROPOSED, NOT executed. Audit-found
  blocker: `control.py` lazily imports shared helpers FROM `dashboard.py`
  (`repo_root`, `process_info`, `pid_is_ours`, `no_window_flags`), so
  file-level retirement is blocked pending helper extraction (proposed
  prerequisite). Operational stop alone is fully reversible today.
- Code added: only the pinning test file (no source change; V2-63 already
  covers presentation, old APIs already serve history/exports).
- Suite: `python run_tests.py` → 905/905 OK (902 + 3 pinning), exit 0. No
  probes, backfills, P1-14C, long runs, paper, orders, Start, or gate
  advancement. Deterministic results only — no longevity claim.

## Helper extraction: control decoupled from the HTTP module (2026-10-11) — RESULT: DONE (acotado)

Per DASH-V2-67 handoff (`dash-v2-03-token-detail` `8712dfb`, read from Git
only): `repo_root / process_info / pid_is_ours / no_window_flags` (+
`_creation_time_ctypes`) moved VERBATIM to new
`src/microstructure_probe/host_process.py` (stdlib only, verified
byte-identical bodies); `dashboard.py` re-exports the same objects (no
duplication; old helpers, importers, and dashboard-namespace tests keep
working); `control.py` binds them at top level with all 16 lazy
`from .dashboard import` removed (one mis-indented `def _probe_env`
repaired to module level). Controller-behavior patch targets moved
`dashboard.pid_is_ours` → `control.pid_is_ours` (24 sites) and
`dashboard.process_info` → `host_process.process_info` (7 sites) after a
full import/caller/cycle/patch-target audit (only control.py imported the
helpers from dashboard; views only use DASHBOARD_VERSION). New
`tests/test_host_process_boundary.py` (H1 source scan, H2 subprocess
isolation with the dashboard import blocked, H3 object-identity compat, H4
parity) — failing-first (collection ImportError + missing API on base).
V2-64 doc corrections applied alongside: manual (not automatic) SHA
verification, current price schema 3 (5 historical ranges, 10k raw / 1200
display), REQUEST-vs-retained + ASCII-vs-Unicode kept explicit,
prospective (microprobe.db) vs historical.db split explicit, purity-scope
limit (`_ensure` writable paths) explicit. Suite 909/909 OK (905 + 4
boundary), exit 0. No probes, backfills, traffic, P1-14C, long runs,
paper, orders, Start, main merge, SUCCESS_GATES, formula, or accepted-fix
changes. No old-UI/server/file retirement executed (file-level removal
still waits on this extraction's review). SQLite/registry/logs preserved.

## DASH-V2-71B System data contracts (2026-10-11) — RESULT: DONE (acotado)

V2 checkpoints read from Git only (`dash-v2-03-token-detail` `f52b68f`:
acceptance, recorded diagnostics, migration plan). No V2/main/SQLite/log/
evidence mutation; no second collector or database; no probes or traffic.

- Preflight/reconciliation: local == origin == `9f3e084` on entry (already
  synced, clean worktree, foreign files preserved); no reset/clean/force.
- Matrix: `docs/DASHBOARD_V2_71_SYSTEM_DATA_CONTRACTS.md` — per-field
  reader/table/column, meaning+unit, observation-vs-read timestamps,
  nullability/absence, scope/limits, historical-vs-current, and side
  effects for persistence, universe/budget, research, classifier/
  opportunities, runtime/watchers/feed; safe-reader allowlist with purity
  notes; NOT_AVAILABLE host resources (no column on schema v9, verified on
  the live DB read-only; log-only `host` block is not a reader contract)
  and ops audit log (latest `last_exit` + capped lifecycle tables only);
  V1 diffs (price anchor, search limits/parser, prospective vs historical
  DBs); real record examples; frontend MUST-respect decisions; concrete
  retirement blockers.
- Validation: `tests/test_read_purity.py` (full read battery leaves
  operational/historical DBs, registry, and evidence byte-identical, no
  new `.db` files, content queries agree; temp fixtures only). No defect
  found in these read paths on existing stores → no source change (fresh-DB
  `init_db`/`_ensure`/WAL paths documented as NOT safe for V2 instead).
- Suite: `python run_tests.py` → 910/910 OK (902 + 3 GET-purity + 4
  boundary + 1 read-purity), exit 0. No probes, backfills, P1-14C, long
  runs, paper, orders, Start, main merge, SUCCESS_GATES, formula, or
  accepted-fix changes. Deterministic only. (One early full run reported
  905 on the same tree; four subsequent consistent measurements — three
  discovery counts plus per-file sum plus a full OK execution — establish
  910; the single 905 reading is unreproduced and superseded.)
