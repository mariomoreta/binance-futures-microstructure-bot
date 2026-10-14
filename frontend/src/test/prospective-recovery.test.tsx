import {afterEach,describe,expect,it,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {ProspectiveView} from "@/components/opportunities/ProspectiveView";
describe("prospective offline recovery",()=>{
 afterEach(()=>vi.unstubAllGlobals());
 it("keeps research controls visible while offline and retries on explicit user request",async()=>{
  const fetchMock=vi.fn().mockRejectedValue(new Error("offline"));
  vi.stubGlobal("fetch",fetchMock);
  render(<ProspectiveView/>);
  expect(await screen.findByText(/BACKEND UNAVAILABLE/)).toBeInTheDocument();
  expect(screen.getByLabelText("Filter outcome symbol")).toBeInTheDocument();
  expect(screen.getByText("UNKNOWN records (backend offline)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Retry Python connection"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(2));
 });
});
