import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeMediaRecorder, installFakeMicrophone, removeFakeMicrophone } from "../test/fakeMicrophone";
import { RECORDER_MESSAGES, useRecorder } from "./useRecorder";

let microphone: ReturnType<typeof installFakeMicrophone>;

beforeEach(() => {
  vi.useFakeTimers();
  microphone = installFakeMicrophone();
});

afterEach(() => {
  vi.useRealTimers();
  removeFakeMicrophone();
});

async function startRecording(result: { current: ReturnType<typeof useRecorder> }) {
  await act(async () => {
    await result.current.start();
  });
}

describe("useRecorder", () => {
  it("asks for the microphone only when recording starts", async () => {
    const { result } = renderHook(() => useRecorder());
    expect(microphone.getUserMedia).not.toHaveBeenCalled();

    await startRecording(result);

    expect(microphone.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(result.current.status).toBe("recording");
  });

  it("records in a format the backend accepts", async () => {
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    expect(FakeMediaRecorder.instances[0].mimeType).toBe("audio/webm;codecs=opus");
  });

  it("uses Safari's mp4 when webm isn't available", async () => {
    FakeMediaRecorder.supported = new Set(["audio/mp4"]);
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    expect(FakeMediaRecorder.instances[0].mimeType).toBe("audio/mp4");
    FakeMediaRecorder.supported = new Set(["audio/webm;codecs=opus", "audio/webm"]);
  });

  it("keeps the clip and releases the microphone on stop", async () => {
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    act(() => result.current.stop());

    expect(result.current.status).toBe("recorded");
    expect(result.current.recording?.size).toBeGreaterThan(0);
    expect(result.current.recording?.type).toBe("audio/webm;codecs=opus");
    expect(microphone.stopTrack).toHaveBeenCalled();
  });

  it("counts seconds and stops on its own at the limit", async () => {
    const { result } = renderHook(() => useRecorder({ maxSeconds: 3 }));
    await startRecording(result);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.elapsed).toBe(1);

    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.status).toBe("recorded");
    expect(microphone.stopTrack).toHaveBeenCalled();
  });

  it.each([
    ["NotAllowedError", RECORDER_MESSAGES.denied],
    ["NotFoundError", RECORDER_MESSAGES.noMicrophone],
    ["NotReadableError", RECORDER_MESSAGES.busy],
    ["AbortError", RECORDER_MESSAGES.failed],
  ])("explains a microphone %s", async (name, message) => {
    microphone.getUserMedia.mockRejectedValue(new DOMException("no", name));
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(message);
    expect(FakeMediaRecorder.instances).toHaveLength(0);
  });

  it("explains a browser or page that can't record", async () => {
    removeFakeMicrophone();
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(RECORDER_MESSAGES.unsupported);
  });

  it("treats an empty clip as an error", async () => {
    FakeMediaRecorder.clip = new Blob([], { type: "audio/webm" });
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);

    act(() => result.current.stop());

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(RECORDER_MESSAGES.empty);
  });

  it("can start over after a recording", async () => {
    const { result } = renderHook(() => useRecorder());
    await startRecording(result);
    act(() => result.current.stop());

    act(() => result.current.reset());

    expect(result.current.status).toBe("idle");
    expect(result.current.recording).toBeNull();
  });

  it("releases the microphone when leaving the screen mid-recording", async () => {
    const { result, unmount } = renderHook(() => useRecorder());
    await startRecording(result);

    unmount();

    expect(microphone.stopTrack).toHaveBeenCalled();
  });
});
