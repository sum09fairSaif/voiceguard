import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getActivity, type ActivityEvent } from "../api/activity";
import { isSignedIn } from "../api/session";
import { apiError, networkError } from "../test/apiError";
import { signInForTest } from "../test/session";
import { ActivityPage } from "./ActivityPage";

// Never talk to a real server in tests.
vi.mock("../api/activity", () => ({ getActivity: vi.fn() }));
const mockGetActivity = vi.mocked(getActivity);

const NOW = new Date(2026, 10, 25, 14, 0);

function minutesAgo(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString();
}

function renderActivity() {
  render(
    <MemoryRouter initialEntries={["/activity"]}>
      <Routes>
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route path="/verify" element={<p>passage screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  signInForTest();
  mockGetActivity.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Activity", () => {
  it("lists the events newest first, grouped by day", async () => {
    const events: ActivityEvent[] = [
      { kind: "voice_check_approved", at: minutesAgo(0) },
      { kind: "login_succeeded", at: minutesAgo(3) },
      { kind: "enrolled", at: minutesAgo(24 * 60) },
    ];
    mockGetActivity.mockResolvedValue(events);
    renderActivity();

    const today = await screen.findByRole("region", { name: "Today" });
    const items = within(today).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Voice verification");
    expect(items[0]).toHaveTextContent("Just now");
    expect(items[1]).toHaveTextContent("Secure sign in");
    expect(within(screen.getByRole("region", { name: "Yesterday" })).getByText("Voice ID created")).toBeInTheDocument();
  });

  it("counts the events and says when everything looks good", async () => {
    mockGetActivity.mockResolvedValue([
      { kind: "login_succeeded", at: minutesAgo(5) },
      { kind: "voice_check_approved", at: minutesAgo(4) },
      { kind: "logout", at: minutesAgo(1) },
    ]);
    renderActivity();

    const summary = await screen.findByRole("region", { name: "The last 30 days" });
    expect(summary).toHaveTextContent("03");
    expect(summary).toHaveTextContent("Everything looks good");
  });

  it("points out wrong passwords and failed voice checks", async () => {
    mockGetActivity.mockResolvedValue([
      { kind: "login_failed", at: minutesAgo(2) },
      { kind: "voice_check_rejected", at: minutesAgo(1) },
      { kind: "login_succeeded", at: minutesAgo(1) },
    ]);
    renderActivity();

    const summary = await screen.findByRole("region", { name: "The last 30 days" });
    expect(summary).toHaveTextContent("2 worth a look");
    expect(summary).not.toHaveTextContent("Everything looks good");
    expect(screen.getByText("Wrong password")).toBeInTheDocument();
    expect(screen.getByText("Voice check failed")).toBeInTheDocument();
  });

  it("never says which voice check failed", async () => {
    mockGetActivity.mockResolvedValue([{ kind: "voice_check_rejected", at: minutesAgo(1) }]);
    renderActivity();

    const item = (await screen.findByText("Voice check failed")).closest("li");
    expect(item).not.toHaveTextContent(/liveness|identity|voice match|words/i);
  });

  it("says when there's nothing in the last 30 days", async () => {
    mockGetActivity.mockResolvedValue([]);
    renderActivity();

    expect(await screen.findByRole("region", { name: "The last 30 days" })).toHaveTextContent(
      "Nothing in the last 30 days",
    );
  });

  it("shows 50+ when the server sent as many as it sends", async () => {
    mockGetActivity.mockResolvedValue(
      Array.from({ length: 50 }, (_, i) => ({ kind: "login_succeeded" as const, at: minutesAgo(i) })),
    );
    renderActivity();

    expect(await screen.findByRole("region", { name: "The last 30 days" })).toHaveTextContent("50+");
  });

  it("offers a way out when something isn't recognised", async () => {
    mockGetActivity.mockResolvedValue([{ kind: "login_failed", at: minutesAgo(1) }]);
    renderActivity();

    expect(await screen.findByRole("link", { name: "Change your password" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("marks Activity as the current tab", async () => {
    mockGetActivity.mockResolvedValue([]);
    renderActivity();
    await screen.findByRole("region", { name: "The last 30 days" });

    const tabs = screen.getByRole("navigation", { name: "Main" });
    expect(within(tabs).getByRole("link", { name: "Activity" })).toHaveAttribute("aria-current", "page");
  });

  it("sends a password-only session back to the voice check", async () => {
    mockGetActivity.mockRejectedValue(apiError(403));
    renderActivity();

    expect(await screen.findByText("passage screen")).toBeInTheDocument();
  });

  it("sends an expired session to sign in and forgets it", async () => {
    mockGetActivity.mockRejectedValue(apiError(401));
    renderActivity();

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(isSignedIn()).toBe(false);
  });

  it("explains other failures in our own words", async () => {
    mockGetActivity.mockRejectedValue(networkError());
    renderActivity();

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach VoiceGuard.");
  });
});
