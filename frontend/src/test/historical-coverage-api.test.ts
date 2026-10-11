// @vitest-environment node
import {it,expect,vi,beforeEach} from "vitest";
const mocks=vi.hoisted(()=>({snapshot:vi.fn()}));
vi.mock("@/lib/historical-coverage",async importOriginal=>({...await importOriginal<typeof import("@/lib/historical-coverage")>(),historicalCoverage:mocks.snapshot}));
import {GET} from "@/app/api/v1/historical-coverage/route";
beforeEach(()=>{mocks.snapshot.mockReset()});
it("rejects invalid or repeated filters before any storage access",async()=>{
 for(const query of ["?symbol=%27DROP","?definition=INVALID","?symbol=BTCUSDT&symbol=ETHUSDT","?definition=EXTENDED_GAINER&definition=EXTENDED_LOSER"]){
  const r=await GET(new Request("http://localhost/api/v1/historical-coverage"+query));expect(r.status).toBe(400);expect(r.headers.get("cache-control")).toBe("no-store")
 }
 expect(mocks.snapshot).not.toHaveBeenCalled();
});
it("fails unavailable storage explicitly without substitute counts",async()=>{mocks.snapshot.mockImplementation(()=>{throw Error("missing source")});const r=await GET(new Request("http://localhost/api/v1/historical-coverage"));expect(r.status).toBe(503);expect(await r.json()).toEqual({error:"HISTORICAL_COVERAGE_UNAVAILABLE",source:"HISTORICAL_SQLITE_READONLY",available:false})});
it("normalizes exact filters and retains no-store JSON response",async()=>{mocks.snapshot.mockReturnValue({available:true,source:"HISTORICAL_SQLITE_READONLY"});const r=await GET(new Request("http://localhost/api/v1/historical-coverage?symbol=btcusdt&definition=extended_gainer"));expect(r.status).toBe(200);expect(mocks.snapshot).toHaveBeenCalledWith({symbol:"BTCUSDT",definition:"EXTENDED_GAINER"});expect(r.headers.get("cache-control")).toBe("no-store")});
