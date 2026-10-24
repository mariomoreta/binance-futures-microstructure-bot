/**
 * Puerta de la paginación hacia atrás (bloque anterior).
 *
 * Regla: una interacción del usuario (rueda, arrastre o teclado) consume como
 * máximo **una** página. Los cambios de rango que provoca anteponer velas no
 * cuentan como interacción, así que no pueden encadenar descargas.
 */

export interface EarlierGateState {
  /** Último gesto ya consumido (0 = ninguno). */
  last_gesture_seq: number;
  /** Ancla del último bloque pedido (para no repetir el mismo rango). */
  last_anchor_ms: number | null;
  /** Marca temporal del último bloque pedido (para agrupar ráfagas). */
  last_request_at_ms: number;
}

/** Ventana de agrupación de una ráfaga de rueda/teclado. */
export const EARLIER_COOLDOWN_MS = 600;
/** Margen del borde izquierdo, en velas. */
export const EARLIER_EDGE_BARS = 3;

export function initialEarlierGate(): EarlierGateState {
  return {last_gesture_seq: 0, last_anchor_ms: null, last_request_at_ms: 0};
}

export interface EarlierRequestInput {
  /** Borde izquierdo visible en ms (null si el gráfico no lo expone). */
  from_ms: number | null;
  /** Ancla del histórico anterior publicada por el modelo. */
  earlier_from_ms: number | null;
  interval_ms: number;
  loading: boolean;
  exhausted: boolean;
  /** El último intento falló: se permite reintentar el mismo bloque. */
  failed: boolean;
  /** Contador de gestos del usuario (se incrementa al iniciar cada gesto). */
  gesture_seq: number;
  now_ms: number;
  gate: EarlierGateState;
  cooldown_ms?: number;
  edge_bars?: number;
}

export function shouldRequestEarlier(input: EarlierRequestInput): boolean {
  if (input.from_ms == null || input.earlier_from_ms == null) return false;
  if (input.loading || input.exhausted) return false;
  // Sin un gesto nuevo no se pide nada: el cambio de rango por anteponer velas
  // (o por una actualización del extremo reciente) no dispara descargas.
  if (!(input.gesture_seq > input.gate.last_gesture_seq)) return false;
  const cooldown = input.cooldown_ms ?? EARLIER_COOLDOWN_MS;
  if (input.now_ms - input.gate.last_request_at_ms < cooldown) return false;
  const edge = input.edge_bars ?? EARLIER_EDGE_BARS;
  if (input.from_ms > input.earlier_from_ms + edge * input.interval_ms) {
    return false;
  }
  // Mismo bloque ya pedido: solo se repite si el intento anterior falló.
  if (!input.failed && input.gate.last_anchor_ms === input.earlier_from_ms) {
    return false;
  }
  return true;
}

export function recordEarlierRequest(
  gate: EarlierGateState, anchor_ms: number, gesture_seq: number, now_ms: number,
): EarlierGateState {
  return {
    last_gesture_seq: gesture_seq,
    last_anchor_ms: anchor_ms,
    last_request_at_ms: now_ms,
  };
}
