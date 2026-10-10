import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
import {Observations} from "@/components/opportunities/Observations";
export default function ObservationsPage(){return <div style={{display:"grid",gap:16}}><ResearchNavigation active="/opportunities/observations"/><header><h1>Persisted Research Observations</h1><p style={{color:"var(--text-3)",fontSize:12}}>Read-only Python records · not live trading signals</p></header><Observations/></div>}
