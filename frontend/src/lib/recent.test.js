import { beforeEach, describe, expect, it } from "vitest";
import { addRecent, getRecent, recentName, removeRecent } from "./recent.js";

beforeEach(() => localStorage.clear());

const entry = (id) => ({ id, filename: `${id}.csv`, rows: 10, at: 1 });

describe("recent datasets", () => {
  it("keeps the newest first and removes duplicates", () => {
    addRecent(entry("a"));
    addRecent(entry("b"));
    addRecent(entry("a"));
    expect(getRecent().map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("keeps at most five", () => {
    ["a", "b", "c", "d", "e", "f"].forEach((id) => addRecent(entry(id)));
    expect(getRecent()).toHaveLength(5);
    expect(getRecent()[0].id).toBe("f");
  });

  it("removes an entry and looks up names", () => {
    addRecent(entry("a"));
    expect(recentName("a")).toBe("a.csv");
    removeRecent("a");
    expect(recentName("a")).toBeUndefined();
  });

  it("survives corrupted storage", () => {
    localStorage.setItem("ada.recentDatasets", "{not json");
    expect(getRecent()).toEqual([]);
  });
});