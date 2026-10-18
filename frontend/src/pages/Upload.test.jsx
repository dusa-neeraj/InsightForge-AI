import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Upload from "./Upload.jsx";

function setup() {
  const view = render(
    <MemoryRouter>
      <Upload />
    </MemoryRouter>
  );
  return view.container.querySelector('input[type="file"]');
}

function choose(input, file) {
  fireEvent.change(input, { target: { files: [file] } });
}

describe("Upload page validation", () => {
  it("rejects unsupported file types without offering to upload", () => {
    const input = setup();
    choose(input, new File(["hello"], "notes.txt", { type: "text/plain" }));
    expect(screen.getByText(/Only \.csv and \.xlsx/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze dataset" })).not.toBeInTheDocument();
  });

  it("rejects empty files", () => {
    const input = setup();
    choose(input, new File([], "empty.csv"));
    expect(screen.getByText("That file is empty.")).toBeInTheDocument();
  });

  it("explains oversized files with their size and a tip", () => {
    const input = setup();
    const huge = new File(["x"], "big.csv", { type: "text/csv" });
    Object.defineProperty(huge, "size", { value: 5 * 1024 ** 3 }); // 5 GB, over any limit
    choose(input, huge);
    expect(screen.getByText("This file can't be uploaded")).toBeInTheDocument();
    expect(screen.getByText(/limit is \d+ MB/)).toBeInTheDocument();
    expect(screen.getByText(/saving it as CSV/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze dataset" })).not.toBeInTheDocument();
  });

  it("accepts a CSV and offers to analyze it", () => {
    const input = setup();
    choose(input, new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" }));
    expect(screen.getByText("data.csv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze dataset" })).toBeInTheDocument();
  });
});