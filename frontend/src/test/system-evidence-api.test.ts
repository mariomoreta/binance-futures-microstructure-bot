import {it,expect,vi} from "vitest";
vi.mock("@/lib/system-evidence",()=>({canonicalSystemEvidence:vi.fn()}));
import {canonicalSystemEvidence} from "@/lib/system-evidence";
import {GET} from "@/app/api/v1/system-evidence/route";
it("unavailable source returns explicit 503 with no-store",async()=>{
 vi.mocked(canonicalSystemEvidence).mockReturnValue({schema_version:1,source:"CANONICAL_SQLITE_READONLY",available:false,read_at:"2026-01-01T00:00:00Z",error:"SYSTEM_EVIDENCE_UNAVAILABLE"});
 const r=GET();expect(r.status).toBe(503);expect(r.headers.get("cache-control")).toBe("no-store");expect((await r.json()).available).toBe(false);
});
