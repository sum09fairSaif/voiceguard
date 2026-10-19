import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { getToken, saveToken } from "../api/session";
import type { VerifyResult } from "../api/verify";
import { ResultPage } from "./ResultPage";

function result(overrides: Partial<VerifyResult> = {}): VerifyResult {
  return {
    decision: "incomplete",
    reason: "server text that must not be shown",
    content: { passed: true, score: 1, matched: 6, total: 6 },
    identity: "not_enrolled",
    liveness: "not_checked",
    ...overrides,
  };
}

function renderResult(state?: { result: VerifyResult }) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/result", state }]}>
      <Routes>
        <Route path="/result" element={<ResultPage />} />
        <Route path="/verify" element={<p>passage screen</p>} />
        <Route path="/signup" element={<p>signup screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function checkRow(label: string) {
  const row = within(screen.getByRole("list", { name: "Checks" }))
    .getAllByRole("listitem")
    .find((item) => item.textContent?.startsWith(label));
  if (!row) throw new Error(`no ${label} row`);
  return row;
}

describe("Result page", () => {
  it("confirms access for an approved check", () => {
    renderResult({ result: result({ decision: "approved", identity: "passed", liveness: "passed" }) });

    expect(screen.getByRole("heading", { name: "You’re in. Securely." })).toBeInTheDocument();
    expect(screen.getByText("Identity confirmed")).toBeInTheDocument();
    expect(checkRow("Live speaker")).toHaveTextContent("Confirmed");
  });

  it("explains a failed check and which part failed", () => {
    renderResult({
      result: result({ decision: "rejected", content: { passed: false, score: 0.33, matched: 2, total: 6 } }),
    });

    expect(screen.getByRole("heading", { name: "That didn’t match." })).toBeInTheDocument();
    expect(screen.getByText(/words didn’t match the phrase/)).toBeInTheDocument();
    expect(checkRow("Words")).toHaveTextContent("2/6 words");
  });

  it("shows each check for a partly verified result", () => {
    renderResult({ result: result() });

    expect(screen.getByRole("heading", { name: "Almost there." })).toBeInTheDocument();
    expect(checkRow("Words")).toHaveTextContent("6/6 words");
    expect(checkRow("Voice")).toHaveTextContent("Not set up yet");
    expect(checkRow("Live speaker")).toHaveTextContent("Not checked yet");
  });

  it("never shows the server's own text", () => {
    renderResult({ result: result({ decision: "rejected" }) });

    expect(screen.queryByText(/server text/)).not.toBeInTheDocument();
  });

  it("goes back for a new passage on Try again", async () => {
    saveToken("token");
    renderResult({ result: result() });

    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("passage screen")).toBeInTheDocument();
    expect(getToken()).toBe("token");
  });

  it("finishes the session on Done", async () => {
    saveToken("token");
    renderResult({ result: result({ decision: "approved", identity: "passed", liveness: "passed" }) });

    await userEvent.setup().click(screen.getByRole("button", { name: /done/i }));

    expect(screen.getByText("signup screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("goes back to the passage screen when there's no result to show", () => {
    renderResult();

    expect(screen.getByText("passage screen")).toBeInTheDocument();
  });
});
