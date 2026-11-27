import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { confirmRecoveryCode, requestRecoveryCode } from "../api/recovery";
import { isSignedIn } from "../api/session";
import { apiError, networkError } from "../test/apiError";
import { signInForTest } from "../test/session";
import { CODE_FORMAT, CODE_NOT_ACCEPTED, CODE_SENT, NOT_PAUSED, RecoverPage } from "./RecoverPage";

// Never talk to a real server in tests.
vi.mock("../api/recovery", () => ({ requestRecoveryCode: vi.fn(), confirmRecoveryCode: vi.fn() }));
const mockRequest = vi.mocked(requestRecoveryCode);
const mockConfirm = vi.mocked(confirmRecoveryCode);

function EnrollStandIn() {
  const state = useLocation().state as { recovering?: boolean } | null;
  return <p>enroll screen {state?.recovering ? "(recovering)" : ""}</p>;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/recover"]}>
      <Routes>
        <Route path="/recover" element={<RecoverPage />} />
        <Route path="/enroll" element={<EnrollStandIn />} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
        <Route path="/verify" element={<p>voice check screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function sendCode(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Email me a code" }));
  await screen.findByLabelText("Code from the email");
}

beforeEach(() => {
  signInForTest();
  mockRequest.mockReset().mockResolvedValue(undefined);
  mockConfirm.mockReset().mockResolvedValue({ enroll_minutes: 30 });
});

describe("RecoverPage", () => {
  it("emails a code, then a correct one goes on to recording, as a replacement", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole("heading", { name: "Record a new Voice ID." })).toBeInTheDocument();
    await sendCode(user);
    expect(screen.getByRole("status")).toHaveTextContent(CODE_SENT);

    await user.type(screen.getByLabelText("Code from the email"), "123 456");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockConfirm).toHaveBeenCalledWith("123456");
    expect(await screen.findByText("enroll screen (recovering)")).toBeInTheDocument();
  });

  it("checks the code's format before sending it", async () => {
    const user = userEvent.setup();
    renderPage();
    await sendCode(user);

    await user.type(screen.getByLabelText("Code from the email"), "12a");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText(CODE_FORMAT)).toBeInTheDocument();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it("says when a code isn't accepted, and can send a new one", async () => {
    mockConfirm.mockRejectedValue(apiError(400, { detail: "server words" }));
    const user = userEvent.setup();
    renderPage();
    await sendCode(user);

    await user.type(screen.getByLabelText("Code from the email"), "654321");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CODE_NOT_ACCEPTED);

    await user.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(mockRequest).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText("Code from the email")).toHaveValue("");
  });

  it("explains when voice checks aren't paused", async () => {
    mockRequest.mockRejectedValue(apiError(409, { detail: "server words" }));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Email me a code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_PAUSED);
    expect(screen.queryByLabelText("Code from the email")).not.toBeInTheDocument();
  });

  it("explains a paused switch and a lost connection in our own words", async () => {
    mockRequest.mockRejectedValueOnce(apiError(503, { paused: "enrollment" })).mockRejectedValueOnce(networkError());
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Setting up a Voice ID is paused for now.");

    await user.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach VoiceGuard.");
  });

  it("sends an ended session to sign in", async () => {
    mockRequest.mockRejectedValue(apiError(401));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Email me a code" }));

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(isSignedIn()).toBe(false);
  });

  it("leads back to the voice check", async () => {
    renderPage();

    await userEvent.setup().click(screen.getByRole("link", { name: "Back to the voice check" }));

    expect(screen.getByText("voice check screen")).toBeInTheDocument();
  });
});
