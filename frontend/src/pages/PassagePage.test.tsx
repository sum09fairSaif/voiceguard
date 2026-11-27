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

  it("offers sign-out", async () => {
    mockRequest.mockResolvedValue(challenge("quilt tiger ocean"));
    renderPage();

    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
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

  it("says when voice checks are paused", async () => {
    mockRequest.mockRejectedValue(apiError(503, { paused: "voice_checks" }));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Voice checks are paused for now.");
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

  it("says when voice checks are paused and offers nothing to retry", async () => {
    mockRequest.mockRejectedValue(apiError(423, { detail: "server text" }, { "retry-after": "840" }));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Voice checks are paused after too many failed attempts. Please try again in 14 minutes.",
    );
    expect(screen.queryByText(/server text/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again|new phrase/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeDisabled();
    expect(screen.getByText("Voice checks are paused")).toBeInTheDocument();
    // #20: the way out is recording a new Voice ID.
    expect(screen.getByRole("link", { name: "Record a new Voice ID" })).toHaveAttribute("href", "/recover");
    expect(mockRequest).toHaveBeenCalledTimes(1);
  });

  it("offers a new phrase again once the pause is over", async () => {
    mockRequest
      .mockRejectedValueOnce(apiError(423, {}, { "retry-after": "60" }))
      .mockResolvedValueOnce(challenge("quilt tiger ocean"));
    renderPage();
    await screen.findByText(/Voice checks are paused after/);
    // Let React start the pause timer before moving the clock on; otherwise
    // the clock can pass before the timer exists, and it never fires.
    await act(async () => {});

    // The pause timer is set in an effect that runs just after the message
    // shows, and the clock also moves with real time (shouldAdvanceTime), so
    // it's due a few milliseconds after 60 s. Check either side with room to
    // spare rather than at exactly 60 s, which failed on slower runs.
    await act(async () => {
      vi.advanceTimersByTime(59_000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/Voice checks are paused after/);

    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Voice checks are available again.");
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(
      screen.getByRole("button", { name: /try again/i }),
    );
    expect(await screen.findByText("“Quilt tiger ocean”")).toBeInTheDocument();
  });

  it("stays paused when the server didn't say for how long", async () => {
    mockRequest.mockRejectedValue(apiError(423));
    renderPage();
    await screen.findByText(/Voice checks are paused after/);

    await act(async () => {
      vi.advanceTimersByTime(24 * 3600 * 1000);
    });

    expect(screen.queryByRole("button", { name: /try again|new phrase/i })).not.toBeInTheDocument();
  });
});
