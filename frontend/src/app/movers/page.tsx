import {MoversDashboard} from "@/components/movers/MoversDashboard";
import {SnapshotRefresh} from "@/components/notices/SnapshotRefresh";
import {canonicalMarket} from "@/lib/canonical-market";
export const dynamic="force-dynamic";export const runtime="nodejs";
export default function MoversPage(){const m=canonicalMarket();return <><SnapshotRefresh readAt={m.readAt} available={m.available}/><MoversDashboard rows={m.rows} asOf={m.discoveryAsOf} available={m.available}/></>}
