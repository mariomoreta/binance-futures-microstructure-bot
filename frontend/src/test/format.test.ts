import { describe, expect, it } from "vitest";
import {
  emDash,
  formatAgeMs,
  formatCompact,
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
});
