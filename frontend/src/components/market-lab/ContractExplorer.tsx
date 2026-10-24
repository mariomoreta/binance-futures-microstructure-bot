"use client";
// Explorador de contratos Binance USD-M + histórico paginado bajo demanda.
//
// Reglas de esta vista:
//  - Solo visualiza: abrir un símbolo NO abre posición, NO inicia el monitor y
//    NO lo añade al universo del bot.
//  - El catálogo se sirve desde la caché aislada con refresco acotado (TTL 6 h o
//    botón explícito = 1 petición).
//  - El histórico se lee primero de lo ya almacenado; solo se consulta Binance
//    para el bloque que falta, con página de 300 velas y 1 página por acción.
//  - Los estados de error, presupuesto agotado, rate limit y falta de cobertura
//    se muestran; nunca se sustituyen por datos inventados.
//  - Ninguna marca de sesión Paper Lab se mezcla aquí (no hay sesión).

import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {PriceChart} from "@/components/chart/PriceChart";
import {
  buildMarketChartModel,
  mergeEarlierSeries,
  type MarketCatalogPayload,
  type MarketContractRow,
  type MarketSeriesPayload,
} from "@/lib/market-chart-contract";
import {
  buildStreamMeta,
  describeGap,
  livePermitted,
  mergeStreamIntoSeries,
  streamStateLabel,
} from "@/lib/market-stream";
import {useMarketStream} from "@/lib/use-market-stream";
import {
  EXPLORER_PAGE_BARS,
  contractLabel,
  describeCoverage,
  fetchSeriesApi,
  formatUtc,
  initialWindow,
  searchContractsApi,
  windowLabel,
} from "@/lib/market-explorer";
import s from "./ContractExplorer.module.css";

const INTERVALS = [
  {id: "1m", ms: 60_000},
  {id: "15m", ms: 900_000},
  {id: "1h", ms: 3_600_000},
  {id: "4h", ms: 14_400_000},
  {id: "1d", ms: 86_400_000},
] as const;

type CatalogState = "idle" | "loading" | "ready" | "unavailable" | "error";
type SeriesState = "idle" | "loading" | "ready" | "error";

const intervalMsOf = (interval: string): number =>
  INTERVALS.find((entry) => entry.id === interval)?.ms ?? 3_600_000;

export function ContractExplorer() {
  const [queryInput, setQueryInput] = useState("");
  const [catalog, setCatalog] = useState<MarketCatalogPayload | null>(null);
  const [catalogState, setCatalogState] = useState<CatalogState>("idle");
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketContractRow | null>(null);
  const [interval, setIntervalId] = useState<string>("1h");
  const [window, setWindow] = useState<{fromMs: number; toMs: number} | null>(null);
  const [series, setSeries] = useState<MarketSeriesPayload | null>(null);
  const [seriesState, setSeriesState] = useState<SeriesState>("idle");
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [earlierExhausted, setEarlierExhausted] = useState(false);
  const [earlierFailed, setEarlierFailed] = useState(false);
  const [earlierError, setEarlierError] = useState<string | null>(null);

  const catalogSeq = useRef(0);
  const seriesSeq = useRef(0);
  const catalogAbort = useRef<AbortController | null>(null);
  const seriesAbort = useRef<AbortController | null>(null);
  const seriesRef = useRef<MarketSeriesPayload | null>(null);
  const loadingEarlierRef = useRef(false);
  const earlierKeyRef = useRef<string | null>(null);
  const liveRef = useRef<HTMLParagraphElement | null>(null);
  const [announce, setAnnounce] = useState("");

  useEffect(() => {
    seriesRef.current = series;
  }, [series]);

  const runCatalog = useCallback(async (query: string, refresh = false) => {
    const seq = ++catalogSeq.current;
    catalogAbort.current?.abort();
    const controller = new AbortController();
    catalogAbort.current = controller;
    setCatalogState("loading");
    setCatalogError(null);
    const result = await searchContractsApi({
      query, limit: 20, refresh, signal: controller.signal,
    });
    // Descarte de respuestas tardías (búsqueda superada por otra).
    if (seq !== catalogSeq.current) return;
    if (!result.ok) {
      if (result.error === "ABORTED") return;
      setCatalogState("error");
      setCatalogError([result.error, result.detail].filter(Boolean).join(" · "));
      setAnnounce("No se pudo consultar el catálogo de contratos.");
      return;
    }
    const data = result.data ?? null;
    setCatalog(data);
    setCatalogState(data?.available ? "ready" : "unavailable");
    setAnnounce(data?.available
      ? `${data.result_count} contratos encontrados.`
      : "Catálogo no disponible en la caché local.");
  }, []);

  const loadSeries = useCallback(async (
    target: {fromMs: number; toMs: number}, opts: {earlier: boolean},
  ) => {
    if (!selected) return;
    const seq = ++seriesSeq.current;
    seriesAbort.current?.abort();
    const controller = new AbortController();
    seriesAbort.current = controller;
    if (opts.earlier) {
      loadingEarlierRef.current = true;
      setLoadingEarlier(true);
      setEarlierError(null);
    } else {
      setSeriesState("loading");
      setSeriesError(null);
    }
    const result = await fetchSeriesApi({
      symbol: selected.symbol,
      interval,
      fromMs: target.fromMs,
      toMs: target.toMs,
      bars: EXPLORER_PAGE_BARS,
      pages: 1,
      pageLimit: EXPLORER_PAGE_BARS,
      signal: controller.signal,
    });
    if (opts.earlier) {
      loadingEarlierRef.current = false;
      earlierKeyRef.current = null;
      setLoadingEarlier(false);
    }
    // Cambio de símbolo/intervalo: la respuesta anterior se descarta.
    if (seq !== seriesSeq.current) return;
    if (!result.ok) {
      if (result.error === "ABORTED") {
        // Cancelación: no es fallo ni agotamiento; un reintento es legítimo.
        if (opts.earlier) setEarlierFailed(false);
        return;
      }
      const detail = [result.error, result.detail].filter(Boolean).join(" · ");
      if (opts.earlier) {
        // El bloque anterior falla: se conserva el gráfico ya cargado y se
        // permite reintentar (no se marca como agotado).
        setEarlierFailed(true);
        setEarlierError(detail);
        setAnnounce("No se pudo cargar el bloque anterior; puedes reintentar.");
        return;
      }
      setSeriesState("error");
      setSeriesError(detail);
      return;
    }
    const data = result.data ?? null;
    if (!data) {
      if (opts.earlier) {
        setEarlierFailed(true);
        setEarlierError("Respuesta vacía del histórico.");
        return;
      }
      setSeriesState("error");
      setSeriesError("Respuesta vacía del histórico.");
      return;
    }
    if (opts.earlier) {
      setEarlierFailed(false);
      setEarlierError(null);
      // Anteponer, no sustituir: el extremo reciente (y sus actualizaciones)
      // sigue siendo el mismo; el bloque solo añade velas más antiguas.
      const merged = seriesRef.current
        ? mergeEarlierSeries(seriesRef.current, data)
        : {payload: data, added: data.candles.length};
      setSeries(merged.payload);
      setWindow({
        fromMs: merged.payload.requested.from_ms,
        toMs: merged.payload.requested.to_ms,
      });
      // Sin velas nuevas y sin más historia detrás, no queda bloque anterior.
      if (merged.added === 0 || data.coverage.exhausted_before) {
        setEarlierExhausted(true);
      }
    } else {
      setSeries(data);
      setWindow(target);
    }
    setSeriesState("ready");
  }, [interval, selected]);

  const applySelection = useCallback(async (target: {fromMs: number; toMs: number}) => {
    setSeries(null);
    setWindow(null);
    setEarlierExhausted(false);
    await loadSeries(target, {earlier: false});
  }, [loadSeries]);

  // Catálogo inicial: solo caché/refresco acotado; no descarga histórico ni
  // inicia nada. La selección de un contrato es la que pide velas.
  useEffect(() => {
    let cancelled = false;
    // El primer setState ocurre en un microtask: el efecto no provoca un
    // render en cascada durante el montaje.
    void Promise.resolve().then(() => {
      if (cancelled) return;
      return runCatalog("");
    });
    return () => { cancelled = true; };
  }, [runCatalog]);

  // Nuevo símbolo o intervalo: ventana recalculada y bloque más reciente.
  useEffect(() => {
    if (!selected) return;
    const step = intervalMsOf(interval);
    const target = initialWindow(Date.now(), step, EXPLORER_PAGE_BARS);
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      return applySelection(target);
    });
    return () => { cancelled = true; };
  }, [applySelection, interval, selected]);

  const requestEarlier = useCallback((beforeMs: number) => {
    // Guard síncrono: dos eventos del mismo gesto no abren dos peticiones.
    if (!selected || loadingEarlierRef.current || earlierExhausted) return;
    const step = intervalMsOf(interval);
    // Bloque estrictamente anterior al borde ya cargado. Pedir hasta
    // `window.toMs` devolvía la misma ventana reciente (solapamiento) y el
    // contador no crecía: no era pérdida de histórico, era una petición mal
    // encuadrada.
    const anchor = beforeMs > 0 ? beforeMs : (window?.fromMs ?? 0);
    if (!anchor) return;
    const toMs = anchor - step;
    const fromMs = toMs - (EXPLORER_PAGE_BARS - 1) * step;
    if (toMs <= 0) {
      setEarlierExhausted(true);
      return;
    }
    const key = `${Math.max(0, fromMs)}:${toMs}`;
    if (earlierKeyRef.current === key) return;
    earlierKeyRef.current = key;
    void loadSeries({fromMs: Math.max(0, fromMs), toMs}, {earlier: true});
  }, [earlierExhausted, interval, loadSeries, selected, window]);

  // Feed continuo: se abre solo con el gráfico ya cargado y se cierra al
  // desmontar o cambiar de símbolo/intervalo. Es visualización: no arranca el
  // monitor ni simulación alguna.
  const streamView = useMarketStream({
    symbol: selected?.symbol ?? null,
    interval,
    fromMs: series?.requested.from_ms ?? null,
    toMs: series?.requested.to_ms ?? null,
    enabled: Boolean(selected && series && seriesState === "ready"),
  });
  const mergedSeries = useMemo(
    () => (series ? mergeStreamIntoSeries(series, streamView) : null),
    [series, streamView],
  );
  const streamMeta = useMemo(() => buildStreamMeta(streamView), [streamView]);
  const model = useMemo(() => (mergedSeries
    ? buildMarketChartModel(mergedSeries, {
      contract: mergedSeries.contract ?? selected, stream: streamMeta,
    })
    : null), [mergedSeries, selected, streamMeta]);
  const stale = catalog?.catalog.stale === true;
  const resultCount = catalog?.result_count ?? 0;

  return (
    <div className={s.root} data-testid="contract-explorer">
      <header className={s.header}>
        <div>
          <small>MARKET INTELLIGENCE / BINANCE USD-M · REST PÚBLICO</small>
          <h2>Contract explorer · histórico bajo demanda</h2>
          <p>
            Busca un contrato de Binance USD-M Futures y visualiza su histórico.
            Solo lectura pública: abrir un símbolo no abre posiciones, no inicia
            el monitor y no lo añade al universo del bot.
          </p>
        </div>
        <span className={`${s.pill} ${stale ? s.pillOff : ""}`} data-testid="explorer-catalog-state">
          {catalogState === "loading" ? "catálogo: consultando"
            : catalogState === "unavailable" ? "catálogo: no disponible"
              : catalogState === "error" ? "catálogo: error"
                : catalog?.available
                  ? `catálogo: ${catalog.catalog.entries} contratos${stale ? " · desactualizado" : ""}`
                  : "catálogo: sin datos"}
        </span>
      </header>

      <p className={s.notice}>
        <strong>HISTÓRICO + FEED BAJO DEMANDA</strong> — datos Binance USD-M
        Futures: histórico paginado por REST público y, si el servicio local de
        datos está arrancado, la vela en formación por WebSocket público. Solo
        se escribe LIVE cuando el backend declara RECIBIENDO con datos frescos
        del símbolo e intervalo actuales; un socket abierto no basta. El volumen
        se muestra solo si la fuente lo publica y en su unidad. Las velas
        adquiridas por REST se guardan únicamente en la caché aislada del
        explorador; el feed no persiste nada.
      </p>

      <form
        className={s.form}
        onSubmit={(event) => {
          event.preventDefault();
          void runCatalog(queryInput.trim());
        }}
      >
        <label htmlFor="contract-query">
          Símbolo o nombre del contrato
          <input
            id="contract-query"
            name="q"
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            maxLength={32}
            placeholder="BTCUSDT, ETH, SOL…"
            autoComplete="off"
            data-testid="explorer-query"
          />
        </label>
        <button type="submit" className={s.button} data-testid="explorer-search"
          disabled={catalogState === "loading"}>
          Buscar contratos
        </button>
        <button type="button" className={s.button} data-testid="explorer-refresh"
          onClick={() => void runCatalog(queryInput.trim(), true)}
          disabled={catalogState === "loading"}
          title="Refresco acotado del catálogo: 1 petición a /fapi/v1/exchangeInfo">
          Actualizar catálogo (1 petición)
        </button>
      </form>

      <p ref={liveRef} className={s.hint} aria-live="polite" data-testid="explorer-announce">
        {announce}
      </p>

      {catalogState === "loading" && (
        <p className={s.loading} role="status">Consultando catálogo de contratos…</p>
      )}
      {catalogState === "error" && (
        <p className={s.error} role="alert" data-testid="explorer-catalog-error">
          Catálogo no disponible: {catalogError ?? "error desconocido"}. No se
          muestran sustitutos.
        </p>
      )}
      {catalogState === "unavailable" && (
        <p className={s.empty} role="status" data-testid="explorer-catalog-unavailable">
          El catálogo aún no está en caché y no se refrescó. Usa «Actualizar
          catálogo» (1 petición pública) para poblarlo. No se inventan contratos.
        </p>
      )}
      {catalogState === "ready" && resultCount === 0 && (
        <p className={s.empty} role="status" data-testid="explorer-empty">
          Sin contratos que coincidan con «{catalog?.query}». La búsqueda es sobre
          el catálogo cacheado ({catalog?.catalog.entries ?? 0} contratos).
        </p>
      )}

      {catalogState === "ready" && resultCount > 0 && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <caption>
              Contratos USD-M Futures ({catalog?.venue} · {catalog?.endpoint}).
              «Elegible» = PERPETUAL + TRADING + quote USDT; el resto se muestra
              con sus motivos. Buscar no es una recomendación.
            </caption>
            <thead>
              <tr>
                <th scope="col">Símbolo</th>
                <th scope="col">Base / Quote</th>
                <th scope="col">Tipo</th>
                <th scope="col">Estado</th>
                <th scope="col">Elegibilidad</th>
                <th scope="col">Histórico</th>
              </tr>
            </thead>
            <tbody>
              {(catalog?.results ?? []).map((row) => {
                const active = selected?.symbol === row.symbol;
                return (
                  <tr key={row.symbol} data-testid={`explorer-row-${row.symbol}`}>
                    <td className={s.symbol}>{row.symbol}</td>
                    <td>{row.base_asset ?? "UNKNOWN"} / {row.quote_asset ?? "UNKNOWN"}</td>
                    <td>{row.contract_type ?? "UNKNOWN"}</td>
                    <td>{row.status ?? "UNKNOWN"}</td>
                    <td>
                      {row.eligible ? (
                        <span className={s.pill}>elegible</span>
                      ) : (
                        <>
                          <span className={`${s.pill} ${s.pillOff}`}>no elegible</span>
                          <div className={s.reason}>{row.exclusion_reasons.join("; ")}</div>
                        </>
                      )}
                    </td>
                    <td>
                      <button type="button" className={s.button}
                        aria-pressed={active}
                        data-testid={`explorer-open-${row.symbol}`}
                        onClick={() => setSelected(row)}>
                        {active ? "Seleccionado" : "Ver histórico"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <section className={s.panel} aria-label={`Histórico de ${selected.symbol}`}>
          <div className={s.row}>
            <div className={s.identity} data-testid="explorer-selected">
              <b>{selected.symbol}</b> · {selected.base_asset ?? "UNKNOWN"}/
              {selected.quote_asset ?? "UNKNOWN"} · {contractLabel(series?.contract ?? selected)}
              {selected.exclusion_reasons.length > 0
                ? ` · motivos: ${selected.exclusion_reasons.join("; ")}`
                : ""}
              <br />
              Fuente: {series?.venue ?? "binance"} · {series?.api_family ?? "fapi"} ·
              {" "}{series?.endpoint ?? "/fapi/v1/klines"} · origen de las velas:
              {" "}{series?.source ?? "klines"}
            </div>
            <label className={s.control} htmlFor="explorer-interval">
              Temporalidad
              <select
                id="explorer-interval"
                value={interval}
                onChange={(event) => setIntervalId(event.target.value)}
                data-testid="explorer-interval"
              >
                {INTERVALS.map((entry) => (
                  <option key={entry.id} value={entry.id}>{entry.id}</option>
                ))}
              </select>
            </label>
          </div>

          {seriesState === "loading" && (
            <p className={s.loading} role="status">Cargando histórico de {selected.symbol}…</p>
          )}
          {seriesState === "error" && (
            <p className={s.error} role="alert" data-testid="explorer-series-error">
              Histórico no disponible: {seriesError ?? "error desconocido"}.
            </p>
          )}

          {series?.fetch?.error && (
            <p className={s.warn} role="status" data-testid="explorer-fetch-warning">
              Adquisición detenida ({series.fetch.error}): {series.fetch.detail ?? "sin detalle"}.
              Se muestra solo lo que ya estaba almacenado; no se reintenta en bucle.
            </p>
          )}
          {earlierError && (
            <p className={s.warn} role="status" data-testid="explorer-earlier-error">
              Bloque anterior no disponible ({earlierError}). El gráfico cargado se
              conserva; pulsa «Cargar anteriores» para reintentar.
            </p>
          )}
          {series && series.candles.length === 0 && seriesState === "ready" && (
            <p className={s.empty} role="status" data-testid="explorer-no-coverage">
              Sin cobertura para {selected.symbol} {interval} en la ventana
              solicitada. No se rellena con datos simulados.
            </p>
          )}

          {series && (
            <div className={s.meta} data-testid="explorer-provenance">
              <div>
                <small>Ventana solicitada (UTC)</small>
                <b>{windowLabel(series.requested.from_ms, series.requested.to_ms)}</b>
              </div>
              <div>
                <small>Cobertura</small>
                <b data-testid="explorer-coverage">{describeCoverage(series)}</b>
              </div>
              <div>
                <small>Frescura (adquisición, no feed)</small>
                <b>
                  {series.freshness.newest_open_ms === null
                    ? "sin velas"
                    : `${formatUtc(series.freshness.newest_open_ms)}${series.freshness.provisional ? " (provisional)" : " (cerrada)"}`}
                  {series.freshness.fetched_at_ms !== null
                    ? ` · guardado ${formatUtc(series.freshness.fetched_at_ms)}` : ""}
                </b>
              </div>
              <div>
                <small>Volumen</small>
                <b data-testid="explorer-volume-unit">
                  {series.volume.available
                    ? `${series.volume.fields.join(" + ")} · base ${series.volume.base_asset ?? "UNKNOWN"}`
                    : `no disponible${series.volume.reason ? ` (${series.volume.reason})` : ""}`}
                </b>
              </div>
              <div>
                <small>Almacenamiento</small>
                <b>
                  canónico {series.storage?.canonical_rows ?? 0} · caché {series.storage?.cache_rows ?? 0}
                  {series.storage?.canonical_error ? ` · ${series.storage.canonical_error}` : ""}
                </b>
              </div>
              <div>
                <small>Adquisición</small>
                <b data-testid="explorer-fetch">
                  {series.fetch.performed
                    ? `${series.fetch.requests} petición(es) · ${series.fetch.bars_stored ?? 0} velas guardadas`
                    : "sin peticiones (solo almacenado)"}
                  {series.budget
                    ? ` · ${series.budget.used_in_window}/${series.budget.max_requests_per_window} en ventana`
                    : ""}
                </b>
              </div>
            </div>
          )}

          {model && mergedSeries && mergedSeries.candles.length > 0 && (
            <PriceChart
              model={model}
              height={360}
              onRequestEarlier={requestEarlier}
              loadingEarlier={loadingEarlier}
              earlierExhausted={earlierExhausted || mergedSeries.coverage.exhausted_before}
              earlierFailed={earlierFailed}
            />
          )}

          <section className={s.stream} aria-label="Estado del feed de velas"
            data-testid="explorer-stream">
            <div className={s.streamRow}>
              <div>
                <small>Fuente / identidad</small>
                <b>Binance USD-M · {selected.symbol} · {interval} · market-stream/v1</b>
              </div>
              <div>
                <small>Estado del feed</small>
                <b data-testid="explorer-stream-state">
                  {streamView.available === false
                    ? "DESCONECTADO · servicio detenido"
                    : streamView.status
                      ? streamStateLabel(streamView.status.connection.state)
                      : streamView.available === null ? "CONECTANDO" : "SIN FEED"}
                </b>
              </div>
              <div>
                <small>LIVE</small>
                <b data-testid="explorer-stream-live">
                  {livePermitted(streamView.status) ? "LIVE" : "no LIVE"}
                </b>
              </div>
              <div>
                <small>Última actualización recibida</small>
                <b data-testid="explorer-stream-updated">
                  {streamView.status?.last_message_ms
                    ? formatUtc(streamView.status.last_message_ms)
                    : "sin mensajes"}
                  {typeof streamView.status?.age_ms === "number"
                    ? ` · hace ${Math.max(0, Math.round(streamView.status.age_ms / 1000))} s`
                    : ""}
                </b>
              </div>
              <div>
                <small>Velas en pantalla</small>
                <b data-testid="explorer-stream-count">
                  {`${mergedSeries?.candles.length ?? 0} cargadas · `}
                  {`${mergedSeries ? mergedSeries.candles.filter((c) => c.provisional).length : 0} provisional`}
                </b>
              </div>
            </div>

            {streamView.available === false && (
              <p className={s.warn} role="status" data-testid="explorer-stream-down">
                Servicio de datos detenido: se conserva el histórico ya cargado y
                no se declara LIVE. El monitor del bot y las sesiones Paper Lab no
                dependen de este feed. Arranque manual:
                {" "}<code>python scripts/market_stream_service.py --port 8791</code>.
              </p>
            )}
            {streamView.error && streamView.available !== false && (
              <p className={s.warn} role="status" data-testid="explorer-stream-error">
                Feed: {streamView.error}
                {streamView.attempts > 0 ? ` · reintento ${streamView.attempts}` : ""}
              </p>
            )}
            {streamView.gaps.length > 0 && (
              <ul className={s.gaps} data-testid="explorer-stream-gaps">
                {streamView.gaps.map((gap, index) => (
                  <li key={`${gap.reason}-${gap.expected_from_ms}-${index}`}>
                    {describeGap(gap)}
                  </li>
                ))}
              </ul>
            )}

            <p className={s.hint}>
              Una sola conexión al exchange para todos los gráficos y pestañas;
              cambiar de símbolo o intervalo descarta respuestas antiguas y libera
              solo las suscripciones sin consumidores. Sin persistencia de
              actualizaciones; los huecos se reparan por REST acotado y se
              informan aunque la reparación sea parcial. Abrir el gráfico no abre
              posiciones ni inicia simulación.
            </p>
          </section>

          <p className={s.foot}>
            Paginación: bloques de {EXPLORER_PAGE_BARS} velas, 1 petición por
            bloque, 1 página concurrente y presupuesto rolling de 30
            peticiones/minuto. Al retroceder hasta el borde cargado se pide el
            bloque anterior y se conserva el encuadre. Los huecos reales se
            informan como huecos; los tramos no consultados, como ausencia de
            cobertura; no se interpolan.
          </p>
        </section>
      )}
    </div>
  );
}
