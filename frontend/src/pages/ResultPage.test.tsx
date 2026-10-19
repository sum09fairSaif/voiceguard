import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { VerifyResult } from "../api/verify";
import { ResultPage } from "./ResultPage";

function result(overrides: Partial<VerifyResult>): VerifyResult {
  return {
    decision: "incomplete",
    reason: "The passage and the voice matched, but the liveness check isn't built yet.",
    content: { passed: true, score: 1, matched: 6, total: 6 },
    identity: "passed",
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
      </Routes>
    </MemoryRouter>,
  );
}

describe("Result page", () => {
  it.each([
    ["approved", "You’re in."],
    ["rejected", "That didn’t match."],
    ["incomplete", "Almost there."],
  ] as const)("shows a %s decision", (decision, title) => {
    renderResult({ result: result({ decision }) });

    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
  });

  it("shows the server's reason and each check", () => {
    renderResult({
      result: result({
        decision: "rejected",
        reason: "The voice didn't match this account.",
        content: { passed: true, score: 1, matched: 6, total: 6 },
        identity: "failed",
      }),
    });

    expect(screen.getByText("The voice didn't match this account.")).toBeInTheDocument();
    expect(screen.getByText("Matched (6/6 words)")).toBeInTheDocument();
    expect(screen.getByText("Didn’t match")).toBeInTheDocument();
    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
  });

  it("says when there's no voiceprint yet", () => {
    renderResult({ result: result({ identity: "not_enrolled" }) });

    expect(screen.getByText("No voiceprint yet")).toBeInTheDocument();
  });

  it("goes back for a new passage on Try again", async () => {
    renderResult({ result: result({}) });

    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("passage screen")).toBeInTheDocument();
  });

  it("goes back to the passage screen when there's no result to show", () => {
    renderResult();

    expect(screen.getByText("passage screen")).toBeInTheDocument();
  });
});
