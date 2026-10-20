import {act, render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

// Mocks de Next.js navigation: controlamos los query params por test.
const paramsRef = {current: new URLSearchParams()};
vi.mock("next/navigation", () => ({
  useSearchParams: () => paramsRef.current,
}));
// El reproductor real se sustituye por un doble identificable: aqui probamos el
// ENRUTADO de PaperLabSource (carga/fallo/cambio de operacion), no el player.
vi.mock("@/components/paper-lab/PaperLabReplay", () => ({
  default: ({source}: {source?: unknown}) => (
    <div data-testid="player" data-replay={(source as {replay_id?: string})?.replay_id ?? "FIXED"} />
  ),
  ReplayUnavailable: ({message}: {message: string}) => (
    <div data-testid="unavailable">{message}</div>
  ),
}));

import PaperLabSource from "@/components/paper-lab/PaperLabSource";

const setParams = (qs: string) => { paramsRef.current = new URLSearchParams(qs); };
const linkedQs = "bt=eval-census-v2-trio&run=bt-1&event_id=E%3A1%3ALONG%3AH1%3AH1-v1%3A5&group=continuation&segment=dev&scale=1";

beforeEach(() => { setParams(""); vi.restoreAllMocks(); });
afterEach(() => { vi.unstubAllGlobals(); });

function mockFetchOnce(payload: unknown, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok, status: ok ? 200 : 422,
    json: async () => payload,
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
describe("PaperLabSource: operation switch never shows the previous operation", () => {
  it("shows the fixed replay when there is no link", () => {
    setParams("");
    render(<PaperLabSource/>);
    expect(screen.getByTestId("player").getAttribute("data-replay")).toBe("FIXED");
  });

  it("loads THAT operation with its backing run identity", async () => {
    setParams(linkedQs);
    const fetchMock = mockFetchOnce({run_id: "bt-1", cached: false,
      artifact: {replay_id: "PLR-linked"}});
    render(<PaperLabSource/>);
    // Estado de carga mientras no llega la respuesta.
    expect(screen.getByTestId("unavailable").textContent).toMatch(/Cargando/);
    await waitFor(() => expect(screen.getByTestId("player").getAttribute("data-replay"))
      .toBe("PLR-linked"));
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).toContain("run=bt-1");
    expect(url).toContain("group=continuation");
  });

  it("does NOT keep the previous operation visible while a NEW one is loading", async () => {
    // Primera operacion cargada.
    setParams(linkedQs);
    mockFetchOnce({run_id: "bt-1", artifact: {replay_id: "PLR-ONE"}});
    const {rerender} = render(<PaperLabSource/>);
    await waitFor(() => expect(screen.getByTestId("player").getAttribute("data-replay"))
      .toBe("PLR-ONE"));
    // Cambio de operacion: la nueva respuesta queda pendiente.
    let resolveNew: ((v: unknown) => void) | null = null;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((res) => { resolveNew = res as never; })));
    setParams("bt=eval-census-v2-trio&run=bt-1&event_id=E%3A2%3ASHORT%3AH1%3AH1-v1%3A6&group=continuation&segment=oos&scale=1");
    rerender(<PaperLabSource/>);
    // NO debe seguir mostrando PLR-ONE: se muestra carga.
    expect(screen.queryByTestId("player")).toBeNull();
    expect(screen.getByTestId("unavailable").textContent).toMatch(/Cargando/);
    await act(async () => {
      resolveNew!({ok: true, status: 200, json: async () => ({artifact: {replay_id: "PLR-TWO"}})});
    });
    await waitFor(() => expect(screen.getByTestId("player").getAttribute("data-replay"))
      .toBe("PLR-TWO"));
  });

  it("shows the failure reason for a new identity instead of the old operation", async () => {
    setParams(linkedQs);
    // Un unico mock que responde distinto segun la identidad solicitada.
    vi.stubGlobal("fetch", vi.fn((u: string) => {
      const ok = !String(u).includes("event_id=NOPE");
      return Promise.resolve({ok, status: ok ? 200 : 422,
        json: async () => (ok ? {artifact: {replay_id: "PLR-ONE"}} : {error: "REPLAY_UNSUPPORTED"})});
    }));
    const {rerender} = render(<PaperLabSource/>);
    await waitFor(() => expect(screen.getByTestId("player")).toBeTruthy());
    // Nueva identidad que falla (no soportada).
    setParams("bt=eval-census-v2-trio&run=bt-1&event_id=NOPE&group=continuation&segment=dev&scale=1");
    rerender(<PaperLabSource/>);
    await waitFor(() => expect(screen.getByTestId("unavailable").textContent)
      .toMatch(/no se fabrica un replay alternativo/i));
    expect(screen.getByTestId("unavailable").textContent).toContain("REPLAY_UNSUPPORTED");
    expect(screen.queryByTestId("player")).toBeNull();
  });
});
