import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, type Me } from "../api/me";
import { getToken, saveToken } from "../api/session";
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

function renderAccount() {
  render(
    <MemoryRouter initialEntries={["/account"]}>
      <Routes>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route path="/verify" element={<p>passage screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function detail(label: string) {
  return screen.getByText(label).nextElementSibling?.textContent;
}

beforeEach(() => {
  saveToken("voice-verified");
  mockGetMe.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Account page", () => {
  it("shows the account to a voice-verified session", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderAccount();

    expect(screen.getByText("Loading your account…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Welcome back, Sam." })).toBeInTheDocument();
    expect(detail("Email")).toBe("sam@example.com");
    expect(detail("Voice ID")).toMatch(/^Set up /);
    expect(detail("Last sign-in")).toMatch(/2026/);
  });

  it("says when it's the first sign-in and voice isn't set up", async () => {
    mockGetMe.mockResolvedValue({ ...ME, enrolled_at: null, previous_sign_in_at: null });
    renderAccount();

    await screen.findByRole("heading", { name: "Welcome back, Sam." });
    expect(detail("Voice ID")).toBe("Not set up");
    expect(detail("Last sign-in")).toBe("This is your first");
  });

  it("sends a password-only session back to the voice check", async () => {
    mockGetMe.mockRejectedValue(apiError(403));
    renderAccount();

    expect(await screen.findByText("passage screen")).toBeInTheDocument();
    expect(getToken()).toBe("voice-verified");
  });

  it("sends an expired or bad session to sign in and forgets it", async () => {
    mockGetMe.mockRejectedValue(apiError(401));
    renderAccount();

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("explains other failures in our own words", async () => {
    mockGetMe.mockRejectedValue(networkError());
    renderAccount();

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach VoiceGuard.");
  });

  it("signs out", async () => {
    mockGetMe.mockResolvedValue(ME);
    renderAccount();
    await screen.findByRole("heading", { name: "Welcome back, Sam." });

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});
