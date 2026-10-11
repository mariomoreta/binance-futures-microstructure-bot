import s from "@/components/opportunities/ResearchWorkspace.module.css";
import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
import {ProspectiveView} from "@/components/opportunities/ProspectiveView";
export default function Page(){return <div className={s.workspace}><ResearchNavigation active="/opportunities/prospective"/><header className={s.header}><h1>Prospective Research</h1><p style={{fontSize:12,color:"var(--text-3)"}}>Horizon observations from Python · research only</p></header><ProspectiveView/></div>}
