"use client";
import {useEffect, useState} from "react";
import {useSearchParams} from "next/navigation";
import PaperLabReplay, {ReplayUnavailable} from "./PaperLabReplay";

// Vista de Paper Lab con enlace opcional desde Backtest. Si llega la identidad
// de una operacion (?bt=<experimento>&event_id=...&group=...&segment=...&scale=...
// [&run=<run_id>]), se materializa y carga ESA operacion (no la fija), vinculada
// a la ejecucion concreta. Sin sustitutos silenciosos: si el enlace falla, se
// muestra el motivo y no se inventa un replay.
//
// Cambio de operacion: mientras carga o si falla una identidad NUEVA, NO se
// sigue mostrando la operacion anterior: se muestra el estado de carga/fallo de
// la identidad solicitada.
export default function PaperLabSource() {
  const params = useSearchParams();
  const experiment = params.get("bt");
  const eventId = params.get("event_id");
  const group = params.get("group");
  const segment = params.get("segment");
  const scale = params.get("scale");
  const run = params.get("run");
  const linked = !!experiment && !!eventId && !!group && !!segment && scale != null;

  const [state, setState] = useState<{key: string; source: unknown} | null>(null);
  const [failed, setFailed] = useState<{key: string; message: string} | null>(null);

  // Clave de la identidad solicitada: si cambia, se descarta el estado previo.
  const requestKey = linked
    ? [experiment, run ?? "", eventId, group, segment, scale].join("|")
    : "fixed";

  useEffect(() => {
    if (!linked) return;
    let cancelled = false;
    const url = `/api/v1/backtest/replay?experiment=${encodeURIComponent(experiment!)}` +
      `&event_id=${encodeURIComponent(eventId!)}&group=${encodeURIComponent(group!)}` +
      `&segment=${encodeURIComponent(segment!)}&scale=${encodeURIComponent(scale!)}` +
      (run ? `&run=${encodeURIComponent(run)}` : "");
    fetch(url, {cache: "no-store"})
      .then(async (r) => {
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          throw new Error(j.error ?? `HTTP_${r.status}`);
        }
        return r.json();
      })
      .then((j) => { if (!cancelled) setState({key: requestKey, source: (j.artifact ?? j)}); })
      .catch((e: unknown) => {
        if (!cancelled) setFailed({key: requestKey,
          message: e instanceof Error ? e.message : "REPLAY_UNSUPPORTED"});
      });
    return () => { cancelled = true; };
  }, [linked, experiment, eventId, group, segment, scale, run, requestKey]);

  if (!linked) return <PaperLabReplay/>;
  // Fallo de la identidad SOLICITADA: tiene prioridad sobre cualquier estado
  // anterior (no se sigue mostrando la operacion previa).
  if (failed && failed.key === requestKey) {
    return <ReplayUnavailable message={
      `No se pudo cargar la operación enlazada desde Backtest (${failed.message}). ` +
      "La operación sigue disponible en la tabla de Backtest; no se fabrica un replay alternativo."} />;
  }
  // La identidad solicitada cambio: no mostrar la operacion anterior.
  if (state && state.key !== requestKey) {
    return <ReplayUnavailable message="Cargando la operación enlazada desde Backtest…" />;
  }
  if (!state || state.key !== requestKey) {
    return <ReplayUnavailable message="Cargando la operación enlazada desde Backtest…" />;
  }
  return <PaperLabReplay source={state.source}/>;
}
