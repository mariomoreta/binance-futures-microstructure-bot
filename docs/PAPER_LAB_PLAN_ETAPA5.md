# ETAPA 5 — Paper Lab plan (2026-10-12, DESIGN ONLY)

No paper engine is implemented, started, or authorized here. Operational
implementation depends on validating Etapas 1–4 plus explicit human
authorization per `docs/PAPER_TRADING.md` + `docs/RISK_RULES.md` +
`docs/SAFETY_RULES.md`. This file designs the work breakdown only.

## Estado actual (reconciliación 2026-10-20, cierre funcional)

Se distingue explícitamente cuatro estados. Ninguno implica que el motor de paper esté completo ni que exista señal de trading.

| Estado | Qué existe | Qué NO existe / no se afirma |
|---|---|---|
| **Trabajo local** | `frontend/src/components/paper-lab/` (`PaperLabReplay`, `ReplayControls`, `ReplayChart`, `PaperLabPanels`), `frontend/src/app/paper-lab/page.tsx` (renderiza `PaperLabReplay`), `frontend/src/lib/paper-lab-replay.ts`, `frontend/src/lib/format.ts` (añade `formatMoney`/`formatPct`), `scripts/build_paper_lab_replay.py`, `frontend/src/artifacts/paper-lab-replay-v1.json`, tests `paper-lab-replay.test.ts` + `paper-lab-components.test.tsx`. | No es motor de paper: no hay position manager, ledger de caja, funding recurrente ni risk engine. |
| **Código publicado en Git** | Artefacto, generador, parser/player, componentes, ruta y tests publicados (ver SHA de cierre abajo). El artefacto vive en `frontend/src/artifacts/` para no quedar bajo el `data/` ignorado. | `/backtest` sigue siendo stub (`FutureWorkspace`); no se toca. |
| **Probado** | `scripts/build_paper_lab_replay.py --check` → `PASS` (regeneración byte-idéntica). Suite frontend completa verde (**368/368**), `tsc --noEmit` sin errores, `eslint` sin errores. Tests cubren versión/schema, identidad (PLR-BTCUSDT-LONG-1788903900000, H1, horizon), fronteras temporales t−1/t/t+1 para entrada y cierre, revelación de la detección (formación vs disponibilidad), contexto inicial, estados del reproductor, reconciliación económica y rechazos. | Los umbrales de estrategia siguen siendo HIPÓTESIS; esta pantalla no valida edge. |
| **Servido y revisado** | Build de Next servida en `127.0.0.1:3020/paper-lab` (sin monitor activo, solo el servidor propio del proyecto reemplazado); la página servida muestra la operación LONG (no la SHORT obsoleta). Capturas desktop+mobile de los tres estados generadas; verificación por árbol de accesibilidad + texto + geometría de DOM. | La inspección **visual** de las PNG queda a cargo del revisor humano (modelo texto; APIs de visión caídas): no se declara PASS visual. El estudio W/LUMIA sigue **separado** y no bloquea esta entrega. |

**Identidad del artefacto:** `frontend/src/artifacts/paper-lab-replay-v1.json` (`PAPER-LAB-REPLAY-V1`, schema 1), determinista, fuente exclusivamente EVAL-CENSUS-V2 + trazas regeneradas; no lee DB canónica, no consulta Binance, falla cerrado ante contratos/hashes inválidos. Operación registrada: **BTCUSDT 15m, familia H1, dirección LONG**, `replay_id=PLR-BTCUSDT-LONG-1788903900000`, `event_time_ms=1788903900000`, `entry_ms=1788904800000`, `exit_ms=1788907500000` (salida `horizon`), `entry_px=78458.7`, `exit_px=78456.8`, `gross_pnl=-0.0242`, `net_pnl=-1.6242` (pérdida). Seleccionada por regla determinista antes de ver P&L. BTC es control de mecánica, **no** validación del selector de extremos.

**Frontera de revelación causal (formación vs disponibilidad vs entrada) — corregida 2026-10-20 (2ª corrección):** la cinta de pasos **separa pasos de vela de pasos de evento**. Un paso de vela se conoce al cierre de la barra (`…59.999`). Un **evento** se revela en **su propio paso, en su instante exacto**: un evento a `04:00:00.000` **NO** es conocido con cursor `03:59:59.999` y **no** se adelanta al paso que cierra la vela anterior. **Corrección adicional:** se **elimina el paso «señal» anticipado** que revelaba la detección en `event_time_ms` (21:45) pese a declarar `available_at=21:59:59.999`. Ahora la detección se revela en un único paso de evento `detection` **en su instante de disponibilidad**, mostrando `formation_time_ms` (21:45) como **metadata**. `formation_time` (a qué momento pertenece el patrón), `available_at` (cuándo puede conocerse) y `entry_time` (ejecución posterior) son distintos; la formación **nunca** autoriza a revelar antes de la disponibilidad. Invariantes verificadas por generador/tests/parser: `event.at_ms <= step.known_at_ms`; `formation_time_ms <= detection.at_ms`; ninguna detección con reloj `< available_at`. La versión previa de este documento proponía revelar todos los eventos en el paso de cierre de la vela; era incorrecta. Sin inventar ticks ni recorrido intrabar.

**Vista inicial y contexto (corregido 2026-10-20):** `initial_cursor_ms` (= último cierre de contexto) define un instante **anterior** a la detección; la vista inicial muestra solo el contexto ya conocido en ese instante y nunca velas cuyo cierre supere el cursor. No se simula un reloj indefinido ni se revelan velas futuras. El contexto (48 velas previas reales, contiguas) es solo informativo: no forma parte de la reproducción ni de posiciones/P&L.

**Estado del reproductor (corregido 2026-10-20):** el **estado del REPRODUCTOR** (`sin_iniciar` / `reproduciendo` / `pausado` / `terminado`) es independiente del **estado de POSICIÓN** (SIN POSICIÓN → EN ESPERA → ABIERTA → CERRADA). Avanzar manualmente con posición abierta ya no muestra «REPOSO»: muestra PAUSADO. Reiniciar restablece ambos de forma coherente; play/pausa/paso a paso/velocidad no llaman al monitor.

**Qué NO es:** no es simulación prospectiva, no es paper en vivo contra el feed, no ejecuta órdenes, no gestiona posiciones, no hay ledger de caja ni funding recurrente ni risk engine, no es selección automática en vivo. No valida el selector real de extremos sobre el universo: BTC/ETH/SOL son controles de mecánica, no prueba de cobertura.

### Enlace operación → replay desde Backtest (2026-10-20, additive)

Paper Lab admite ahora cargar UNA operación concreta elegida en `/backtest`,
en lugar de la operación fija. Contrato:

- **Entrada:** `/paper-lab?bt=<experimento>&event_id=<id>&group=<g>&segment=<s>&scale=<n>`.
  Sin esos parámetros, la página carga el artefacto fijo versionado (sin
  cambios de comportamiento).
- **Materialización:** el BFF `GET /api/v1/backtest/replay` invoca
  `scripts/build_paper_lab_replay.py --trades-json <run>/trades.json
  --target-event-id … --target-group … --target-segment … --target-scale …`
  y cachea por hash de identidad `(experimento, event_id, group, segment, scale)`.
- **Reutiliza** parser, reproductor, componentes y contrato PAPER-LAB-REPLAY-V1;
  conserva revelación en `available_at`, `formation` como metadata, estados
  temporales/fronteras, contexto causal previo, costes ejecutados vs
  hipotéticos y resultado final reconciliado. Sin recorrido intrabar
  inventado.
- **No soportado → explícito:** si una operación no es soportada por el
  reproductor, se muestra el motivo (HTTP 422 `REPLAY_UNSUPPORTED`) y sus
  datos permanecen en la tabla de Backtest; no se fabrica un replay.
- **Identidad del artefacto fijo (supersede 2026-10-20):** el `replay_id`
  incorpora ahora group+scale para que los enlaces sean únicos;
  sha256 regenerado `72af8007d5956244ec7b902c0b12f960cdc6993b6912b4749fff9fcfcb62f172`
  (supersede `0db0c4d0…`). `--check` PASS; ventana y pasos idénticos.
- **Vinculación a la corrida (2026-10-20, Bloque B):** el enlace admite
  `&run=<run_id>`; la materialización exige que la operación pertenezca a los
  resultados verificados de ESA corrida (`TARGET_NOT_IN_RUN` si no) y el
  artefacto viaja con `provenance.backtest_run_id` + `backtest_run_id`
  (`build_paper_lab_replay.py --run-id`, `backtest_trades` en `source_paths`).
  Sin `run`, se usa `current.json`. Un fallo muestra el motivo y no se
  sustituye por el artefacto fijo ni por otro replay.

---

### Estudio retrospectivo de extremos — paquete W/LUMIA (auditoría, no segunda implementación)

Se auditó el paquete existente `binance_case_study/` (WUSDT / LUMIAUSDT + BTCUSDT / GTCUSDT como controles), **sin reiniciar ni duplicar la implementación de Paper Lab y sin crear una segunda implementación**. Hallazgos:

- **Cobertura:** 1.499 velas de 5m cerradas + 1.499 de 1m cerradas por símbolo (WUSDT, LUMIAUSDT, BTCUSDT, GTCUSDT), corte `2026-10-12T10:57:19.690Z`, última vela 5m `10:54:59.999Z` (~5,2 días). Series sin duplicados ni huecos temporales; OHLC consistente. BTC como referencia sincronizada y control de mecánica; GTC como contexto adicional, no validación independiente.
- **Costes / compatibilidad con el motor (corregido 2026-10-20):** `funding_info` reportó `fundingIntervalHours=4` para WUSDT y LUMIAUSDT (100 registros históricos por contrato, jitter máx. 7 ms). El motor revisado **ya acepta un `FundingCalendar` por contrato** (`src/microstructure_probe/backtest_offline.py`, `class FundingCalendar`; consumido vía `cfg.funding_calendar`). `FUNDING_INTERVAL_MS = 8 * 3600 * 1000` es **solo el fallback cuando no se inyecta calendario**; el `interval_ms` del calendario es cadencia nominal informativa y la contabilidad usa las liquidaciones realizadas (timestamp + tasa), no el intervalo nominal. Por tanto, para W/LUMIA la fidelidad se logra **inyectando su `FundingCalendar` real**, no cambiando una constante: datos ausentes → UNKNOWN o exclusión según contrato. No resolverlo cambiando el 8 global por un 4 global ni creando una segunda contabilidad.
- **Casos documentados (descriptivos, in-sample):** WUSDT subió estando sobrecomprada (RSI 80+) antes de corregir (−10,97% máximo→último cierre); LUMIAUSDT fue ganadora de 24h que cayó, rebotó brevemente y siguió deteriorándose (mínimo 0,10598 conocido después; atribuir entrada a ese mínimo es sesgo retrospectivo). Ex-post high/low marcado explícitamente como `NOT_SIGNAL`.
- **Qué falta para mostrar esos casos en Paper Lab / V2:** calendario de funding real por símbolo y tasa liquidada; spread, profundidad y coste estimado para el tamaño de posición; fills reales (no asumidos); serie OOS (fuera de la ventana de selección); partición cronológica; vinculación `run_id`/`event_id` con versión de features e `as_of`; snapshot por evento con disponibilidad/recepción y hash del dataset. **No se calibran reglas sobre estos casos ni se seleccionan ejemplos por beneficio.** El estudio no demuestra ventaja rentable ni permite proyectar porcentajes.
- **Captura relacionada:** `binance_case_study/Casos_Binance_W_LUMIA.png` existe pero **no fue inspeccionada visualmente aquí** (`NOT_ASSESSED`; no se declara equivalencia visual). Se reference solo como archivo del paquete.

**Pendiente (motor completo de paper, aún en diseño, no implementado ni autorizado):** position manager, cash/fees/funding/P&L ledger, risk + halts/kill-switch, comparación paper-vs-backtest, entry gates de la sección 7. Ninguno iniciado. Este estado no altera SUCCESS_GATES ni Fase 4/5; el replay es pantalla de ingeniería (observación), no entrada automática.

**Entrega del replay (cerrada 2026-10-20):** generador + artefacto determinista publicados; parser/player/componentes y ruta V2; tests y evidencia; selección de operación independiente del P&L; separación de pasos de evento/vela sin anticipación; reconciliación de P&L/costes al cierre; capturas antes de entrada, abierta y cerrada (desktop+mobile); build servida y URL local verificada. Controles del replay separados de Start/Stop del monitor. Sin Binance ni paper prospectivo.

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
