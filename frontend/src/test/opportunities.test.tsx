import {describe,it,expect} from "vitest";
import {render,screen,fireEvent} from "@testing-library/react";
import {DEFAULT_FILTERS,DEMO_OPPORTUNITIES,filterOpportunities,sortOpportunities} from "@/lib/opportunities-domain";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
describe("DASH V2 Opportunities DEMO",()=>{
 it("retains missing scores last without filling zero",()=>{const rows=sortOpportunities(DEMO_OPPORTUNITIES);expect(rows.at(-1)?.priority).toBeNull();});
 it("filters family and lifecycle independently",()=>{const rows=filterOpportunities(DEMO_OPPORTUNITIES,{...DEFAULT_FILTERS,family:"REVERSAL_WATCH",lifecycle:"DETECTED"});expect(rows.map(x=>x.symbol)).toEqual(["ETHUSDT"]);});
 it("renders honest demo disclaimer and evidence inspector",()=>{render(<OpportunitiesDashboard/>);expect(screen.getByText("Research Opportunities")).toBeInTheDocument();expect(screen.getByText(/Backend integration pending verified contract/)).toBeInTheDocument();expect(screen.getByText("Evidence inspector")).toBeInTheDocument();});
 it("search narrows results and reset restores",()=>{render(<OpportunitiesDashboard/>);fireEvent.change(screen.getByLabelText("Search symbol"),{target:{value:"OGN"}});expect(screen.getByText("1 matching · priority score is NOT probability")).toBeInTheDocument();fireEvent.click(screen.getByText("Reset"));expect(screen.getByText("5 matching · priority score is NOT probability")).toBeInTheDocument();});
 it("shows selected candidate lifecycle, state, priority and stale provenance",()=>{render(<OpportunitiesDashboard/>);const summary=screen.getByRole("region",{name:"Selected candidate summary"});expect(summary).toHaveTextContent("WATCHING");expect(summary).toHaveTextContent("EXPANSION · UP");expect(summary).toHaveTextContent("6.4");expect(summary).toHaveTextContent("STALE");fireEvent.click(screen.getByRole("button",{name:/Inspect ETHUSDT/}));expect(summary).toHaveTextContent("DETECTED");expect(summary).toHaveTextContent("REVERSAL · DOWN");expect(summary).toHaveTextContent("5.1");});
 it("never displays filtered-out candidate evidence",()=>{render(<OpportunitiesDashboard/>);fireEvent.change(screen.getByLabelText("Search symbol"),{target:{value:"NO_SUCH_SYMBOL"}});expect(screen.getByText(/No candidate matches the current filters/)).toBeInTheDocument();expect(screen.queryByRole("region",{name:"Selected candidate summary"})).not.toBeInTheDocument();fireEvent.click(screen.getByText("Clear filters"));expect(screen.getByRole("region",{name:"Selected candidate summary"})).toHaveTextContent("WATCHING");});
});

describe("DASH V2 Opportunities provenance and lifecycle presentation", () => {
  it("labels stale demo data without presenting it as live", () => {
    render(<OpportunitiesDashboard />);
    const provenance = screen.getByLabelText("Dataset provenance");
    expect(provenance).toHaveTextContent("DEMO FIXTURE");
    expect(provenance).toHaveTextContent("5/5 STALE");
    expect(provenance).toHaveTextContent("0 VERIFIED OUTCOMES");
    expect(provenance).toHaveTextContent("API NOT CONNECTED");
  });
  it("marks selected lifecycle and direction for visual status treatment", () => {
    render(<OpportunitiesDashboard />);
    const inspector = screen.getByRole("region", { name: "Selected candidate summary" });
    expect(inspector.querySelector('[data-lifecycle="WATCHING"]')).not.toBeNull();
    expect(inspector.querySelector('[data-direction="UP"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Inspect ETHUSDT/ }));
    expect(inspector.querySelector('[data-lifecycle="DETECTED"]')).not.toBeNull();
    expect(inspector.querySelector('[data-direction="DOWN"]')).not.toBeNull();
  });
});
