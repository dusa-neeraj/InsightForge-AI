import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAsync } from "./useAsync.js";

describe("useAsync", () => {
  it("loads data", async () => {
    const fn = vi.fn(() => Promise.resolve("ok"));
    const { result } = renderHook(() => useAsync(fn, ["a"]));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe("ok");
    expect(result.current.error).toBeNull();
  });

  it("reports errors", async () => {
    const failure = new Error("nope");
    const { result } = renderHook(() => useAsync(() => Promise.reject(failure), ["a"]));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(failure);
    expect(result.current.data).toBeNull();
  });

  it("runs again when reload is called", async () => {
    const fn = vi.fn(() => Promise.resolve("ok"));
    const { result } = renderHook(() => useAsync(fn, ["a"]));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.reload());
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("ignores a slow response that arrives after the inputs changed", async () => {
    let finishFirst;
    const fn = vi.fn((id) =>
      id === "a" ? new Promise((resolve) => { finishFirst = resolve; }) : Promise.resolve("B")
    );
    const { result, rerender } = renderHook(({ id }) => useAsync(() => fn(id), [id]), {
      initialProps: { id: "a" },
    });
    rerender({ id: "b" });
    await waitFor(() => expect(result.current.data).toBe("B"));
    await act(async () => finishFirst("A"));
    expect(result.current.data).toBe("B");
  });
});