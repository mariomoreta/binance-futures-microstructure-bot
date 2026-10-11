import s from "@/components/opportunities/ResearchWorkspace.module.css";
import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
import {Observations} from "@/components/opportunities/Observations";
export default function ObservationsPage(){return <div className={s.workspace}><ResearchNavigation active="/opportunities/observations"/><header className={s.header}><h1>Persisted Research Observations</h1><p style={{color:"var(--text-3)",fontSize:12}}>Read-only Python records · not live trading signals</p></header><Observations/></div>}
