import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, type Me } from "../api/me";
import { isSignedIn } from "../api/session";
import { signInForTest } from "../test/session";
import { apiError, networkError } from "../test/apiError";
import { AccountPage } from "./AccountPage";

// Never talk to a real server in tests.
vi.mock("../api/me", () => ({ getMe: vi.fn() }));
const mockGetMe = vi.mocked(getMe);

const ME: Me = {
  full_name: "Sam Doe",
  email: "sam@example.com",
  created_at: "2026-11-01T09:00:00Z",
  enrolled_at: "2026-11-02T10:00:00Z",
  previous_sign_in_at: "2026-11-13T18:30:00Z",
};

function renderHome() {
  render(
    <MemoryRouter initialEntries={["/account"]}>
      <Routes>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route path="/verify" element={<p>passage screen</p>} />
        <Route path="/enroll" element={<p>enroll screen</p>} />
        <Route path="/settings" element={<p>settings screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function detail(label: string) {
  return screen.getByText(label).nextElementSibling?.textContent;
}

beforeEach(() => {
  signInForTest();
  mockGetMe.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Home", () => {
  it("greets a voice-verified session and shows its Voice ID and last sign-in", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderHome();

    expect(screen.getByText("Loading your account…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "Hello, Sam." })).toBeInTheDocument();
    expect(screen.getByText("Protected")).toBeInTheDocument();
    expect(detail("My Voice ID")).toBe("Enrolled & encrypted");
    expect(detail("Last sign-in")).toMatch(/2026/);
  });

  it("offers a voice check once Voice ID is set up", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderHome();

    await userEvent.setup().click(await screen.findByRole("link", { name: /Try a voice check/ }));

    expect(await screen.findByText("passage screen")).toBeInTheDocument();
  });

  it("says when it's the first sign-in, and offers to set up a missing Voice ID", async () => {
    mockGetMe.mockResolvedValue({ ...ME, enrolled_at: null, previous_sign_in_at: null });
    renderHome();

    await screen.findByRole("heading", { level: 1, name: "Hello, Sam." });
    expect(detail("My Voice ID")).toBe("Not set up");
    expect(detail("Last sign-in")).toBe("This is your first");
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Set up Voice ID/ })).toHaveAttribute("href", "/enroll");
  });

  it("marks Home as the current tab and links to Settings", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderHome();
    await screen.findByRole("heading", { level: 1, name: "Hello, Sam." });

    const tabs = screen.getByRole("navigation", { name: "Main" });
    expect(within(tabs).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");

    await userEvent.setup().click(within(tabs).getByRole("link", { name: "Settings" }));
    expect(await screen.findByText("settings screen")).toBeInTheDocument();
  });

  it("sends a password-only session back to the voice check", async () => {
    mockGetMe.mockRejectedValue(apiError(403));
    renderHome();

    expect(await screen.findByText("passage screen")).toBeInTheDocument();
    expect(isSignedIn()).toBe(true);
  });

  it("sends an expired or bad session to sign in and forgets it", async () => {
    mockGetMe.mockRejectedValue(apiError(401));
    renderHome();

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(isSignedIn()).toBe(false);
  });

  it("explains other failures in our own words", async () => {
    mockGetMe.mockRejectedValue(networkError());
    renderHome();

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach VoiceGuard.");
  });
});
