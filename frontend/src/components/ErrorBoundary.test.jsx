import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary.jsx";

function Crash() {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("shows a friendly message when a child crashes", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Crash />
      </ErrorBoundary>
    );
    expect(screen.getByRole("alert")).toHaveTextContent("ran into a problem");
  });

  it("renders its children when nothing is wrong", () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>
    );
    expect(screen.getByText("All good")).toBeInTheDocument();
  });
});