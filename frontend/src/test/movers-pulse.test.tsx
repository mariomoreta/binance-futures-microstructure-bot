import {describe,it,expect} from "vitest";
import {render,screen} from "@testing-library/react";
import {MoversMarketPulse} from "@/components/movers/MoversMarketPulse";
import {DEMO_PROFESSIONAL_MOVERS} from "@/lib/movers-fixtures";
describe("market breadth visual integrity",()=>{it("states retained-subset limits and labels missing observations",()=>{render(<MoversMarketPulse rows={DEMO_PROFESSIONAL_MOVERS}/>);expect(screen.getByText(/SELECTED TOPS ONLY/)).toBeInTheDocument();expect(screen.getByRole("img",{name:/Retained subset direction/})).toBeInTheDocument();expect(screen.getByText(/DISCOVERY IS NOT DEEP LIVE/)).toBeInTheDocument()});});
