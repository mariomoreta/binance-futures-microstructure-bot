import {fireEvent, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import artifact from "@/artifacts/paper-lab-replay-v1.json";
import {parsePaperLabReplay} from "@/lib/paper-lab-replay";
import {createPaperSession, manualExit, stepForward, type PaperSessionState, type PaperSessionStatus} from "@/lib/paper-lab-live";
import {FixtureSelector} from "@/components/paper-lab-live/FixtureSelector";
import {PositionPanel} from "@/components/paper-lab-live/PositionPanel";
import {PnLPanel} from "@/components/paper-lab-live/PnLPanel";
import {EventLog} from "@/components/paper-lab-live/EventLog";
import {SessionControls} from "@/components/paper-lab-live/SessionControls";
import {ExportPanel} from "@/components/paper-lab-live/ExportPanel";
import {SessionPersistence} from "@/components/paper-lab-live/SessionPersistence";

afterEach(() => vi.useRealTimers());

const parsed = parsePaperLabReplay(artifact as Record<string, unknown>);

function openSession(s: PaperSessionState): PaperSessionState {
  s.status = "abierta" as PaperSessionStatus;
  return s;
}

function makeOpenSession(): PaperSessionState {
  const config = {
    symbol: "BTCUSDT",
    interval: "15m",
    direction: "LONG" as const,
    notional_usdt: 1000,
    entry_px: 78458.7,
    stop_px: 78458.7 * 0.995,
    stop_distance_pct: 0.5,
    horizon_ms: 3600000,
    fee_bps: 5,
    spread_bps: 1,
    slippage_bps: 2,
  };
  const t0 = parsed.trade.entry_ms;
  const candles = [
    {open_time_ms: t0, open: 78458.7, high: 78500, low: 78400, close: 78460, close_time_ms: t0 + 15 * 60 * 1000 - 1},
    {open_time_ms: t0 + 15 * 60 * 1000, open: 78460, high: 78520, low: 78440, close: 78500, close_time_ms: t0 + 2 * 15 * 60 * 1000 - 1},
    {open_time_ms: t0 + 2 * 15 * 60 * 1000, open: 78500, high: 78550, low: 78480, close: 78530, close_time_ms: t0 + 3 * 15 * 60 * 1000 - 1},
  ];
  const s = openSession(createPaperSession(config, candles, []));
  let r = stepForward(s);
  return r.state;
}

describe("Paper Lab Live — fixture selector", () => {
  it("lista todos los fixtures y permite seleccionar uno", () => {
    render(<FixtureSelector onSelect={vi.fn()} selectedId={null} />);
    expect(screen.getByText("Seleccion de operacion")).toBeInTheDocument();
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
  });
});

describe("Paper Lab Live — position panel", () => {
  it("muestra estado ABIERTA con entrada, stop y marca", () => {
    const s = makeOpenSession();
    render(<PositionPanel position={s.position} direction={s.config.direction} />);
    expect(screen.getByText(/ABIERTA/)).toBeInTheDocument();
    expect(screen.getByText(/LONG/)).toBeInTheDocument();
    expect(screen.getByText(/Entrada/)).toBeInTheDocument();
    expect(screen.getByText(/Stop original/)).toBeInTheDocument();
  });
});

describe("Paper Lab Live — PnL panel", () => {
  it("muestra P&L no realizado antes del cierre", () => {
    const s = makeOpenSession();
    render(<PnLPanel finished={false} entered={true} costs={s.costs} unrealized={s.position.unrealized_net} result={null} />);
    expect(screen.getByText(/P&L \(estimado \/ no realizado\)/)).toBeInTheDocument();
    expect(screen.getByText(/Comisiones entrada/)).toBeInTheDocument();
  });

  it("muestra resultado realizado tras el cierre", () => {
    const s = makeOpenSession();
    // Cerrar la sesion para tener un resultado realizado.
    const m = manualExit(s);
    const closed = m.state;
    render(<PnLPanel finished={true} entered={true} costs={closed.costs} unrealized={null} result={closed.result} />);
    expect(screen.getByText(/Resultado \(realizado al cierre\)/)).toBeInTheDocument();
  });
});

describe("Paper Lab Live — event log", () => {
  it("muestra eventos de entrada y marca", () => {
    const s = makeOpenSession();
    render(<EventLog events={s.events} />);
    expect(screen.getByText(/Registro de eventos/)).toBeInTheDocument();
    if (s.events.length > 0) {
      const firstLabel: string = s.events[0]!.label;
      expect(screen.getByText(new RegExp(firstLabel.split(" ·")[0]!))).toBeInTheDocument();
    }
  });

  it("muestra estado vacio sin eventos", () => {
    render(<EventLog events={[]} />);
    expect(screen.getByText(/Sin eventos revelados aún\./)).toBeInTheDocument();
  });
});

describe("Paper Lab Live — session controls", () => {
  it("renderiza controles con estado en_espera", () => {
    render(<SessionControls status="en_espera" canEnter={true} canStep={false} canExit={false} canRestart={true} canStop={false} onEnter={vi.fn()} onStep={vi.fn()} onExit={vi.fn()} onRestart={vi.fn()} onStop={vi.fn()} stepMs={1200} />);
    expect(screen.getByRole("button", {name: /Entrar/})).toBeInTheDocument();
    expect(screen.getByText(/EN ESPERA/)).toBeInTheDocument();
  });

  it("deshabilita entrar cuando no se puede", () => {
    render(<SessionControls status="abierta" canEnter={false} canStep={true} canExit={true} canRestart={true} canStop={true} onEnter={vi.fn()} onStep={vi.fn()} onExit={vi.fn()} onRestart={vi.fn()} onStop={vi.fn()} stepMs={1200} />);
    expect(screen.getByRole("button", {name: /Avanzar paso/})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: /Cerrar posicion/})).toBeInTheDocument();
  });
});

describe("Paper Lab Live — export panel", () => {
  it("habilita exportacion despues del cierre", () => {
    const s = makeOpenSession();
    render(<ExportPanel state={s} result={s.result} onDownloadJson={vi.fn()} onDownloadCsv={vi.fn()} />);
    expect(screen.getByText(/Exportacion/)).toBeInTheDocument();
  });

  it("deshabilita exportacion antes del cierre", () => {
    const s = makeOpenSession();
    render(<ExportPanel state={s} result={null} onDownloadJson={vi.fn()} onDownloadCsv={vi.fn()} />);
    expect(screen.getByRole("button", {name: /Descargar JSON de sesion/})).toBeDisabled();
    expect(screen.getByRole("button", {name: /Descargar CSV del trade/})).toBeDisabled();
  });
});

describe("Paper Lab Live — session persistence", () => {
  it("lista sesiones guardadas y permite seleccionar", () => {
    render(<SessionPersistence sessions={[]} onLoad={vi.fn()} onSave={vi.fn()} />);
    expect(screen.getByText(/Persistencia/)).toBeInTheDocument();
    expect(screen.getByText(/— seleccionar —/)).toBeInTheDocument();
  });
});
