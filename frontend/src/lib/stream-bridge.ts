// Puente BFF -> servicio local `market-stream/v1` (loopback).
//
// El servicio Python es la autoridad del feed: el navegador nunca habla con
// Binance ni con el puerto del servicio directamente. Si el servicio está
// detenido, el histórico REST sigue disponible y la UI lo declara.

const DEFAULT_URL = "http://127.0.0.1:8791";

export function streamServiceUrl(): string {
  const raw = (process.env.MICROPROBE_STREAM_URL ?? DEFAULT_URL).trim();
  return (raw || DEFAULT_URL).replace(/\/+$/, "");
}

export function streamErrorDetail(error: unknown): string {
  if (error instanceof Error) {
    const cause = (error as {cause?: {code?: string}}).cause;
    if (cause?.code) return `${error.name}: ${cause.code}`;
    return `${error.name}: ${error.message}`;
  }
  return String(error).slice(0, 300);
}
