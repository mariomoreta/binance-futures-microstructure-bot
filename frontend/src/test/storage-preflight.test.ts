// @vitest-environment node
import {describe, expect, it} from "vitest";
import {readStorageEvidence} from "@/lib/storage-preflight";
import {GET} from "@/app/api/v1/storage/route";

describe("storage preflight evidence (measured, never zero-filled)", () => {
  it("measures real stores with informational alerts and no blockers", () => {
    const s = readStorageEvidence("2026-10-13T00:00:00Z");
    expect(s.read_at).toBe("2026-10-13T00:00:00Z");
    expect(s.blocked).toEqual([]);
    expect(s.note).toMatch(/never estimated/);
    expect(typeof s.measured.logs.files === "number" || s.measured.logs.files === null).toBe(true);
  });
  it("labels every error UNKNOWN and keeps blockers empty", () => {
    const s = readStorageEvidence();
    for (const e of s.errors) expect(e).toMatch(/UNKNOWN/);
    expect(s.blocked).toEqual([]);
    expect(s.alerts.every(a => a.level === "info" || a.level === "error")).toBe(true);
  });
  it("serves JSON with no-store through the BFF route", async () => {
    const r = await GET();
    expect(r.status).toBe(200);
    expect(r.headers.get("cache-control")).toBe("no-store");
    const body = await r.json();
    expect(body.blocked).toEqual([]);
    expect(typeof body.note).toBe("string");
  });
});
