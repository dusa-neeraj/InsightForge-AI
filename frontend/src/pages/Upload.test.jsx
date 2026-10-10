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
    expect(screen.getByRole("alert")).toHaveTextContent("Only .csv and .xlsx");
    expect(screen.queryByRole("button", { name: "Analyze dataset" })).not.toBeInTheDocument();
  });

  it("rejects empty files", () => {
    const input = setup();
    choose(input, new File([], "empty.csv"));
    expect(screen.getByRole("alert")).toHaveTextContent("empty");
  });

  it("accepts a CSV and offers to analyze it", () => {
    const input = setup();
    choose(input, new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" }));
    expect(screen.getByText("data.csv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze dataset" })).toBeInTheDocument();
  });
});