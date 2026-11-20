import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { confirmEmail, sendEmailCode } from "../api/emailVerification";
import { MESSAGES } from "../api/errors";
import { clearToken, getSignedInUser, getToken, saveToken } from "../api/session";
import { RequireSession } from "../components/RequireSession";
import { apiError, networkError } from "../test/apiError";
import { CODE_FORMAT, CODE_NOT_ACCEPTED, ConfirmEmailPage, NEW_CODE_SENT } from "./ConfirmEmailPage";

// Never talk to a real server in tests; keep the real code checks.
vi.mock("../api/emailVerification", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/emailVerification")>()),
  confirmEmail: vi.fn(),
  sendEmailCode: vi.fn(),
}));
const mockConfirm = vi.mocked(confirmEmail);
const mockSend = vi.mocked(sendEmailCode);

const USER = { id: "u1", full_name: "Sam Lee", email: "sam@example.com" };

function renderApp() {
  render(
    <MemoryRouter initialEntries={["/confirm-email"]}>
      <Routes>
        <Route
          path="/confirm-email"
          element={
            <RequireSession>
              <ConfirmEmailPage />
            </RequireSession>
          }
        />
        <Route path="/enroll" element={<p>enroll screen</p>} />
        <Route path="/signup" element={<p>signup screen</p>} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function enter(code: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Confirmation code"), code);
  await user.click(screen.getByRole("button", { name: /confirm email/i }));
  return user;
}

beforeEach(() => {
  mockConfirm.mockReset();
  mockSend.mockReset();
  saveToken("token-1", USER);
});

describe("Confirm email screen", () => {
  it("says where the code went, with a field suited to one-time codes", () => {
    renderApp();

    expect(screen.getByRole("heading", { name: "Check your email." })).toBeInTheDocument();
    expect(screen.getByText(/sent a 6-digit code to sam@example\.com/)).toBeInTheDocument();
    const field = screen.getByLabelText("Confirmation code");
    expect(field).toHaveAttribute("autocomplete", "one-time-code");
    expect(field).toHaveAttribute("inputmode", "numeric");
  });

  it("needs a session", () => {
    clearToken();
    renderApp();

    expect(screen.getByText("sign-in screen")).toBeInTheDocument();
  });

  it("checks the code's shape before sending it", async () => {
    renderApp();
    await enter("12345");

    expect(screen.getByText(CODE_FORMAT)).toBeInTheDocument();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it("confirms a pasted code with spaces and goes on to set up a Voice ID", async () => {
    mockConfirm.mockResolvedValue({
      user: { ...USER, created_at: "2026-11-19T00:00:00Z", email_verified: true },
    });
    renderApp();
    await enter("123 456");

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
    expect(mockConfirm).toHaveBeenCalledWith("123456");
    // Still the same sign-in.
    expect(getToken()).toBe("token-1");
    expect(getSignedInUser()?.email).toBe("sam@example.com");
  });

  it("says a wrong or expired code didn't work, in our words", async () => {
    mockConfirm.mockRejectedValue(apiError(400, { detail: "server words" }));
    renderApp();
    await enter("123456");

    expect(await screen.findByRole("alert")).toHaveTextContent(CODE_NOT_ACCEPTED);
    expect(screen.queryByText("server words")).not.toBeInTheDocument();
    // The field can be used again.
    expect(screen.getByLabelText("Confirmation code")).toBeEnabled();
  });

  it("goes on if the address is already confirmed", async () => {
    mockConfirm.mockRejectedValue(apiError(409));
    renderApp();
    await enter("123456");

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
  });

  it("says when there have been too many tries", async () => {
    mockConfirm.mockRejectedValue(apiError(429, {}, { "retry-after": "600" }));
    renderApp();
    await enter("123456");

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Please try again in 10 minutes.");
  });

  it("sends a new code and says so", async () => {
    mockSend.mockResolvedValue();
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: "Send a new code" }));

    expect(await screen.findByRole("status")).toHaveTextContent(NEW_CODE_SENT);
    expect(mockSend).toHaveBeenCalledTimes(1);
  });

  it("explains when a new code can't be sent", async () => {
    mockSend.mockRejectedValue(apiError(503));
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: "Send a new code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.unavailable);
  });

  it("explains when VoiceGuard can't be reached", async () => {
    mockSend.mockRejectedValue(networkError());
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: "Send a new code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.network);
  });

  it("lets someone who typed the wrong address start over", async () => {
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: /wrong address/i }));

    expect(await screen.findByText("signup screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});
