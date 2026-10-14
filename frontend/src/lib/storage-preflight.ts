import {existsSync, readFileSync, readdirSync, statSync, statfsSync} from "node:fs";
const ROOT = "C:/proyectos/binance-futures-microstructure-bot";
const DB_OP = ROOT + "/data/microprobe.db";
const DB_HIST = ROOT + "/data/historical/historical.db";
const DIR_LOGS = ROOT + "/logs";
const SNAPSHOT = ROOT + "/logs/storage-preflight.json";
export type StorageAlert = {level: "info" | "error"; text: string};
export type StorageEvidence = {
  available: boolean; read_at: string;
  snapshot: {present: boolean; measured_at: string | null; warnings: string[]} | null;
  measured: {
    operational_db: {bytes: number | null; wal_bytes: number | null; shm_bytes: number | null};
    historical_db: {bytes: number | null; wal_bytes: number | null; shm_bytes: number | null};
    logs: {bytes: number | null; files: number | null};
    disk_free_bytes: number | null;
  };
  alerts: StorageAlert[]; errors: string[];
  blocked: [];
  note: string;
};
function trio(base: string): {bytes: number | null; wal_bytes: number | null; shm_bytes: number | null} {
  const size = (p: string): number | null => {
    try { return statSync(p).isFile() ? statSync(p).size : null; } catch { return null; }
  };
  return {bytes: size(base), wal_bytes: size(base + "-wal"), shm_bytes: size(base + "-shm")};
}
function dirSize(dir: string): {bytes: number | null; files: number | null} {
  try {
    let bytes = 0, files = 0;
    const walk = (d: string) => {
      for (const e of readdirSync(d, {withFileTypes: true})) {
        const p = d + "/" + e.name;
        if (e.isDirectory()) walk(p);
        else if (e.isFile()) { try { bytes += statSync(p).size; files++; } catch { /* skip */ } }
      }
    };
    walk(dir);
    return {bytes, files};
  } catch { return {bytes: null, files: null}; }
}
export function readStorageEvidence(readAt = new Date().toISOString()): StorageEvidence {
  const alerts: StorageAlert[] = [];
  const errors: string[] = [];
  let snapshot: StorageEvidence["snapshot"] = null;
  if (existsSync(SNAPSHOT)) {
    try {
      const raw: unknown = JSON.parse(readFileSync(SNAPSHOT, "utf8"));
      const w = (raw as {warnings?: unknown}).warnings;
      snapshot = {
        present: true,
        measured_at: typeof (raw as {measured_at?: unknown}).measured_at === "string"
          ? (raw as {measured_at: string}).measured_at : null,
        warnings: Array.isArray(w) ? w.map(String) : [],
      };
      for (const text of snapshot.warnings) alerts.push({level: "info", text});
    } catch {
      errors.push("preflight snapshot illegible: logs/storage-preflight.json");
      snapshot = {present: false, measured_at: null, warnings: []};
    }
  } else {
    alerts.push({level: "info", text: "No preflight snapshot: run scripts/storage_preflight.py --out logs/storage-preflight.json"});
  }
  const op = trio(DB_OP);
  const hist = trio(DB_HIST);
  if (op.bytes === null) errors.push("operational DB absent/unreadable: run state UNKNOWN");
  if (hist.bytes === null) errors.push("historical DB absent/unreadable: research coverage UNKNOWN");
  const logs = dirSize(DIR_LOGS);
  let disk_free_bytes: number | null = null;
  try {
    const st = statfsSync(ROOT);
    disk_free_bytes = typeof st.bfree === "number" && typeof st.bsize === "number" ? st.bfree * st.bsize : null;
  } catch { disk_free_bytes = null; }
  if (disk_free_bytes === null) errors.push("disk free UNKNOWN: statfs unavailable");
  return {
    available: errors.length === 0, read_at: readAt,
    snapshot, measured: {operational_db: op, historical_db: hist, logs, disk_free_bytes},
    alerts, errors, blocked: [],
    note: "Measured only, never estimated. UNKNOWN is never zero. Storage alerts are informational; blocking stays with supervisor gates and launch readiness.",
  };
}
