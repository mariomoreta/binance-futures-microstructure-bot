import {describe,it,expect} from "vitest";
import {render,screen} from "@testing-library/react";
import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
describe("Research workspace navigation",()=>{it("labels all research tabs as read-only records",()=>{render(<ResearchNavigation active="/opportunities"/>);expect(screen.getByText("Setup Explorer").closest("a")).toHaveAttribute("aria-current","page");expect(screen.getByText("Saved observations")).toBeInTheDocument();expect(screen.getByText("Prospective outcomes")).toBeInTheDocument();expect(screen.getAllByText("READ ONLY")).toHaveLength(3);});});
