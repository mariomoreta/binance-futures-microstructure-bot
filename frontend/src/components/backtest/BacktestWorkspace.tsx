"use client";
import {useCallback, useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {
  parseBacktestSummary, parseBacktestTrades,
  utcOf, moneyOf, pctOf, durationOf,
  countsByScale, hypothesisPlacebo1x, openMarksOf, summaryRowBreakdown,
  type BacktestSummary, type BacktestTrade,
} from "@/lib/backtest-results";
import s from "./Backtest.module.css";

// Configuracion del primer experimento soportado (misma lista permitida que
// el ejecutor backend). Nada de sliders arbitrarios: solo combinaciones
// soportadas. Los 1x/2x/3x son ESCENARIOS DE COSTES, no apalancamiento.
const EXPERIMENT = "eval-census-v2-trio";
const EXPERIMENT_LABEL = "Evaluación histórica de reglas candidatas sobre dataset conocido";
const NOT_LABEL = "NO es un backtest completo del descubrimiento de extremos";

type JobState = {
  status: "pendiente" | "ejecutando" | "completado" | "fallido" | "sin_ejecutar";
  error: string | null; detail: string | null;
  n_trades: number | null; reconciliation_ok: boolean | null;
  run_id: string | null; duration_ms: number | null; updated_at_ms: number | null;
  identity?: "verified" | "UNKNOWN";
};

const STATUS_LABEL: Record<string, string> = {
  sin_ejecutar: "SIN EJECUTAR", pendiente: "PENDIENTE", ejecutando: "EJECUTANDO",
  completado: "COMPLETADO", fallido: "FALLIDO",
};

export default function BacktestWorkspace() {
  const [job, setJob] = useState<JobState | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pollNonce, setPollNonce] = useState(0);
  const [filter, setFilter] = useState<"todas" | "ganadoras" | "perdedoras" | "abiertas">("todas");
  const [showAll, setShowAll] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const r = await fetch(`/api/v1/backtest/status?experiment=${EXPERIMENT}`, {cache: "no-store"});
      const j = await r.json();
      setJob(j.state ?? {status: "sin_ejecutar", error: null, detail: null,
        n_trades: null, reconciliation_ok: null, run_id: null, duration_ms: null, updated_at_ms: null});
      if (j.run_id) setRunId(j.run_id);
      return (j.state?.status ?? "sin_ejecutar") as string;
    } catch {
      setJob({status: "sin_ejecutar", error: "STATUS_UNAVAILABLE", detail: null,
        n_trades: null, reconciliation_ok: null, run_id: null, duration_ms: null, updated_at_ms: null});
      return "sin_ejecutar";
    }
  }, []);

  const loadResults = useCallback(async (targetRun?: string | null) => {
    try {
      const q = targetRun ? `&run=${encodeURIComponent(targetRun)}` : "";
      const r = await fetch(`/api/v1/backtest/results?experiment=${EXPERIMENT}${q}`, {cache: "no-store"});
      if (!r.ok) { setSummary(null); setTrades([]); return false; }
      const j = await r.json();
      if (j.run_id) setRunId(j.run_id);
      setSummary(parseBacktestSummary(j.summary));
      setTrades(parseBacktestTrades({trades: j.trades}));
      return true;
    } catch {
      setSummary(null); setTrades([]); return false;
    }
  }, []);

  // Sondeo del estado: refrescar o cerrar el navegador no pierde ni relanza la
  // tarea (el estado vive en el backend). Se detiene al terminar.
  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const tick = async () => {
      const status = await refreshStatus();
      if (cancelled) return;
      if (status === "completado") await loadResults();
      if (cancelled) return;
      if (status === "pendiente" || status === "ejecutando") {
        timer = window.setTimeout(tick, 2500) as unknown as number;
      }
    };
    tick();
    return () => { cancelled = true; if (timer !== null) clearTimeout(timer); };
  }, [refreshStatus, loadResults, pollNonce]);

  const onRun = useCallback(async () => {
    setBusy(true); setRunError(null);
    try {
      const r = await fetch("/api/v1/backtest/run", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({experiment: EXPERIMENT}),
      });
      const j = await r.json();
      if (!r.ok) setRunError(j.error ?? "RUN_FAILED");
      else if (j.started === false) setRunError("DUPLICATE_IGNORED");
      else if (j.run_id) setRunId(j.run_id);
      setPollNonce((n) => n + 1);
    } catch {
      setRunError("RUN_FAILED");
    } finally {
      setBusy(false);
    }
  }, []);

  const realized = useMemo(() => trades.filter((t) => t.exit_executed && !t.open_at_end), [trades]);
  const opened = useMemo(() => trades.filter((t) => t.open_at_end || !t.exit_executed), [trades]);
  const winners = useMemo(() => realized.filter((t) => (t.net_pnl ?? 0) > 0), [realized]);
  const losers = useMemo(() => realized.filter((t) => (t.net_pnl ?? 0) < 0), [realized]);

  const filtered = useMemo(() => {
    const base = filter === "ganadoras" ? winners : filter === "perdedoras" ? losers
      : filter === "abiertas" ? opened : trades;
    // Orden cronologico (no por beneficio).
    return [...base].sort((a, b) => a.event_time_ms - b.event_time_ms || a.trade_id.localeCompare(b.trade_id));
  }, [filter, trades, winners, losers, opened]);
  const visible = showAll ? filtered : filtered.slice(0, 100);

  const reconOk = summary?.reconciliation_ok ?? job?.reconciliation_ok ?? null;
  const status = job?.status ?? "sin_ejecutar";
  const oneX = useMemo(() => countsByScale(summary?.cells ?? [], 1), [summary]);
  const hp = useMemo(() => hypothesisPlacebo1x(summary?.cells ?? []), [summary]);
  const rowBreakdown = useMemo(() => summaryRowBreakdown(summary?.cells ?? []), [summary]);
  // Un dato ausente se muestra UNKNOWN; nunca se convierte en 0.
  const countOf = (v: number | null) => (v === null ? "UNKNOWN" : String(v));
  const marksOneX = openMarksOf(oneX);
  const identityUnknown = job?.identity === "UNKNOWN"
    && (status === "ejecutando" || status === "pendiente"
      || job?.error === "PROCESS_IDENTITY_UNKNOWN");

  return (
    <section className={s.root} aria-label="Backtest offline controlado">
      <div className={s.labelStrip}>
        <span className={s.badge}><span className={s.dot} aria-hidden="true"></span>BACKTEST HISTÓRICO OFFLINE</span>
        <span className={s.chip}>Ejecución separada del monitor (no es una corrida Binance)</span>
      </div>
      <h1 className={s.title}>Backtest</h1>
      <p className={s.subtitle}>
        {EXPERIMENT_LABEL}. Ejecuta una evaluación histórica reproducible con el motor existente
        sobre el paquete versionado EVAL-CENSUS-V2 y permite revisar cada operación en Paper Lab.
      </p>
      <p className={s.warning}><strong>{NOT_LABEL}.</strong> No aprueba ninguna familia ni estrategia:
        H1/H3/H2 fueron rechazadas o fenced en estudios previos. Los 1x/2x/3x son escenarios de
        costes, no apalancamiento. Sin adquisición nueva, sin órdenes, sin credenciales.</p>

      <div className={s.card}>
        <h3>1. Configuración del experimento (solo combinaciones soportadas)</h3>
        <div className={s.defs}>
          <div><dt>Dataset y versión</dt><dd className={s.mono}>EVAL-CENSUS-V2 · docs/evidence/eval-census-v2-package</dd></div>
          <div><dt>Símbolos y cobertura</dt><dd>BTCUSDT, ETHUSDT, SOLUSDT · resoluciones 15m y 1h tal como las contiene el paquete</dd></div>
          <div><dt>Familia / dirección</dt><dd>H1 LONG, H3 SHORT, H2 fade (hipótesis) y baseline (referencia); mapping MAP-CANDIDATE-v2 (no aprobado)</dd></div>
          <div><dt>Resolución y horizonte</dt><dd className={s.mono}>15m→1h, 1h→4h (HORIZON-GRID4-V1)</dd></div>
          <div><dt>Corte dev / held-out</dt><dd>Split por tiempo de evento en el cutoff del paquete; held-out NO prístino (ventana reutilizada, sin purga adicional)</dd></div>
          <div><dt>Costes 1x/2x/3x</dt><dd>ESCENARIOS DE COSTES (fee 5 bps / spread 1 bps / slippage 2 bps asumidos), no apalancamiento</dd></div>
          <div><dt>Funding y cobertura</dt><dd>Funding realizado de calendarios por contrato; la cobertura incompleta queda visible</dd></div>
          <div><dt>Solapes / exposición</dt><dd>Una posición por celda; solapes descartados y contados; sin cartera conjunta modelada</dd></div>
          <div><dt>Selección retrospectiva</dt><dd>Definiciones anteriores a los resultados; no se elige por rentabilidad; placebo separado de hipótesis</dd></div>
        </div>
        <p className={s.note}>Antes de ejecutar se muestran dataset+hash, símbolos+cobertura, familia/dirección, resolución/horizonte,
          corte dev/held-out, costes como escenarios, funding y política de solapes. No se permiten sliders ni ajuste de parámetros.</p>
      </div>

      <div className={s.card}>
        <h3>2. Ejecución offline controlada</h3>
        <div className={s.row}>
          <div className={s.actions}>
            <button className={s.run} onClick={onRun}
              disabled={busy || status === "ejecutando" || status === "pendiente"}>
              {status === "ejecutando" || status === "pendiente" ? "Ejecutando…" : "Ejecutar backtest"}
            </button>
            <button className={s.ghost} type="button" onClick={() => setPollNonce((n) => n + 1)}>Actualizar estado</button>
            {(status === "completado") && <button className={s.ghost} type="button" onClick={() => { setShowAll(false); loadResults(runId); }}>Recargar resultados</button>}
          </div>
          <span className={`${s.chip} ${status === "completado" ? s.pos : status === "fallido" ? s.neg : status === "ejecutando" || status === "pendiente" ? s.warn : ""}`}
            data-job-status={status}>
            Tarea: {STATUS_LABEL[status] ?? status}
          </span>
        </div>
        <p className={s.note}>La tarea se ejecuta una sola vez (sin duplicados por doble clic o refresco), en un directorio propio
          <span className={s.mono}> backtest-results/</span> aislado de datos operacionales y DBs canónicas. Cada ejecución tiene identidad propia
          (<span className={s.mono}>{runId ?? "sin ejecución"}</span>); el bloqueo entre procesos impide dos ejecuciones simultáneas. Refrescar o cerrar el navegador
          no pierde ni relanza la tarea. Los fallos se muestran; nunca se sustituyen por mocks.</p>
        {runError && <p className={s.error} role="alert">Estado de la ejecución: {runError}
          {runError === "DUPLICATE_IGNORED" && " (ya había una tarea en curso: no se lanzó otra)."}
          {runError === "ALREADY_RUNNING" && " (hay una ejecución con el ejecutor activo o con identidad no verificable: no se lanzó otra)."}
          {runError === "GUARD_BUSY" && " (otra operación de control está en curso; reintente)."}</p>}
        {identityUnknown && <p className={s.warn} role="status">
          Identidad del ejecutor no verificable (UNKNOWN): no se declara «verificada» ni se lanza otra ejecución.
          El estado y la exclusión se conservan hasta poder confirmar que no queda ningún proceso de la ejecución anterior.
        </p>}
        {status === "fallido" && job?.error && <p className={s.error} role="alert">
          Backtest fallido: {job.error}{job.detail ? ` — ${job.detail}` : ""}</p>}
      </div>

      {status === "completado" && summary && (
        <>
          <div className={s.card}>
            <h3>3. Resultados del experimento</h3>
            <div className={s.metrics}>
              <div><small>Operaciones @1x</small><strong>{summary.n_trades_1x ?? "—"}</strong><span>realizadas {countOf(oneX.n_realized)} + abiertas {countOf(oneX.n_open)}</span></div>
              <div><small>Resultado REALIZADO @1x — hipótesis</small><strong>{moneyOf(hp.hypothesis.total_net_realized)}</strong><span>solo operaciones cerradas de las hipótesis (sin marcas)</span></div>
              <div><small>Resultado REALIZADO @1x — placebo (referencia)</small><strong>{moneyOf(hp.placebo.total_net_realized)}</strong><span>ledger del baseline; NO es una estrategia</span></div>
              <div><small>Marcas de abiertas @1x</small><strong>{moneyOf(marksOneX)}</strong><span>valoración a cierre, NO beneficio realizado</span></div>
              <div><small>Suma aritmética de ledgers @1x (control)</small><strong>{moneyOf(hp.ledger_sum.total_net_realized)}</strong><span>suma técnica de dos ledgers distintos; NO es cartera ni beneficio de una estrategia</span></div>
              <div><small>Reconciliación con el motor</small><strong>{reconOk === true ? "OK" : reconOk === false ? "FALLA" : "UNKNOWN"}</strong><span>{summary.reconciliation_rows ?? "—"} celdas (56 resultado + 14 aux.)</span></div>
            </div>
            <p className={s.note}>
              Escenarios de coste (NO apalancamiento): <span className={s.mono}>{(summary.scales ?? []).map((x) => `${x}x`).join(" · ")}</span>.
              Los totales agregados de esta sección son <strong>@1x únicamente</strong>; 2x/3x solo escalan costes asumidos.
              Operaciones totales (1x+2x+3x) = {summary.n_trades_total ?? "—"}: son el MISMO conjunto de operaciones bajo tres
              escenarios de coste, no 15 765 oportunidades independientes.
            </p>
            <div className={s.metrics}>
              <div><small>Hipótesis @1x</small><strong>{countOf(hp.hypothesis.n_trades)}</strong><span>{countOf(hp.hypothesis.n_realized)} realizadas + {countOf(hp.hypothesis.n_open)} abiertas · realizado {moneyOf(hp.hypothesis.total_net_realized)}</span></div>
              <div><small>Placebo (baseline) @1x</small><strong>{countOf(hp.placebo.n_trades)}</strong><span>{countOf(hp.placebo.n_realized)} realizadas + {countOf(hp.placebo.n_open)} abiertas · realizado {moneyOf(hp.placebo.total_net_realized)}</span></div>
              <div><small>Suma aritmética de ledgers @1x (control)</small><strong>{countOf(hp.ledger_sum.n_trades)}</strong><span>{countOf(hp.ledger_sum.n_realized)} realizadas + {countOf(hp.ledger_sum.n_open)} abiertas · NO es una cartera</span></div>
            </div>
            <p className={s.note}>
              Hipótesis y placebo se presentan SEPARADOS: el baseline es referencia, no una estrategia con la misma definición.
              La «suma aritmética de ledgers» solo existe como control técnico de dos ledgers distintos; no se presenta como
              beneficio de una estrategia. Las celdas se agregan como eventos de una misma familia de reglas y NO como una
              cartera: la exposición conjunta no está modelada, así que no se suman símbolos ni grupos como si fueran un portafolio.
            </p>
            <p className={s.note}>
              Filas del summary: {rowBreakdown.result_cells} celdas de resultado (con segmento) + {rowBreakdown.auxiliary_rows} auxiliares
              (agregados por escala, sin segmento) = {rowBreakdown.total}. No son {rowBreakdown.total} resultados independientes.
            </p>
            <p className={s.note}>
              Paquete verificado: <span className={s.mono}>{summary.package_files_verified ?? "?"} archivos</span> ·
              manifest sha256 <span className={s.mono}>{(summary.package_manifest_sha256 ?? "").slice(0, 16)}…</span> ·
              mapping <span className={s.mono}>{summary.mapping}</span> · horizonte <span className={s.mono}>{summary.horizon_rule}</span>
            </p>
            <p className={s.note}>{summary.cost_model}</p>
            <p className={s.note}>{summary.placebo_note}</p>
            <p className={s.note}>Motor <span className={s.mono}>{summary.engine_version}</span> ·
              ejecutor <span className={s.mono}>{summary.executor_version}</span> ·
              duración <span className={s.mono}>{durationOf(summary.duration_ms)}</span></p>
          </div>

          <div className={s.card}>
            <h3>Celdas agregadas (por símbolo, resolución, grupo, segmento y escala)</h3>
            <p className={s.note}>Cada celda es un agregado; NO se suma como cartera (la exposición conjunta no está modelada).
              n=0 significa «sin operaciones»; una muestra insuficiente permanece identificada como tal. Las celdas NO son
              observaciones estadísticamente independientes: solo los ledgers de operaciones están separados.
              «Neto» incluye las marcas de las abiertas; «Neto real.» es solo lo cerrado.</p>
            <div className={s.tableWrap}>
              <table>
                <thead><tr>
                  <th>Símbolo</th><th>Res.</th><th>Grupo</th><th>Seg.</th><th>Esc.</th>
                  <th className={s.mono}>Eventos</th><th>Op.</th><th>Real.</th><th>Abiertas</th><th>Solapes</th>
                  <th>E·neto</th><th>E·bruto</th><th>Neto</th><th>Neto real.</th><th>Costes</th><th>Funding</th>
                  <th>DD realizado</th><th>MFE</th><th>MAE</th><th className={s.mono}>config</th>
                </tr></thead>
                <tbody>
                  {summary.cells.filter((c) => c.segment).map((c) => (
                    <tr key={`${c.symbol}-${c.res}-${c.group}-${c.segment}-${c.scale}`}>
                      <td>{c.symbol}</td><td>{c.res}</td><td>{c.group}</td><td>{c.segment}</td>
                      <td className={s.num}>{c.scale}{"x"}</td>
                      <td className={s.num}>{c.n_events}</td><td className={s.num}>{c.n_trades}</td>
                      <td className={s.num}>{c.n_realized}</td><td className={s.num}>{c.n_open}</td>
                      <td className={s.num}>{c.skipped_overlap}</td>
                      <td className={s.num}>{moneyOf(c.expectancy_net)}</td>
                      <td className={s.num}>{moneyOf(c.expectancy_gross)}</td>
                      <td className={s.num}>{moneyOf(c.total_net)}</td>
                      <td className={s.num}>{moneyOf(c.total_net_realized)}</td>
                      <td className={s.num}>{moneyOf(c.total_fees)}</td>
                      <td className={s.num}>{moneyOf(c.total_funding)}</td>
                      <td className={s.num}>{moneyOf(c.max_drawdown_realized)}</td>
                      <td className={s.num}>{pctOf(c.mfe_mean)}</td>
                      <td className={s.num}>{pctOf(c.mae_mean)}</td>
                      <td className={s.mono}>{c.config_hash}</td>
                    </tr>
                  ))}
                  {summary.cells.filter((c) => c.segment).length === 0 &&
                    <tr><td colSpan={20} className={s.empty}>Sin celdas con operaciones.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className={s.note}>MFE/MAE son EXCURSIONES (máximas a favor/en contra), no ganancias capturadas.
              «DD realizado» es el drawdown realizado de la celda, no el drawdown total de una cartera.</p>
          </div>

          <div className={s.card}>
            <h3>Operaciones (con enlace a Paper Lab)</h3>
            <div className={s.filters} role="group" aria-label="Filtros de operaciones">
              <button data-active={filter === "todas"} onClick={() => { setFilter("todas"); setShowAll(false); }}>Todas ({trades.length})</button>
              <button data-active={filter === "ganadoras"} onClick={() => { setFilter("ganadoras"); setShowAll(false); }}>Ganadoras ({winners.length})</button>
              <button data-active={filter === "perdedoras"} onClick={() => { setFilter("perdedoras"); setShowAll(false); }}>Perdedoras ({losers.length})</button>
              <button data-active={filter === "abiertas"} onClick={() => { setFilter("abiertas"); setShowAll(false); }}>Abiertas ({opened.length})</button>
              <span className={s.chip}>Orden cronológico</span>
            </div>
            <div className={s.tableWrap}>
              <table>
                <thead><tr>
                  <th>ID</th><th>Símbolo</th><th>Familia</th><th>Dir.</th><th>Seg.</th><th>Esc.</th>
                  <th>Evento (formación)</th><th>Entrada</th><th>Salida</th><th>Duración</th><th>Motivo</th>
                  <th>Estado</th><th>Bruto</th><th>Costes</th><th>Funding</th><th>Neto (marca)</th><th>Neto real.</th><th>Cobertura</th><th>Replay</th>
                </tr></thead>
                <tbody>
                  {visible.map((t) => (
                    <tr key={t.trade_id}>
                      <td className={s.mono}>{t.event_id.split(":").slice(-1)[0]}:{t.family}</td>
                      <td>{t.symbol}</td><td>{t.group}</td><td>{t.direction}</td>
                      <td>{t.segment}</td><td className={s.num}>{t.scale}x</td>
                      <td className={s.mono}>{utcOf(t.event_time_ms)}</td>
                      <td className={s.mono}>{utcOf(t.entry_ms)}</td>
                      <td className={s.mono}>{utcOf(t.exit_ms)}</td>
                      <td className={s.num}>{durationOf(t.holding_ms)}</td>
                      <td>{t.exit_reason}</td>
                      <td className={t.open_at_end ? s.warn : ""}>{t.status}</td>
                      <td className={s.num}>{moneyOf(t.gross_pnl)}</td>
                      <td className={s.num}>{moneyOf(t.fees)}</td>
                      <td className={s.num}>{moneyOf(t.funding)}</td>
                      <td className={`${s.num} ${(t.net_pnl ?? 0) >= 0 ? "" : ""}`}>{moneyOf(t.net_pnl)}</td>
                      <td className={s.num}>{t.realized_net === null ? "—" : moneyOf(t.realized_net)}</td>
                      <td>{t.coverage ?? "UNKNOWN"}</td>
                      <td>
                        <Link className={s.link}
                          href={`/paper-lab?bt=${EXPERIMENT}${runId ? `&run=${encodeURIComponent(runId)}` : ""}&event_id=${encodeURIComponent(t.event_id)}&group=${encodeURIComponent(t.group)}&segment=${encodeURIComponent(t.segment)}&scale=${t.scale}`}>
                          Abrir replay
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {visible.length === 0 && <tr><td colSpan={19} className={s.empty}>
                    {filter === "ganadoras" ? "Sin operaciones ganadoras en esta muestra."
                      : filter === "perdedoras" ? "Sin operaciones perdedoras en esta muestra."
                      : filter === "abiertas" ? "Sin operaciones abiertas."
                      : "Sin operaciones."}</td></tr>}
                </tbody>
              </table>
            </div>
            {!showAll && filtered.length > visible.length &&
              <div className={s.row}><span className={s.note}>Mostrando {visible.length} de {filtered.length} operaciones (orden cronológico).</span>
                <button className={s.ghost} type="button" onClick={() => setShowAll(true)}>Mostrar todas ({filtered.length})</button></div>}
            <p className={s.note}>«Neto (marca)» es la valoración a cierre (incluye operaciones abiertas); «Neto real.» es el
              resultado de las operaciones cerradas y queda vacío (—) para las abiertas. La cobertura y el funding faltantes
              permanecen visibles como UNKNOWN; no se rellenan ni se estiman.</p>
          </div>

          {summary.limitations.length > 0 && (
            <details className={s.details}>
              <summary>Limitaciones y advertencias del experimento</summary>
              <ul>{summary.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </details>
          )}
        </>
      )}

      {status !== "completado" && (
        <div className={s.card}>
          <h3>Resultados</h3>
          <p className={s.note}>Aún no hay resultados completados. Ejecuta el backtest para generar agregados y operaciones.
            Si la tarea falla o queda incompleta, se muestra el estado real; nunca se sustituye por datos de ejemplo.</p>
        </div>
      )}
    </section>
  );
}
