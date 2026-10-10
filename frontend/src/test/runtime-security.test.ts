import {describe,expect,it} from "vitest";
import {requestAllowed} from "@/lib/runtime-control";
describe("DASH-V2-42 runtime mutation boundary",()=>{
 it("rejects posts without origin or confirmation header",()=>{const r=new Request("http://127.0.0.1:3020/api/v1/runtime/start",{method:"POST"});expect(requestAllowed(r)).toBe(false)});
 it("rejects cross-origin callers and cross-site navigation",()=>{
  const r=new Request("http://127.0.0.1:3020/api/v1/runtime/start",{method:"POST",headers:{origin:"http://evil.example",host:"127.0.0.1:3020","x-v2-action":"observe-only"}});expect(requestAllowed(r)).toBe(false);
  const s=new Request("http://127.0.0.1:3020/api/v1/runtime/start",{method:"POST",headers:{origin:"http://127.0.0.1:3020",host:"127.0.0.1:3020","x-v2-action":"observe-only","sec-fetch-site":"cross-site"}});expect(requestAllowed(s)).toBe(false)
 });
 it("accepts only locally originated, explicit observe-only request",()=>{
  const r=new Request("http://127.0.0.1:3020/api/v1/runtime/start",{method:"POST",headers:{origin:"http://127.0.0.1:3020",host:"127.0.0.1:3020","x-v2-action":"observe-only","sec-fetch-site":"same-origin"}});expect(requestAllowed(r)).toBe(true)
 })
});
