import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getPreview, sendChat } from "./client.js";

function respond(status, body) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
}

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("returns the parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(200, { rows: [] })));
    await expect(getPreview("abc", 5)).resolves.toEqual({ rows: [] });
    expect(fetch.mock.calls[0][0]).toContain("/datasets/abc/preview?rows=5");
  });

  it("turns the backend error format into an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(404, { error: "Dataset not found." })));
    const error = await getPreview("abc").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("Dataset not found.");
    expect(error.status).toBe(404);
  });

  it("still understands FastAPI's own validation format", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(422, { detail: [{ msg: "Field required" }] })));
    await expect(getPreview("abc")).rejects.toMatchObject({ message: "Field required", status: 422 });
  });

  it("gives a friendly message when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(getPreview("abc")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("Cannot reach the server"),
    });
  });

  it("sends chat messages as JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(200, { answer: "ok" })));
    await sendChat("abc", "How many rows?", null);
    const [, options] = fetch.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ question: "How many rows?", session_id: null });
  });
});