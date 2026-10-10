import {fireEvent,render,screen} from "@testing-library/react";
import {describe,it,expect,vi} from "vitest";
import {TopNav} from "@/components/shell/TopNav";
import {FutureWorkspace} from "@/components/future/FutureWorkspace";
const route=vi.hoisted(()=>({value:"/opportunities/prospective"}));
vi.mock("next/navigation",()=>({usePathname:()=>route.value}));
describe("Terminal navigation",()=>{
 it("marks the parent route and closes the mobile menu by Escape",()=>{
  render(<TopNav/>);
  expect(screen.getByRole("link",{name:"Opportunities"})).toHaveAttribute("aria-current","page");
  const menu=screen.getByRole("button",{name:"Open navigation"});
  fireEvent.click(menu);expect(menu).toHaveAttribute("aria-expanded","true");
  fireEvent.keyDown(document,{key:"Escape"});
  expect(menu).toHaveAttribute("aria-expanded","false");expect(menu).toHaveFocus();
 });
 it("closes navigation after selecting a destination",()=>{
  render(<TopNav/>);const menu=screen.getByRole("button",{name:"Open navigation"});
  fireEvent.click(menu);fireEvent.click(screen.getByRole("link",{name:"System"}));
  expect(menu).toHaveAttribute("aria-expanded","false");
 });
});
describe("Future engines remain unavailable",()=>{
 it.each(["backtest","paper"] as const)("does not enable %s actions or fabricate result series",kind=>{
  render(<FutureWorkspace kind={kind}/>);
  for(const button of screen.getAllByRole("button"))expect(button).toBeDisabled();
  expect(screen.getByText("No verified series")).toBeInTheDocument();
  expect(screen.getAllByText("NOT VERIFIED")).toHaveLength(kind==="paper"?2:4);
 });
});
