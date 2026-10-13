import { describe, expect, it } from "vitest";
import { validateImageFile } from "./files";
import { count, DASH, fileSize, humanize, ms, num, pct } from "./format";
import { can } from "./present";

describe("number formatting", () => {
  it("shows a dash - never a made-up zero - when a value is missing", () => {
    expect(pct(null)).toBe(DASH);
    expect(pct(undefined)).toBe(DASH);
    expect(num(Number.NaN)).toBe(DASH);
    expect(ms(null)).toBe(DASH);
    expect(count(null)).toBe(DASH);
  });
  it("keeps real zeros as zeros", () => {
    expect(pct(0)).toBe("0.0%");
    expect(num(0)).toBe("0.000");
    expect(ms(0)).toBe("0 ms");
  });
  it("formats rates, scores and times", () => {
    expect(pct(0.1234, 2)).toBe("12.34%");
    expect(num(0.81266)).toBe("0.813");
    expect(ms(1530)).toBe("1.53 s");
    expect(ms(281.4)).toBe("281 ms");
    expect(fileSize(2_621_440)).toBe("2.5 MB");
    expect(humanize("ambiguous_margin")).toBe("Ambiguous margin");
  });
});

describe("client-side image validation", () => {
  const limits = { maxBytes: 1000, extensions: [".jpg", ".png"] };
  const file = (name: string, size: number) => new File([new Uint8Array(size)], name);
  it("accepts a supported image within the size limit", () => {
    expect(validateImageFile(file("a.PNG", 500), limits)).toBeNull();
  });
  it("rejects unsupported types, empty files and oversized files with a plain message", () => {
    expect(validateImageFile(file("report.pdf", 10), limits)).toMatch(/not a supported image type/);
    expect(validateImageFile(file("noext", 10), limits)).toMatch(/not a supported image type/);
    expect(validateImageFile(file("a.jpg", 0), limits)).toMatch(/empty/);
    expect(validateImageFile(file("a.jpg", 5000), limits)).toMatch(/limit/);
  });
});

describe("role checks", () => {
  it("orders viewer < operator < admin", () => {
    expect(can("viewer", "operator")).toBe(false);
    expect(can("operator", "operator")).toBe(true);
    expect(can("admin", "operator")).toBe(true);
    expect(can("operator", "admin")).toBe(false);
    expect(can(undefined, "viewer")).toBe(false);
  });
});
