import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { logOut } from "../api/auth";
import { getMe, type Me } from "../api/me";
import { isSignedIn } from "../api/session";
import { apiError } from "../test/apiError";
import { signInForTest } from "../test/session";
import { SettingsPage } from "./SettingsPage";

// Never talk to a real server in tests.
vi.mock("../api/me", () => ({ getMe: vi.fn() }));
const mockGetMe = vi.mocked(getMe);
vi.mock("../api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/auth")>()),
  logOut: vi.fn().mockResolvedValue(undefined),
}));

const ME: Me = {
  full_name: "Sam Doe",
  email: "sam@example.com",
  created_at: "2026-11-01T09:00:00Z",
  enrolled_at: "2026-11-02T10:00:00Z",
  previous_sign_in_at: "2026-11-13T18:30:00Z",
};

function renderSettings() {
  render(
    <MemoryRouter initialEntries={["/settings"]}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/account" element={<p>home screen</p>} />
        <Route path="/forgot-password" element={<p>reset screen</p>} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route path="/verify" element={<p>passage screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  signInForTest();
  mockGetMe.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Settings", () => {
  it("shows the account and when Voice ID was set up", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderSettings();

    const account = await screen.findByRole("region", { name: "Your account" });
    expect(within(account).getByText("Sam Doe")).toBeInTheDocument();
    expect(within(account).getByText("sam@example.com")).toBeInTheDocument();
    expect(screen.getByText("Voice ID").nextElementSibling).toHaveTextContent(/^Set up /);
  });

  it("says when Voice ID isn't set up", async () => {
    mockGetMe.mockResolvedValue({ ...ME, enrolled_at: null });
    renderSettings();

    expect(await screen.findByText("Not set up")).toBeInTheDocument();
  });

  it("changes the password through the emailed reset link", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderSettings();

    await userEvent.setup().click(await screen.findByRole("link", { name: "Change password" }));

    expect(await screen.findByText("reset screen")).toBeInTheDocument();
  });

  it("shows only controls that work", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderSettings();
    await screen.findByText("Sam Doe");

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByText(/Voice sign in|Security notifications|Manage Voice ID/)).not.toBeInTheDocument();
  });

  it("marks Settings as the current tab and links back Home", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderSettings();
    await screen.findByText("Sam Doe");

    const tabs = screen.getByRole("navigation", { name: "Main" });
    expect(within(tabs).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");

    await userEvent.setup().click(within(tabs).getByRole("link", { name: "Home" }));
    expect(await screen.findByText("home screen")).toBeInTheDocument();
  });

  it("sends a password-only session back to the voice check", async () => {
    mockGetMe.mockRejectedValue(apiError(403));
    renderSettings();

    expect(await screen.findByText("passage screen")).toBeInTheDocument();
  });

  it("signs out", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderSettings();
    await screen.findByText("Sam Doe");

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(vi.mocked(logOut)).toHaveBeenCalledTimes(1);
    expect(isSignedIn()).toBe(false);
  });
});
