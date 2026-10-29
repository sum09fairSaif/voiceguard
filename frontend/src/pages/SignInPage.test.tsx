import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

function renderApp() {
  render(
    <MemoryRouter initialEntries={["/signin"]}>
      <Routes>
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<p>signup screen</p>} />
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
    expect(screen.getByRole("button", { name: "Forgot password?" })).toBeInTheDocument();
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

  it("does nothing yet when Forgot password? is tapped", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));

    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(mockLogIn).not.toHaveBeenCalled();
  });

  it("links to Create account", async () => {
    renderApp();
    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: /create account/i }));

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
});
