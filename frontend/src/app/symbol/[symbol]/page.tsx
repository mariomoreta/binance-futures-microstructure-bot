import { SectionHeader } from "@/components/shell/SectionHeader";
import { WarmingState } from "@/components/notices/states";
import { Placeholder } from "@/components/shell/AppShell";

export default async function SymbolPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const display = decodeURIComponent(symbol).toUpperCase();
  return (
    <div>
      <SectionHeader title={display} />
      <WarmingState what={`Live features for ${display}`} />
      <Placeholder
        title="Detail contract (future)"
        what="Chart, returns/momentum, flow, book, OI, VWAP/vol/structure, coverage, events, and identity arrive with the normalized detail contract in DASH-V2-03 — including history-only routes."
      />
    </div>
  );
}
