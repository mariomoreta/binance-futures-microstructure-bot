import { SectionHeader } from "@/components/shell/SectionHeader";
import { Placeholder } from "@/components/shell/AppShell";

export default function BacktestPage() {
  return (
    <div>
      <SectionHeader title="Backtest (future)" />
      <Placeholder
        title="Blocked explanation"
        what="Run definitions and results arrive with the P1-14 backtest engine. Nothing is backtested here."
      />
    </div>
  );
}
