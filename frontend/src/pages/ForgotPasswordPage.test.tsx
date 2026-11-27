import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MESSAGES } from "../api/errors";
import { requestPasswordReset } from "../api/passwordReset";
import { apiError, networkError } from "../test/apiError";
import { ForgotPasswordPage } from "./ForgotPasswordPage";

// Never talk to a real server in tests.
vi.mock("../api/passwordReset", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/passwordReset")>()),
  requestPasswordReset: vi.fn(),
}));
const mockRequest = vi.mocked(requestPasswordReset);

function renderPage(state?: unknown) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/forgot-password", state }]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/signin" element={<p>sign in screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function send(email = " sam@example.com ") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email address"), email);
  await user.click(screen.getByRole("button", { name: /send reset link/i }));
  return user;
}

beforeEach(() => {
  mockRequest.mockReset().mockResolvedValue(undefined);
});

describe("ForgotPasswordPage", () => {
  it("shows the Figma heading, field, link and note", () => {
    renderPage();

    expect(screen.getByText("We’ve got you")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "A fresh start." })).toBeInTheDocument();
    expect(
      screen.getByText("It happens. Enter your email and we’ll help you get back into your account."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("placeholder", "you@example.com");
    expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/signin");
    expect(screen.getByText("Your account stays protected throughout the reset process")).toBeInTheDocument();
  });

  it("fills in the email carried over from sign in", () => {
    renderPage({ email: "sam@example.com" });

    expect(screen.getByLabelText("Email address")).toHaveValue("sam@example.com");
  });

  it("sends the trimmed email and then says to check it, the same for any address", async () => {
    renderPage();
    await send();

    expect(mockRequest).toHaveBeenCalledWith("sam@example.com");
    const sent = await screen.findByRole("status");
    expect(sent).toHaveTextContent("Check your email");
    expect(sent).toHaveTextContent(
      "If there’s an account for sam@example.com, we’ve sent it a link to reset your password.",
    );
    expect(screen.queryByLabelText("Email address")).not.toBeInTheDocument();
  });

  it("can send it again with the email kept", async () => {
    renderPage();
    const user = await send();
    await user.click(await screen.findByRole("button", { name: "Send it again" }));

    expect(screen.getByLabelText("Email address")).toHaveValue("sam@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(mockRequest).toHaveBeenCalledTimes(2);
  });

  it("checks the email before sending", async () => {
    renderPage();
    await send("not-an-email");

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(mockRequest).not.toHaveBeenCalled();
  });

  it("locks the form while sending", async () => {
    mockRequest.mockReturnValue(new Promise(() => {}));
    renderPage();
    await send();

    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
    expect(screen.getByLabelText("Email address")).toBeDisabled();
  });

  it("says how long to wait when there have been too many requests", async () => {
    mockRequest.mockRejectedValue(apiError(429, {}, { "retry-after": "1800" }));
    renderPage();
    await send();

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Please try again in 30 minutes.");
    expect(screen.getByLabelText("Email address")).toBeEnabled();
  });

  it.each([
    ["email can't be sent", apiError(503), MESSAGES.unavailable],
    ["server can't be reached", networkError(), MESSAGES.network],
  ])("says so when the %s", async (_, error, message) => {
    mockRequest.mockRejectedValue(error);
    renderPage();
    await send();

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText("Check your email")).not.toBeInTheDocument();
  });

  it("marks the email when the server refuses it", async () => {
    mockRequest.mockRejectedValue(apiError(422, { detail: [{ type: "value_error", loc: ["body", "email"], msg: "" }] }));
    renderPage();
    await send();

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
  });

  it("goes back to sign in", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: "Back to sign in" }));

    expect(screen.getByText("sign in screen")).toBeInTheDocument();
  });
});
