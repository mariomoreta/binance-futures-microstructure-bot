"use client";
import {useEffect, useState} from "react";
import {useSearchParams} from "next/navigation";
import PaperLabReplay, {ReplayUnavailable} from "./PaperLabReplay";

// Vista de Paper Lab con enlace opcional desde Backtest. Si llega la identidad
// de una operación (?bt=<experimento>&event_id=...&group=...&segment=...&scale=...),
// se materializa y carga ESA operación (no la fija). Si no llega, se usa el
// replay fijo versionado. Sin sustitutos silenciosos: si el enlace falla, se
// muestra el motivo y no se inventa un replay.
export default function PaperLabSource() {
  const params = useSearchParams();
  const experiment = params.get("bt");
  const eventId = params.get("event_id");
  const group = params.get("group");
  const segment = params.get("segment");
  const scale = params.get("scale");
  const linked = !!experiment && !!eventId && !!group && !!segment && scale != null;

  const [source, setSource] = useState<unknown>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!linked) return;
    let cancelled = false;
    const url = `/api/v1/backtest/replay?experiment=${encodeURIComponent(experiment!)}` +
      `&event_id=${encodeURIComponent(eventId!)}&group=${encodeURIComponent(group!)}` +
      `&segment=${encodeURIComponent(segment!)}&scale=${encodeURIComponent(scale!)}`;
    fetch(url, {cache: "no-store"})
      .then(async (r) => {
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          throw new Error(j.error ?? `HTTP_${r.status}`);
        }
        return r.json();
      })
      .then((j) => { if (!cancelled) setSource(j); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : "REPLAY_UNSUPPORTED"); });
    return () => { cancelled = true; };
  }, [linked, experiment, eventId, group, segment, scale]);

  if (!linked) return <PaperLabReplay/>;
  if (error) {
    return <ReplayUnavailable message={
      `No se pudo cargar la operación enlazada desde Backtest (${error}). ` +
      "La operación sigue disponible en la tabla de Backtest; no se fabrica un replay alternativo."} />;
  }
  if (source === undefined) return <ReplayUnavailable message="Cargando la operación enlazada desde Backtest…" />;
  return <PaperLabReplay source={source}/>;
}
