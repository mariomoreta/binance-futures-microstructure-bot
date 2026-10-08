import type { ReactNode } from "react";

export function SectionHeader({
  title,
  aside,
}: {
  title: string;
  aside?: ReactNode;
}) {
  return (
    <header
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: 12,
        marginBottom: 12,
      }}
    >
      <h1 style={{ margin: 0 }}>{title}</h1>
      {aside}
    </header>
  );
}
