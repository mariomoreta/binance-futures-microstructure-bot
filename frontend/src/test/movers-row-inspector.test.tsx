import {describe,it,expect} from "vitest";import {render,screen} from "@testing-library/react";
import {MoversRowInspector} from "@/components/movers/MoversRowInspector";
import {DEMO_PROFESSIONAL_MOVERS} from "@/lib/movers-fixtures";
describe("per-symbol recorded evidence inspector",()=>{it("identifies recorded sources and missing values honestly",()=>{render(<MoversRowInspector row={DEMO_PROFESSIONAL_MOVERS[1]!}/>);expect(screen.getByText(/PERSISTED RECORD/)).toBeInTheDocument();expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(1);expect(screen.getByText(/not time-aligned with deep samples/)).toBeInTheDocument();});});
