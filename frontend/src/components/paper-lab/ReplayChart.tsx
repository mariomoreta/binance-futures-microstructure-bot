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

// Dimensiones lógicas del SVG. El SVG es RESPONSIVE: se escala a la anchura del
// contenedor (viewBox + width:100%) y conserva proporción, de modo que en móvil
// (360/390px) no se recorta el extremo derecho ni se pierden entrada/cierre/niveles.
const W = 860, H = 340, PAD = {l: 74, r: 120, t: 30, b: 40};
// Reserva vertical para apilar etiquetas de nivel sin solaparse.
const LABEL_GAP = 13;

// `zoom` (>0) amplía la ventana visible alrededor del cursor de reproducción.
// No inventa datos: solo cambia cuántas velas reales entran en el eje de tiempo.
function extent(all: ReplayCandle[], marks: (number | null | false)[]) {
  let lo = Infinity, hi = -Infinity;
  for (const c of all) { lo = Math.min(lo, c.low); hi = Math.max(hi, c.high); }
  for (const v of marks) if (typeof v === "number" && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return {lo: 0, hi: 1, span: 1};
  // Margen superior/inferior para que las etiquetas de los extremos no se recorten.
  const span = (hi - lo) || (hi * 0.001) || 1;
  return { lo: lo - span * 0.06, hi: hi + span * 0.06, span };
}

export function ReplayChart({
  candles, contextCandles = [], entryPx, stopPx, exitPx, exitShown,
  currentTimeMs, zoom = 1, width = W, height = H,
}: ReplayChartProps) {
  // Clases de color (coherentes con la leyenda del componente padre).
  if (candles.length === 0 && contextCandles.length === 0) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Grafico esperando la primera vela cerrada" preserveAspectRatio="xMidYMid meet">
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

  // Frontera real contexto/replay: comienzo del tramo de operación (primera vela
  // del replay), NO el inicio de toda la serie (que incluiría el contexto).
  const replayStartX = candles.length > 0 ? cx(candles[0]!.open_time_ms) : null;

  // Etiquetas de nivel con ANTI-SOLAPE: se mantiene la línea en su precio real;
  // solo el texto se desplaza verticalmente cuando colisiona con otra etiqueta.
  type Mark = {px: number; text: string; fill: string; dash: string; strong: boolean};
  const marks: Mark[] = [];
  if (entryPx != null) marks.push({px: entryPx, text: `Entrada ${formatPrice(entryPx)}`, fill: "#7fd0f8", dash: "4 3", strong: false});
  if (stopPx != null) marks.push({px: stopPx, text: `Stop ${formatPrice(stopPx)}`, fill: "#fb7185", dash: "4 3", strong: false});
  if (exitShown && exitPx != null) marks.push({px: exitPx, text: `Cierre ${formatPrice(exitPx)}`, fill: "#38bdf8", dash: "6 4", strong: true});
  // Ordenar por y creciente para apilar sin solape.
  const placed = marks
    .map((m) => ({...m, y: cy(m.px)}))
    .sort((a, b) => a.y - b.y)
    .reduce<Array<Mark & {y: number; labelY: number}>>((acc, m) => {
      const prev = acc[acc.length - 1];
      const labelY = prev && m.y - prev.labelY < LABEL_GAP ? prev.labelY + LABEL_GAP : m.y;
      acc.push({...m, labelY});
      return acc;
    }, []);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Grafico de velas del replay con contexto previo"
      preserveAspectRatio="xMidYMid meet"
      style={{width: "100%", height: "auto", maxWidth: `${width}px`}}
    >
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
      {/* sombreado del tramo de contexto (izquierda de la frontera real) */}
      {replayStartX != null && replayStartX > PAD.l && (
        <rect x={PAD.l} y={PAD.t} width={Math.max(0, replayStartX - PAD.l)} height={height - PAD.t - PAD.b} fill="#0e2233" opacity={0.5} />
      )}
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
      {/* separador contexto/replay en la FRONTERA REAL (primera vela del replay) */}
      {replayStartX != null && (
        <line x1={replayStartX} y1={PAD.t} x2={replayStartX} y2={height - PAD.b} stroke="#4a6b8a" strokeWidth="1" strokeDasharray="2 3" opacity={0.7} />
      )}
      {/* niveles: línea en su precio real + etiqueta apilada sin solape */}
      {placed.map((m, i) => (
        <g key={`lvl-${i}`}>
          <line x1={PAD.l} y1={m.y} x2={width - PAD.r} y2={m.y} stroke={m.fill} strokeDasharray={m.dash} strokeWidth={m.strong ? 1.4 : 1} opacity={m.strong ? 0.9 : 0.55} />
          {Math.abs(m.labelY - m.y) > 0.5 && (
            <line x1={width - PAD.r} y1={m.y} x2={width - PAD.r + 5} y2={m.labelY} stroke={m.fill} strokeWidth="0.6" opacity={0.6} />
          )}
          <text x={width - PAD.r + 6} y={m.labelY + 4} fill={m.fill} fontSize="10" fontFamily="var(--font-mono)">{m.text}</text>
        </g>
      ))}
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
      {/* playhead: siempre dentro del viewport */}
      {currentTimeMs != null && (
        <line x1={cx(Math.max(v0, Math.min(currentTimeMs, v1)))} y1={PAD.t} x2={cx(Math.max(v0, Math.min(currentTimeMs, v1)))} y2={height - PAD.b} stroke="#38bdf8" strokeWidth="1.6" strokeDasharray="5 4" markerEnd="url(#head)" opacity={0.9} />
      )}
      {/* ejes: tiempo y precio con margen para no recortar extremos */}
      <text x={PAD.l} y={height - 12} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)">{fmtTime(v0)}</text>
      <text x={(PAD.l + width - PAD.r) / 2} y={height - 12} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="middle">{fmtTime((v0 + v1) / 2)}</text>
      <text x={width - PAD.r} y={height - 12} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{fmtTime(v1)}</text>
      <text x={PAD.l - 8} y={PAD.t + 4} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{formatPrice(ex.hi - ex.span * 0.06)}</text>
      <text x={PAD.l - 8} y={cy((ex.lo + ex.hi) / 2) + 4} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{formatPrice((ex.lo + ex.hi) / 2)}</text>
      <text x={PAD.l - 8} y={height - PAD.b - 4} fill="#78909c" fontSize="10" fontFamily="var(--font-mono)" textAnchor="end">{formatPrice(ex.lo + ex.span * 0.06)}</text>
      <text x={PAD.l - 8} y={PAD.t - 8} fill="#8fc8e6" fontSize="9" fontFamily="var(--font-mono)" textAnchor="end">{contextCandles.length > 0 ? `+${contextCandles.length} ctx` : ""}</text>
    </svg>
  );
}
