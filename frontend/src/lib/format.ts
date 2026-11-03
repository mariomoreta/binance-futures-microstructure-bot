// Centralized numeric formatting. Raw values stay numeric for sorting;
// only render strings here. Null renders as an em dash, never zero.

export function emDash(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : String(value);
}

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (value >= 0 ? "+" : "") + value.toFixed(2);
}

export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (value > 0 ? "+" : "") + value.toFixed(digits) + "%";
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatSignedPct(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(value)<1?8:2,
  }).format(value);
}

export function formatAgeMs(ageMs: number | null | undefined): string {
  if (ageMs === null || ageMs === undefined || Number.isNaN(ageMs)) return "—";
  const s = Math.max(0, Math.floor(ageMs / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

// Coste ejecutado conocido: cero conocido se muestra como "0.00" (nunca "—",
// nunca "+0.00"). Valor ausente (no ejecutado) → UNKNOWN con motivo.
export function formatCost(
  value: number | null,
  executed: boolean,
  missingReason: string = "no ejecutado",
): string {
  if (!executed) return `UNKNOWN (${missingReason})`;
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value === 0) return "0.00";
  return formatMoney(value);
}

// Coste hipotético conocido (salida no ejecutada): se muestra la estimación,
// claramente marcada como no ejecutada. Si no hay estimación, UNKNOWN.
export function formatCostEstimate(
  value: number | null,
  available: boolean,
): string {
  if (!available || value === null || value === undefined || Number.isNaN(value)) {
    return "UNKNOWN (sin estimación disponible)";
  }
  if (value === 0) return "0.00 (estimación, no ejecutada)";
  return `${formatMoney(value)} (estimación, no ejecutada)`;
}

// Funding devengado: null significa calendario no disponible (UNKNOWN).
// Cero conocido (calendario disponible, importe cero) se muestra como "0.00".
export function formatFunding(funding: number | null): string {
  if (funding === null || funding === undefined || Number.isNaN(funding)) {
    return "UNKNOWN (calendario de funding no disponible)";
  }
  if (funding === 0) return "0.00";
  return formatMoney(funding);
}
