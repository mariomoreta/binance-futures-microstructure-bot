import Link from "next/link";
import { Observations } from "@/components/opportunities/Observations";
export default function ObservationsPage(){return <main style={{display:"grid",gap:18}}><header><Link href="/opportunities">← Research Opportunities</Link><h1 style={{margin:"12px 0 4px"}}>Persisted Research Observations</h1><p style={{color:"var(--text-3)",fontSize:12}}>Read-only Python records · not live trading signals</p></header><Observations/></main>}
