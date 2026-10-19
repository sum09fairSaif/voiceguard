import { act, renderHook, screen, waitFor } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { requestChallenge, type Challenge } from "../api/challenge";
import { getToken, saveToken } from "../api/session";
import { apiError, networkError } from "../test/apiError";
import { useChallenge } from "./useChallenge";

// Never talk to a real server in tests.
vi.mock("../api/challenge", () => ({ requestChallenge: vi.fn() }));
const mockRequest = vi.mocked(requestChallenge);

const NOW = Date.parse("2026-10-19T03:00:00Z");

function challenge(id: string, secondsFromNow = 120): Challenge {
  return {
    attempt_id: id,
    passage: `passage for ${id}`,
    expires_at: new Date(NOW + secondsFromNow * 1000).toISOString(),
  };
}

// Renders the hook inside a router (it navigates on 401) and in StrictMode,
// which mounts twice like the real app does in development.
function renderChallenge() {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <StrictMode>
      <MemoryRouter initialEntries={["/verify"]}>
        <Routes>
          <Route path="/verify" element={children} />
          <Route path="/signup" element={<p>signup screen</p>} />
        </Routes>
      </MemoryRouter>
    </StrictMode>
  );
  return renderHook(() => useChallenge(), { wrapper });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  mockRequest.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useChallenge", () => {
  it("asks for one passage when the screen opens, even in StrictMode", async () => {
    mockRequest.mockResolvedValue(challenge("a1"));
    const { result } = renderChallenge();

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.challenge?.attempt_id).toBe("a1"));
    expect(result.current.loading).toBe(false);
    expect(result.current.secondsRemaining).toBe(120);
    expect(mockRequest).toHaveBeenCalledTimes(1);
  });

  it("counts down every second and expires at zero", async () => {
    mockRequest.mockResolvedValue(challenge("a1", 3));
    const { result } = renderChallenge();
    await waitFor(() => expect(result.current.challenge).not.toBeNull());

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.secondsRemaining).toBe(2);

    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.secondsRemaining).toBe(0);
    expect(result.current.expired).toBe(true);
  });

  it("gets a new passage on request", async () => {
    mockRequest.mockResolvedValueOnce(challenge("a1")).mockResolvedValueOnce(challenge("a2"));
    const { result } = renderChallenge();
    await waitFor(() => expect(result.current.challenge?.attempt_id).toBe("a1"));

    act(() => result.current.newPhrase());
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.challenge?.attempt_id).toBe("a2"));
    expect(result.current.expired).toBe(false);
  });

  it("keeps only the newest passage when an older reply arrives late", async () => {
    const slow = deferred<Challenge>();
    const fast = deferred<Challenge>();
    mockRequest.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise);
    const { result } = renderChallenge();

    act(() => result.current.newPhrase());
    await act(async () => fast.resolve(challenge("newest")));
    await act(async () => slow.resolve(challenge("stale")));

    expect(result.current.challenge?.attempt_id).toBe("newest");
  });

  it("sends a signed-out user back to signup and clears the session", async () => {
    saveToken("expired-token");
    mockRequest.mockRejectedValue(apiError(401));
    renderChallenge();

    expect(await screen.findByText("signup screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it.each([
    [apiError(429, {}, { "retry-after": "600" }), "Too many attempts. Please try again in 10 minutes."],
    [apiError(503), "VoiceGuard is temporarily unavailable. Please try again shortly."],
    [networkError(), "Can't reach VoiceGuard. Check your connection and try again."],
  ])("explains a failed request and can try again (%#)", async (error, message) => {
    mockRequest.mockRejectedValueOnce(error).mockResolvedValueOnce(challenge("a1"));
    const { result } = renderChallenge();

    await waitFor(() => expect(result.current.error).toBe(message));
    expect(result.current.challenge).toBeNull();
    expect(result.current.loading).toBe(false);

    act(() => result.current.newPhrase());
    await waitFor(() => expect(result.current.challenge?.attempt_id).toBe("a1"));
    expect(result.current.error).toBe("");
  });
});
