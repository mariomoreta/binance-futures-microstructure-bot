// Instancia compartida de FlowEngine (singleton) para el BFF.
// Un único motor en memoria atiende a todos los clientes del mismo origen.
// No hay conexión a Binance público; sin fuente conectada, no hay cobertura.

import { FlowEngine, type FlowEvent } from "./flow-engine";

export const flowEngine = new FlowEngine([], 5);

// Suscriptores SSE por símbolo: symbol -> Set de controllers
export const flowSseSubscribers: Map<string, Set<ReadableStreamDefaultController>> =
  new Map();

export function subscribeToFlow(symbol: string,
                                controller: ReadableStreamDefaultController): void {
  if (!flowSseSubscribers.has(symbol)) {
    flowSseSubscribers.set(symbol, new Set());
  }
  flowSseSubscribers.get(symbol)!.add(controller);
}

export function unsubscribeFromFlow(symbol: string,
                                    controller: ReadableStreamDefaultController): void {
  const set = flowSseSubscribers.get(symbol);
  if (set) {
    set.delete(controller);
    if (set.size === 0) {
      flowSseSubscribers.delete(symbol);
    }
  }
}

export function publishFlowUpdate(symbol: string,
                                  payload: Record<string, unknown>): void {
  const set = flowSseSubscribers.get(symbol);
  if (!set) return;
  const encoder = new TextEncoder();
  const frame = `event: update\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const controller of [...set]) {
    try {
      controller.enqueue(encoder.encode(frame));
    } catch {
      // controller cerrado o error: se limpiará por el cliente
    }
  }
}

export function ingestFlowEvent(event: FlowEvent): {
  ok: boolean; duplicate: boolean; reason?: string; block?: any;
} {
  const result = flowEngine.ingest(event);
  if (!result.ok) {
    return result;
  }
  const block = flowEngine.snapshot(
    event.symbol.toUpperCase(),
    event.event_ms,
    true,
  );
  publishFlowUpdate(event.symbol.toUpperCase(), {
    symbol: event.symbol.toUpperCase(),
    event_id: event.event_id,
    block,
  });
  return { ...result, block };
}
