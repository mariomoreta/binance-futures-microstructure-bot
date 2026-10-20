import {act, fireEvent, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import artifact from "@/artifacts/paper-lab-replay-v1.json";
import PaperLabReplay from "@/components/paper-lab/PaperLabReplay";
import {parsePaperLabReplay} from "@/lib/paper-lab-replay";

afterEach(() => vi.useRealTimers());

const parsed = parsePaperLabReplay(artifact as Record<string, unknown>);
const N = parsed.window.steps.length; // 4 velas + 4 eventos = 8

describe("Paper Lab visible replay", () => {
  it("muestra fuente no disponible para un contrato incompatible", () => {
    render(<PaperLabReplay source={{schema_version: 999}} />);
    expect(screen.getByText("Fuente de replay no disponible")).toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Reproducir"})).not.toBeInTheDocument();
  });

  it("no filtra entrada, salida ni P&L final en el estado inicial", () => {
    render(<PaperLabReplay source={artifact} />);
    expect(screen.getByText(`Paso 0 de ${N}`)).toBeInTheDocument();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: SIN POSICIÓN");
    expect(screen.getByText("Sin P&L ni costes ejecutados antes de la entrada.")).toBeInTheDocument();
    expect(screen.queryByText("Resumen final (tras el cierre)")).not.toBeInTheDocument();
    expect(screen.queryByText("-0.02")).not.toBeInTheDocument();
    expect(screen.queryByText("-1.62")).not.toBeInTheDocument();
  });

  it("identidad coherente: simbolo, direccion separada de la accion de cierre, familia y replay_id", () => {
    render(<PaperLabReplay source={artifact} />);
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("LONG · familia H1")).toBeInTheDocument();
    expect(screen.getAllByText("PLR-BTCUSDT-LONG-1788903900000").length).toBeGreaterThanOrEqual(1);
    // direccion separada de la accion de cierre; nunca "compra en espera"
    expect(screen.getByText(/cierre = venta/)).toBeInTheDocument();
    expect(screen.queryByText(/compra en espera/i)).not.toBeInTheDocument();
    // BTC identificado como control de mecanica
    expect(screen.getByText(/Control de mecánica \(BTC\)/)).toBeInTheDocument();
  });

  it("estados por paso: EN_ESPERA -> ABIERTA -> CERRADA con motivo y resultado realizado", () => {
    vi.useFakeTimers();
    render(<PaperLabReplay source={artifact} />);
    const stateText = () => screen.getByText(/^Posición: /).textContent;
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    // paso 0: sin señal
    expect(stateText()).toBe("Posición: SIN POSICIÓN");
    step(); // 1: señal formada -> en espera
    expect(stateText()).toBe("Posición: SIN POSICIÓN / EN ESPERA");
    step(); // 2: disponible
    expect(stateText()).toBe("Posición: SIN POSICIÓN / EN ESPERA");
    step(); // 3: entrada ejecutada -> abierta
    step(); // 4: (ya revelada la entrada)
    expect(stateText()).toBe("Posición: ABIERTA");
    // la frase "la entrada aún no se ejecutó" debe desaparecer tras la entrada
    expect(screen.queryByText(/la entrada aún no se ejecutó/i)).not.toBeInTheDocument();
    // avanzar hasta el cierre
    for (let i = 0; i < N; i++) step();
    expect(stateText()).toBe("Posición: CERRADA");
    expect(screen.getByText("Resumen final (tras el cierre)")).toBeInTheDocument();
    expect(screen.getByText("horizon")).toBeInTheDocument();
  });

  it("no revela el cierre en el paso anterior (frontera temporal en UI)", () => {
    render(<PaperLabReplay source={artifact} />);
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    // avanzar hasta el paso de vela inmediatamente anterior al cierre
    for (let i = 0; i < N - 1; i++) step();
    expect(screen.getByText(`Paso ${N - 1} de ${N}`)).toBeInTheDocument();
    expect(screen.queryByText("Resumen final (tras el cierre)")).not.toBeInTheDocument();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: ABIERTA");
  });

  it("play, pausa, reinicio y cierre avanzan solo el reloj del replay", () => {
    vi.useFakeTimers();
    render(<PaperLabReplay source={artifact} />);
    fireEvent.click(screen.getByRole("button", {name: "Reproducir"}));
    expect(screen.getByRole("button", {name: "Pausar"})).toBeEnabled();
    act(() => vi.advanceTimersByTime(1200));
    expect(screen.getByText("Paso 1 de 8")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Pausar"}));
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("Paso 1 de 8")).toBeInTheDocument();
    expect(screen.getByText("Replay: PAUSADO")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", {name: "Reanudar"}));
    act(() => vi.advanceTimersByTime(1200 * N));
    expect(screen.getByText(`Paso ${N} de ${N}`)).toBeInTheDocument();
    expect(screen.getByText("Resumen final (tras el cierre)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", {name: "Reiniciar"}));
    expect(screen.getByText(`Paso 0 de ${N}`)).toBeInTheDocument();
    expect(screen.queryByText("Resumen final (tras el cierre)")).not.toBeInTheDocument();
  });

  it("los controles no exponen Start/Stop del monitor", () => {
    render(<PaperLabReplay source={artifact} />);
    expect(screen.queryByRole("button", {name: /start|stop|monitor/i})).not.toBeInTheDocument();
  });
});
