import {describe, expect, it} from "vitest";
import {
  EARLIER_COOLDOWN_MS,
  initialEarlierGate,
  recordEarlierRequest,
  shouldRequestEarlier,
  type EarlierRequestInput,
} from "@/lib/earlier-gate";

const H = 3_600_000;
const T0 = 1_790_000_000_000;
const NOW = 1_000_000;

function input(overrides: Partial<EarlierRequestInput> = {}): EarlierRequestInput {
  return {
    from_ms: T0,
    earlier_from_ms: T0,
    interval_ms: H,
    loading: false,
    exhausted: false,
    failed: false,
    gesture_seq: 1,
    now_ms: NOW,
    gate: initialEarlierGate(),
    ...overrides,
  };
}

describe("earlier-gate — una interacción, como máximo una página", () => {
  it("pide una página al llegar al borde con un gesto nuevo", () => {
    expect(shouldRequestEarlier(input())).toBe(true);
  });

  it("no encadena tras anteponer: el cambio de rango no es un gesto", () => {
    let gate = initialEarlierGate();
    let now = NOW;
    // Gesto 1 -> una petición.
    expect(shouldRequestEarlier(input({now_ms: now, gate}))).toBe(true);
    gate = recordEarlierRequest(gate, T0, 1, now);

    // Anteponer mueve el ancla y el rango visible emite varios eventos, pero
    // el gesto sigue siendo el 1: ninguna petición más.
    for (const anchor of [T0 - 300 * H, T0 - 600 * H, T0 - 900 * H]) {
      now += 5_000;
      expect(shouldRequestEarlier(input({
        from_ms: anchor, earlier_from_ms: anchor, now_ms: now,
        gesture_seq: 1, gate,
      }))).toBe(false);
    }

    // Gesto 2 tras el prepend: una página más, con el ancla nueva.
    now += EARLIER_COOLDOWN_MS;
    expect(shouldRequestEarlier(input({
      from_ms: T0 - 900 * H, earlier_from_ms: T0 - 900 * H,
      now_ms: now, gesture_seq: 2, gate,
    }))).toBe(true);
  });

  it("agrupa la ráfaga dentro del cooldown", () => {
    const gate = recordEarlierRequest(initialEarlierGate(), T0, 1, NOW);
    expect(shouldRequestEarlier(input({
      earlier_from_ms: T0 - H, from_ms: T0 - H, gesture_seq: 2,
      now_ms: NOW + 100, gate,
    }))).toBe(false);
    expect(shouldRequestEarlier(input({
      earlier_from_ms: T0 - H, from_ms: T0 - H, gesture_seq: 2,
      now_ms: NOW + EARLIER_COOLDOWN_MS, gate,
    }))).toBe(true);
  });

  it("no repite el mismo bloque salvo que el intento anterior fallara", () => {
    const gate = recordEarlierRequest(initialEarlierGate(), T0, 1, NOW);
    const now = NOW + EARLIER_COOLDOWN_MS;
    expect(shouldRequestEarlier(input({gesture_seq: 2, now_ms: now, gate})))
      .toBe(false);
    expect(shouldRequestEarlier(input({
      gesture_seq: 2, now_ms: now, gate, failed: true,
    }))).toBe(true);
  });

  it("no pide si ya carga, está agotado o no está en el borde", () => {
    expect(shouldRequestEarlier(input({loading: true}))).toBe(false);
    expect(shouldRequestEarlier(input({exhausted: true}))).toBe(false);
    expect(shouldRequestEarlier(input({from_ms: T0 + 10 * H}))).toBe(false);
    expect(shouldRequestEarlier(input({from_ms: null}))).toBe(false);
    expect(shouldRequestEarlier(input({earlier_from_ms: null}))).toBe(false);
  });
});
