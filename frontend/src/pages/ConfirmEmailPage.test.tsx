import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { confirmEmail, sendEmailCode } from "../api/emailVerification";
import { MESSAGES } from "../api/errors";
import { isSignedIn } from "../api/session";
import { apiError, networkError } from "../test/apiError";
import {
  CODE_FORMAT,
  CODE_NOT_ACCEPTED,
  ConfirmEmailPage,
  EMAIL_FORMAT,
  NEW_CODE_SENT,
  type ConfirmEmailState,
} from "./ConfirmEmailPage";

// Never talk to a real server in tests; keep the real code checks.
vi.mock("../api/emailVerification", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/emailVerification")>()),
  confirmEmail: vi.fn(),
  sendEmailCode: vi.fn(),
}));
const mockConfirm = vi.mocked(confirmEmail);
const mockSend = vi.mocked(sendEmailCode);

const CONFIRMED = {
  user: {
    id: "u1",
    full_name: "Sam Lee",
    email: "sam@example.com",
    created_at: "2026-11-20T00:00:00Z",
    email_verified: true,
  },
  access_token: "token-1",
  token_type: "bearer",
};

function renderApp(state: ConfirmEmailState | null = { email: "sam@example.com" }) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/confirm-email", state }]}>
      <Routes>
        <Route path="/confirm-email" element={<ConfirmEmailPage />} />
        <Route path="/enroll" element={<p>enroll screen</p>} />
        <Route path="/signup" element={<p>signup screen</p>} />
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
});

describe("Confirm email screen", () => {
  it("says where the email went, with a field suited to one-time codes", () => {
    renderApp();

    expect(screen.getByRole("heading", { name: "Check your email." })).toBeInTheDocument();
    expect(screen.getByText(/sent an email to sam@example\.com/)).toBeInTheDocument();
    // The address came from signup, so it isn't asked for again.
    expect(screen.queryByLabelText("Email address")).not.toBeInTheDocument();
    const field = screen.getByLabelText("Confirmation code");
    expect(field).toHaveAttribute("autocomplete", "one-time-code");
    expect(field).toHaveAttribute("inputmode", "numeric");
  });

  it("needs no session: confirming is what starts it", () => {
    renderApp();

    expect(isSignedIn()).toBe(false);
    expect(screen.getByRole("button", { name: /confirm email/i })).toBeEnabled();
  });

  it("checks the code's shape before sending it", async () => {
    renderApp();
    await enter("12345");

    expect(screen.getByText(CODE_FORMAT)).toBeInTheDocument();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it("confirms with the address and a pasted code, signs in and goes on to set up a Voice ID", async () => {
    mockConfirm.mockResolvedValue(CONFIRMED);
    renderApp();
    await enter("123 456");

    expect(await screen.findByText("enroll screen")).toBeInTheDocument();
    expect(mockConfirm).toHaveBeenCalledWith("sam@example.com", "123456");
    expect(isSignedIn()).toBe(true);
  });

  it("says a code didn't work, in our words", async () => {
    mockConfirm.mockRejectedValue(apiError(400, { detail: "server words" }));
    renderApp();
    await enter("123456");

    expect(await screen.findByRole("alert")).toHaveTextContent(CODE_NOT_ACCEPTED);
    expect(screen.queryByText("server words")).not.toBeInTheDocument();
    expect(isSignedIn()).toBe(false);
    // The field can be used again.
    expect(screen.getByLabelText("Confirmation code")).toBeEnabled();
  });

  it("says when there have been too many tries", async () => {
    mockConfirm.mockRejectedValue(apiError(429, {}, { "retry-after": "600" }));
    renderApp();
    await enter("123456");

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Please try again in 10 minutes.");
  });

  it("sends a new code to the address and says so without saying whether it has an account", async () => {
    mockSend.mockResolvedValue();
    renderApp();
    await userEvent.setup().click(screen.getByRole("button", { name: "Send a new code" }));

    expect(await screen.findByRole("status")).toHaveTextContent(NEW_CODE_SENT);
    expect(mockSend).toHaveBeenCalledWith("sam@example.com");
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
    await userEvent.setup().click(screen.getByRole("link", { name: /wrong address/i }));

    expect(await screen.findByText("signup screen")).toBeInTheDocument();
  });

  describe("opened without an address (e.g. after a refresh)", () => {
    it("asks for the address too", () => {
      renderApp(null);

      expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "email");
      expect(screen.getByText(/enter your email address and the 6-digit code/i)).toBeInTheDocument();
    });

    it("checks the address before confirming or sending", async () => {
      renderApp(null);
      const user = await enter("123456");
      await user.click(screen.getByRole("button", { name: "Send a new code" }));

      expect(screen.getAllByText(EMAIL_FORMAT).length).toBeGreaterThan(0);
      expect(mockConfirm).not.toHaveBeenCalled();
      expect(mockSend).not.toHaveBeenCalled();
    });

    it("confirms with the address typed in", async () => {
      mockConfirm.mockResolvedValue(CONFIRMED);
      renderApp(null);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText("Email address"), " sam@example.com ");
      await enter("123456");

      expect(await screen.findByText("enroll screen")).toBeInTheDocument();
      expect(mockConfirm).toHaveBeenCalledWith("sam@example.com", "123456");
    });
  });
});
