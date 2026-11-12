# Dashboard V2 Progress

**Purpose:** factual slice ledger for Dashboard V2.  
**Status:** DASH-V2-01 COMPLETE 2026-10-07 (professional Overview composition; fixtures only, no API integration).  
**Rule:** update after every slice; never describe planned code as implemented.

## DASH-V2-ARCH — 2026-10-07

- Starting SHA: `6270be29a5444e56d4fac9e51f04d5882bc5554b`.
- Workspace/branch gate: PASS.
- Pre-existing untracked content: `.firecrawl/`, preserved and excluded.
- Audit: current Python SSR/API/control/history/research contracts verified.
- External research: official CMC, CoinGecko, Next.js/Vite and TradingView
  documentation reviewed; two CMC keyless routes live-probed HTTP 200 and an
  immediate third received 429, proving keyless access and the need for a
  conservative unknown-rate budget.
- Decisions: Python preserved; Next.js+BFF recommended; Binance canonical;
  stable-ID mapping; CMC-first optional context; CoinGecko fallback.
- Application code: unchanged.
- Runtime: unchanged; no dashboard/probe restart and no soak.
- Dependency installation/scaffold: none.
- Verification/ending SHA/commit/remote: fill at checkpoint completion.

## Future slice template

```text
SLICE / DATE
STARTING_SHA / ENDING_SHA
SCOPE / FILES
CONTRACTS CHANGED
TESTS + EXACT RESULT
VISUAL CAPTURES + REFERENCE RESULT
RUNTIME IMPACT
KNOWN GAPS / DECISIONS
COMMIT / REMOTE STATUS
NEXT AUTHORIZED SLICE
```

## DASH-V2-00 — 2026-10-07 (isolated frontend foundation)

- Starting SHA: `8be06aa8824126785bdc10734a97f0e3adff5d63`.
- Scope: `frontend/` only (Next 16.4.0 + React 19.3.0 + TS strict
  `react-jsx`, eslint flat, vitest+jsdom+testing-library). Tokens,
  15 foundation components, 7 static routes + dynamic `/symbol/[symbol]`
  (singular, matching the Python backend; architecture folder plan shows
  plural — resolved in slice decision, see DASHBOARD_V2_DECISIONS.md).
- No API integration: zero fetch/Binance/CMC/127.0.0.1 references in
  `frontend/src`; fixtures labeled DEMO DATA — NOT LIVE; no Start/Stop
  wiring; no chart library.
- Tests: `tsc --noEmit` clean; `eslint src` clean; `vitest run` 10/10;
  `next build` 9 routes prerendered; ephemeral `next start :3000`
  served 7/7 routes HTTP 200 then stopped (no persistent server).
- Visual: /overview + /movers screenshots captured from the ephemeral
  server; NO visual PASS claimed (four reference mockups absent).
- Python suite: 408/408 green (untouched backend, verification only).
- P1-10R: running probe (PID 19084) undisturbed; no DB/registry/config
  contact; `node_modules/` + `.next/` local-only, never committed.
## DASH-V2-01 — 2026-10-07 (professional market overview)

- Starting SHA: `75c34815e8963e25237b93344b3a66e8b2cc107f`.
- Scope: `frontend/` only — TopBar (market context, ENGINE/FEED/RESEARCH
  chips, OBSERVE ONLY example, last-data, compact DEMO pill),
  OverviewMetricGrid (6 provenance-carrying metric cards), MarketPulsePanel
  (breadth bar + accel/vol/activity/concentration, no-signal disclaimer),
  MoversSnapshot (8-column table + /movers link + symbol links),
  ExtremeMoveWatch (descriptive monitor, no predictions/entries/targets),
  ResearchHealthPanel (recorder/feed/persistence states kept distinct),
  MarketContextPanel (BTC/ETH refs + CMC-future note, no endpoints called).
  Nav regrouped with icons; literal `/symbol/[symbol]` menu link removed.
- Data: centralized fixtures with BFF-forward types (MetricPoint/PulseData/
  ExtremeMoveRow/HealthFacts/MarketContextFacts); null stays missing;
  zero external references in `frontend/src` (grep-verified).
- Tests: `tsc` clean; `eslint` clean; `vitest` 15/15 (freshness states,
  null-vs-zero, no-prediction language, snapshot links); `next build`
  9 routes; ephemeral checks + persistent preview on :3000 serve 5/5
  routes 200 (server PID renewed 31648 → 28552, old process
  identity-verified before stop; probe PID 19084 untouched).
- Visual QA: desktop + 390px-mobile overview screenshots, movers
  regression shot, 0 console errors; tables scroll intentionally on
  narrow widths. VISUAL_REFERENCE_COMPARISON: NOT AVAILABLE (four
  reference mockups absent).
- Python suite: 408/408 green (backend untouched, verification only).
- P1-10R: RUNNING throughout (read-only status checks only); no DB,
  registry, config, or evidence contact.
- Pending integration data per panel: versioned overview/pulse/movers/
  research/health/context contracts (DASH-V2-02+); provider legal review;
  reference mockups for future visual PASS.
- Next authorized slice: DASH-V2-02 only on explicit instruction.

## O2-RUN-OBS10M — 2026-10-15 (corrida autorizada 600s COMPLETADA)

- Starting SHA: `10cad5c` (presetcommit pre-ejecucion).
- Run: probe-20261015T230630Z (UUID 893f...), 602.615s, 468162 msgs,
  0 rechazos/reconnects/parse, lags sanos, watchers 22+22, cierre
  natural, PIDs muertos, COMPLETED 610s, sin journal, DB 0B.
- Evidencia: RUN_OBS10M_20261015_COMPLETED.txt + 2 capturas terminal.
- Informe push 67472e0; reconciliacion push d7dcc70. V2 abierto, monitor detenido.

## DASH-V2-OPS-3020 — 2026-10-16 (entrega operativa V2 en puerto canonico)

- Canonical dashboard: `http://127.0.0.1:3020` (unico principal),
  `next start` desde `frontend/` de este repo, PID 23588,
  BUILD_ID `u0ziTGs3Q12uEMZapEWf7` construido del arbol d126141
  (ruta `/api/v1/detections` presente, `probe_run_id` en runtime).
- Reemplazo: instancia 3020 obsoleta (PID 24364, sin `/detections`
  ni `probe_run_id`, build anterior a d126141) + instancia 8093
  propia (PID 12268, build d126141) detenidas; `requestAllowed`
  sigue pineado a 127.0.0.1:3020 (sin ampliar CORS/origenes).
- Auth en vivo sin monitor: stop/start sin headers 403, origen evil
  403, canonico + confirm erroneo 400 previo a cualquier spawn;
  suites mockeadas 59/59 (security/start/stop/contract/feed/
  detections/panel). Registro intacto (COMPLETED/gone), 0 python.
- Visual 3020: barra global + panel episodios (98/4 parcial con
  `evidence-tail-truncated`, enlace UNKNOWN, etiqueta research);
  245/13 = reconstruccion completa del fixture, no equivalente.
- Evidencia: `docs/evidence/V2_3020_SYSTEM_TOP.png`,
  `V2_3020_SYSTEM_EPISODES.png`. Monitor detenido.

## DASH-V2-R3CAP-V2 — 2026-10-16 (veredicto R3 + causalidad)

- Starting SHA: `69d55ba`. Sin corridas, papel ni ordenes.
- Captura v2: veredicto separado, UUID tardio/ausencias,
  detections verificado, identidades fijadas (6 tests R3 nuevos).
- Export v2: close_time/as_of/cadena + regresion intra-vela +
  runner preserva tiempos, hash intacto (4 tests nuevos).
- Comando proxima ventana: sin cambios
  (`capture_run_window.py --run-id <stem> --out
  docs/evidence/R3_WINDOW_<stem>.json`).
- Verification: suites + barrera en el cierre.

## DASH-V2-R3CAP — 2026-10-16 (captura R3 lista + prep offline)

- Starting SHA: `48445f2`. Sin corridas, papel ni ordenes.
- `scripts/capture_run_window.py` + 10 tests + `export_engine_inputs.py`
  + 2 tests + `docs/ENGINE_ENTRY_EVAL_INVENTORY.md` (matriz H1/H2/H3,
  prep mecanico 1558 eventos en temp, economia retenida).
- Comando proxima ventana autorizada (tras el launch):
  `python scripts/capture_run_window.py --run-id <stem> --out
  docs/evidence/R3_WINDOW_<stem>.json`.
- Verification: suites + barrera en el cierre.

## DASH-V2-BRIEF-PILOT — 2026-10-16 (piloto 120s probe-20261016T005550Z)

- Starting SHA: `510c4ff` (funcional `d126141`, sin diff).
- Run: UUID 4303b1c5 auto-enlazado, 122.377s probe / 131s registro,
  COMPLETED duration-reached code 0, PIDs muertos, leases STOPPED.
  89360 msgs, 0 rechazos/reconnects, reloj 1/1, research 54/0/0 =
  54 filas UUID; 10 funding = 2 episodios v1 sin mezcla.
- V2 3020: barra (RUN/START/PLAN/END/CLOSE/FROZEN/STALE) + panel
  10/2 con enlace exacto; feed mid-run en vivo no capturado (R3
  UNKNOWN, residual). Seguridad 0/0/0.
- Evidencia: `RUN_BRIEF120_20261016_CLOSEOUT.json` (matriz R1-R11:
  10 PASS, R3 UNKNOWN, 0 FAIL; correccion del "9 PASS": la matriz
  siempre tuvo 10 PASS + 1 UNKNOWN) + `V2_BRIEF120_CLOSE_TOP.png` +
  `V2_BRIEF120_CLOSE_EPISODES.png`. Sin gates ni rentabilidad.
- Nota feed: respuesta `feed_health` UNKNOWN (slot del controlador,
  nunca rellenado por el lector V2 por diseño) vs barra STALE
  (enriquecimiento BFF desde ultimo snapshot grabado): dos capas,
  sin contradiccion.

## DASH-V2-LINK-EP — 2026-10-16 (trazabilidad stem<->UUID + episodios v1)

- Starting SHA: `d7dcc70`.
- Scope: `link_probe_run_id` + `probe_run_id` + `read_run_detections`
  + `event_episodes.py` v1 + BFF `runtime-control`/`detections` +
  ruta `/detections` + panel System + fixture 245 + contrato
  EVENT_EPISODES; correccion documental agrupados/sin-byte-identidad.
  Sin corridas, umbrales, estrategias, calibracion ni Start/Stop nuevos.
- Verification: backend 1139 OK + frontend 300/300 + typecheck + build
  + barrera 0/0/1RO hashes iguales + visual escritorio/movil.
- Commit d126141 + push review/o1-funcional-v2-observacion.

## DASH-V2-FEEDATTR — 2026-10-16 (correccion atribucion del feed, push 8c73de2)

- Starting SHA: `3f2fcea`.
- Scope: `runtime-control.ts` (sin gracia pre-start, run_id exacto
  primero con fallback temporal conservador + cruce runtime_seconds,
  previous-run distinguido); `runtime-feed.test.ts` (regresion 20s A/B
  + exacto + inconsistente); contratos + decisiones; Start/Stop,
  umbrales e identidad intactos; sin nuevas corridas.
- Verification: typecheck + suites + build + QA visual en el cierre.
- Next: barrera, commit selectivo, push, entrega.

## DASH-V2-RUNVIS-HARDEN — 2026-10-16 (identidad UNKNOWN + feed estricto, push 3f2fcea)

- Starting SHA: `3544ad6`.
- Scope: `supervision.ts` (display owned/gone/replaced/unknown,
  terminal explicito, expiracion 30s); `runtime-control.ts` (feed
  estricto + atribucion current/previous-run/none, 0.05 vs 0.5
  documentados, missing/silent/parse); `RunStatusBar` + `BotControl`
  (misma semantica); contratos + decisiones; tests feed/supervision/
  barra/BotControl (incluida evidencia reciente de otro run);
  Start/Stop/propiedad intactos; sin nuevas corridas.
- Verification: typecheck limpio; frontend 286/286; propiedad backend
  67 verdes; build + QA visual pendientes en el cierre.
- Runtime: ninguna corrida Binance; registry COMPLETED retenido.
- Next: barrera completa, commit selectivo, push, entrega.

## DASH-V2-RUNVIS — 2026-10-16 (visibilidad y control global de corridas, push 3544ad6)

- Starting SHA: `5d4fef6`.
- Scope: backend `control.py` (run_id/process_state/verified/last_exit_at
  aditivos); BFF `runtime-control.ts` (preserva contrato + feed desde
  telemetry + stop proyecto dashboard/agent/direct); `RunStatusBar` global
  en `AppShell` (todas las pantallas); `BotControl` (registrado vs
  verificado, terminal congelado, stop proyecto con confirmación);
  contratos + reconciliación piloto (sin nuevas corridas).
- Tests: backend `test_run_visibility.py` 10 OK (fixtures + sleep
  aislados); frontend 63 OK (bot-control/run-status-bar/stop/contract);
  `tsc --noEmit` limpio; barrera completa + QA visual desktop/móvil
  pendientes en el cierre.
- Runtime: ninguna corrida Binance iniciada; registry COMPLETED retenido;
  V2 abierto para verificación, monitor detenido.
- Next: barrera, commit selectivo, push, entrega con SHA/pruebas/capturas.

## Gate status

P1-10R: RUNNING since 2026-10-08T00:48:20Z (do not disturb). P1-12:
blocked pending P1-10R PASS. P1-12B: DONE. P1-13A: DONE (backend
opportunity engine + dashboard API). Dashboard V2: architecture +
static foundation (DASH-V2-00/01/02); no integration.

## DASH-V2-02 - Professional Futures Market Movers (2026-10-07)

- Implementation: professional DEMO screener with summary cards, combined search/direction/coverage/state/research-interest filters, stable numeric sorting with nulls last, ranked gainers/losers, coverage/data-quality counts, resettable empty state and 8-row pagination.
- Fixture contract: 16 centralized records with raw numeric values, explicit source/as-of, tier, capability and nulls. Criteria are UI exercise boundaries, not validated economic thresholds.
- Semantics: zero is neither gainer nor loser; missing fields never become zero; rankings use only comparable observations; all symbol links use /symbol/[symbol].
- Verification: typecheck PASS; ESLint PASS; Vitest 24/24 PASS; Next production build PASS.
- Responsive/browser QA (recovery agent, live preview :3000): desktop 1440 overview + movers screenshots, 390 mobile overview + movers screenshots, interactive filter/search/sort/pagination/empty/reset checks all correct, overview regression clean, console errors/warnings 0. Table overflow stays table-local on narrow widths.
- Visual reference comparison: NOT EVALUABLE because the reference mockups remain unavailable; no visual-comparison PASS claimed.
- Preview: http://127.0.0.1:3000/movers (production server; PID renewed with identity verification, see decisions).
- Recovery fixes applied: removed both route templates (root CSS-hack banner suppressor + movers children-ignoring override); /movers now composes MoversDashboard directly in page.tsx; AppShell foundation banner replaced by a compact demo strip; fixed summary double-% unit bug. Rankings scope note kept as designed (filtered dataset, explicitly labeled).
- Python backend, databases, runtime registry and formal P1-10R evidence: unchanged.
- P1-10R last observed RUNNING (PID 19084, read-only checks); no PASS/FAIL conclusion made.


## Accesos directos V2 — 2026-10-21 (F-NAV-V2-ACCESS-01)

La navegación incorpora `Mercado / Gráficos` -> `/market-lab` en Terminal, `Paper Lab — Simulación` -> `/paper-lab-live` y `Replay histórico` -> `/paper-lab` en Laboratorios. Se elimina el rótulo ambiguo Future workspace para estas capacidades existentes. ContractExplorer aparece antes del contenido histórico previo en /market-lab. Se preservan rutas y motores.

Verificado: navigation.test.tsx 4/4, tsc --noEmit y eslint de los dos archivos exit 0; next build exit 0 (13 advertencias de tracing preexistente en rutas no modificadas). BUILD_ID `3ThnqxocDEmcursE2ZYpu`, servidor propio PID 32104 (sustituye solo PID 16164 tras revalidar PID+creation time+comando y ausencia de monitor/Python). HTTP /overview, /market-lab, /paper-lab-live y /paper-lab 200; enlaces exactos y BUILD_ID comprobados en HTML servido. El cambio de navegación es de bajo impacto; backend y DB no cambiaron, no se repite su suite. Inspección visual/clics de navegador NO realizada: no hay herramienta de navegador disponible para esta sesión; verificación por pruebas de componente y HTML servido, sin PASS visual.

ESTADO DEL OBJETIVO VIVO: estos accesos NO implementan streaming. Mercado consulta histórico REST bajo demanda; Paper Lab usa fixtures; Replay reproduce histórico. El usuario reitera el objetivo de buscar contratos Futures elegibles y verlos actualizarse en vivo. Pendiente: adaptar feed existente, gestión compartida de suscripciones, vela provisional/cerrada, reconexión y reparación de huecos, frescura visible e indicadores backend compartidos; pruebas controladas y ventana acotada. No suscribir todo el universo a máxima resolución por pestaña ni confundir catálogo completo con seguimiento permanente. Abrir gráfico nunca abre una operación. Contrato rector: [ACUERDOS_GRAFICO_BINANCE_V1](ACUERDOS_GRAFICO_BINANCE_V1.md). Sin adquisición, monitor, paper prospectivo, órdenes, pagos, móvil ni gates en este cambio.

## DASH-V2-MONITOR-PILOTO — 2026-11-12 (monitor de solo lectura del piloto operativo)

- Starting SHA: `ea984c235eb5234d508bf46f52d794321cfc6ab4`.
- Alcance: slice de observabilidad mínima para la ventana única del experimento
  operativo v2 (vía A). NO amplía el dashboard: reutiliza `/market-lab` como
  modo de vista (`?vista=piloto&run=<run_id>`) sobre el dashboard Next.js que ya
  sirve el puerto 3020. Sin dashboard, motor, gestor de corridas, servicio ni
  puerto nuevos; sin indicadores, gráficos ni controles de ejecución.
- Contratos nuevos (solo lectura): `frontend/src/lib/pilot-monitor.ts` (lector
  acotado), `frontend/src/app/api/v1/pilot-monitor/route.ts` (BFF),
  `frontend/src/components/pilot-monitor/` (panel), modo de vista en
  `frontend/src/app/market-lab/page.tsx`. El cliente envía **solo** un `run_id`
  validado; la lectura queda acotada a `PILOT_MONITOR_ROOT` (por defecto
  `C:/proyectos/binance-futures-data`) y se rechaza cualquier ruta arbitraria.
- Exposición de estado ya existente (sin cambiar decisiones ni cálculos):
  `scripts/research_pilot.py` publica en el snapshot atómico `run_id`, `mode`,
  `activar_publico`, `presupuesto` (`RunBudget.status()`), `almacenamiento`
  (`RunStorageBudget.status()`), `duracion_maxima_total_ms` y
  `espera_contable_plazo_max_ms`; `scripts/research_operativo_adapter.py`
  publica `stop_px` (ya calculado por la regla congelada) en la fila operativa.
- Lectura incremental: los JSONL se consumen por offset; una actualización
  contable de la misma `observation_id` actualiza su fila sin contar una
  operación nueva. Si el fichero se reescribe, el estado derivado se
  reconstruye (carrera nueva en el mismo directorio).
- Pruebas: `frontend/src/test/pilot-monitor.test.ts` (9) y
  `frontend/src/test/pilot-monitor-panel.test.tsx` (6) en verde;
  `tsc --noEmit` y eslint limpios; suite completa del frontend 650 passed /
  1 skipped; `tests/test_pilot_monitor_observabilidad.py` (2 passed) y
  regresiones Python afectadas 33 passed.
- Aceptación local (navegador real, sin mercado público): corrida real del
  piloto en modo local con proveedores loopback y reloj controlado, servida por
  el build de producción en 3020. Secuencia observada **sin recargar**:
  Captura -> Resolución -> Espera contable -> Finalizada; una única operación
  con `upd` 0->1->2 (PENDIENTE/UNKNOWN -> ACREDITADA), tiempos de entrada y
  salida históricos conservados, feeds cerrados con aviso explícito de que el
  mercado no está LIVE, contadores de presupuesto autoritativos y
  `corte=trabajo_resuelto`. Cero peticiones fuera de `127.0.0.1:3020` y cero
  procesos nuevos al abrir y recargar la vista (solo el renderer del navegador
  de prueba).
- Capturas: `docs/evidence/monitor-piloto-20261112/` (fase captura, fase
  resolución, fase espera contable, fase finalizada, informe de aceptación con
  línea temporal y capturas por fase).
- Runtime: dashboard propio en `127.0.0.1:3020` (`next start`, PID y BUILD_ID
  verificados). El servicio ajeno de 8792 no se tocó ni se arrancó (no había
  listener antes ni después).
- Límites: la simulación no acredita ejecuciones reales ni rentabilidad
  generalizable; cobertura solo PERPETUAL/TRADING/USDT; futuros con
  vencimiento y GARCH siguen fuera de alcance. El panel observa: no inicia,
  reinicia ni detiene corridas.
- Ending SHA / commit / remote: `4b83498def6ae303795d50b2d8fe5276159312e5`
  (`Monitor de solo lectura del piloto operativo en /market-lab`), local ==
  remoto en `research/universe-liquidez-v1`.
- Verificacion posterior contra la corrida publica real
  `exp-v2-ventana-1-20261112a` (2026-11-12, build `wb_4SUPhODUEJgUSAmDP8`,
  BUILD_ID presente en el HTML servido, PID y proceso `next start` propios):
  el monitor mostro la fuente «Binance publico - experimento simulado», la
  fase de Captura a Finalizada, los contadores de presupuesto coincidentes
  con el ledger HTTP real (24/2000 intentos, 492/5000 peso) y el detalle del
  embudo (12 ciclos, 0 aptas, 232 descartadas). Se detecto y corrigio una
  imprecision de copy del aviso de feeds cerrados, que afirmaba
  incondicionalmente que «solo continua la contabilidad de funding» aun sin
  posiciones pendientes: ahora es condicional y hay test de regresion
  (`frontend/src/test/pilot-monitor-panel.test.tsx`). El panel sigue sin
  calcular nada. Evidencia:
  `docs/evidence/exp-v2-ventana-1-20261112a/`.
