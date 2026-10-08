import { SectionHeader } from "@/components/shell/SectionHeader";
import { EmptyState } from "@/components/notices/states";
import { Placeholder } from "@/components/shell/AppShell";

export default function OpportunitiesPage() {
  return (
    <div>
      <SectionHeader title="Opportunities" />
      <EmptyState
        title="No candidates — classifier not built"
        hint="This shell stays empty until P1-12/P1-13A provide validated setups. No rankings, probabilities, or trade fields are shown."
      />
      <Placeholder
        title="Lifecycle contract (future)"
        what="Selection reasons, evidence, counterevidence, risks, and nullable research fields arrive with the typed contract."
      />
    </div>
  );
}
