import { SectionHeader } from "@/components/shell/SectionHeader";
import { Placeholder } from "@/components/shell/AppShell";

export default function PaperLabPage() {
  return (
    <div>
      <SectionHeader title="Paper Lab (future)" />
      <Placeholder
        title="Blocked explanation"
        what="Paper portfolio, orders, fills, and risk contracts arrive with P1-15/16. Nothing is simulated here."
      />
    </div>
  );
}
