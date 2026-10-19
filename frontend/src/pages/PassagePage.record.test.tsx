import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { requestChallenge, type Challenge } from "../api/challenge";
import { getToken, saveToken } from "../api/session";
import { submitAttempt, type VerifyResult } from "../api/verify";
import { RECORDER_MESSAGES } from "../hooks/useRecorder";
import { apiError } from "../test/apiError";
import { installFakeMicrophone, removeFakeMicrophone } from "../test/fakeMicrophone";
import { PassagePage } from "./PassagePage";
import { ResultPage } from "./ResultPage";

// Never talk to a real server in tests; keep the real error messages.
vi.mock("../api/challenge", () => ({ requestChallenge: vi.fn() }));
vi.mock("../api/verify", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/verify")>()),
  submitAttempt: vi.fn(),
}));
const mockChallenge = vi.mocked(requestChallenge);
const mockSubmit = vi.mocked(submitAttempt);

function challenge(id: string): Challenge {
  return {
    attempt_id: id,
    passage: `passage ${id}`,
    expires_at: new Date(Date.now() + 120_000).toISOString(),
  };
}

const INCOMPLETE: VerifyResult = {
  decision: "incomplete",
  reason: "The passage was read correctly, but this account has no voiceprint yet and the liveness check isn't built yet.",
  content: { passed: true, score: 1, matched: 6, total: 6 },
  identity: "not_enrolled",
  liveness: "not_checked",
};

let microphone: ReturnType<typeof installFakeMicrophone>;

function renderFlow() {
  render(
    <MemoryRouter initialEntries={["/verify"]}>
      <Routes>
        <Route path="/verify" element={<PassagePage />} />
        <Route path="/result" element={<ResultPage />} />
        <Route path="/signup" element={<p>signup screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function recordClip(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText("“Passage a1”");
  await user.click(screen.getByRole("button", { name: "Start recording" }));
  await user.click(await screen.findByRole("button", { name: "Stop recording" }));
  await screen.findByText("Recording ready");
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

beforeEach(() => {
  microphone = installFakeMicrophone();
  mockChallenge.mockReset().mockResolvedValueOnce(challenge("a1")).mockResolvedValue(challenge("a2"));
  mockSubmit.mockReset();
});

afterEach(() => {
  removeFakeMicrophone();
});

describe("Recording and submitting", () => {
  it("records, checks, and shows the result", async () => {
    const reply = deferred<VerifyResult>();
    mockSubmit.mockReturnValue(reply.promise);
    const user = userEvent.setup();
    renderFlow();

    await recordClip(user);
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(screen.getByRole("button", { name: /checking your voice/i })).toBeDisabled();
    const [audio, attemptId] = mockSubmit.mock.calls[0];
    expect(attemptId).toBe("a1");
    expect((audio as Blob).size).toBeGreaterThan(0);

    reply.resolve(INCOMPLETE);
    expect(await screen.findByText("Almost there.")).toBeInTheDocument();
    expect(screen.getByText("No voiceprint yet")).toBeInTheDocument();
  });

  it("lets you record again before submitting", async () => {
    const user = userEvent.setup();
    renderFlow();
    await recordClip(user);

    await user.click(screen.getByRole("button", { name: /record again/i }));

    expect(screen.getByRole("button", { name: "Start recording" })).toBeEnabled();
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it("clears the recording when you get a new phrase", async () => {
    const user = userEvent.setup();
    renderFlow();
    await recordClip(user);

    await user.click(screen.getByRole("button", { name: /new phrase/i }));

    expect(await screen.findByText("“Passage a2”")).toBeInTheDocument();
    expect(screen.queryByText("Recording ready")).not.toBeInTheDocument();
    expect(screen.getByText("Tap to start recording")).toBeInTheDocument();
  });

  it.each([
    [apiError(400), "This phrase has expired or was already used. Get a new phrase and try again."],
    [apiError(422), "We couldn't make out the recording. Get a new phrase and record again."],
    [apiError(503), "VoiceGuard is temporarily unavailable. Please try again shortly."],
  ])("asks for a new phrase when the passage may be used up (%#)", async (error, message) => {
    mockSubmit.mockRejectedValue(error);
    const user = userEvent.setup();
    renderFlow();
    await recordClip(user);

    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Start recording" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /get a new phrase/i }));
    expect(await screen.findByText("“Passage a2”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeEnabled();
  });

  it.each([
    [apiError(413), "That recording is too long. Please read just the phrase."],
    [apiError(429, {}, { "retry-after": "120" }), "Too many attempts. Please try again in 2 minutes."],
  ])("keeps the same phrase when it wasn't used up (%#)", async (error, message) => {
    mockSubmit.mockRejectedValue(error);
    const user = userEvent.setup();
    renderFlow();
    await recordClip(user);

    await user.click(screen.getByRole("button", { name: /submit/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);

    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(screen.getByText("“Passage a1”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeEnabled();
  });

  it("sends a signed-out user back to signup", async () => {
    saveToken("expired");
    mockSubmit.mockRejectedValue(apiError(401));
    const user = userEvent.setup();
    renderFlow();
    await recordClip(user);

    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(await screen.findByText("signup screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("explains a blocked microphone", async () => {
    microphone.getUserMedia.mockRejectedValue(new DOMException("no", "NotAllowedError"));
    const user = userEvent.setup();
    renderFlow();
    await screen.findByText("“Passage a1”");

    await user.click(screen.getByRole("button", { name: "Start recording" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(RECORDER_MESSAGES.denied);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("can't record before a passage has arrived", async () => {
    mockChallenge.mockReset().mockReturnValue(new Promise(() => {}));
    renderFlow();

    expect(screen.getByRole("button", { name: "Start recording" })).toBeDisabled();
  });
});
