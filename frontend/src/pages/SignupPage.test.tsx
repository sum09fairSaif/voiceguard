import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { signup } from "../api/auth";
import { getToken } from "../api/session";
import { RequireSession } from "../components/RequireSession";
import { apiError, networkError } from "../test/apiError";
import { SignupPage } from "./SignupPage";

// Never talk to a real server in tests.
vi.mock("../api/auth", () => ({ signup: vi.fn() }));
const mockSignup = vi.mocked(signup);

function renderApp(start = "/signup") {
  render(
    <MemoryRouter initialEntries={[start]}>
      <Routes>
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/enroll" element={<p>enroll screen</p>} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route
          path="/verify"
          element={
            <RequireSession>
              <p>verify screen</p>
            </RequireSession>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillAndSubmit(email = "alex@example.com") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Full name"), "  Alex Morgan ");
  await user.type(screen.getByLabelText("Email address"), email);
  await user.type(screen.getByLabelText("Password"), "correct-horse");
  await user.click(screen.getByRole("button", { name: /create account/i }));
}

const SIGNED_UP = {
  user: { id: "u1", full_name: "Alex Morgan", email: "alex@example.com", created_at: "2026-10-18T00:00:00Z" },
  access_token: "token-abc",
  token_type: "bearer",
};

beforeEach(() => {
  mockSignup.mockReset();
});

describe("Create account screen", () => {
  it("checks the form before sending anything", async () => {
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: /create account/i }));

    expect(screen.getByText("Enter your full name.")).toBeInTheDocument();
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(mockSignup).not.toHaveBeenCalled();
  });

  it("signs up, keeps the token and goes on to set up a Voice ID", async () => {
    mockSignup.mockResolvedValue(SIGNED_UP);
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
    expect(mockSignup).toHaveBeenCalledWith({
      full_name: "Alex Morgan",
      email: "alex@example.com",
      password: "correct-horse",
    });
    expect(getToken()).toBe("token-abc");
  });

  it("shows a taken email under the email field", async () => {
    mockSignup.mockRejectedValue(apiError(409, { detail: "An account with this email already exists." }));
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("An account with this email already exists.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
    expect(getToken()).toBeNull();
  });

  it.each([
    [apiError(503), "VoiceGuard is temporarily unavailable. Please try again shortly."],
    [networkError(), "Can't reach VoiceGuard. Check your connection and try again."],
    [apiError(429, {}, { "retry-after": "120" }), "Too many attempts. Please try again in 2 minutes."],
  ])("explains a failed signup (%#)", async (error, message) => {
    mockSignup.mockRejectedValue(error);
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: /create account/i })).toBeEnabled();
  });

  it("marks fields the server rejected", async () => {
    mockSignup.mockRejectedValue(
      apiError(422, { detail: [{ type: "value_error", loc: ["body", "email"], msg: "bad" }] }),
    );
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("Check this field and try again.")).toBeInTheDocument();
  });

  it("can't be sent twice while waiting", async () => {
    mockSignup.mockReturnValue(new Promise(() => {}));
    renderApp();
    await fillAndSubmit();

    expect(screen.getByRole("button", { name: /creating account/i })).toBeDisabled();
    expect(mockSignup).toHaveBeenCalledTimes(1);
  });

  it("locks the fields while sending, so an error always matches what was sent", async () => {
    mockSignup.mockReturnValue(new Promise(() => {}));
    renderApp();
    await fillAndSubmit();

    expect(screen.getByLabelText("Full name")).toBeDisabled();
    expect(screen.getByLabelText("Email address")).toBeDisabled();
    expect(screen.getByLabelText("Password")).toBeDisabled();
  });

  it("unlocks the fields again after a failed signup", async () => {
    mockSignup.mockRejectedValue(apiError(409));
    renderApp();
    await fillAndSubmit();

    await screen.findByText("An account with this email already exists.");
    expect(screen.getByLabelText("Email address")).toBeEnabled();
  });
});

describe("Session guard", () => {
  it("sends you to sign in without a token", () => {
    renderApp("/verify");

    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
  });
});

describe("Sign in link", () => {
  it("takes an existing member to sign in", async () => {
    renderApp();
    await userEvent.setup().click(screen.getByRole("link", { name: /already a member\? sign in/i }));

    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
  });
});

describe("Leaving while the account is being created", () => {
  it("ignores a signup that finishes after the user went to Sign in", async () => {
    let finish!: (value: typeof SIGNED_UP) => void;
    mockSignup.mockReturnValue(new Promise((r) => (finish = r)));
    renderApp();
    await fillAndSubmit();

    await userEvent.setup().click(screen.getByRole("link", { name: /already a member\? sign in/i }));
    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
    finish(SIGNED_UP);
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});
