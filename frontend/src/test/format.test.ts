import { describe, expect, it } from "vitest";
import { dec, num, pct, seasonSpan } from "../components/format";

/**
 * The null-vs-zero distinction is the whole point of these helpers. "No data"
 * and "zero" are different facts, and rendering the first as 0 would silently
 * invent a result.
 */
describe("formatters keep null distinct from zero", () => {
  it("renders null as an em dash, not 0", () => {
    expect(num(null)).toBe("—");
    expect(pct(null)).toBe("—");
    expect(dec(null)).toBe("—");
  });

  it("renders a genuine zero as zero", () => {
    expect(num(0)).toBe("0");
    expect(pct(0)).toBe("0.0%");
    expect(dec(0)).toBe("0.00");
  });

  it("treats undefined like null", () => {
    expect(num(undefined)).toBe("—");
    expect(pct(undefined)).toBe("—");
  });
});

describe("pct", () => {
  it("converts a rate to a percentage", () => {
    expect(pct(0.5)).toBe("50.0%");
    expect(pct(0.0805)).toBe("8.1%");
  });

  it("honours the digit count", () => {
    expect(pct(0.12345, 2)).toBe("12.35%");
  });
});

describe("dec", () => {
  it("pads to fixed precision so columns align", () => {
    expect(dec(7)).toBe("7.00");
    expect(dec(8.756)).toBe("8.76");
  });
});


describe("seasonSpan", () => {
  it("collapses a single season", () => {
    expect(seasonSpan([2011])).toBe("2011");
  });

  it("spans min to max, ignoring gaps in between", () => {
    expect(seasonSpan([2007, 2008, 2013, 2014])).toBe("2007–2014");
  });

  it("returns a dash for no seasons", () => {
    expect(seasonSpan([])).toBe("—");
  });
});
