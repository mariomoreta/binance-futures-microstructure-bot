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
import type {PaperChartModel} from "@/lib/paper-chart-contract";
import {msToChartSecond} from "@/lib/paper-chart-contract";
import type {MarketChartModel} from "@/lib/market-chart-contract";
import {formatPrice} from "@/lib/format";
import {fmtUtcPL} from "@/lib/paper-lab-live";
import s from "./PriceChart.module.css";

/** Unión versionada: `paper-chart/v1` (fixtures) | `market-chart/v1` (Binance). */
export type PriceChartModel = PaperChartModel | MarketChartModel;

export function isMarketChartModel(m: PriceChartModel): m is MarketChartModel {
  return m.contract_version === "market-chart/v1";
}

type ChartLib = typeof import("lightweight-charts");

/** Forma mínima común para dibujar una vela OHLC. */
interface CandlestickSource {
  open_time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

type Bundle = {
  chart: IChartApi;
  context: ISeriesApi<"Candlestick"> | null;
  candles: ISeriesApi<"Candlestick">;
  /** Vela en formación: serie aparte, visible y claramente distinguible. */
  provisional: ISeriesApi<"Candlestick"> | null;
  open: ISeriesApi<"Line"> | null;
  volume: ISeriesApi<"Histogram"> | null;
  markers: ISeriesMarkersPluginApi<Time>;
  openMarkers: ISeriesMarkersPluginApi<Time> | null;
  priceLines: IPriceLine[];
  identityKey: string;
  contextData: CandlestickData<Time>[];
  candleData: CandlestickData<Time>[];
  lineSignature: string;
  market: boolean;
  // Encuadre inicial diferido: se ajusta cuando el contenedor ya tiene ancho
  // real. Nunca se reencuadra en actualizaciones normales: se respeta el zoom
  // y el desplazamiento del usuario.
  pendingFit: boolean;
  userTouched: boolean;
  lastEarlierRequest: number | null;
};

// Carga diferida: la biblioteca solo se monta en el cliente y una sola vez
// por pagina (no en SSR ni por cada modelo).
let chartLibPromise: Promise<ChartLib> | null = null;
function loadChartLib(): Promise<ChartLib> {
  chartLibPromise ??= import("lightweight-charts");
  return chartLibPromise;
}

function chartTime(ms: number): UTCTimestamp {
  return msToChartSecond(ms) as UTCTimestamp;
}

function toCandleData(c: CandlestickSource): CandlestickData<Time> {
  return {
    time: chartTime(c.open_time_ms),
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

/** `a` es sufijo de `b` (se antepusieron velas antiguas al bloque cargado). */
function isSuffix(a: CandlestickData<Time>[], b: CandlestickData<Time>[]): boolean {
  if (a.length === 0 || a.length > b.length) return false;
  const offset = b.length - a.length;
  for (let i = 0; i < a.length; i += 1) {
    const prev = a[i];
    const next = b[offset + i];
    if (!prev || !next || !sameCandle(prev, next)) return false;
  }
  return true;
}

function timeToMs(t: Time): number | null {
  return typeof t === "number" ? t * 1000 : null;
}

function hostWidth(node: HTMLElement | null): number {
  return node ? node.clientWidth : 0;
}

export function formatAgeShort(ageMs: number): string {
  const seconds = Math.max(0, Math.floor(ageMs / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

interface MetaCommonProps {
  visible: {from: number; to: number} | null;
  cursor: {ms: number; price: number | null} | null;
  id: (suffix: string) => string;
}

function MarketMeta({
  model, visible, cursor, id, onRequestEarlier, loadingEarlier, earlierExhausted,
}: MetaCommonProps & {
  model: MarketChartModel;
  onRequestEarlier?: (beforeMs: number) => void;
  loadingEarlier: boolean;
  earlierExhausted: boolean;
}) {
  return (
    <>
      <span className={`${s.chartBadge} ${s.chartBadgeMarket}`}
        data-testid={id("-source")}>{model.capabilities.banner}</span>
      <span data-testid={id("-contract")}>
        Binance USD-M · {model.identity.endpoint} ·{" "}
        {model.identity.contract
          ? `${model.identity.contract.contract_type ?? "UNKNOWN"} / ${model.identity.contract.status ?? "UNKNOWN"} / ${model.identity.contract.eligible ? "elegible" : "no elegible"}`
          : "contrato no está en el catálogo"}
      </span>
      <span data-testid={id("-coverage")}>
        {model.candles.closed.length} cerradas · {model.candles.provisional.length} provisional ·
        {" "}{model.coverage.state}
        {model.coverage.gap_count ? ` · ${model.coverage.gap_count} huecos` : " · sin huecos"}
        {model.coverage.absent_ranges.length ? ` · ${model.coverage.absent_ranges.length} ausencia(s)` : ""}
        {model.coverage.exhausted_before ? " · fin de histórico" : ""}
      </span>
      <span data-testid={id("-window")}>
        Ventana {visible ? `${fmtUtcPL(visible.from)} → ${fmtUtcPL(visible.to)}` : "—"}
      </span>
      <span data-testid={id("-cursor")}>
        Cursor {cursor ? `${fmtUtcPL(cursor.ms)}${cursor.price != null ? ` · ${formatPrice(cursor.price)}` : ""}` : "—"}
      </span>
      <span data-testid={id("-volume")} title={model.volume_reason ?? undefined}>
        {model.volume_status === "AVAILABLE"
          ? `Volumen ${model.volume_unit ?? "unidad UNKNOWN"}`
          : `Volumen no disponible${model.volume_reason ? ` (${model.volume_reason})` : ""}`}
      </span>
      <span data-testid={id("-freshness")}>
        Última vela {fmtUtcPL(model.times.newest_open_ms)}
        {model.freshness?.provisional ? " (provisional)" : " (cerrada)"}
        {model.times.age_ms != null
          ? ` · adquisición hace ${formatAgeShort(model.times.age_ms)}` : ""}
      </span>
      <span title="El explorador no produce indicadores ni señales">
        Indicadores: ninguno
      </span>
      {onRequestEarlier && (
        <button type="button" className={s.chartFit}
          onClick={() => onRequestEarlier(model.capabilities.earlier_from_ms ?? 0)}
          disabled={loadingEarlier || earlierExhausted
            || model.capabilities.earlier_from_ms == null}
          data-testid={id("-earlier")}>
          {loadingEarlier ? "Cargando anteriores…"
            : earlierExhausted ? "Sin histórico anterior" : "Cargar anteriores"}
        </button>
      )}
    </>
  );
}

function PaperMeta({model, visible, cursor, id}: MetaCommonProps & {
  model: PaperChartModel;
}) {
  return (
    <>
      <span className={s.chartBadge} data-testid={id("-source")}>FIXTURE / SIMULACIÓN</span>
      <span>Reloj {fmtUtcPL(model.times.clock_ms)}</span>
      <span data-testid={id("-coverage")}>
        {model.candles.context.length} contexto · {model.candles.closed.length} cerradas ·
        {" "}{model.candles.open_only.length} solo-open
      </span>
      <span data-testid={id("-window")}>
        Ventana {visible ? `${fmtUtcPL(visible.from)} → ${fmtUtcPL(visible.to)}` : "—"}
      </span>
      <span data-testid={id("-cursor")}>
        Cursor {cursor ? `${fmtUtcPL(cursor.ms)}${cursor.price != null ? ` · ${formatPrice(cursor.price)}` : ""}` : "—"}
      </span>
      <span title="La fixture no incluye volumen; no se inventa">Volumen UNKNOWN</span>
      <span title="El backend de Paper Lab no produce indicadores en esta fase">Indicadores: ninguno</span>
    </>
  );
}

interface PriceChartProps {
  model: PriceChartModel;
  height?: number;
  /** Mercado: pide el bloque anterior a `beforeMs` (paginación hacia atrás). */
  onRequestEarlier?: (beforeMs: number) => void;
  loadingEarlier?: boolean;
  earlierExhausted?: boolean;
}

export function PriceChart({
  model, height = 340, onRequestEarlier, loadingEarlier = false,
  earlierExhausted = false,
}: PriceChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const bundleRef = useRef<Bundle | null>(null);
  const latestModel = useRef(model);
  const applyRef = useRef<((m: PriceChartModel, fit: boolean) => void) | null>(null);
  const propsRef = useRef({model, onRequestEarlier, loadingEarlier, earlierExhausted});
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cursor, setCursor] = useState<{ms: number; price: number | null} | null>(null);
  const [visible, setVisible] = useState<{from: number; to: number} | null>(null);

  // Props vigentes para los manejadores de eventos estables del gráfico.
  // Se sincronizan en un efecto (nunca durante el render).
  useEffect(() => {
    propsRef.current = {model, onRequestEarlier, loadingEarlier, earlierExhausted};
  }, [model, onRequestEarlier, loadingEarlier, earlierExhausted]);

  const tryInitialFit = useCallback((bundle: Bundle, force: boolean) => {
    if (!bundle.pendingFit && !force) return;
    if (hostWidth(hostRef.current) <= 0) return; // sin layout no se fija encuadre
    bundle.chart.timeScale().fitContent();
    bundle.pendingFit = false;
  }, []);

  const applyModel = useCallback((
    lib: ChartLib, bundle: Bundle, next: PriceChartModel, fit: boolean,
  ) => {
    const market = isMarketChartModel(next);
    const identityKey = market
      ? `${next.identity.symbol}|${next.identity.interval}|market`
      : `${next.identity.session_id}|fixture`;
    const newIdentity = bundle.identityKey !== identityKey;
    const newMode = bundle.market !== market;

    const contextData = market ? [] : next.candles.context.map(toCandleData);
    const candleData = next.candles.closed.map(toCandleData);
    const previousLength = bundle.candleData.length;

    // Al anteponer un bloque anterior (paginación hacia atrás) se conserva el
    // encuadre desplazando el rango lógico visible por las velas añadidas.
    const prepended = !newIdentity && !newMode
      && isSuffix(bundle.candleData, candleData)
      && candleData.length > previousLength;
    let logical: {from: number; to: number} | null = null;
    if (prepended) {
      const scale = bundle.chart.timeScale() as unknown as {
        getVisibleLogicalRange?: () => {from: number; to: number} | null;
      };
      logical = typeof scale.getVisibleLogicalRange === "function"
        ? scale.getVisibleLogicalRange() : null;
    }

    if (bundle.context && (newIdentity || newMode
      || !isPrefix(bundle.contextData, contextData))) {
      bundle.context.setData(contextData);
    } else if (bundle.context) {
      for (let i = bundle.contextData.length; i < contextData.length; i += 1) {
        const point = contextData[i];
        if (point) bundle.context.update(point);
      }
    }
    if (newIdentity || newMode || !isPrefix(bundle.candleData, candleData)) {
      bundle.candles.setData(candleData);
    } else {
      for (let i = bundle.candleData.length; i < candleData.length; i += 1) {
        const point = candleData[i];
        if (point) bundle.candles.update(point);
      }
    }
    bundle.identityKey = identityKey;
    bundle.market = market;
    bundle.contextData = contextData;
    bundle.candleData = candleData;

    // Vela en formación (solo mercado): serie ámbar translúcida, separada de
    // las cerradas para que la diferencia sea visible. Se reemplaza en cada
    // actualización (0 o 1 vela) y desaparece cuando el backend la cierra.
    if (bundle.provisional) {
      const provisionalData = market ? next.candles.provisional.map(toCandleData) : [];
      bundle.provisional.setData(provisionalData);
    }

    if (prepended && logical) {
      const shift = candleData.length - previousLength;
      const scale = bundle.chart.timeScale() as unknown as {
        setVisibleLogicalRange?: (r: {from: number; to: number}) => void;
      };
      if (typeof scale.setVisibleLogicalRange === "function") {
        scale.setVisibleLogicalRange({from: logical.from + shift,
          to: logical.to + shift});
      }
    }

    // Vela solo-open (Paper Lab): punto en el open conocido, sin OHLC
    // inventado; se diferencia de una vela cerrada por su forma y marcador.
    const openData: LineData<Time>[] = market ? []
      : next.candles.open_only.map((c) => ({
        time: chartTime(c.open_time_ms), value: c.open,
      }));
    if (bundle.open) bundle.open.setData(openData);

    // Volumen: solo cuando la fuente lo publica (klines). Nunca se inventa.
    if (bundle.volume) {
      const bars = next.volume ?? [];
      bundle.volume.setData(bars.map((b) => ({
        time: chartTime(b.time_ms),
        value: b.value,
        color: b.close >= b.open ? "rgba(52,211,153,0.42)"
          : "rgba(251,113,133,0.42)",
      })));
    }

    const openTimes = new Set(market ? []
      : next.candles.open_only.map((c) => c.open_time_ms));
    const openSeriesMarkers: SeriesMarker<Time>[] = market ? []
      : next.candles.open_only.map((c) => ({
        time: chartTime(c.open_time_ms),
        position: "aboveBar" as const,
        shape: "circle" as const,
        color: "#fbbf24",
        text: "open",
        size: 1,
        id: `open:${next.identity.session_id}:${c.open_time_ms}`,
      }));

    const candleMarkers: SeriesMarker<Time>[] = [];
    if (market) {
      // Solo histórico de mercado: la vela actual provisional se rotula como
      // tal. No se dibujan señales, entradas, stops ni salidas.
      for (const m of next.markers) {
        candleMarkers.push({
          time: m.time_s as UTCTimestamp,
          id: m.id,
          text: m.label,
          size: 1,
          position: "aboveBar" as const,
          shape: "circle" as const,
          color: "#7fd0f8",
        });
      }
    } else {
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
    }
    if (bundle.openMarkers) bundle.openMarkers.setMarkers(openSeriesMarkers);
    bundle.markers.setMarkers(candleMarkers);

    // Niveles (solo Paper Lab): derivados de campos del backend, informativos.
    const op = isMarketChartModel(next) ? null : next.operation;
    const lines: Array<{price: number; color: string; title: string; style: number}> = [];
    if (op?.pending_entry) {
      lines.push({price: op.pending_entry.reference_px, color: "#fbbf24",
        title: "Entrada pendiente (ref.)", style: lib.LineStyle.Dotted});
    }
    if (op?.entry) {
      lines.push({price: op.entry.px, color: "#7fd0f8", title: "Entrada",
        style: lib.LineStyle.Dashed});
    }
    if (op?.stop_effective_px != null) {
      lines.push({price: op.stop_effective_px, color: "#fb7185", title: "Stop",
        style: lib.LineStyle.Dashed});
    }
    if (op?.exit) {
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

    if (newIdentity || newMode) bundle.pendingFit = true;
    const observedStart = isMarketChartModel(next)
      ? next.capabilities.earlier_from_ms : null;
    if (bundle.lastEarlierRequest != null
      && bundle.lastEarlierRequest !== observedStart) {
      bundle.lastEarlierRequest = null;
    }
    tryInitialFit(bundle, fit);
  }, [tryInitialFit]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let bundle: Bundle | null = null;
    let observer: ResizeObserver | null = null;
    let onCrosshair: MouseEventHandler<Time> | null = null;
    let onRange: TimeRangeChangeEventHandler<Time> | null = null;
    setLoadError(null);

    loadChartLib().then((lib) => {
      if (cancelled || !hostRef.current) return;
      const market = isMarketChartModel(latestModel.current);
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

      // Series por modo: Paper Lab usa contexto + velas + solo-open; el
      // explorador de mercado usa velas + volumen (sin contexto ni niveles).
      const contextSeries = market ? null : chart.addSeries(lib.CandlestickSeries, {
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
      const openSeries = market ? null : chart.addSeries(lib.LineSeries, {
        color: "#fbbf24",
        lineVisible: false,
        pointMarkersVisible: true,
        pointMarkersRadius: 4,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: true,
      });
      const volumeSeries = market
        ? chart.addSeries(lib.HistogramSeries, {
          priceFormat: {type: "volume"},
          priceScaleId: "volume",
          priceLineVisible: false,
          lastValueVisible: false,
        })
        : null;
      if (volumeSeries) {
        volumeSeries.priceScale().applyOptions({
          scaleMargins: {top: 0.82, bottom: 0},
        });
      }
      // Serie propia de la vela en formación (solo mercado): ámbar translúcido
      // para que se distinga de una vela cerrada. Se crea después del volumen
      // para no desplazar los índices existentes de las series.
      const provisionalSeries = market
        ? chart.addSeries(lib.CandlestickSeries, {
          upColor: "rgba(251,191,36,0.28)", downColor: "rgba(251,191,36,0.28)",
          borderUpColor: "#fbbf24", borderDownColor: "#fbbf24",
          wickUpColor: "#fbbf24", wickDownColor: "#fbbf24",
          priceLineVisible: false,
          lastValueVisible: false,
        })
        : null;

      const created: Bundle = {
        chart,
        context: contextSeries,
        candles: candleSeries,
        provisional: provisionalSeries,
        open: openSeries,
        volume: volumeSeries,
        markers: lib.createSeriesMarkers(candleSeries, []),
        openMarkers: openSeries ? lib.createSeriesMarkers(openSeries, []) : null,
        priceLines: [],
        identityKey: "",
        contextData: [],
        candleData: [],
        lineSignature: "",
        market,
        pendingFit: true,
        userTouched: false,
        lastEarlierRequest: null,
      };
      bundle = created;
      bundleRef.current = created;
      applyRef.current = (m, fit) => applyModel(lib, created, m, fit);

      const crosshairHandler: MouseEventHandler<Time> = (param) => {
        created.userTouched = true;
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
        else if (openSeries) {
          const point = param.seriesData.get(openSeries) as LineData<Time> | undefined;
          if (point && "value" in point) price = point.value;
        }
        if (price == null && contextSeries) {
          // El contexto también es una fuente válida de precio bajo el cursor;
          // sin esto el readout solo mostraba fecha en velas de contexto.
          const ctx = param.seriesData.get(contextSeries) as CandlestickData<Time> | undefined;
          if (ctx && "close" in ctx) price = ctx.close;
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
        const props = propsRef.current;
        const current = props.model;
        if (!isMarketChartModel(current)) return;
        if (from == null || !props.onRequestEarlier) return;
        if (props.loadingEarlier || props.earlierExhausted) return;
        // Solo tras interacción del usuario: el encuadre inicial y las
        // actualizaciones normales no disparan descargas.
        if (!created.userTouched) return;
        const observedStart = current.capabilities.earlier_from_ms;
        if (observedStart == null) return;
        if (from > observedStart + 3 * current.identity.interval_ms) return;
        if (created.lastEarlierRequest === observedStart) return;
        created.lastEarlierRequest = observedStart;
        props.onRequestEarlier(observedStart);
      };
      onRange = rangeHandler;
      chart.timeScale().subscribeVisibleTimeRangeChange(rangeHandler);

      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => {
          if (bundle) tryInitialFit(bundle, false);
        });
        observer.observe(host);
      }

      applyModel(lib, created, latestModel.current, true);
      setReady(true);
    }).catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof Error ? err.message : "No se pudo cargar el gráfico");
      }
    });

    return () => {
      cancelled = true;
      if (observer) observer.disconnect();
      if (bundle) {
        if (onCrosshair) bundle.chart.unsubscribeCrosshairMove(onCrosshair);
        if (onRange) bundle.chart.timeScale().unsubscribeVisibleTimeRangeChange(onRange);
        bundle.markers.detach();
        bundle.openMarkers?.detach();
        bundle.chart.remove();
      }
      bundleRef.current = null;
      applyRef.current = null;
    };
  }, [applyModel, tryInitialFit]);

  useEffect(() => {
    latestModel.current = model;
    if (applyRef.current) applyRef.current(model, false);
  }, [model]);

  const fit = useCallback(() => {
    const bundle = bundleRef.current;
    if (bundle) tryInitialFit(bundle, true);
  }, [tryInitialFit]);

  const id = (suffix: string) => `${isMarketChartModel(model) ? "market" : "paper"}-chart${suffix}`;
  const summary = isMarketChartModel(model)
    ? [
      `Gráfico histórico ${model.identity.symbol} ${model.identity.interval}`,
      `${model.candles.closed.length} velas cerradas`,
      `${model.candles.provisional.length} vela provisional`,
      `cobertura ${model.capabilities.coverage_state}`,
      model.volume_status === "AVAILABLE"
        ? `volumen en ${model.volume_unit ?? "unidad UNKNOWN"}`
        : "volumen no disponible",
    ].join(" · ")
    : [
      `Gráfico ${model.identity.symbol} ${model.identity.interval}`,
      `${model.candles.context.length} velas de contexto`,
      `${model.candles.closed.length} velas cerradas`,
      `${model.candles.open_only.length} velas solo-open`,
      model.operation.entry ? `entrada ${formatPrice(model.operation.entry.px)}` : "sin fill",
      model.operation.stop_effective_px != null
        ? `stop ${formatPrice(model.operation.stop_effective_px)}` : "sin stop efectivo",
      model.operation.exit ? `salida ${formatPrice(model.operation.exit.px)}` : "sin salida ejecutada",
    ].join(" · ");

  return (
    <div className={s.chartFrame} data-testid={id("-frame")}>
      <div className={s.chartMeta}>
        {isMarketChartModel(model)
          ? <MarketMeta model={model} visible={visible} cursor={cursor} id={id}
            onRequestEarlier={onRequestEarlier} loadingEarlier={loadingEarlier}
            earlierExhausted={earlierExhausted} />
          : <PaperMeta model={model} visible={visible} cursor={cursor} id={id} />}
        <button type="button" className={s.chartFit} onClick={fit}
          data-testid={id("-fit")}>Ajustar</button>
      </div>
      <div
        ref={hostRef}
        className={s.chartCanvas}
        style={{height}}
        data-testid={isMarketChartModel(model) ? "market-chart" : "paper-chart"}
        role="img"
        aria-label={summary}
      />
      {!ready && !loadError && <p className={s.note}>Cargando gráfico interactivo…</p>}
      {loadError && (
        <p className={s.note} role="alert">Gráfico no disponible: {loadError}</p>
      )}
      <p className={s.note}>
        {isMarketChartModel(model) ? (
          <>
            {model.capabilities.limits}. Histórico consultado bajo demanda sobre
            REST público: no es un feed continuo y no se rotula como LIVE. La
            vela actual se marca provisional y no publica cierre. No se dibujan
            indicadores, objetivos ni marcas de operaciones; el volumen se
            muestra solo si la fuente lo publica, en la unidad declarada.
          </>
        ) : (
          <>
            {model.capabilities.limits}. Velas solo-open: punto ámbar sobre el open
            conocido; sin high/low/close inventados. Los niveles son informativos
            (arrastrar stop/objetivo queda diferido).
          </>
        )}
      </p>
    </div>
  );
}
