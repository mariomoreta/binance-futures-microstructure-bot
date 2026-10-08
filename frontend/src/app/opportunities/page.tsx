import Link from "next/link";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
export default function OpportunitiesPage(){return <><div style={{display:"flex",justifyContent:"flex-end",marginBottom:10}}><Link href="/opportunities/observations" style={{fontSize:12}}>Inspect saved Python observations →</Link></div><OpportunitiesDashboard/></>;}
