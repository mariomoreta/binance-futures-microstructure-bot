import {describe,it,expect} from "vitest";
import {render,screen,fireEvent,within} from "@testing-library/react";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
import {DEMO_OPPORTUNITIES,type Opportunity} from "@/lib/opportunities-domain";
import {persistedMarket,recordedToken} from "@/lib/persisted-market";
import {formatPrice} from "@/lib/format";
describe("migration interaction and precision",()=>{
 it("bounds the candidate page and keeps its evidence on the visible page",()=>{
  const items:Opportunity[]=Array.from({length:13},(_,i)=>({...DEMO_OPPORTUNITIES[0]!,id:"record-"+i,symbol:"T"+i+"USDT",priority:100-i}));
  render(<OpportunitiesDashboard items={items}/>);
  const table=screen.getByRole("region",{name:"Opportunity candidates table"});
  expect(within(table).getAllByRole("button",{name:/Inspect/})).toHaveLength(12);
  expect(screen.getByRole("region",{name:"Candidate evidence"})).toHaveTextContent("T0USDT");
  fireEvent.click(screen.getByRole("button",{name:"Next candidates"}));
  expect(within(table).getAllByRole("button",{name:/Inspect/})).toHaveLength(1);
  expect(screen.getByRole("region",{name:"Candidate evidence"})).toHaveTextContent("T12USDT");
  expect(screen.getByRole("button",{name:"Next candidates"})).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Search symbol"),{target:{value:"T0USDT"}});
  expect(within(table).getByRole("button",{name:/Inspect T0USDT/})).toBeInTheDocument();
  expect(screen.getByRole("region",{name:"Candidate evidence"})).toHaveTextContent("T0USDT");
  expect(screen.queryByText("DEMO FIXTURE")).not.toBeInTheDocument();
 });
 it("small token prices and velocities remain nonzero in presentation",()=>{
  expect(formatPrice(.000123)).toBe("0.000123");
  const now=1791720000000,t=now-10000;
  const m=persistedMarket({discovery:null,features:{return_features:[{symbol:"BTCUSDT",updated_ms:t,feature_json:JSON.stringify({symbol:"BTCUSDT",current_price:1,source_timestamp_ms:t,momentum:{as_of_ms:t,velocity:{"1m":1e-10}}})}]},counts:{setups:0,outcomes:0,samples:0},latestSampleMs:null},now);
  expect(recordedToken(m,"BTCUSDT",now).metrics[1]!.value).toBe("1.000e-10 /s");
 });
});

describe("source availability",()=>{
 it("does not turn a missing candidate source into a zero cohort",()=>{
  render(<OpportunitiesDashboard items={[]} available={false}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("source unavailable");
  expect(screen.getByRole("region",{name:"Research summary"})).toHaveTextContent("UNKNOWN");
  expect(screen.getByRole("region",{name:"Research summary"})).not.toHaveTextContent("NONE");
 });
});
