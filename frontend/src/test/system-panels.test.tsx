import {it,expect} from "vitest";
import {render,screen} from "@testing-library/react";
import {PersistencePanel,ResearchPanel,UniversePanel,ClassifierPanel} from "@/components/system/RecordedSystemPanels";
import type {SystemEvidenceData,SystemEvidenceResult} from "@/lib/system-evidence";
const data:SystemEvidenceData={schema_version:1,source:"CANONICAL_SQLITE_READONLY",available:true,read_at:"2026-01-01T00:00:00Z",
 persistence:{schema:9,allocated_bytes:0,telemetry_rows:0,price_rows:0,last_telemetry_ms:null,last_price_ms:null},
 universe:{updated_ms:1000,core:3,hot_dynamic:0,hot_subscribed:null,eligible:439,unverified_test_detail_rows:2},
 research:{setups:0,outcomes:0,complete_outcomes:0,latest_setup_ms:null,latest_outcome_ms:null,opportunity_events:0,state_transitions:0,universe_events:0},
 classifier:{records:1,span:{first_ms:1000,last_ms:2000},states:[{label:"NORMAL",count:1}],versions:["v0.1"],versions_truncated:false},
 opportunities:{records:1,span:{first_ms:3000,last_ms:4000},lifecycles:[{label:"ACTIVE_RESEARCH",count:1}],versions:["v0.2"],versions_truncated:false}
};
it("unknown subscription list is distinct from genuine zero HOT allocation",()=>{
 render(<UniversePanel data={data}/>);
 expect(screen.getByText("HOT dynamic (recorded)").nextSibling).toHaveTextContent("0");
 expect(screen.getByText("HOT subscribed list (recorded)").nextSibling).toHaveTextContent("UNKNOWN");
 expect(screen.getByText("Rows flagged for provenance review").nextSibling).toHaveTextContent("2");
 expect(screen.getByRole("status")).toHaveTextContent("2 records carry a test marker");
 expect(screen.getByText(/not proof of current websocket subscriptions/)).toBeInTheDocument();
});
it("lifecycle labels and versions remain explicitly historical with separate source spans",()=>{
 render(<ClassifierPanel data={data}/>);
 expect(screen.getByText("ACTIVE_RESEARCH")).toBeInTheDocument();
 expect(screen.getByText(/not a live position/)).toBeInTheDocument();
 expect(screen.getByText(/Candidate stored update span/)).toHaveTextContent("1970-01-01T00:00:03.000Z");
 expect(screen.queryByText("HEALTHY")).not.toBeInTheDocument();
});
it("reports the actual store schema in the eyebrow, never a hardcoded label",()=>{
 const r=render(<PersistencePanel data={data}/>);
 expect(screen.getByText("CANONICAL STORE / SCHEMA 9")).toBeInTheDocument();
 const v10:SystemEvidenceData={...data,persistence:{...data.persistence,schema:10}};
 r.rerender(<PersistencePanel data={v10}/>);
 expect(screen.getByText("CANONICAL STORE / SCHEMA 10")).toBeInTheDocument();
 expect(screen.queryByText("CANONICAL STORE / SCHEMA 9")).not.toBeInTheDocument();
});
it("missing source returns absence notices while real empty counts stay zero",()=>{
 const missing:SystemEvidenceResult={schema_version:1,source:"CANONICAL_SQLITE_READONLY",available:false,read_at:"x",error:"SYSTEM_EVIDENCE_UNAVAILABLE"};
 const r=render(<PersistencePanel data={missing}/>);
 expect(screen.getByRole("alert")).toHaveTextContent("Source unavailable");
 r.rerender(<ResearchPanel data={data}/>);
 expect(screen.getByText("Retained setups").nextSibling).toHaveTextContent("0");
 expect(screen.getByText(/Queue, drops and writer liveness remain UNKNOWN/)).toBeInTheDocument();
});
