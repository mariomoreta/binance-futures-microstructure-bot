// Contexto BTC compartido — comparación normalizada (market-btc-context/v1).
//
// Componente de SOLO LECTURA del backend: dibuja las dos curvas
// normalizadas (token y BTC, % desde la base común declarada) que el bloque
// trae ya calculadas. El navegador NO recalcula indicadores; si el bloque no
// trae base común conocida, no se dibuja nada (nunca se inventa).
//
// Contexto informativo: NO es una señal, NO es un filtro de entrada y la
// diferencia de retornos NO se presenta como "alpha" ni rentabilidad.
// Misma escala simétrica para ambas curvas; los huecos de la rejilla cortan
// la línea (no se intercalan ni interpolan datos ausentes).

import type {MarketContextBtcBlock} from "@/lib/market-chart-contract";

import s from "./BtcCompareStrip.module.css";

const WIDTH = 640;
const HEIGHT = 120;
const PADDING = 10;
const GAP_TOLERANCE = 1.5;

function slicesOf(
  points: Array<{x: number; y: number}>, oneStepPx: number,
): string[] {
  const slices: string[] = [];
  let current: string[] = [];
  for (let index = 0; index < points.length; index += 1) {
    if (index > 0 && current.length >= 2
      && points[index]!.x - points[index - 1]!.x > oneStepPx * GAP_TOLERANCE) {
      slices.push(current.join(" "));
      current = [];
    }
    current.push(`${(Math.round(points[index]!.x * 10) / 10).toFixed(1)},${
      (Math.round(points[index]!.y * 10) / 10).toFixed(1)}`);
  }
  if (current.length >= 2) slices.push(current.join(" "));
  return slices;
}

export default function BtcCompareStrip(
  {block}: {block: MarketContextBtcBlock | null},
) {
  const normalized = block?.normalized ?? null;
  if (!block || !normalized || normalized.series.length < 2) return null;
  const first = normalized.series[0]!.open_time_ms;
  const last = normalized.series[normalized.series.length - 1]!.open_time_ms;
  if (last <= first) return null;
  const spanPx = WIDTH - 2 * PADDING;
  const oneStepPx = (block.identity.interval_ms / (last - first)) * spanPx;
  const spread = Math.max(0.01, ...normalized.series.map(
    (point) => Math.max(Math.abs(point.token_pct),
      Math.abs(point.btc_pct))));
  const xOf = (ms: number) =>
    PADDING + ((ms - first) / (last - first)) * spanPx;
  const yOf = (pct: number) =>
    HEIGHT / 2 - (pct / spread) * (HEIGHT / 2 - PADDING);
  const tokenPoints = normalized.series.map(
    (point) => ({x: xOf(point.open_time_ms), y: yOf(point.token_pct)}));
  const btcPoints = normalized.series.map(
    (point) => ({x: xOf(point.open_time_ms), y: yOf(point.btc_pct)}));
  const tokenSlices = slicesOf(tokenPoints, oneStepPx);
  const btcSlices = slicesOf(btcPoints, oneStepPx);
  const baseLabel = new Date(normalized.base_open_time_ms)
    .toISOString().slice(0, 16).replace("T", " ");
  return (
    <div className={s.strip} data-testid="market-chart-btc-strip">
      <p className={s.title}>
        Contexto BTC compartido (market-btc-context/v1) · comparación
        normalizada desde base común {baseLabel} UTC · porcentaje desde la
        base, NO rentabilidad y NO señal
      </p>
      <svg className={s.plot} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img" preserveAspectRatio="none"
        aria-label={`Retorno normalizado de ${block.identity.symbol} y de ${block.context.symbol} desde ${normalized.base_open_time_ms} (ms)`}>
        <line className={s.zero} x1={PADDING} x2={WIDTH - PADDING}
          y1={HEIGHT / 2} y2={HEIGHT / 2} />
        {tokenSlices.map((slice, index) => (
          <polyline key={`token-${index}-${slice.slice(0, 12)}`}
            points={slice} className={s.tokenLine} />
        ))}
        {btcSlices.map((slice, index) => (
          <polyline key={`btc-${index}-${slice.slice(0, 12)}`}
            points={slice} className={s.btcLine} />
        ))}
      </svg>
      <p className={s.legend}>
        <span className={s.tokenKey}>token {block.identity.symbol}</span>
        <span className={s.btcKey}>BTC {block.context.symbol}</span>
        <span className={s.note}>
          fuente {block.context.sources.join("+") || "declarada"} ·
          {" "}cobertura {block.context.timeframe.present_grid}/
          {block.context.timeframe.expected_grid}
        </span>
      </p>
    </div>
  );
}
