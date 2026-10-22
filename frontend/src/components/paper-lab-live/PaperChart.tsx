"use client";
import {useCallback, useEffect, useRef, useState} from "react";
import type {
  CandlestickData,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  LineData,
  MouseEventHandler,
  SeriesMarker,
  Time,
  TimeRangeChangeEventHandler,
  UTCTimestamp,
} from "lightweight-charts";
import type {
  ClosedChartCandle,
  PaperChartModel,
} from "@/lib/paper-chart-contract";
import {msToChartSecond} from "@/lib/paper-chart-contract";
import {formatPrice} from "@/lib/format";
import {fmtUtcPL} from "@/lib/paper-lab-live";
import s from "./PaperLabLive.module.css";

type ChartLib = typeof import("lightweight-charts");
type Bundle = {
  chart: IChartApi;
  context: ISeriesApi<"Candlestick">;
  candles: ISeriesApi<"Candlestick">;
  open: ISeriesApi<"Line">;
  markers: ISeriesMarkersPluginApi<Time>;
  openMarkers: ISeriesMarkersPluginApi<Time>;
  priceLines: IPriceLine[];
  sessionId: string;
  contextData: CandlestickData<Time>[];
  candleData: CandlestickData<Time>[];
  lineSignature: string;
};

// Carga diferida: la biblioteca solo se monta en el cliente y una sola vez
// por pagina (no en SSR ni por cada sesion).
let chartLibPromise: Promise<ChartLib> | null = null;
function loadChartLib(): Promise<ChartLib> {
  chartLibPromise ??= import("lightweight-charts");
  return chartLibPromise;
}

function toCandleData(c: ClosedChartCandle): CandlestickData<Time> {
  return {
    time: msToChartSecond(c.open_time_ms) as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function sameCandle(a: CandlestickData<Time>, b: CandlestickData<Time>): boolean {
  return a.time === b.time && a.open === b.open && a.high === b.high
    && a.low === b.low && a.close === b.close;
}

function isPrefix(a: CandlestickData<Time>[], b: CandlestickData<Time>[]): boolean {
  if (a.length > b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const prev = a[i];
    const next = b[i];
    if (!prev || !next || !sameCandle(prev, next)) return false;
  }
  return true;
}

function timeToMs(t: Time): number | null {
  return typeof t === "number" ? t * 1000 : null;
}

interface PaperChartProps {
  model: PaperChartModel;
  height?: number;
}

export function PaperChart({model, height = 340}: PaperChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const bundleRef = useRef<Bundle | null>(null);
  const latestModel = useRef(model);
  const applyRef = useRef<((m: PaperChartModel, fit: boolean) => void) | null>(null);
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cursor, setCursor] = useState<{ms: number; price: number | null} | null>(null);
  const [visible, setVisible] = useState<{from: number; to: number} | null>(null);

  const applyModel = useCallback((lib: ChartLib, bundle: Bundle, next: PaperChartModel,
    fit: boolean) => {
    const contextData = next.candles.context.map(toCandleData);
    const candleData = next.candles.closed.map(toCandleData);
    const newSession = bundle.sessionId !== next.identity.session_id;

    if (newSession || !isPrefix(bundle.contextData, contextData)) {
      bundle.context.setData(contextData);
    } else {
      for (let i = bundle.contextData.length; i < contextData.length; i += 1) {
        const point = contextData[i];
        if (point) bundle.context.update(point);
      }
    }
    if (newSession || !isPrefix(bundle.candleData, candleData)) {
      bundle.candles.setData(candleData);
    } else {
      for (let i = bundle.candleData.length; i < candleData.length; i += 1) {
        const point = candleData[i];
        if (point) bundle.candles.update(point);
      }
    }
    bundle.sessionId = next.identity.session_id;
    bundle.contextData = contextData;
    bundle.candleData = candleData;

    // Vela solo-open: un punto en el open conocido, sin cuerpos ni mechas
    // inventados. La forma (dot + marcador "open") la diferencia de una vela
    // cerrada; no se interpola ni se rellena con OHLC.
    const openData: LineData<Time>[] = next.candles.open_only.map((c) => ({
      time: msToChartSecond(c.open_time_ms) as UTCTimestamp,
      value: c.open,
    }));
    bundle.open.setData(openData);

    const openTimes = new Set(next.candles.open_only.map((c) => c.open_time_ms));
    const openSeriesMarkers: SeriesMarker<Time>[] = next.candles.open_only.map((c) => ({
      time: msToChartSecond(c.open_time_ms) as UTCTimestamp,
      position: "aboveBar" as const,
      shape: "circle" as const,
      color: "#fbbf24",
      text: "open",
      size: 1,
      id: `open:${next.identity.session_id}:${c.open_time_ms}`,
    }));

    const candleMarkers: SeriesMarker<Time>[] = [];
    for (const m of next.markers) {
      const base = {
        time: m.time_s as UTCTimestamp,
        id: m.id,
        text: m.label,
        size: 1.2,
      };
      const marker: SeriesMarker<Time> = m.kind === "signal"
        ? {...base, position: "belowBar" as const, shape: "circle" as const,
          color: "#fbbf24"}
        : m.price == null
          ? {...base, position: "aboveBar" as const,
            shape: m.kind === "entry" ? "arrowUp" as const : "arrowDown" as const,
            color: m.kind === "entry" ? "#7fd0f8" : "#38bdf8"}
          : {...base, position: "atPriceMiddle" as const, price: m.price,
            shape: m.kind === "entry" ? "arrowUp" as const : "arrowDown" as const,
            color: m.kind === "entry" ? "#7fd0f8" : "#38bdf8"};
      // Mientras la vela de señal sigue solo-open, su tiempo no existe en la
      // serie de velas cerradas: el marcador viaja con el punto open.
      if (m.kind === "signal" && openTimes.has(m.time_ms)) openSeriesMarkers.push(marker);
      else candleMarkers.push(marker);
    }
    bundle.openMarkers.setMarkers(openSeriesMarkers);
    bundle.markers.setMarkers(candleMarkers);

    const op = next.operation;
    const lines: Array<{price: number; color: string; title: string; style: number}> = [];
    if (op.pending_entry) {
      lines.push({price: op.pending_entry.reference_px, color: "#fbbf24",
        title: "Entrada pendiente (ref.)", style: lib.LineStyle.Dotted});
    }
    if (op.entry) {
      lines.push({price: op.entry.px, color: "#7fd0f8", title: "Entrada",
        style: lib.LineStyle.Dashed});
    }
    if (op.stop_effective_px != null) {
      lines.push({price: op.stop_effective_px, color: "#fb7185", title: "Stop",
        style: lib.LineStyle.Dashed});
    }
    if (op.exit) {
      lines.push({price: op.exit.px, color: "#38bdf8", title: "Salida",
        style: lib.LineStyle.Solid});
    }
    const signature = lines.map((l) => `${l.price}|${l.title}`).join(";");
    if (signature !== bundle.lineSignature) {
      for (const line of bundle.priceLines) bundle.candles.removePriceLine(line);
      bundle.priceLines = lines.map((l) => bundle.candles.createPriceLine({
        price: l.price,
        color: l.color,
        lineWidth: 1,
        lineStyle: l.style,
        axisLabelVisible: true,
        title: `${l.title} ${formatPrice(l.price)}`,
      }));
      bundle.lineSignature = signature;
    }

    if (fit || newSession) {
      bundle.chart.timeScale().fitContent();
    }
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let bundle: Bundle | null = null;
    let onCrosshair: MouseEventHandler<Time> | null = null;
    let onRange: TimeRangeChangeEventHandler<Time> | null = null;
    setLoadError(null);

    loadChartLib().then((lib) => {
      if (cancelled || !hostRef.current) return;
      const chart = lib.createChart(host, {
        autoSize: true,
        layout: {
          background: {type: lib.ColorType.Solid, color: "#071a26"},
          textColor: "#9fb8c8",
          fontFamily: "var(--font-mono), monospace",
          fontSize: 11,
        },
        grid: {
          vertLines: {color: "#123246"},
          horzLines: {color: "#123246"},
        },
        rightPriceScale: {borderColor: "#1d4d68"},
        timeScale: {
          borderColor: "#1d4d68",
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 2,
        },
        crosshair: {
          mode: lib.CrosshairMode.Normal,
          vertLine: {color: "#38bdf8", width: 1, style: lib.LineStyle.Dashed,
            labelBackgroundColor: "#0b2334"},
          horzLine: {color: "#38bdf8", width: 1, style: lib.LineStyle.Dashed,
            labelBackgroundColor: "#0b2334"},
        },
        localization: {priceFormatter: (p: number) => formatPrice(p)},
      });
      const contextSeries = chart.addSeries(lib.CandlestickSeries, {
        upColor: "rgba(52,211,153,0.32)", downColor: "rgba(251,113,133,0.32)",
        borderUpColor: "rgba(52,211,153,0.42)",
        borderDownColor: "rgba(251,113,133,0.42)",
        wickUpColor: "rgba(52,211,153,0.32)",
        wickDownColor: "rgba(251,113,133,0.32)",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const candleSeries = chart.addSeries(lib.CandlestickSeries, {
        upColor: "#34d399", downColor: "#fb7185",
        borderUpColor: "#34d399", borderDownColor: "#fb7185",
        wickUpColor: "#34d399", wickDownColor: "#fb7185",
        priceLineVisible: false,
        lastValueVisible: true,
      });
      const openSeries = chart.addSeries(lib.LineSeries, {
        color: "#fbbf24",
        lineVisible: false,
        pointMarkersVisible: true,
        pointMarkersRadius: 4,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: true,
      });
      const created: Bundle = {
        chart,
        context: contextSeries,
        candles: candleSeries,
        open: openSeries,
        markers: lib.createSeriesMarkers(candleSeries, []),
        openMarkers: lib.createSeriesMarkers(openSeries, []),
        priceLines: [],
        sessionId: "",
        contextData: [],
        candleData: [],
        lineSignature: "",
      };
      bundle = created;
      bundleRef.current = created;
      applyRef.current = (m, fit) => applyModel(lib, created, m, fit);

      const crosshairHandler: MouseEventHandler<Time> = (param) => {
        if (param.time == null || param.point == null) {
          setCursor(null);
          return;
        }
        const ms = timeToMs(param.time);
        if (ms == null) {
          setCursor(null);
          return;
        }
        let price: number | null = null;
        const candle = param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined;
        if (candle && "close" in candle) price = candle.close;
        else {
          const point = param.seriesData.get(openSeries) as LineData<Time> | undefined;
          if (point && "value" in point) price = point.value;
          else {
            // El contexto también es una fuente válida de precio bajo el cursor;
            // sin esto el readout solo mostraba fecha en velas de contexto.
            const ctx = param.seriesData.get(contextSeries) as CandlestickData<Time> | undefined;
            if (ctx && "close" in ctx) price = ctx.close;
          }
        }
        setCursor({ms, price});
      };
      onCrosshair = crosshairHandler;
      chart.subscribeCrosshairMove(crosshairHandler);

      const rangeHandler: TimeRangeChangeEventHandler<Time> = (range) => {
        if (!range) {
          setVisible(null);
          return;
        }
        const from = timeToMs(range.from);
        const to = timeToMs(range.to);
        setVisible(from != null && to != null ? {from, to} : null);
      };
      onRange = rangeHandler;
      chart.timeScale().subscribeVisibleTimeRangeChange(rangeHandler);

      applyModel(lib, created, latestModel.current, true);
      setReady(true);
    }).catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof Error ? err.message : "No se pudo cargar el gráfico");
      }
    });

    return () => {
      cancelled = true;
      if (bundle) {
        if (onCrosshair) bundle.chart.unsubscribeCrosshairMove(onCrosshair);
        if (onRange) bundle.chart.timeScale().unsubscribeVisibleTimeRangeChange(onRange);
        bundle.markers.detach();
        bundle.openMarkers.detach();
        bundle.chart.remove();
      }
      bundleRef.current = null;
      applyRef.current = null;
    };
  }, [applyModel]);

  useEffect(() => {
    latestModel.current = model;
    if (applyRef.current) applyRef.current(model, false);
  }, [model]);

  const fit = useCallback(() => {
    bundleRef.current?.chart.timeScale().fitContent();
  }, []);

  const op = model.operation;
  const summary = [
    `Gráfico ${model.identity.symbol} ${model.identity.interval}`,
    `${model.candles.context.length} velas de contexto`,
    `${model.candles.closed.length} velas cerradas`,
    `${model.candles.open_only.length} velas solo-open`,
    op.entry ? `entrada ${formatPrice(op.entry.px)}` : "sin fill",
    op.stop_effective_px != null ? `stop ${formatPrice(op.stop_effective_px)}` : "sin stop efectivo",
    op.exit ? `salida ${formatPrice(op.exit.px)}` : "sin salida ejecutada",
  ].join(" · ");

  return (
    <div className={s.chartFrame} data-testid="paper-chart-frame">
      <div className={s.chartMeta}>
        <span className={s.chartBadge} data-testid="paper-chart-source">FIXTURE / SIMULACIÓN</span>
        <span>Reloj {fmtUtcPL(model.times.clock_ms)}</span>
        <span data-testid="paper-chart-coverage">
          {model.candles.context.length} contexto · {model.candles.closed.length} cerradas ·
          {" "}{model.candles.open_only.length} solo-open
        </span>
        <span data-testid="paper-chart-window">
          Ventana {visible ? `${fmtUtcPL(visible.from)} → ${fmtUtcPL(visible.to)}` : "—"}
        </span>
        <span data-testid="paper-chart-cursor">
          Cursor {cursor ? `${fmtUtcPL(cursor.ms)}${cursor.price != null ? ` · ${formatPrice(cursor.price)}` : ""}` : "—"}
        </span>
        <span title="La fixture no incluye volumen; no se inventa">Volumen UNKNOWN</span>
        <span title="El backend de Paper Lab no produce indicadores en esta fase">Indicadores: ninguno</span>
        <button type="button" className={s.chartFit} onClick={fit} data-testid="paper-chart-fit">
          Ajustar
        </button>
      </div>
      <div
        ref={hostRef}
        className={s.chartCanvas}
        style={{height}}
        data-testid="paper-chart"
        role="img"
        aria-label={summary}
      />
      {!ready && !loadError && <p className={s.note}>Cargando gráfico interactivo…</p>}
      {loadError && (
        <p className={s.note} role="alert">Gráfico no disponible: {loadError}</p>
      )}
      <p className={s.note}>
        {model.capabilities.limits}. Velas solo-open: punto ámbar sobre el open
        conocido; sin high/low/close inventados. Los niveles son informativos
        (arrastrar stop/objetivo queda diferido).
      </p>
    </div>
  );
}
