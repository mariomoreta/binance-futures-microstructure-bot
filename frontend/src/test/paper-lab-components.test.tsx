import {act, fireEvent, render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import artifact from "@/artifacts/paper-lab-replay-v1.json";
import PaperLabReplay from "@/components/paper-lab/PaperLabReplay";
import {parsePaperLabReplay} from "@/lib/paper-lab-replay";

afterEach(() => vi.useRealTimers());

const parsed = parsePaperLabReplay(artifact as Record<string, unknown>);
// Cinta: candle(formacion), detection, entry, candle, candle, candle, exit = 7 pasos
const N = parsed.window.steps.length;

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
    expect(screen.getAllByText("PLR-BTCUSDT-LONG-1788903900000-continuation-1.0x").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/cierre = venta/)).toBeInTheDocument();
    expect(screen.queryByText(/compra en espera/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Control de mecánica \(BTC\)/)).toBeInTheDocument();
  });

  it("distingue 'escenario seleccionado offline' de la deteccion revelada durante el replay", () => {
    render(<PaperLabReplay source={artifact} />);
    // El escenario (identidad fija) se declara explicitamente como no-deteccion.
    expect(screen.getByText(/escenario seleccionado offline/i)).toBeInTheDocument();
    // Al inicio la deteccion NO esta revelada.
    const revealed = () => screen.getByText(/Detección (revelada|aún no conocida)/).textContent;
    expect(revealed()).toBe("Detección aún no conocida");
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    step(); // candle formacion (no revela deteccion)
    step(); // deteccion revelada
    expect(revealed()).toBe("Detección revelada");
  });

  it("revelacion: la deteccion no aparece antes de su disponibilidad (frontera en UI)", () => {
    render(<PaperLabReplay source={artifact} />);
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    // Paso 1 = vela de formacion (reloj = formacion + 1 vela). Aun sin deteccion.
    step();
    expect(screen.getByText(/Detección aún no conocida/)).toBeInTheDocument();
    // El registro de eventos no contiene aun la deteccion.
    expect(screen.queryByText(/Detección conocida/)).not.toBeInTheDocument();
    // Paso 2 = deteccion conocida; muestra su hora de formacion como metadata.
    step();
    expect(screen.getByText(/Detección revelada/)).toBeInTheDocument();
    expect(screen.getByText(/Detección conocida \(formación conservada como metadata\)/)).toBeInTheDocument();
    expect(screen.getByText(/· formación /)).toBeInTheDocument();
  });

  it("muestra la seccion de formacion vs disponibilidad con horas distintas", () => {
    render(<PaperLabReplay source={artifact} />);
    expect(screen.getByText("Revelación de la detección (formación vs disponibilidad)")).toBeInTheDocument();
    expect(screen.getByText("Hora de formación (metadata)")).toBeInTheDocument();
    expect(screen.getByText("Disponible a partir de")).toBeInTheDocument();
  });

  it("contexto visible en la vista inicial (antes de la deteccion) y con leyenda", () => {
    render(<PaperLabReplay source={artifact} />);
    // El grafico no esta vacio: hay contexto + leyenda.
    expect(screen.getByLabelText("Grafico de velas del replay con contexto previo")).toBeInTheDocument();
    expect(screen.getByText(/contexto previo \(atenuado\)/)).toBeInTheDocument();
    expect(screen.getByText("cursor")).toBeInTheDocument();
  });

  it("estados de posicion por paso: EN_ESPERA -> ABIERTA -> CERRADA con motivo y resultado realizado", () => {
    vi.useFakeTimers();
    render(<PaperLabReplay source={artifact} />);
    const stateText = () => screen.getByText(/^Posición: /).textContent;
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    expect(stateText()).toBe("Posición: SIN POSICIÓN");
    step(); // candle formacion: sin deteccion
    expect(stateText()).toBe("Posición: SIN POSICIÓN");
    step(); // deteccion -> en espera
    expect(stateText()).toBe("Posición: SIN POSICIÓN / EN ESPERA");
    step(); // entrada ejecutada -> abierta
    expect(stateText()).toBe("Posición: ABIERTA");
    expect(screen.queryByText(/la entrada aún no se ejecutó/i)).not.toBeInTheDocument();
    for (let i = 0; i < N; i++) step();
    expect(stateText()).toBe("Posición: CERRADA");
    expect(screen.getByText("Resumen final (tras el cierre)")).toBeInTheDocument();
    expect(screen.getByText("horizon")).toBeInTheDocument();
  });

  it("no revela el cierre en el paso anterior (frontera temporal en UI)", () => {
    render(<PaperLabReplay source={artifact} />);
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    for (let i = 0; i < N - 1; i++) step();
    expect(screen.getByText(`Paso ${N - 1} de ${N}`)).toBeInTheDocument();
    expect(screen.queryByText("Resumen final (tras el cierre)")).not.toBeInTheDocument();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: ABIERTA");
  });

  it("estado del reproductor distingue sin iniciar / pausado / reproduciendo / terminado", () => {
    vi.useFakeTimers();
    render(<PaperLabReplay source={artifact} />);
    const player = () => screen.getByText(/^Reproducción: /).textContent;
    expect(player()).toBe("Reproducción: SIN INICIAR");
    fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    expect(player()).toBe("Reproducción: PAUSADO");
    // Pausado en el paso actual: el boton principal ofrece REANUDAR (no "Reproducir").
    fireEvent.click(screen.getByRole("button", {name: "Reanudar"}));
    expect(player()).toBe("Reproducción: REPRODUCIENDO");
    act(() => vi.advanceTimersByTime(1200 * (N + 2)));
    expect(player()).toBe("Reproducción: TERMINADO");
  });

  it("tras avanzar manualmente con posicion abierta aparece PAUSADO, no 'REPOSO'", () => {
    render(<PaperLabReplay source={artifact} />);
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    // avanzar hasta posicion abierta (paso 3: candle, detection, entry)
    step(); step(); step();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: ABIERTA");
    expect(screen.getByText("Reproducción: PAUSADO")).toBeInTheDocument();
    expect(screen.queryByText("Reproducción: REPOSO")).not.toBeInTheDocument();
  });

  it("reiniciar restablece reproductor y posicion de forma coherente", () => {
    render(<PaperLabReplay source={artifact} />);
    const step = () => fireEvent.click(screen.getByRole("button", {name: "Paso a paso"}));
    step(); step(); step();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: ABIERTA");
    fireEvent.click(screen.getByRole("button", {name: "Reiniciar"}));
    expect(screen.getByText(`Paso 0 de ${N}`)).toBeInTheDocument();
    expect(screen.getByText("Reproducción: SIN INICIAR")).toBeInTheDocument();
    expect(screen.getByText(/^Posición: /).textContent).toBe("Posición: SIN POSICIÓN");
  });

  it("play, pausa, reinicio y cierre avanzan solo el reloj del replay", () => {
    vi.useFakeTimers();
    render(<PaperLabReplay source={artifact} />);
    fireEvent.click(screen.getByRole("button", {name: "Reproducir"}));
    expect(screen.getByRole("button", {name: "Pausar"})).toBeEnabled();
    act(() => vi.advanceTimersByTime(1200));
    expect(screen.getByText("Paso 1 de 7")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Pausar"}));
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("Paso 1 de 7")).toBeInTheDocument();
    expect(screen.getByText("Reproducción: PAUSADO")).toBeInTheDocument();

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
