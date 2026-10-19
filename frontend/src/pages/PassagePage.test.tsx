import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { requestChallenge, type Challenge } from "../api/challenge";
import { apiError } from "../test/apiError";
import { displayPassage } from "../utils/passage";
import { PassagePage } from "./PassagePage";

// Never talk to a real server in tests.
vi.mock("../api/challenge", () => ({ requestChallenge: vi.fn() }));
const mockRequest = vi.mocked(requestChallenge);

const NOW = Date.parse("2026-10-19T03:00:00Z");

function challenge(passage: string, secondsFromNow = 120): Challenge {
  return {
    attempt_id: passage,
    passage,
    expires_at: new Date(NOW + secondsFromNow * 1000).toISOString(),
  };
}

function renderPage() {
  render(
    <MemoryRouter>
      <PassagePage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  mockRequest.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("displayPassage", () => {
  it("capitalises only the first letter", () => {
    expect(displayPassage("quilt tiger ocean")).toBe("Quilt tiger ocean");
  });
});

describe("Passage screen", () => {
  it("shows the passage with its countdown", async () => {
    mockRequest.mockResolvedValue(challenge("quilt tiger ocean pebble winter planet"));
    renderPage();

    expect(screen.getByText("Getting your phrase…")).toBeInTheDocument();
    expect(await screen.findByText("“Quilt tiger ocean pebble winter planet”")).toBeInTheDocument();
    expect(screen.getByText("Expires in 2:00")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  });

  it("swaps in a new passage on request", async () => {
    mockRequest
      .mockResolvedValueOnce(challenge("quilt tiger ocean"))
      .mockResolvedValueOnce(challenge("anchor bridge candle"));
    renderPage();
    await screen.findByText("“Quilt tiger ocean”");

    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(
      screen.getByRole("button", { name: /new phrase/i }),
    );

    expect(await screen.findByText("“Anchor bridge candle”")).toBeInTheDocument();
    expect(mockRequest).toHaveBeenCalledTimes(2);
  });

  it("hides New phrase while a request is in flight", async () => {
    mockRequest.mockResolvedValueOnce(challenge("quilt tiger ocean")).mockReturnValueOnce(new Promise(() => {}));
    renderPage();
    await screen.findByText("“Quilt tiger ocean”");

    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(
      screen.getByRole("button", { name: /new phrase/i }),
    );

    expect(screen.getByText("Getting a new phrase…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new phrase/i })).not.toBeInTheDocument();
  });

  it("marks the passage expired and offers a new one", async () => {
    mockRequest.mockResolvedValue(challenge("quilt tiger ocean", 2));
    renderPage();
    await screen.findByText("“Quilt tiger ocean”");

    // Let React finish setting up the countdown timer, then go a little past
    // the expiry. Advancing before the timer exists made this test flaky.
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(screen.getByText("This phrase has expired.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /get a new phrase/i })).toBeInTheDocument();
  });

  it("explains a failure and can try again", async () => {
    mockRequest.mockRejectedValueOnce(apiError(503)).mockResolvedValueOnce(challenge("quilt tiger ocean"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "VoiceGuard is temporarily unavailable. Please try again shortly.",
    );

    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(
      screen.getByRole("button", { name: /try again/i }),
    );

    expect(await screen.findByText("“Quilt tiger ocean”")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
