import {describe,it,expect} from "vitest";
import {render,screen,fireEvent} from "@testing-library/react";
import {DEFAULT_FILTERS,DEMO_OPPORTUNITIES,filterOpportunities,sortOpportunities} from "@/lib/opportunities-domain";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
describe("DASH V2 Opportunities DEMO",()=>{
 it("retains missing scores last without filling zero",()=>{const rows=sortOpportunities(DEMO_OPPORTUNITIES);expect(rows.at(-1)?.priority).toBeNull();});
 it("filters family and lifecycle independently",()=>{const rows=filterOpportunities(DEMO_OPPORTUNITIES,{...DEFAULT_FILTERS,family:"REVERSAL_WATCH",lifecycle:"DETECTED"});expect(rows.map(x=>x.symbol)).toEqual(["ETHUSDT"]);});
 it("renders honest demo disclaimer and evidence inspector",()=>{render(<OpportunitiesDashboard/>);expect(screen.getByText("Research Opportunities")).toBeInTheDocument();expect(screen.getByText(/Backend integration pending verified contract/)).toBeInTheDocument();expect(screen.getByText("Evidence inspector")).toBeInTheDocument();});
 it("search narrows results and reset restores",()=>{render(<OpportunitiesDashboard/>);fireEvent.change(screen.getByLabelText("Search symbol"),{target:{value:"OGN"}});expect(screen.getByText("1 matching · priority score is NOT probability")).toBeInTheDocument();fireEvent.click(screen.getByText("Reset"));expect(screen.getByText("5 matching · priority score is NOT probability")).toBeInTheDocument();});
});
