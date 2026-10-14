export const WATCHER_FRESHNESS_MS = 90_000;
export type WatcherKind = "supervisor" | "sentinel";
export type WatcherEvidence = {
  state: string;
  lease_state: string | null;
  lease_last_check_at: string | null;
  last_check_at: string | null;
  watcher_pid: number | null;
  watcher_create_time: string | null;
  watched_pid: number | null;
  run_id: string | null;
  supervision_source: string | null;
  abort_triggered: boolean | null;
  abort_reason: string | null;
  abort_rule: string | null;
  abort_threshold: number | string | null;
  abort_observed: number | string | null;
  action_taken: string | null;
  action_reason: string | null;
};
const text = (v: unknown) => typeof v === "string" && v.trim() ? v : null;
const pid = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v > 0 ? v : null;
const measurement = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? v : text(v);
export function normalizeWatcher(value: unknown, kind: WatcherKind): WatcherEvidence {
  const x = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
  return {
    state: text(x.state) ?? kind.toUpperCase() + "_UNKNOWN",
    lease_state: text(x.lease_state), lease_last_check_at: text(x.lease_last_check_at),
    last_check_at: text(x.last_check_at), watcher_pid: pid(x.watcher_pid),
    watcher_create_time: text(x.watcher_create_time), watched_pid: pid(x.watched_pid),
    run_id: text(x.run_id), supervision_source: text(x.supervision_source),
    abort_triggered: typeof x.abort_triggered === "boolean" ? x.abort_triggered : null,
    abort_reason: text(x.abort_reason), abort_rule: text(x.abort_rule),
    abort_threshold: measurement(x.abort_threshold), abort_observed: measurement(x.abort_observed),
    action_taken: text(x.action_taken), action_reason: text(x.action_reason),
  };
}
export function utcTimestamp(value: string | null | undefined): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(value)) return null;
  const n = Date.parse(value);
  return Number.isFinite(n) && new Date(n).toISOString().slice(0,19) === value.slice(0,19) ? n : null;
}
export function watcherDisplayState(kind: WatcherKind, e: WatcherEvidence | undefined,
  runPid: number | null | undefined, observedAt: string | null | undefined, now: number): string {
  const prefix = kind.toUpperCase();
  if (!e || (e.state === prefix + "_UNKNOWN" && !e.lease_state && !e.watcher_pid))
    return prefix + "_UNKNOWN";
  const heartbeat = utcTimestamp(e.lease_last_check_at);
  const observation = utcTimestamp(observedAt);
  const fresh = (n: number | null) => n !== null && now - n >= 0 && now - n <= WATCHER_FRESHNESS_MS;
  // Identity/liveness is the canonical controller's point-in-time observation.
  // The browser only ages/rejects evidence; it never confirms continuing protection.
  return e.state === prefix + "_ACTIVE" && e.lease_state === "ACTIVE" &&
    e.watched_pid !== null && e.watched_pid === runPid && e.watcher_pid !== null &&
    utcTimestamp(e.watcher_create_time) !== null && fresh(heartbeat) && fresh(observation)
    ? prefix + "_ACTIVE" : prefix + "_STALE";
}
