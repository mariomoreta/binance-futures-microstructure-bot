import { describe, expect, it } from "vitest";
import {
  emDash,
  formatAgeMs,
  formatCompact,
  formatCost,
  formatCostEstimate,
  formatFunding,
  formatPrice,
  formatSignedPct,
} from "@/lib/format";

describe("format", () => {
  it("renders null as em dash, never zero", () => {
    expect(formatCompact(null)).toBe("—");
    expect(formatPrice(undefined)).toBe("—");
    expect(formatSignedPct(null)).toBe("—");
    expect(formatAgeMs(null)).toBe("—");
    expect(emDash(null)).toBe("—");
    expect(formatCompact(0)).not.toBe("—");
  });

  it("signs positive percentages explicitly", () => {
    expect(formatSignedPct(2.4)).toBe("+2.40%");
    expect(formatSignedPct(-1.5)).toBe("-1.50%");
    expect(formatSignedPct(0)).toBe("0.00%");
  });

  it("compacts large notionals", () => {
    expect(formatCompact(1_900_000_000)).toMatch(/B$/);
  });

  it("formats ages in descending units", () => {
    expect(formatAgeMs(9000)).toBe("9s");
    expect(formatAgeMs(120_000)).toBe("2m");
    expect(formatAgeMs(3_700_000)).toBe("1h");
  });

  describe("cost semantics", () => {
    it("costo ejecutado conocido cero se muestra como cero, nunca guion", () => {
      // entry_fees_executed > 0 pero importe cero: cero conocido
      expect(formatCost(0, true, "sin fill de entrada")).toBe("0.00");
      expect(formatCost(0, true, "sin salida ejecutada")).toBe("0.00");
      // importe positivo conocido
      expect(formatCost(4.5, true)).toBe("+4.50");
    });

    it("valor ausente (no ejecutado) muestra UNKNOWN con motivo", () => {
      expect(formatCost(null, false, "sin fill de entrada")).toBe(
        "UNKNOWN (sin fill de entrada)",
      );
      expect(formatCost(0, false, "sin fill de entrada")).toBe(
        "UNKNOWN (sin fill de entrada)",
      );
      expect(formatCost(5, false, "sin salida ejecutada")).toBe(
        "UNKNOWN (sin salida ejecutada)",
      );
    });

    it("costo ejecutado con valor nulo muestra guion (inconsistencia defensiva)", () => {
      expect(formatCost(null, true)).toBe("—");
    });

    it("costo hipotético conocido se muestra como estimación no ejecutada", () => {
      expect(formatCostEstimate(3.2, true)).toBe("+3.20 (estimación, no ejecutada)");
      expect(formatCostEstimate(0, true)).toBe("0.00 (estimación, no ejecutada)");
    });

    it("costo hipotético sin estimación disponible muestra UNKNOWN", () => {
      expect(formatCostEstimate(null, false)).toBe(
        "UNKNOWN (sin estimación disponible)",
      );
      expect(formatCostEstimate(null, true)).toBe(
        "UNKNOWN (sin estimación disponible)",
      );
    });

    it("funding ausente muestra UNKNOWN con motivo; cero conocido como cero", () => {
      expect(formatFunding(null)).toBe(
        "UNKNOWN (calendario de funding no disponible)",
      );
      expect(formatFunding(0)).toBe("0.00");
      expect(formatFunding(1.25)).toBe("+1.25");
    });
  });
});
