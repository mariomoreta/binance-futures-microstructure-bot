# ETAPA 5 — Paper Lab plan (2026-10-12, DESIGN ONLY)

No paper engine is implemented, started, or authorized here. Operational
implementation depends on validating Etapas 1–4 plus explicit human
authorization per `docs/PAPER_TRADING.md` + `docs/RISK_RULES.md` +
`docs/SAFETY_RULES.md`. This file designs the work breakdown only.

## Estado actual (reconciliación 2026-10-20)

Se distingue explícitamente cuatro estados. Ninguno de ellos implica que el motor de paper esté completo ni que exista una señal de trading.

| Estado | Qué existe | Qué NO existe / no se afirma |
|---|---|---|
| **Trabajo local en curso** | `frontend/src/components/paper-lab/` (`PaperLabReplay`, `ReplayControls`, `ReplayChart`, `PaperLabPanels`), `frontend/src/app/paper-lab/page.tsx` (renderiza `PaperLabReplay` en lugar de `FutureWorkspace`), `frontend/src/lib/format.ts` (añade `formatMoney`/`formatPct`), `scripts/build_paper_lab_replay.py`, `frontend/src/test/paper-lab-replay.test.ts` + `frontend/src/test/paper-lab-components.test.tsx`. | Todo lo anterior está **untracked / no publicado en Git** (`git ls-files` vacío para `paper-lab-replay-v1.json`, `build_paper_lab_replay.py`, `paper-lab-replay.ts`). No es entrega de este agente; es trabajo del otro agente en curso. |
| **Código publicado en Git** | Solo `docs/PAPER_LAB_PLAN_ETAPA5.md` (commit `b9c2733`, push a `review/o1-funcional-v2-observacion`). | **Ningún** archivo de implementación de Paper Lab (artefacto, parser, componentes, tests, generador) está publicado en Git en este SHA. |
| **Probado** | `scripts/build_paper_lab_replay.py --check` → `PASS: artefacto determinista sha256=7ba452c308378c7f26a20b12761625dcace6b839ba7576d0221bba0346f41826` (regeneración byte-identica sobre EVAL-CENSUS-V2). Tests `parsePaperLabReplay` / `ReplayPlayer` / `msPerStep` / `reconciledNet` existen y cubren versión, schema, identidad de operación (PLR-BTCUSDT-LONG-1788903900000, H1, horizon), tiempos causales, niveles/costes, reconciliación económica, procedencia y rechazos de artefacto inválido. | La existencia de archivos o comentarios **no** se afirma como "verificado" globalmente. Los tests existen pero no están publicados; no se ha ejecutado la suite frontend de este agente sobre ellos. |
| **Servido y revisado visualmente** | — (no confirmado por este agente) | No se sirvió el frontend, no se ejecutó `next start`/`next build` sobre esta rama por este agente, no hay capturas de paper-lab revisadas, no hay URL local verificada por este agente. El V2 en `:3020` tiene monitor detenido. `/backtest` es stub (`FutureWorkspace`), no real. |

**Identidad del artefacto (verificada en código, no por capturas):** `frontend/src/data/paper-lab-replay-v1.json` (`PAPER-LAB-REPLAY-V1`, schema 1), determinista, fuente exclusivamente EVAL-CENSUS-V2 + trazas regeneradas; no lee DB canónica, no consulta Binance, falla cerrado ante contratos/hashes inválidos. **No existen capturas de pantalla de Paper Lab verificables en este entorno**; no se afirma "BTC SHORT" ni ningún estado visual sin archivo de captura inspeccionado. Operación registrada: **BTCUSDT 15m, familia H1, dirección LONG** (no SHORT), `replay_id=PLR-BTCUSDT-LONG-1788903900000`, `event_time_ms=1788903900000` (2026-09-08T21:45:00Z), `entry_ms=1788904800000` (22:00:00Z), `exit_ms=1788907500000` (22:45:00Z, salida por `horizon`), `entry_px=78458.7`, `exit_px=78456.8`, `gross_pnl=-0.0242`, `net_pnl=-1.6242` (pérdida, no ganancia). Seleccionada por regla determinista antes de ver P&L; no es selección por rentabilidad. Causalidad en el replay: `event_time_ms < entry_ms <= exit_ms` y `available_at <= entry_ms` (verificado por tests). Ventana: 4 velas cerradas de 15m.

**Frontera de revelación causal (cursor vs evento):** las velas cerradas se conocen al cierre de la barra (marcas `.999` en series 5m/15m, ej. `10:54:59.999`). El evento y la disponibilidad deben revelarse **en el paso del cursor que cierra la vela de formación**, nunca al minuto redondo siguiente ni con ticks inventados intrabar. `known_at_ms` de cada paso debe ser el `close_time_ms` de la vela conocida hasta ese cursor; un evento con `event_time_ms` igual al cierre de una vela se revela en ese mismo paso, no en el siguiente.

**Capturas:** no hay capturas de Paper Lab (`before/abierta/cerrada`) localizadas en este entorno. La aceptación de entrega las exige; hasta que el agente responsable las publique y verifique, el estado es "no servido ni revisado visualmente por este agente".

**Qué NO es:** no es simulación prospectiva, no es paper en vivo contra el feed, no ejecuta órdenes, no gestiona posiciones, no hay ledger de caja ni funding recurrente ni risk engine, no es selección automática en vivo. No valida el selector real de extremos sobre el universo: BTC/ETH/SOL son controles de mecánica, no prueba de cobertura.

---

### Estudio retrospectivo de extremos — paquete W/LUMIA (auditoría, no segunda implementación)

Se auditó el paquete existente `binance_case_study/` (WUSDT / LUMIAUSDT + BTCUSDT / GTCUSDT como controles), **sin reiniciar ni duplicar la implementación de Paper Lab y sin crear una segunda implementación**. Hallazgos:

- **Cobertura:** 1.499 velas de 5m cerradas + 1.499 de 1m cerradas por símbolo (WUSDT, LUMIAUSDT, BTCUSDT, GTCUSDT), corte `2026-10-12T10:57:19.690Z`, última vela 5m `10:54:59.999Z` (~5,2 días). Series sin duplicados ni huecos temporales; OHLC consistente. BTC como referencia sincronizada y control de mecánica; GTC como contexto adicional, no validación independiente.
- **Costes / compatibilidad con el motor:** `funding_info` reportó `fundingIntervalHours=4` para WUSDT y LUMIAUSDT (100 registros históricos por contrato, jitter máx. 7 ms). El motor revisado declara `FUNDING_INTERVAL_MS = 8 * 3600 * 1000` y cuenta intervalos completos entrada→salida: **ese supuesto no representa estos contratos**. Propuesta de fidelidad de replay (no evidencia de beneficio): contabilizar cada liquidación de funding realmente cruzada con calendario y tasa del contrato, exposición vigente, signo y fuente/versionado; datos ausentes → UNKNOWN o exclusión según contrato. No resolverlo cambiando el 8 global por un 4 global.
- **Casos documentados (descriptivos, in-sample):** WUSDT subió estando sobrecomprada (RSI 80+) antes de corregir (−10,97% máximo→último cierre); LUMIAUSDT fue ganadora de 24h que cayó, rebotó brevemente y siguió deteriorándose (mínimo 0,10598 conocido después; atribuir entrada a ese mínimo es sesgo retrospectivo). Ex-post high/low marcado explícitamente como `NOT_SIGNAL`.
- **Qué falta para mostrar esos casos en Paper Lab / V2:** calendario de funding real por símbolo y tasa liquidada; spread, profundidad y coste estimado para el tamaño de posición; fills reales (no asumidos); serie OOS (fuera de la ventana de selección); partición cronológica; vinculación `run_id`/`event_id` con versión de features e `as_of`; snapshot por evento con disponibilidad/recepción y hash del dataset. **No se calibran reglas sobre estos casos ni se seleccionan ejemplos por beneficio.** El estudio no demuestra ventaja rentable ni permite proyectar porcentajes.
- **Captura relacionada:** `binance_case_study/Casos_Binance_W_LUMIA.png` existe pero **no fue inspeccionada visualmente aquí** (`NOT_ASSESSED`; no se declara equivalencia visual). Se reference solo como archivo del paquete.

**Pendiente (motor completo, aún en diseño, no implementado ni autorizado):** position manager, cash/fees/funding/P&L ledger, risk + halts/kill-switch, comparación paper-vs-backtest, entry gates de la sección 7, publicación en Git, servido y revisado visualmente. Ninguno iniciado. Este estado no altera SUCCESS_GATES ni Fase 4/5; el replay es pantalla de ingeniería (observación), no entrada automática.

**Aceptación para entrega del agente responsable de Paper Lab:** generador + artefacto determinista; parser/player/componentes y ruta V2; tests y evidencias; selección de operación independiente del P&L; reconciliación de P&L/costes al cierre; capturas antes de entrada, abierta y cerrada; SHA/build efectivamente servido y URL local verificada. Controles del replay separados de Start/Stop del monitor. Sin Binance ni paper prospectivo.

## 1. Simulation engine + fill model (pending)

- Consume live public streams through the existing probe path (no new
  venue); paper fills simulated at touch-adjusted prices from bookTicker/
  depth snapshots with the Etapa-4 cost stack (fees, funding, spread,
  slippage) plus a latency distribution from measured corrected lags.
- Partial fills against sampled depth levels; unfilled remainder rests or
  cancels per versioned policy (no silent full-fill assumption).
- Deterministic seed + config/version recording per session; replayable
  from persisted snapshots for divergence forensics.

## 2. Position manager (pending)

- State-driven, evidence-driven exits (classifier states, invalidation
  levels from the Etapa-3 contract); fixed-time exits as baseline
  comparator only. Mirrors backtest exit semantics so paper-vs-backtest
  comparison is apples-to-apples.
- The ACTION VOCABULARY exists as a design document
  (`docs/POSITION_MANAGEMENT.md`: HOLD / LET_WINNER_RUN / RAISE_STOP /
  PROTECT_PROFIT / PARTIAL_EXIT / FULL_EXIT, state-driven durations);
  what is pending is its IMPLEMENTATION as an engine plus the
  authoritative paper-only position ledger below.
- One authoritative position ledger (paper-only store, separate from
  research DBs); every action timestamped with event-time + receive-time.

## 3. Cash / fees / funding / P&L accounting (pending)

- Paper cash ledger: starting equity (fictitious, labeled), per-fill fee
  debits, 8h funding accruals while open, realized/unrealized P&L split,
  exposure-time-weighted returns. All cost inputs versioned per session.

## 4. Risk: per-position + portfolio (pending)

- Per-trade MAE stop, max concurrent positions, max notional/position,
  max total exposure, daily loss limit — tighten-only starting values
  from `docs/RISK_RULES.md`; any loosening needs a DECISIONS entry.
- Risk engine unbypassable by signal/position logic (architectural
  invariant, tested before any session).

## 5. Exposure limits, halts, kill-switch (pending)

- Halts: daily-loss breach, cost-sensitivity failure, version/config
  mismatch → new entries stop, opens go to protect/exit mode.
- Kill-switch: data staleness beyond tolerance, WS outage, clock-sync
  failure → immediate halt + human review. Halt/kill events are
  first-class persisted records.

## 6. Paper-vs-backtest comparison (pending)

- Same H-family, same config hash class, same horizons: compare fill
  prices, exit timing, cost drag, expectancy distributions, drawdown.
- Tolerance band predeclared per study; breach stops promotion and opens
  an investigation task — never adjust the backtest to match (per
  PAPER_TRADING rules).

## 7. Entry gates (all must hold before implementation)

Etapa-1 barrier green on the implementation SHA; Etapa-2 dataset fit for
the traded family (costs + versions + OOS exist — they do not today);
Etapa-3 contract accepted per family; Etapa-4 engine validated on a real
versioned dataset; explicit human authorization; dashboard embodies the
read contract (reviewed, unwired until then).

## Closeout (seven fields)

- `DECISIONS_REVIEWED`: PAPER_TRADING, RISK_RULES, POSITION_MANAGEMENT
  (pending doc), Etapa-3 contract, Etapa-4 read contract.
- `NEW_DECISIONS_RECORDED`: paper-lab work breakdown + entry gates above
  — appended to `docs/DECISIONS.md`.
- `FEATURES_IMPLEMENTED`: this design (no backlog ID).
- `FEATURES_VERIFIED`: none (nothing built).
- `DEFERRED_FEATURES`: all six build items; live validation; sizing/risk
  contract values; dashboard wiring.
- `BACKLOG_UPDATED`: Etapa-5 line (design only).
- `DOCUMENTATION_CONFLICTS`: none.
