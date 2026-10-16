// @vitest-environment node
import {it, expect, vi, beforeEach} from "vitest";
const mocks = vi.hoisted(() => ({read: vi.fn()}));
vi.mock("@/lib/offline-eval", async importOriginal => ({...await importOriginal<typeof import("@/lib/offline-eval")>(), offlineEval: mocks.read}));
import {GET} from "@/app/api/v1/offline-eval/route";
beforeEach(() => {mocks.read.mockReset()});
it("serves the versioned artifact read-only with no-store", async () => {
  mocks.read.mockReturnValue({artifact_version: "OFFLINE-EVAL-V1", available: true});
  const r = await GET();
  expect(r.status).toBe(200);
  expect(r.headers.get("cache-control")).toBe("no-store");
  expect(await r.json()).toMatchObject({artifact_version: "OFFLINE-EVAL-V1"});
  expect(mocks.read).toHaveBeenCalledTimes(1);
});
it("reports unavailable explicitly without substitute data", async () => {
  mocks.read.mockImplementation(() => {throw Error("OFFLINE_EVAL_UNAVAILABLE")});
  const r = await GET();
  expect(r.status).toBe(503);
  expect(await r.json()).toEqual({error: "OFFLINE_EVAL_UNAVAILABLE", available: false});
});
