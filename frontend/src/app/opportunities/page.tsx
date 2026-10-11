import s from "@/components/opportunities/ResearchWorkspace.module.css";
import {OpportunitiesDashboard} from "@/components/opportunities/OpportunitiesDashboard";
import {ResearchNavigation} from "@/components/opportunities/ResearchNavigation";
import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalOpportunityView} from "@/lib/canonical-market";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default function OpportunitiesPage(){const m=canonicalOpportunityView();return <div className={s.workspace}><ResearchNavigation active="/opportunities"/><SnapshotRefresh readAt={m.readAt} available={m.available}/><OpportunitiesDashboard items={m.items} available={m.available}/></div>;}
