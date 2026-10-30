"use client";

import {
  useCallback, useEffect, useRef, useState,
} from "react";
import {
  formatMoneyPL, formatPricePL, fmtUtcPL, listSessionsApi,
  sessionView, type PaperCandidateDecision, type PaperSessionConfig,
  type PaperSessionState, type PaperCandle,
} from "@/lib/paper-lab-live";
import { buildPaperChartModel } from "@/lib/paper-chart-contract";
import {
  createBackendSession, fetchMarketSeries, marketCandlesToPaper,
  buildEngineeringConfig, splitContextAndOperation, lastContextClose,
  controlBackendSession, fetchBackendSession,
  fetchEngineeringService, startEngineeringService,
  fetchEngineeringDemo, startEngineeringDemo, stopEngineeringDemo,
  ENGINEERING_TRANSPORT_MARKET_STREAM,
  type EngineeringControlAction, type EngineeringDriveState,
  type EngineeringDemoStatus, type EngineeringTransport,
} from "@/lib/session-lab";
import { PaperChart } from "../paper-lab-live/PaperChart";
import { PositionPanel } from "../paper-lab-live/PositionPanel";
import { PnLPanel } from "../paper-lab-live/PnLPanel";
import { EventLog } from "../paper-lab-live/EventLog";
import { ExportPanel } from "../paper-lab-live/ExportPanel";
import { SessionControls } from "../paper-lab-live/SessionControls";
import { SessionPersistence } from "../paper-lab-live/SessionPersistence";
import { SessionStatusPanels } from "./SessionStatusPanels";
import s from "./EngineeringSession.module.css";

// Clave de persistencia del puntero de sesion (solo un identificador, nunca
// estado economico: el estado autoritativo vive en el backend). Cerrar la
// pestaña no detiene al backend: al reabrir, la sesión y su conducción solo
// se observan de nuevo con GET.
const SESSION_ID_STORAGE_KEY = "paper-lab-sesion-ingenieria-id";

// Intervalo de observación: el navegador LEEE el estado del backend; no
// conduce. El avance ocurre en el backend con los eventos del transporte
// local, sin llamadas periodicas a /step.
const OBSERVER_INTERVAL_MS = 800;

// Dos ventanas de CONTEXTO sobre el MISMO simbolo y la MISMA configuracion
// de sesion (modo live: la ventana de operacion la produce el feed del
// servicio de mercado, no el navegador). Se usan para demostrar que, bajo
// igual configuracion, una ventana de contexto distinta fija un entry_px
// distinto (no es un escaner ni una estrategia rentable).
const PREFIX_CONTEXT_COUNT: Record<"A" | "B", number> = { A: 20, B: 35 };
const PREFIX_LABEL: Record<"A" | "B", string> = {
  A: "A (ventana de contexto 20)",
  B: "B (ventana de contexto 35)",
};

// Texto visible de la causa de fin de conducción (moteado del estado del
// drive del backend). SESSION_CLOSED: el motor cerró la sesión; END_OF_TRANSPORT:
// el transporte local se agotó (no hay mas velas reveladas); OPERATOR_STOP:
// el operador detuvo la conducción; SESSION_STOPPED: la sesión quedó
// congelada (detenida); DRIVE_EVENT_LIMIT: techo de seguridad por conducción.
const DRIVE_CAUSE_TEXT: Record<string, string> = {
  SESSION_CLOSED: "Conducción terminada: la sesión se cerró con la gestión de la posición.",
  END_OF_TRANSPORT: "Conducción terminada: el transporte local se agotó (no hay más velas por revelar).",
  OPERATOR_STOP: "Conducción detenida por el operador.",
  SESSION_STOPPED: "Conducción terminada: la sesión quedó congelada (detenida).",
  DRIVE_EVENT_LIMIT: "Conducción detenida: alcanzó el techo de seguridad de eventos (DRIVE_EVENT_LIMIT).",
  IDENTITY_MISMATCH: "Conducción detenida: la identidad del stream (símbolo/intervalo) no coincide con la sesión.",
  TRANSPORT_LOST: "Conducción detenida: el transporte de mercado se perdió (hilo del adaptador terminado).",
};

// Texto visible de la puerta de evaluación live (drive.last_gate). La puerta
// ABSTIENE (no bloquea la conducción): la sesión conserva su decisión hasta
// que el feed vuelve a ser evaluable.
const GATE_CAUSE_TEXT: Record<string, string> = {
  DATA_STALE: "Puerta live: frescura de velas insuficiente para evaluar (DATA_STALE); la conducción espera sin reevaluar.",
  FEED_SILENCE: "Puerta live: silencio del feed (sin velas cerradas dentro del límite, FEED_SILENCE); la sesión conserva su última decisión sin reevaluar.",
  GRID_GAP: "Puerta live: hueco en la rejilla de velas cerradas (GRID_GAP); se abstiene hasta completar la serie.",
  SESSION_NOT_EVALUABLE: "Puerta live: la sesión no está evaluable en este reloj (SESSION_NOT_EVALUABLE).",
  IDENTITY_MISMATCH: "Puerta live: identidad del stream distinta a la de la sesión (IDENTITY_MISMATCH); sin evaluación.",
};

// Estados VISIBLES del servicio de ingeniería: distinguen comprobando /
// arrancando / disponible / detenido / con error. El arranque ocurre SOLO por
// la acción explícita del operador (POST del propio botón); ninguna consulta
// GET ni la apertura de la página inicia procesos.
type EngineeringServiceUiState =
  | "checking" | "starting" | "ready" | "down" | "error";

const SERVICE_CHIP_TEXT: Record<EngineeringServiceUiState, string> = {
  checking: "Comprobando servicio de ingeniería…",
  starting: "Arrancando servicio de ingeniería…",
  ready: "Servicio de ingeniería listo",
  down: "Servicio de ingeniería detenido",
  error: "Servicio de ingeniería con error",
};

// Fuente de mercado (lo que el servicio de ingeniería consume): estado
// VISIBLE ANTES de crear una sesión. Sin fuente conectada/fresca NO se
// crea una sesión que inevitablemente fallaría (aviso previo); una caída
// POSTERIOR sí se registra dentro de la sesión (visible).
type SourceUiState = "checking" | "ready" | "unavailable";

const SOURCE_CHIP_TEXT: Record<SourceUiState, string> = {
  checking: "Comprobando fuente…",
  ready: "Fuente: lista",
  unavailable: "FUENTE NO DISPONIBLE",
};

interface EngineeringSessionProps {
  symbol?: string;
  interval?: string;
  bars?: number;
}

export default function EngineeringSession({
  symbol = "MINAUSDT",
  interval = "1m",
  bars = 90,
}: EngineeringSessionProps) {
  const [state, setState] = useState<PaperSessionState | null>(null);
  const [marketSeries, setMarketSeries] = useState<{
    candles: PaperCandle[];
    context: PaperCandle[];
    indicators: unknown;
    contextBtc: unknown;
    coverage: string;
    receivedAt: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [prefixOption, setPrefixOption] = useState<"A" | "B">("A");
  // entry_px se fija UNA VEZ (antes de evaluar): cierre de la ultima vela de
  // contexto (precio conocido ANTES de la ventana de operacion). Nunca es el
  // cierre de la vela de entrada, con lo que la regla no garantiza entrada por
  // igualdad automatica. Al cambiar de prefijo se conserva.
  const [entryPxFixed, setEntryPxFixed] = useState<number | null>(null);

  // clock_ms del estado autoritativo aplicado por última vez. Se usa para
  // detectar cambios de T (incluido Entrar) y evitar mostrar valores de un T
  // anterior como si fueran actuales mientras se recarga el contexto.
  const lastClockRef = useRef<number | null>(null);

  // --- Conducción autónoma del backend (no del navegador) ------------------
  // La sesión vive en un servicio Python de larga vida (motor paper_lab_engine
  // = autoridad económica única). El proceso backend es único: no hay un
  // proceso Python por tick ni otro gestor paralelo. El navegador solo pide
  // start/stop (control) y OBSERVA leyendo el estado; nunca avanza el reloj.
  const [drive, setDrive] = useState<EngineeringDriveState | null>(null);
  // Ref al último estado observado: evita capturas obsoletas (stale closure).
  const stateRef = useRef<PaperSessionState | null>(null);
  // Ref al último drive observado (runner/evidencia del transporte live).
  const driveRef = useRef<EngineeringDriveState | null>(null);
  // Transporte de la sesión en curso: live (market_stream, default) o
  // local_replay. Tras recuperar una sesión se toma del drive del backend
  // (incluye el transporte persistido aunque el drive esté idle).
  const [transportKind, setTransportKind] = useState<EngineeringTransport>(
    ENGINEERING_TRANSPORT_MARKET_STREAM);
  // Ref a la última identidad observada (para el observador con GetSession).
  const observeRef = useRef(false);
  // Guardia síncrona de arranque: bloquea el segundo click de un gesto doble
  // (ref actualizada sin esperar render de React).
  const startInFlightRef = useRef(false);
  const [refreshing, setRefreshing] = useState(false);

  // Estado del SERVICIO de ingeniería (visto por el BFF con guardia de
  // origen): unknown / checking / starting / ready / down / error. Se
  // consulta al montaje con GET puro (sin arranque); el arranque es una
  // POST acción explícita del operador.
  const [serviceState, setServiceState] = useState<EngineeringServiceUiState>(
    "checking");
  const [serviceDetail, setServiceDetail] = useState<string | null>(null);

  // DEMOSTRACIÓN local (datos simulados; NO Binance): estado visible y
  // control del operador. El GET de montaje no arranca nada; iniciar/
  // detener son POST explícitos con guardia síncrona contra doble clic.
  const [demo, setDemo] = useState<EngineeringDemoStatus | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const demoInFlightRef = useRef(false);

  const [requestIdCounter, setRequestIdCounter] = useState(0);
  const nextRequestId = useCallback(() => {
    const id = "eng-req-" + Date.now() + "-" + requestIdCounter;
    setRequestIdCounter((n) => n + 1);
    return id;
  }, [requestIdCounter]);

  // Pide indicadores / contexto BTC / flujo al backend con el reloj T de la
  // sesion: solo velas conocidas en T, sin futuros. Fuente solo lectura
  // (--no-fetch: cero upstream). symbol/interval se toman de la identidad
  // autoritativa (config de la sesion recuperada) cuando se pasan; de las
  // props del componente para una sesion nueva.
  const loadContextForClock = useCallback(async (atMs: number | null,
    symbolOverride?: string, intervalOverride?: string) => {
    if (atMs == null) return;
    const sym = symbolOverride ?? symbol;
    const ivl = intervalOverride ?? interval;
    const series = await fetchMarketSeries(sym, ivl, bars, atMs, true);
    if (!series) return;
    const receivedAt = Date.now();
    const all = marketCandlesToPaper(series.candles, receivedAt);
    const { context, operation } = splitContextAndOperation(
      all, PREFIX_CONTEXT_COUNT[prefixOption],
    );
    setMarketSeries({
      candles: operation,
      context,
      indicators: series.indicators,
      contextBtc: series.context_btc,
      coverage: "NO_COVERAGE",
      receivedAt,
    });
  }, [symbol, interval, bars, prefixOption]);

  // Actualizacion centralizada de la vista tras cada respuesta autoritativa.
  // Si clock_ms cambia respecto del T aplicado (incluido Entrar), descarta el
  // contexto anterior (no se muestran valores de otro T como actuales) y
  // recarga indicadores / contexto BTC / flujo para el nuevo T con la
  // identidad autoritativa de la sesion (config.symbol / config.interval).
  // En transporte LIVE (market_stream), indicadores/contexto vienen de los
  // bloques de evidencia del STREAM (mismo feed que conduce); el contexto de
  // velas se toma del estado autoritativo (el BFF puede no ver la cache del
  // stream) o de la ventana que el operador eligió (opts.liveContext en la
  // carga inicial). En local_replay se mantiene la recarga por BFF (solo
  // lectura).
  const applyAuthoritative = useCallback(async (
    next: PaperSessionState | null,
    opts?: { liveContext?: PaperCandle[] },
  ) => {
    if (!next) {
      stateRef.current = null;
      setState(null);
      setMarketSeries(null);
      lastClockRef.current = null;
      setRefreshing(false);
      return;
    }
    // Live en la carga inicial de create: el drive aún no existe
    // (applyDrive(null)); la ventana liveContext pasada por startSession
    // indica transporte market_stream. En observación se decide por el
    // runner observado del drive.
    const live = opts?.liveContext != null
      || driveRef.current?.runner === "market_stream";
    const prevClock = lastClockRef.current;
    const clockChanged = prevClock !== null && prevClock !== next.clock_ms;
    const initialLoad = prevClock === null;
    if (clockChanged) {
      setRefreshing(true);
      setMarketSeries(null); // valores de T anterior no se muestran como actuales
    }
    stateRef.current = next;
    setState(next);
    lastClockRef.current = next.clock_ms ?? null;
    try {
      if ((initialLoad || clockChanged) && next.clock_ms != null) {
        if (live) {
          const evidence = driveRef.current?.evidence ?? {};
          setMarketSeries({
            candles: [],
            // Ventana de contexto elegida por el operador en create (live);
            // en recuperación (sin liveContext) se usa la autoritativa.
            context: (initialLoad && opts?.liveContext
              ? opts.liveContext
              : next.context_candles).filter(
              (c) => c.open_time_ms <= (next.clock_ms ?? 0),
            ),
            indicators: evidence.indicators?.block ?? null,
            contextBtc: evidence.context_btc?.block ?? null,
            coverage: "NO_COVERAGE",
            receivedAt: Date.now(),
          });
        } else {
          await loadContextForClock(next.clock_ms, next.config.symbol, next.config.interval);
        }
      }
    } finally {
      setRefreshing(false);
    }
  }, [loadContextForClock]);

  // Set centralizado del drive: estado + ref (la ref evita stale closures
  // en applyAuthoritative dentro del observador).
  const applyDrive = useCallback((next: EngineeringDriveState | null) => {
    driveRef.current = next;
    setDrive(next);
    const runner = next?.runner;
    if (runner === "market_stream" || runner === "local_replay") {
      setTransportKind(runner);
    }
  }, []);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // --- Observador (solo lectura) -------------------------------------------
  // El navegador LEE el estado del backend con GET: observar no conduce. La
  // conducción vive en el backend con los eventos del transporte local y
  // continúa aunque esta pestaña se cierre.
  const observeOnce = useCallback(async () => {
    const current = stateRef.current;
    if (!current) return;
    const result = await fetchBackendSession(current.session_id);
    if (!result.ok || !result.data) {
      setError(result.error ?? "OBSERVE_FAILED");
      return;
    }
    applyDrive(result.data.drive ?? null);
    await applyAuthoritative(result.data.session);
  }, [applyAuthoritative, applyDrive]);

  const observeActive = useCallback(async (sessionId: string) => {
    const result = await fetchBackendSession(sessionId);
    if (!result.ok || !result.data) {
      setError(result.error ?? "OBSERVE_FAILED");
      return null;
    }
    applyDrive(result.data.drive ?? null);
    await applyAuthoritative(result.data.session);
    return result.data.session;
  }, [applyAuthoritative, applyDrive]);

  // Recupera el estado autoritativo tras recarga (incluida posicion abierta)
  // leyendo el servicio backend; la conducción backend siguió avanzando
  // aunque la pestaña estuviera cerrada. La identidad (simbolo/intervalo) se
  // toma del config de la sesion recuperada, nunca de las propiedades por
  // defecto del componente.
  const recoverAuthoritative = useCallback(async (sessionId: string) => {
    const next = await observeActive(sessionId);
    if (next) {
      setStarted(true);
      setError(null);
      return next;
    }
    return null;
  }, [observeActive]);

  useEffect(() => {
    const stored = typeof localStorage !== "undefined"
      ? localStorage.getItem(SESSION_ID_STORAGE_KEY)
      : null;
    if (stored && !state && !observeRef.current) {
      observeRef.current = true;
      const handle = setTimeout(() => {
        void recoverAuthoritative(stored).catch(() => { /* persistencia opcional */ });
      }, 0);
      return () => clearTimeout(handle);
    }
  }, [state, recoverAuthoritative]);

  // Estado del servicio al montaje: GET puro (consulta; NUNCA arranca nada).
  // Abrir la página inicia cero procesos: el marcador informa honestamente
  // si el servicio está detenido. El estado inicial es "checking".
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchEngineeringService();
      if (cancelled) return;
      const info = result.data;
      if (!result.ok || !info) {
        setServiceState("error");
        setServiceDetail(result.detail ?? result.error ?? "sin respuesta del BFF");
        return;
      }
      if (info.state === "ready") {
        setServiceState("ready");
        setServiceDetail(info.pid != null ? `pid ${info.pid}` : null);
      } else if (info.state === "down") {
        setServiceState("down");
        setServiceDetail(info.detail ?? null);
      } else {
        setServiceState("error");
        setServiceDetail(info.detail ?? "identidad del servicio no verificable");
      }
    })().catch(() => {
      if (!cancelled) setServiceState("error");
    });
    return () => { cancelled = true; };
  }, []);

  // DEMOSTRACIÓN local: estado visible (GET puro en montaje + refresco
  // acotado cada 10 s). Nada de esto arranca procesos.
  const [nowMs, setNowMs] = useState<number>(0);
  const refreshDemo = useCallback(async () => {
    const result = await fetchEngineeringDemo();
    if (result.ok && result.data) setDemo(result.data);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchEngineeringDemo();
      if (!cancelled && result.ok && result.data) {
        setDemo(result.data);
        setNowMs(Date.now());
      }
    })();
    const timer = setInterval(() => {
      void (async () => {
        const result = await fetchEngineeringDemo();
        if (!cancelled && result.ok && result.data) {
          setDemo(result.data);
          setNowMs(Date.now());
        }
      })();
    }, 10_000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  // Puerta de arranque explícito: usada SOLO por el click del operador.
  // Comprueba (GET) y, si está detenido, arranca la instancia canónica del
  // proyecto vía BFF (readiness con límite + identidad verificada). Si ya
  // está disponible no vuelve a arrancar nada (idempotente).
  const ensureService = useCallback(async (): Promise<boolean> => {
    let info = (await fetchEngineeringService()).data;
    if (!info || info.state !== "ready") {
      if (info?.state === "unidentified") {
        setServiceState("error");
        setServiceDetail(info.detail
          ?? "puerto ocupado por un servicio de identidad no verificable");
        setError(
          "SERVICIO_DE_INGENIERIA: el puerto del servicio lo ocupa un proceso no identificable; no se reutiliza ni se detiene. Deténgalo manualmente si corresponde."
        );
        return false;
      }
      setServiceState("starting");
      setServiceDetail(null);
      const started = await startEngineeringService();
      if (!started.ok || !started.data) {
        setServiceState("error");
        setServiceDetail(started.detail ?? started.error ?? "sin detalle");
        setError(
          `SERVICIO_DE_INGENIERIA: el arranque del servicio falló (${started.error ?? "desconocido"})${started.detail ? ` — ${started.detail}` : ""}. No quedó ninguna sesión creada.`
        );
        return false;
      }
      info = (await fetchEngineeringService()).data;
      if (!info || info.state !== "ready") {
        setServiceState("error");
        setServiceDetail("arrancado pero la verificación de identidad falló");
        setError("SERVICIO_DE_INGENIERIA: instancia arrancada sin identidad verificable.");
        return false;
      }
    }
    setServiceState("ready");
    setServiceDetail(info.pid != null ? `pid ${info.pid}` : null);
    return true;
  }, []);

  // --- Demostración local: control del operador (POST explícito) -----------
  const startDemoAction = useCallback(async () => {
    // Guardia SÍNCRONA contra doble clic (el disabled de React no lo es).
    if (demoInFlightRef.current) return;
    demoInFlightRef.current = true;
    setDemoBusy(true);
    try {
      const result = await startEngineeringDemo();
      if (!result.ok) {
        setError(
          `DEMOSTRACION_LOCAL: el arranque falló (${result.error ?? "desconocido"})` +
          `${result.detail ? ` — ${result.detail}` : ""}. No quedó ninguna sesión creada.`);
      }
      await refreshDemo();
    } catch (exc: unknown) {
      setError(`DEMOSTRACION_LOCAL: ${exc instanceof Error ? exc.message : String(exc)}`);
    } finally {
      demoInFlightRef.current = false;
      setDemoBusy(false);
    }
  }, [refreshDemo]);

  const stopDemoAction = useCallback(async () => {
    if (demoInFlightRef.current) return;
    demoInFlightRef.current = true;
    setDemoBusy(true);
    try {
      const result = await stopEngineeringDemo();
      if (!result.ok) {
        setError(
          `DEMOSTRACION_LOCAL: la parada falló (${result.error ?? "desconocido"})` +
          `${result.detail ? ` — ${result.detail}` : ""}. Los recursos sin identidad verificable NO se detienen.`);
      }
      await refreshDemo();
    } catch (exc: unknown) {
      setError(`DEMOSTRACION_LOCAL: ${exc instanceof Error ? exc.message : String(exc)}`);
    } finally {
      demoInFlightRef.current = false;
      setDemoBusy(false);
    }
  }, [refreshDemo]);

  // --------------------------------------------------------------------------
  // Conducción backend: arranque, observación y parada.
  // --------------------------------------------------------------------------

  // Control explícito en el backend (por petición del navegador). Cada acción
  // es una transición única idempotente con revisión; el avance autónomo
  // nunca lo inicia el frontend: el backend lo conduce con los eventos del
  // transporte local.
  const manualControl = useCallback(async (
    action: EngineeringControlAction,
    opts?: { expectedRevision?: number | null; requestId?: string | null },
  ): Promise<PaperSessionState | null> => {
    const current = stateRef.current;
    if (!current) return null;
    setLoading(true);
    setError(null);
    try {
      const result = await controlBackendSession(
        current.session_id, action, {
          expectedRevision: opts?.expectedRevision ?? current.revision,
          requestId: opts?.requestId ?? nextRequestId(),
        },
      );
      if (!result.ok) {
        setError(result.error ?? `CONTROL_${action}_FAILED`);
        if (result.status === 409) await observeActive(current.session_id);
        return null;
      }
      if (!result.data) return null;
      applyDrive(result.data.drive ?? null);
      await applyAuthoritative(result.data.session);
      return result.data.session;
    } finally {
      setLoading(false);
    }
  }, [nextRequestId, applyAuthoritative, observeActive, applyDrive]);

  // Observador: mientras la página está abierta y hay una sesión, LEE el
  // estado del backend con GET al intervalo de observación. Cerrar la
  // pestaña detiene el observador y NO la conducción: el backend continúa.
  const sessionId = state?.session_id ?? null;
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      await observeOnce();
    };
    const handle = setInterval(tick, OBSERVER_INTERVAL_MS);
    void tick();
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [sessionId, observeOnce]);

  // Causa visible de fin de conducción (moteada desde el estado del drive).
  const driveCause = drive?.cause ?? null;
  const driveRunning = drive?.state === "running";

  // Puerta de evaluación live visible (drive.last_gate): la causa explica
  // por qué la sesión se abstiene de reevaluar (silencio, hueco, frescura).
  // Se muestra también la nota del backend si existe.
  const gate = drive?.last_gate ?? null;
  const gateCause = gate?.cause ?? null;
  const gateVisible = gate != null && (gateCause != null || gate?.ok === false);

  // Panel de evidencia del transporte live: identidad del stream (url del
  // servicio de mercado, barras), marca de agua y bloques de evidencia
  // (indicadores / contexto BTC) con su hora de recepción. Todo viene del
  // drive observado con GET; el navegador no interpreta nada.
  const liveDrive = transportKind === ENGINEERING_TRANSPORT_MARKET_STREAM
    && drive?.runner === "market_stream"
    ? drive
    : null;
  const evidenceEntries = liveDrive
    ? Object.entries(liveDrive.evidence ?? {})
    : [];

  const startSession = useCallback(async () => {
    // Guardia SÍNCRONA contra doble clic: un segundo click puede llegar
    // antes de que React re-renderice el `disabled` del botón (el estado de
    // React no es síncrono); la ref bloquea el segundo arranque en el MISMO
    // gesto. Sin esto, un doble clic creaba DOS sesiones (duplicado).
    if (startInFlightRef.current) return;
    startInFlightRef.current = true;
    setLoading(true);
    setError(null);
    setStarted(false);
    // Puerta EXPLÍCITA del operador: comprobar el servicio y, si está
    // detenido, arrancar la instancia canónica del proyecto (readiness con
    // límite + identidad verificada). Si falla, no se crea ninguna sesión.
    const serviceOk = await ensureService();
    if (!serviceOk) {
      setLoading(false);
      startInFlightRef.current = false;
      return;
    }
    try {
      // AVISO PREVIO de fuente (distingue servicio / fuente / sesión): sin
      // fuente conectada y fresca NO se crea una sesión que inevitablemente
      // fallaría; una caída POSTERIOR sí queda registrada dentro de la
      // sesión (visible, sin decisión falsa).
      const demoInfo = (await fetchEngineeringDemo()).data;
      if (demoInfo) setDemo(demoInfo);
      if (!demoInfo || !demoInfo.source.available) {
        setError(
          "FUENTE NO DISPONIBLE: la fuente de mercado configurada no responde. " +
          "Inicie la demostración local (datos simulados) o conecte la fuente " +
          "autorizada; no se creó ninguna sesión."
        );
        return;
      }
      setTransportKind(ENGINEERING_TRANSPORT_MARKET_STREAM);
      // Hasta 300 velas recientes por símbolo (ventana reciente, no backfill
      // de la caché antigua). La caché antigua se conserva; no se conecta
      // mediante backfill con la nueva sesión.
      const series = await fetchMarketSeries(symbol, interval, 300);
      if (!series || !series.candles || series.candles.length === 0) {
        setError("SERIES_EMPTY: no hay velas en cache local para el símbolo.");
        setLoading(false);
        return;
      }

      const receivedAt = Date.now();
      const all = marketCandlesToPaper(series.candles, receivedAt);
      // Modo live: SOLO la ventana de CONTEXTO viaja en create; la ventana
      // de operación la produce el feed del servicio de mercado (velas
      // cerradas por eventos SSE). Nada de listas de velas futuras.
      const contextCount = PREFIX_CONTEXT_COUNT[prefixOption];
      // Calentamiento mínimo: al menos contextCount velas cerradas para fijar
      // entry_px y calentar indicadores (velocity_bps_5 necesita 5,
      // rel_volume_10 y vwap_typical_10 necesitan 10).
      if (all.length < contextCount) {
        setError(
          `INSUFICIENT_CANDLES: se necesitan al menos ${contextCount} velas cerradas para calentar la sesión; hay ${all.length}.`,
        );
        setLoading(false);
        return;
      }
      const context = all.slice(Math.max(0, all.length - contextCount));
      if (context.length < 2) {
        setError("INSUFICIENT_CANDLES: cache local sin suficientes velas para la ventana de contexto.");
        setLoading(false);
        return;
      }

      // No usar last_cache_close + 1 como inicio de operación si la caché
      // está obsoleta. La última vela de contexto debe estar cercana al
      // presente para que from_ms (= última vela de contexto + 1 paso) caiga
      // dentro del rango que el feed público puede entregar.
      const lastCtx = context[context.length - 1]!;
      const lastCtxCloseMs = lastCtx.close_time_ms ?? lastCtx.open_time_ms;
      const nowMs = Date.now();
      const stepMs = 60_000; // 1m
      const maxStalenessMs = 2 * stepMs; // tolerancia de 2 pasos de rejilla
      if (nowMs - lastCtxCloseMs > maxStalenessMs) {
        setError(
          "CACHE_OBSOLETO: la última vela de contexto está demasiado atrasada " +
          `(última: ${new Date(lastCtxCloseMs).toISOString()}, hace ${Math.round(
            (nowMs - lastCtxCloseMs) / 1000,
          )} s). No se puede iniciar sesión live sin continuidad verificada. ` +
          "Esperar a nuevos datos o usar contexto reciente.",
        );
        setLoading(false);
        return;
      }

      // Fijar entry_px UNA VEZ antes de evaluar: cierre de la última vela de
      // contexto (precio conocido ANTES de la ventana de operación). Nunca es
      // el cierre de la vela de entrada, con lo que la regla no garantiza
      // entrada por igualdad automática. Al cambiar de ventana se conserva.
      let entryPx = entryPxFixed;
      if (entryPx == null) {
        entryPx = lastContextClose(context);
        if (entryPx == null) {
          setError("CLOCK_REQUIRED: no se pudo establecer el precio de referencia.");
          setLoading(false);
          return;
        }
        setEntryPxFixed(entryPx);
      }

      const config: PaperSessionConfig = buildEngineeringConfig({
        symbol, interval, entryPx,
        horizonMs: 30 * 60 * 1000,
      });

      // Rango de operación esperado para el stream: from_ms = primera frontera
      // después del contexto (continuidad exacta con last_ctx + 1), to_ms =
      // reloj de pared actual. El servicio usa from_ms para fijar
      // deliver_from_ms y no entregar velas ya cubiertas por el contexto.
      const fromMs = lastCtxCloseMs + 1;
      const toMs = nowMs;

      // La sesión se crea EN el backend (motor Python + transporte
      // market_stream); la evaluación y todo avance lo conduce el backend
      // con los eventos del servicio de mercado. El navegador no evalúa ni
      // programa pasos.
      const created = await createBackendSession({
        config, candles: [], context,
        transport: ENGINEERING_TRANSPORT_MARKET_STREAM,
        requestId: nextRequestId(),
        fromMs,
        toMs,
      });
      if (!created.ok || !created.data) {
        setError(created.error ?? "CREATE_FAILED");
        setLoading(false);
        return;
      }
      applyDrive(null); // nuevo backend: el drive previo no aplica
      // applyAuthoritative (carga inicial) fija el contexto visible de la
      // ventana elegida; los indicadores/contexto llegarán por el stream.
      await applyAuthoritative(created.data.session, { liveContext: context });
      localStorage.setItem(SESSION_ID_STORAGE_KEY, created.data.session.session_id);
      setStarted(true);

      // Conducción autónoma del backend: el avance ocurre por los eventos
      // del servicio de mercado (SSE consumido por el servicio); una
      // abstención (SIN_ENTRADA/sin_iniciar) es temporal y sigue recibiendo
      // eventos para reevaluar sin intervención.
      await manualControl("start", { requestId: nextRequestId() });
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
      startInFlightRef.current = false;
    }
  }, [symbol, interval, bars, prefixOption, entryPxFixed, applyAuthoritative, nextRequestId, manualControl, ensureService, applyDrive]);

  const changePrefix = useCallback(async (next: "A" | "B") => {
    // La eleccion de prefijo antes de iniciar solo fija la opcion para el
    // proximo "Iniciar sesion" (aun no hay sesion que reconstruir); con una
    // sesion viva se reconstruye la sesion con el MISMO entry_px fijo.
    setPrefixOption(next);
    if (!state) return;
    // Volver a crear y evaluar con la MISMA entry_px fija pero distinto
    // prefijo de datos, para demostrar admision vs abstencion bajo igual
    // configuracion.
    setLoading(true);
    setError(null);
    try {
      const series = await fetchMarketSeries(symbol, interval, bars);
      if (!series || !series.candles || series.candles.length === 0) {
        setError("SERIES_EMPTY: no hay velas en cache local para el simbolo.");
        setLoading(false);
        return;
      }
      const receivedAt = Date.now();
      const all = marketCandlesToPaper(series.candles, receivedAt);
      const contextCount = PREFIX_CONTEXT_COUNT[next];
      const operationNeeded = 40;
      const window = contextCount + operationNeeded;
      const recent = all.slice(Math.max(0, all.length - window));
      if (recent.length < contextCount + 2) {
        setError("INSUFICIENT_CANDLES: cache local sin suficientes velas.");
        setLoading(false);
        return;
      }
      const { context, operation } = splitContextAndOperation(recent, contextCount);
      const firstOp = operation[0];
      if (operation.length === 0 || !firstOp || firstOp.close == null || firstOp.close_time_ms == null) {
        setError("INSUFICIENT_CANDLES: primera vela de operacion sin cierre.");
        setLoading(false);
        return;
      }
      const entryPx = entryPxFixed;
      if (entryPx == null) {
        setError("ENTRY_PX_MISSING: precio de referencia no fijado.");
        setLoading(false);
        return;
      }
      const config: PaperSessionConfig = buildEngineeringConfig({
        symbol, interval, entryPx,
        horizonMs: 30 * 60 * 1000,
      });
      // Cambio de prefijo: se reconstruye la sesión en el backend con la
      // misma configuración (motor y conducción idénticos a Iniciar sesion).
      const created = await createBackendSession({
        config, candles: operation, context,
      });
      if (!created.ok || !created.data) {
        setError(created.error ?? "CREATE_FAILED");
        setLoading(false);
        return;
      }
      applyDrive(null); // nuevo backend: el drive previo no aplica
      await applyAuthoritative(created.data.session);
      await loadContextForClock(created.data.session.clock_ms ?? null, symbol, interval);
      localStorage.setItem(SESSION_ID_STORAGE_KEY, created.data.session.session_id);
      setStarted(true);

      // Conducción backend: el avance ocurre por los eventos del transporte
      // local; abstenciones temporales siguen esperando datos nuevos.
      await manualControl("start", { requestId: nextRequestId() });
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, bars, entryPxFixed, nextRequestId, applyAuthoritative, loadContextForClock, state, manualControl, applyDrive]);

  const stopSession = useCallback(async () => {
    if (!state) return;
    // Política de parada explícita en el backend: primero conduce stop (la
    // conducción autónoma queda detenida con causa visible) y luego congela
    // la sesión (detenida) sin inventar cierre. La posición queda tal cual.
    setLoading(true);
    setError(null);
    try {
      await manualControl("stop");
      await manualControl("stop_session");
    } finally {
      setLoading(false);
    }
  }, [state, manualControl]);

  const handleEnter = useCallback(async () => {
    // "Entrar": un evento manual = un avance; el motor decide el fill.
    await manualControl("step");
  }, [manualControl]);

  const handleStep = useCallback(async () => {
    // "Paso a paso": el backend interpreta un evento del transporte local
    // (reveled + reevaluación si solo hay abstención temporal vigente).
    await manualControl("step");
  }, [manualControl]);

  const handleExit = useCallback(async () => {
    await manualControl("exit");
  }, [manualControl]);

  const handleRestart = useCallback(async () => {
    await manualControl("restart");
  }, [manualControl]);

  const handleDecide = useCallback(async (_decision: PaperCandidateDecision) => {
    await manualControl("evaluate");
  }, [manualControl]);

  // sessionReady es un objeto combinado que TypeScript puede reducir a
  // no-nulo dentro de la rama correspondiente del condicional JSX.
  const sessionReady = state && marketSeries ? { state, marketSeries } : null;

  const cfg = state?.config;
  const pos = state?.position;
  const csts = state?.costs;
  const evts = state?.events ?? [];
  const res = state?.result;
  const clockMs = state?.clock_ms ?? null;
  const v = state ? sessionView(state) : null;
  const opn = pos?.open === true;
  const fin = state ? (state.status === "cerrada" || state.status === "detenida") : false;

  const chartModel = sessionReady
    ? buildPaperChartModel(
      {
        ...sessionReady.state,
        candles: sessionReady.state.candles.filter(
          (c) => c.open_time_ms <= (sessionReady.state.clock_ms ?? 0),
        ),
        context_candles: sessionReady.state.context_candles.filter(
          (c) => c.open_time_ms <= (sessionReady.state.clock_ms ?? 0),
        ),
      },
      { fixtureId: null },
    )
    : null;

  const abstentionReason =
    (cfg?.decision === "SIN_ENTRADA" || cfg?.decision === "DESCARTADO")
      ? cfg?.decision_reason ?? null
      : null;

  // sessionReady garantiza que state es no-nulo, por tanto v y chartModel
  // también lo son dentro de la rama correspondiente.
  const vReady = v!;
  const chartModelReady = chartModel!;

  // Titulo y fuente visibles coherentes con el transporte de la sesion:
  // live consume el servicio de mercado existente (SSE, solo loopback);
  // local_replay reproduce velas ya conocidas con cadencia.
  const transportTitle = transportKind === ENGINEERING_TRANSPORT_MARKET_STREAM
    ? "Sesion de ingenieria - transporte market_stream (live)"
    : "Sesion de ingenieria - transporte local (local_replay)";
  const transportSource = transportKind === ENGINEERING_TRANSPORT_MARKET_STREAM
    ? "LIVE - servicio de mercado (SSE, solo loopback); solo velas cerradas conducen"
    : "LOCAL SIMULADA - cache local (klines), client=None, 0 upstream";

  // Fuente y demo: estados derivados para los chips visibles.
  const sourceUiState: SourceUiState = demo === null
    ? "checking"
    : (demo.engineering.state === "ready" && demo.source.available
      ? "ready"
      : "unavailable");
  const demoActive = demo?.demo.active === true && !demo.demo.expired;
  const demoText = (() => {
    if (!demo || (!demo.demo.present && !demo.demo.active)) {
      return "Inactiva — sin recursos de demostración propios";
    }
    if (demo.demo.expired) {
      return "Expirada (duración acotada) — pulse Detener demostración y vuelva a iniciar";
    }
    if (demoActive) {
      const anchor = demo.demo.started_at_ms ?? 0;
      const elapsed = nowMs > anchor ? nowMs - anchor : 0;
      const remainMin = demo.demo.max_runtime_s != null
        ? Math.max(0, Math.round(
            (demo.demo.max_runtime_s * 1000 - elapsed) / 60_000))
        : null;
      return `Activa — productor pid ${demo.demo.producer.pid ?? "?"}, fuente ` +
        `${demo.source.url ?? "?"} (datos simulados` +
        `${remainMin != null ? `, expira en ~${remainMin} min` : ""})`;
    }
    return "Detenida";
  })();

  return (
    <section className={s.root} aria-label={transportTitle}>
      <header className={s.header}>
        <div className={s.titleBlock}>
          <h1>{transportTitle}</h1>
          <p className={s.subtitle}>
            Flujo: transporte (live: velas cerradas del servicio de mercado;
            replay: cache local) → grafico → indicadores / contexto BTC
            (evidencia del stream, recalculados con el reloj T de la sesion) →
            candidato → decision → posicion paper → gestion → cierre →
            exportacion. El backend es la autoridad; el navegador solo
            solicita acciones y presenta estados.
          </p>
        </div>
        <div className={s.actions}>
          <label className={s.prefixLabel}>Ventana de contexto:</label>
          <select
            value={prefixOption}
            onChange={(e) => changePrefix((e.target.value as "A" | "B") ?? "A")}
            disabled={loading || !!sessionReady || refreshing}
            className={s.prefixSelect}
          >
            <option value="A">{PREFIX_LABEL.A}</option>
            <option value="B">{PREFIX_LABEL.B}</option>
          </select>
          <button
            type="button"
            className={s.startButton}
            disabled={loading || started || !!sessionReady}
            onClick={startSession}
            data-testid="btn-iniciar-sesion"
          >
            {loading ? "Iniciando..." : "Iniciar sesion"}
          </button>
          {/* Estado explícito del servicio: distingue detenido / arrancando /
              disponible / error. El GET de montaje no inicia procesos. */}
          <span
            className={s.serviceChip ?? s.autonomousChip}
            data-testid="service-chip"
            data-state={serviceState}
            data-service-pid={serviceDetail ?? undefined}
          >
            {SERVICE_CHIP_TEXT[serviceState]}
          </span>
          {/* Fuente: estado visible ANTES de crear la sesión (sin fallback
              silencioso). Con fuente caída, Iniciar sesión avisa
              FUENTE NO DISPONIBLE y NO crea sesión. */}
          <span
            className={s.sourceChip ?? s.serviceChip}
            data-testid="source-chip"
            data-state={sourceUiState}
          >
            {SOURCE_CHIP_TEXT[sourceUiState]}
          </span>
          <button
            type="button"
            className={s.stopButton}
            disabled={loading || !started || !state}
            onClick={stopSession}
            data-testid="btn-detener-sesion"
          >
            Detener sesion
          </button>
          {driveRunning && (
            <span className={s.autonomousChip} data-state="autonomo">
              Autónomo (backend)
            </span>
          )}
        </div>
      </header>

      {/* DEMOSTRACIÓN local — datos simulados: control visible del operador.
          Recursos propios identificados y acotados (productor WS loopback +
          servicio de mercado --transport local). Claramente separada de la
          futura fuente Binance pública (autorización y presupuesto aparte);
          nunca usa el servicio preexistente 8792 ni transporte público. */}
      <div
        className={s.card}
        data-testid="demo-card"
        data-active={demoActive ? "true" : "false"}
      >
        <strong>Demostración local — datos simulados (no Binance)</strong>
        <p className={s.small} data-testid="demo-status">{demoText}</p>
        <button
          type="button"
          className={s.startButton}
          disabled={demoBusy || demoActive}
          onClick={startDemoAction}
          data-testid="btn-iniciar-demo"
        >
          {demoBusy ? "Gestionando demostración…" : "Iniciar demostración"}
        </button>
        <button
          type="button"
          className={s.stopButton}
          disabled={demoBusy || !demoActive}
          onClick={stopDemoAction}
          data-testid="btn-detener-demo"
        >
          Detener demostración
        </button>
      </div>

      {error && (
        <div className={s.errorBanner} role="alert" data-testid="session-error">
          <strong>Error:</strong> {error}
          <button
            type="button"
            className={s.recoverButton}
            onClick={() => state && recoverAuthoritative(state.session_id)}
          >
            Recuperar estado autoritativo
          </button>
        </div>
      )}

      {state ? (
        <div>
          {refreshing && marketSeries == null ? (
            <p className={s.note} role="status">
              Actualizando indicadores y contexto al reloj T de la sesión…
            </p>
          ) : null}
          {sessionReady ? (
            <div>
              <SessionStatusPanels
                state={sessionReady.state}
                marketSymbol={sessionReady.state.config.symbol}
                source={transportSource}
                freshness={{
                  received: vReady.cursor,
                  cursor: vReady.cursor,
                  total: vReady.n,
                  clockMs: sessionReady.state.clock_ms,
                  endOfData: fin && opn && res?.open_at_end === true,
                  stale: false,
                }}
                indicators={sessionReady.marketSeries.indicators}
                contextBtc={sessionReady.marketSeries.contextBtc}
                flowCoverage={sessionReady.marketSeries.coverage}
                lastError={error}
                abstentionReason={abstentionReason}
              />
              {driveRunning && (
                <p className={s.note} role="status" data-testid="session-autonomous">
                  Conducción backend activa: el servicio avanza el reloj con
                  los eventos del transporte local y gestiona la posición sin
                  intervención del navegador. Use Detener sesión para congelar
                  la sesión.
                </p>
              )}
              {driveCause && (
                <p className={s.note} role="status" data-testid="session-drive-cause">
                  {DRIVE_CAUSE_TEXT[driveCause] ?? driveCause}
                </p>
              )}
              {gateVisible && (
                <p className={s.note} role="status" data-testid="session-abstention-gate">
                  {GATE_CAUSE_TEXT[gateCause ?? ""] ?? `Puerta live: ${gateCause ?? "no evaluable"}`}
                  {gate?.note ? ` ${gate.note}.` : ""}
                  {gate?.silence_ms != null && (
                    <span>
                      {" "}Silencio medido entre disparos: {Math.round(gate.silence_ms)} ms
                      {" "}(límite {Math.round(gate.live_silence_ms ?? 0)} ms).
                    </span>
                  )}
                </p>
              )}
              {liveDrive && (
                <section
                  className={s.cardFull}
                  aria-label="Evidencia del transporte de mercado"
                  data-testid="stream-evidence"
                >
                  <h3>Transporte market_stream (evidencia del stream)</h3>
                  <div className={s.exportMeta}>
                    <div className={s.row}>
                      <span className={s.k}>servicio de mercado</span>
                      <span className={s.v + " " + s.mono}>{liveDrive.market_url ?? "-"}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>barras del snapshot</span>
                      <span className={s.v}>{liveDrive.bars ?? "-"}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>marca de agua (última vela cerrada)</span>
                      <span className={s.v + " " + s.mono}>
                        {liveDrive.watermark != null ? fmtUtcPL(liveDrive.watermark) : "-"}
                      </span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>eventos del transporte</span>
                      <span className={s.v}>{liveDrive.transport_events ?? 0}</span>
                    </div>
                    {evidenceEntries.map(([kind, block]) => (
                      <div className={s.row} key={kind}>
                        <span className={s.k}>evidencia {kind}</span>
                        <span className={s.v}>
                          recibida {fmtUtcPL(block?.received_at_ms ?? null)} (pared)
                        </span>
                      </div>
                    ))}
                    {evidenceEntries.length === 0 && (
                      <div className={s.row}>
                        <span className={s.k}>evidencia</span>
                        <span className={s.v}>
                          sin bloques aún (UNKNOWN hasta que el stream publique)
                        </span>
                      </div>
                    )}
                  </div>
                  <p className={s.note}>
                    Indicadores y contexto BTC provienen de los bloques de
                    evidencia del MISMO stream que conduce la sesión; la
                    recepción (pared) se muestra junto a la marca de agua del
                    feed (evento). Sin bloque recibido, el panel muestra
                    UNKNOWN: no se inventan valores.
                  </p>
                </section>
              )}

              <SessionControls
                status={sessionReady.state.status}
                // Durante la autonomía el backend conduce las transiciones; el
                // operador no pulsa "Entrar" ni "Paso a paso" ni las necesita.
                canEnter={vReady.canEnter && !driveRunning}
                canStep={vReady.canStep && !driveRunning}
                canExit={vReady.canExit}
                canRestart={vReady.canRestart}
                canStop={vReady.canStop}
                canDecide={vReady.canDecide}
                decision={sessionReady.state.config.decision ?? null}
                onDecide={handleDecide}
                onEnter={handleEnter}
                onStep={handleStep}
                onExit={handleExit}
                onRestart={handleRestart}
                onStop={stopSession}
                stepMs={1200}
              />

              <div className={s.grid}>
                <section className={s.cardFull} aria-label="Grafico de operacion">
                  <div className={s.chartHead}>
                    <h3>
                      Grafico - velas, niveles y eventos (
                      {sessionReady.state.config.interval},
                      {transportKind === ENGINEERING_TRANSPORT_MARKET_STREAM
                        ? " live)"
                        : " simulacion)"}
                    </h3>
                    <span className={s.sourceChip}>
                      Fuente: {transportKind === ENGINEERING_TRANSPORT_MARKET_STREAM
                        ? `LIVE stream (${sessionReady.state.config.symbol})`
                        : `LOCAL SIMULADA (${sessionReady.state.config.symbol})`}
                    </span>
                  </div>
                  <div className={s.chartLegend} aria-label="Leyenda del grafico">
                    <span><i className={s.swContext} aria-hidden="true"></i> contexto conocido</span>
                    <span><i className={s.swReplay} aria-hidden="true"></i> velas reveladas</span>
                    <span><i className={s.swOpen} aria-hidden="true"></i> solo-open (open, sin OHLC)</span>
                    {chartModelReady.operation.signal && (
                      <span><i className={s.swSignal} aria-hidden="true"></i> senal</span>
                    )}
                    {chartModelReady.operation.pending_entry && (
                      <span><i className={s.swPending} aria-hidden="true"></i> entrada pendiente (no ejecutada)</span>
                    )}
                    {chartModelReady.operation.entry && (
                      <span><i className={s.swEntry} aria-hidden="true"></i> Entrada {formatPricePL(chartModelReady.operation.entry.px)}</span>
                    )}
                    {chartModelReady.operation.stop_effective_px != null && (
                      <span><i className={s.swStop} aria-hidden="true"></i> Stop efectivo {formatPricePL(chartModelReady.operation.stop_effective_px)}</span>
                    )}
                    {chartModelReady.operation.exit && (
                      <span><i className={s.swExit} aria-hidden="true"></i> Salida {formatPricePL(chartModelReady.operation.exit.px)} ({chartModelReady.operation.exit.reason ?? "-"})</span>
                    )}
                  </div>
                  <div className={s.chartWrap}>
                    {chartModel && <PaperChart model={chartModel} />}
                  </div>
                  <p className={s.note}>
                    Solo velas conocidas en T; open conocido al abrir y OHLC completo
                    solo al cierre. La vela solo-open se marca como punto ambar y no
                    se interpola. Entrada y stop salen de position.entry_px /
                    position.stop_px efectivos; la salida solo se dibuja con
                    exit_executed=true. Los indicadores y el contexto BTC se
                    recalculan en el backend con el reloj T de la sesion (sin
                    futuros); sin cobertura de flujo para el instante, se muestra
                    UNKNOWN. Volumen e indicadores de negociacion no los produce el
                    backend en esta fase: se muestran como UNKNOWN.
                  </p>
                </section>
              </div>

              <div className={s.grid}>
                <section className={s.card}>
                  <PositionPanel position={sessionReady.state.position} direction={sessionReady.state.config.direction} />
                </section>
                <section className={s.card}>
                  <PnLPanel
                    finished={fin}
                    entered={opn}
                    costs={csts!}
                    unrealized={sessionReady.state.position.unrealized_net}
                    result={res!}
                    exitExecuted={res?.exit_executed === true}
                  />
                </section>
              </div>

              <div className={s.grid}>
                <section className={s.cardFull}>
                  <h3>Historial de eventos</h3>
                  <EventLog events={evts} />
                </section>
              </div>

              <div className={s.grid}>
                <section className={s.card}>
                  <h3>Exportacion</h3>
                  <ExportPanel
                    state={sessionReady.state}
                    result={res ?? null}
                    onDownloadJson={(payload: string, fileName: string) => {
                      const blob = new Blob([payload], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url; a.download = fileName; a.click();
                      URL.revokeObjectURL(url);
                    }}
                    onDownloadCsv={(payload: string, fileName: string) => {
                      const blob = new Blob([payload], { type: "text/csv" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url; a.download = fileName; a.click();
                      URL.revokeObjectURL(url);
                    }}
                  />
                  <div className={s.exportMeta}>
                    <div className={s.row}>
                      <span className={s.k}>session_id</span>
                      <span className={s.v + " " + s.mono}>{sessionReady.state.session_id}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>simbolo</span>
                      <span className={s.v}>{sessionReady.state.config.symbol}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>intervalo</span>
                      <span className={s.v}>{sessionReady.state.config.interval}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>config_hash</span>
                      <span className={s.v + " " + s.mono}>{sessionReady.state.config_hash}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>motor</span>
                      <span className={s.v + " " + s.mono}>{sessionReady.state.engine_version}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>regla</span>
                      <span className={s.v + " " + s.mono}>{sessionReady.state.config.rule_version}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>reloj T</span>
                      <span className={s.v}>{fmtUtcPL(clockMs)}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>revision</span>
                      <span className={s.v}>{sessionReady.state.revision}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>prefijo</span>
                      <span className={s.v}>{prefixOption}</span>
                    </div>
                    <div className={s.row}>
                      <span className={s.k}>entry_px fijo</span>
                      <span className={s.v}>{entryPxFixed != null ? entryPxFixed.toFixed(4) : "-"}</span>
                    </div>
                  </div>
                </section>
              </div>

            </div>
            ) : (
              <p className={s.note}>
                Contexto de mercado sin cobertura para el reloj T actual (UNKNOWN).
              </p>
            )}
          <SessionPersistence
            sessions={[]}
            onLoad={recoverAuthoritative}
            onSave={async () => {
              const s = await listSessionsApi();
              if (s.ok) {
                // refrescar lista sin efectos
              }
            }}
          />
        </div>
      ) : (
        <section className={s.empty}>
          <p>Sesion no iniciada. Abrir el dashboard no inicia servicios ni operaciones.</p>
          <p className={s.emptyNote}>
            Seleccione una ventana de contexto y pulse Iniciar sesion para
            abrir la sesion de ingenieria de {symbol}: la ventana de operacion
            la produce el feed del servicio de mercado (solo velas cerradas);
            el contexto inicial viene de la cache local.
          </p>
        </section>
      )}
    </section>
  );
}
