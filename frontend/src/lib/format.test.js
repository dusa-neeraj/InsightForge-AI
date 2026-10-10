import { describe, expect, it } from "vitest";
import { formatBytes, formatNumber, formatPercent, kpiValue } from "./format.js";

describe("number formatting", () => {
  it("groups digits the Indian way and limits decimals", () => {
    expect(formatNumber(1234567)).toBe("12,34,567");
    expect(formatNumber(12.3456)).toBe("12.35");
  });

  it("shows a dash for missing values", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });

  it("formats percentages and file sizes", () => {
    expect(formatPercent(12.34)).toBe("12.3%");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(500)).toBe("500 B");
  });
});

describe("kpiValue", () => {
  it("adds the currency symbol to money values only", () => {
    expect(kpiValue({ value: 1234, format: "money", display: "1,234" }, "₹")).toBe("₹1,234");
    expect(kpiValue({ value: 1234, format: "count", display: "1,234" }, "₹")).toBe("1,234");
  });

  it("falls back to the display text for text and percent cards", () => {
    expect(kpiValue({ value: "Laptop", format: "text", display: "Laptop" })).toBe("Laptop");
    expect(kpiValue({ value: -12.5, format: "percent", display: "-12.5%" })).toBe("-12.5%");
  });
});