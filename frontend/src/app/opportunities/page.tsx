import s from "@/components/opportunities/ResearchWorkspace.module.css";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
export default function OpportunitiesPage(){return <div className={s.workspace}><ResearchNavigation active="/opportunities"/><OpportunitiesDashboard/></div>}
