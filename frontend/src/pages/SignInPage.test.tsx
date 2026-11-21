import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WRONG_CREDENTIALS, logIn } from "../api/auth";
import { getEnrollment, type Enrollment } from "../api/enroll";
import { MESSAGES } from "../api/errors";
import { getToken } from "../api/session";
import { RequireSession } from "../components/RequireSession";
import { apiError, networkError } from "../test/apiError";
import { SignInPage } from "./SignInPage";

// Never talk to a real server in tests; keep the real error wording.
vi.mock("../api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/auth")>()),
  logIn: vi.fn(),
}));
const mockLogIn = vi.mocked(logIn);
vi.mock("../api/enroll", () => ({ getEnrollment: vi.fn() }));
const mockGetEnrollment = vi.mocked(getEnrollment);

const ENROLLED: Enrollment = { status: "enrolled", samples_accepted: 3, samples_required: 3, prompt: null };
const NOT_ENROLLED: Enrollment = { status: "not_started", samples_accepted: 0, samples_required: 3, prompt: "amber lantern" };

const account = {
  user: { id: "u1", full_name: "Sam Lee", email: "sam@example.com", created_at: "2026-10-22T12:00:00Z" },
  access_token: "token-1",
  token_type: "bearer",
};

function ForgotPasswordStandIn() {
  const email = (useLocation().state as { email?: string } | null)?.email;
  return <p>forgot password screen for {email || "no email"}</p>;
}

function ConfirmEmailStandIn() {
  const email = (useLocation().state as { email?: string } | null)?.email;
  return <p>confirm email screen for {email || "no email"}</p>;
}

function renderApp(state?: unknown) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/signin", state }]}>
      <Routes>
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<p>signup screen</p>} />
        <Route path="/forgot-password" element={<ForgotPasswordStandIn />} />
        <Route path="/confirm-email" element={<ConfirmEmailStandIn />} />
        <Route path="/enroll" element={<p>enroll screen</p>} />
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

async function fillAndSubmit(email = " sam@example.com ", password = "Correct-horse-9") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email address"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: /sign in securely/i }));
  return user;
}

beforeEach(() => {
  mockLogIn.mockReset();
  mockGetEnrollment.mockReset().mockResolvedValue(ENROLLED);
});

describe("SignInPage", () => {
  it("shows the Figma heading, fields and links", () => {
    renderApp();
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toBeInTheDocument();
    expect(screen.queryByText(/voice id/i)).not.toBeInTheDocument();
  });

  it("sends someone without a Voice ID to set one up", async () => {
    mockLogIn.mockResolvedValue(account);
    mockGetEnrollment.mockResolvedValue(NOT_ENROLLED);
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
    expect(getToken()).toBe("token-1");
  });

  it("sends people to the enrollment page if their Voice ID status can't be read", async () => {
    mockLogIn.mockResolvedValue(account);
    mockGetEnrollment.mockRejectedValue(apiError(503));
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
  });

  it("signs in, saves the token and, with a Voice ID, goes on to the voice check", async () => {
    mockLogIn.mockResolvedValue(account);
    renderApp();
    await fillAndSubmit();

    expect(mockLogIn).toHaveBeenCalledWith({ email: "sam@example.com", password: "Correct-horse-9" });
    expect(await screen.findByText("verify screen")).toBeInTheDocument();
    expect(getToken()).toBe("token-1");
  });

  it("checks the fields before sending anything", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign in securely/i }));

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(mockLogIn).not.toHaveBeenCalled();
  });

  it("says the credentials are wrong without marking either field", async () => {
    mockLogIn.mockRejectedValue(apiError(401, { detail: "server text" }));
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(WRONG_CREDENTIALS);
    expect(screen.getByLabelText("Email address")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Password")).not.toHaveAttribute("aria-invalid");
    expect(getToken()).toBeNull();
  });

  it("explains a lockout with the minutes left", async () => {
    mockLogIn.mockRejectedValue(apiError(423, { detail: "server text" }, { "retry-after": "1800" }));
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent("try again in 30 minutes");
  });

  // An unconfirmed account gets the same answers as a wrong password (#111),
  // so the way back to confirming comes with every one of them.
  it.each([
    ["a wrong password", apiError(401)],
    ["a lockout", apiError(423, {}, { "retry-after": "1800" })],
  ])("after %s, offers the way to confirm an email, carrying the email typed", async (_, error) => {
    mockLogIn.mockRejectedValue(error);
    renderApp();
    const user = await fillAndSubmit();

    await user.click(await screen.findByRole("link", { name: "Enter your code" }));

    expect(screen.getByText("confirm email screen for sam@example.com")).toBeInTheDocument();
  });

  it("doesn't offer it before trying, or for other problems", async () => {
    mockLogIn.mockRejectedValue(networkError());
    renderApp();
    expect(screen.queryByRole("link", { name: "Enter your code" })).not.toBeInTheDocument();

    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.network);
    expect(screen.queryByRole("link", { name: "Enter your code" })).not.toBeInTheDocument();
  });

  it("points at the field the server rejected", async () => {
    mockLogIn.mockRejectedValue(apiError(422, { detail: [{ loc: ["body", "email"] }] }));
    renderApp();
    await fillAndSubmit();

    expect(await screen.findByText("Check this field and try again.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
  });

  it("explains when VoiceGuard can't be reached and lets the user try again", async () => {
    mockLogIn.mockRejectedValueOnce(networkError()).mockResolvedValueOnce(account);
    renderApp();
    const user = await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.network);
    await user.click(screen.getByRole("button", { name: /sign in securely/i }));
    expect(await screen.findByText("verify screen")).toBeInTheDocument();
  });

  it("locks the form while signing in", async () => {
    mockLogIn.mockReturnValue(new Promise(() => {}));
    renderApp();
    await fillAndSubmit();

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    expect(screen.getByLabelText("Email address")).toBeDisabled();
    expect(screen.getByLabelText("Password")).toBeDisabled();
  });

  it("opens Reset password from Forgot password?, carrying the email typed", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), " sam@example.com ");
    await user.click(screen.getByRole("link", { name: "Forgot password?" }));

    expect(screen.getByText("forgot password screen for sam@example.com")).toBeInTheDocument();
    expect(mockLogIn).not.toHaveBeenCalled();
  });

  it("says when the password was just changed", () => {
    renderApp({ passwordChanged: true });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Your password has been changed, and your account has been signed out on every device.",
    );
  });

  it("says nothing about a password change otherwise", () => {
    renderApp();

    expect(screen.queryByText(/password has been changed/)).not.toBeInTheDocument();
  });

  it("links to Create account", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: "Create account" }));

    expect(screen.getByText("signup screen")).toBeInTheDocument();
  });

  describe("leaving while signing in", () => {
    function deferred<T>() {
      let resolve!: (value: T) => void;
      const promise = new Promise<T>((r) => (resolve = r));
      return { promise, resolve };
    }

    it("ignores a sign-in that succeeds after the user went to Create account", async () => {
      const pending = deferred<typeof account>();
      mockLogIn.mockReturnValue(pending.promise);
      renderApp();
      const user = await fillAndSubmit();

      await user.click(screen.getByRole("link", { name: /create account/i }));
      expect(screen.getByText("signup screen")).toBeInTheDocument();
      pending.resolve(account);
      await new Promise((r) => setTimeout(r, 0));

      expect(screen.getByText("signup screen")).toBeInTheDocument();
      expect(getToken()).toBeNull();
      expect(mockGetEnrollment).not.toHaveBeenCalled();
    });

    it("drops the session if the user left while their Voice ID status was loading", async () => {
      mockLogIn.mockResolvedValue(account);
      const pending = deferred<typeof ENROLLED>();
      mockGetEnrollment.mockReturnValue(pending.promise);
      renderApp();
      const user = await fillAndSubmit();
      await screen.findByRole("button", { name: /signing in/i });
      await new Promise((r) => setTimeout(r, 0));

      await user.click(screen.getByRole("link", { name: /create account/i }));
      pending.resolve(ENROLLED);
      await new Promise((r) => setTimeout(r, 0));

      expect(screen.getByText("signup screen")).toBeInTheDocument();
      expect(getToken()).toBeNull();
    });
  });

  it("says when a sign-out couldn't end the session on the server", () => {
    renderApp({ serverSignOutFailed: true });

    expect(screen.getByRole("status")).toHaveTextContent("couldn't reach VoiceGuard to end your session everywhere");
  });

  it("says nothing extra after a normal visit or sign-out", () => {
    renderApp({ serverSignOutFailed: false });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
