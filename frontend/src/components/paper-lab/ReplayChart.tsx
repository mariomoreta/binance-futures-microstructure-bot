"use client";
import type {ReplayCandle} from "@/lib/paper-lab-replay";
import {formatPrice} from "@/lib/format";

interface ReplayChartProps {
  candles: ReplayCandle[];
  contextCandles?: ReplayCandle[];
  entryPx: number | null;
  stopPx: number | null;
  exitPx: number | null;
  exitShown: boolean;
  currentTimeMs: number | null;
  zoom?: number;
  width?: number;
  height?: number;
}

const W = 860, H = 300, PAD = {l: 66, r: 96, t: 26, b: 34};

// `zoom` (>0) amplía la ventana visible alrededor del cursor de reproducción.
// No inventa datos: solo cambia cuántas velas reales entran en el eje de tiempo.
function extent(all: ReplayCandle[], marks: (number | null | false)[]) {
  let lo = Infinity, hi = -Infinity;
  for (const c of all) { lo = Math.min(lo, c.low); hi = Math.max(hi, c.high); }
  for (const v of marks) if (typeof v === "number" && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return {lo: 0, hi: 1, span: 1};
  const span = hi - lo || 1;
  return { lo: lo - span * 0.06, hi: hi + span * 0.06, span };
}

export function ReplayChart({
  candles, contextCandles = [], entryPx, stopPx, exitPx, exitShown,
  currentTimeMs, zoom = 1, width = W, height = H,
}: ReplayChartProps) {
  if (candles.length === 0) {
    return (
      <svg width={width} height={height} role="img" aria-label="Grafico esperando la primera vela cerrada">
        <text x="50%" y="50%" textAnchor="middle" fill="#78909c" fontSize="12">Esperando primera vela cerrada</text>
      </svg>
    );
  }
  const all = [...contextCandles, ...candles];
  const ex = extent(all, [entryPx, stopPx, exitShown ? exitPx : false]);
  const t0 = all[0]?.open_time_ms ?? 0;
  const t1 = all[all.length - 1]?.close_time_ms ?? t0 + 3_600_000;
  const full = Math.max(t1 - t0, 1);
  const z = Math.max(1, zoom);
  const viewSpan = full / z;
  const cursorT = currentTimeMs ?? t1;
  // Ventana visible: centrada en el cursor si hay zoom, acotada a la serie.
  let v0 = z === 1 ? t0 : cursorT - viewSpan / 2;
  v0 = Math.max(t0, Math.min(v0, t1 - viewSpan));
  const v1 = Math.min(t1, v0 + viewSpan);
  const tr = Math.max(v1 - v0, 1);
  const cx = (t: number) => PAD.l + ((t - v0) / tr) * (width - PAD.l - PAD.r);
  const cy = (p: number) => height - PAD.b - ((p - ex.lo) / ex.span) * (height - PAD.t - PAD.b);

  const dir = (c: ReplayCandle) => (c.close >= c.open ? "up" : "down");
  const color = (d: string) => (d === "up" ? "#34d399" : "#fb7185");
  const inView = (c: ReplayCandle) => c.close_time_ms != null && c.open_time_ms >= v0 && c.open_time_ms <= v1;

  const widthPer = (width - PAD.l - PAD.r) / Math.max(1, Math.round(tr / 900000));
  const bw = Math.max(2, Math.min(14, widthPer * 0.55));

  const fmtTime = (ms: number) => new Date(ms).toISOString().slice(5, 16).replace("T", " ");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Grafico de velas del replay con contexto previo">
      <defs>
        <marker id="head" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L6,4 L0,8 Z" fill="#38bdf8" />
        </marker>
      </defs>
      {/* grid horizontal */}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const y = PAD.t + f * (height - PAD.t - PAD.b);
        return <line key={f} x1={PAD.l} y1={y} x2={width - PAD.r} y2={y} stroke="#173347" strokeWidth="0.6" />;
      })}
      {/* contexto previo (atenuado) */}
      {contextCandles.filter(inView).map((c, i) => {
        const x = cx(c.open_time_ms);
        const top = cy(Math.max(c.open, c.close));
        const bot = cy(Math.min(c.open, c.close));
        const col = color(dir(c));
        return (
          <g key={`ctx-${i}`} opacity={0.32}>
            <line x1={x} y1={cy(c.low)} x2={x} y2={cy(c.high)} stroke={col} strokeWidth="1" />
            <rect x={x - bw / 2} y={top} width={bw} height={Math.max(1, bot - top)} fill="none" stroke={col} strokeWidth="1" />
          </g>
        );
      })}
      {/* separador contexto/replay */}
      {contextCandles.length > 0 && (
        <line x1={cx(t0)} y1={PAD.t} x2={cx(t0)} y2={height - PAD.b} stroke="#4a6b8a" strokeWidth="1" strokeDasharray="2 3" opacity={0.7} />
      )}
      {/* niveles */}
      {entryPx != null && (
        <g stroke="#7fd0f8" strokeDasharray="4 3" strokeWidth="1" opacity={0.55}>
          <line x1={PAD.l} y1={cy(entryPx)} x2={width - PAD.r} y2={cy(entryPx)} />
          <text x={width - PAD.r + 6} y={cy(entryPx) - 3} fill="#7fd0f8" fontSize="10" fontFamily="var(--font-mono)">Entrada {formatPrice(entryPx)}</text>
        </g>
      )}
      {stopPx != null && (
        <g stroke="#fb7185" strokeDasharray="4 3" strokeWidth="1" opacity={0.55}>
          <line x1={PAD.l} y1={cy(stopPx)} x2={width - PAD.r} y2={cy(stopPx)} />
          <text x={width - PAD.r + 6} y={cy(stopPx) - 3} fill="#fb7185" fontSize="10" fontFamily="var(--font-mono)">Stop {formatPrice(stopPx)}</text>
        </g>
      )}
      {exitShown && exitPx != null && (
        <g stroke="#38bdf8" strokeDasharray="6 4" strokeWidth="1.4" opacity={0.9}>
          <line x1={PAD.l} y1={cy(exitPx)} x2={width - PAD.r} y2={cy(exitPx)} />
          <text x={width - PAD.r + 6} y={cy(exitPx) - 3} fill="#38bdf8" fontSize="10" fontFamily="var(--font-mono)">Cierre {formatPrice(exitPx)}</text>
        </g>
      )}
      {/* velas del replay (reveladas) */}
      {candles.filter(inView).map((c, i) => {
        const x = cx(c.open_time_ms);
        const top = cy(Math.max(c.open, c.close));
        const bot = cy(Math.min(c.open, c.close));
        const col = color(dir(c));
        return (
          <g key={`c-${i}`}>
            <line x1={x} y1={cy(c.low)} x2={x} y2={cy(c.high)} stroke={col} strokeWidth="1.2" opacity={0.6} />
            <rect x={x - bw / 2} y={top} width={bw} height={Math.max(1, bot - top)} fill={col} fillOpacity={0.16} stroke={col} strokeWidth="1.6" />
          </g>
        );
      })}
      {/* playhead */}
      {currentTimeMs != null && (
        <line x1={cx(currentTimeMs)} y1={PAD.t} x2={cx(currentTimeMs)} y2={height - PAD.b} stroke="#38bdf8" strokeWidth="1.6" strokeDasharray="5 4" markerEnd="url(#head)" opacity={0.9} />
      )}
      {/* ejes */}
      <text x={PAD.l} y={height - 8} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)">{fmtTime(v0)}</text>
      <text x={(PAD.l + width - PAD.r) / 2} y={height - 8} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="middle">{fmtTime((v0 + v1) / 2)}</text>
      <text x={width - PAD.r} y={height - 8} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{fmtTime(v1)}</text>
      <text x={PAD.l - 8} y={cy(ex.hi) + 4} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{formatPrice(ex.hi)}</text>
      <text x={PAD.l - 8} y={cy(ex.lo) + 4} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{formatPrice(ex.lo)}</text>
      <text x={PAD.l - 8} y={PAD.t + 4} fill="#8fc8e6" fontSize="9" fontFamily="var(--font-mono)" textAnchor="end">{contextCandles.length > 0 ? `+${contextCandles.length} ctx` : ""}</text>
    </svg>
  );
}
