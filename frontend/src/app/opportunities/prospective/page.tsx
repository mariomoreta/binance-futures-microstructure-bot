import Link from "next/link";
import {ProspectiveView} from "@/components/opportunities/ProspectiveView";
export default function Page(){return <main style={{display:"grid",gap:16}}><header><Link href="/opportunities">← Opportunities</Link><h1>Prospective Research</h1><p style={{fontSize:12,color:"var(--text-3)"}}>Horizon observations from Python · research only</p></header><ProspectiveView/></main>}
