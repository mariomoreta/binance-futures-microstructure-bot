import { SectionHeader } from "@/components/shell/SectionHeader";
import { Placeholder } from "@/components/shell/AppShell";

export default function SystemPage() {
  return (
    <div>
      <SectionHeader title="System" />
      <Placeholder
        title="Diagnostics contract (future)"
        what="Health, control, research capture, and API inventory arrive with the consolidated runtime contract in DASH-V2-04. No Start/Stop wiring in this slice."
      />
    </div>
  );
}
