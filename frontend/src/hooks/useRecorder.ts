import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderStatus = "idle" | "requesting" | "recording" | "recorded" | "error";

export const RECORDER_MESSAGES = {
  unsupported: "This browser can't record audio here. Please use an up-to-date Chrome or Safari.",
  denied:
    "Microphone access is blocked. Allow it in your browser's site settings (the icon next to the address bar), then try again.",
  noMicrophone: "No microphone was found. Connect one and try again.",
  busy: "Your microphone is being used by another app. Close it and try again.",
  failed: "Couldn't start the microphone. Please try again.",
  empty: "Nothing was recorded. Please try again.",
};

// Formats the backend accepts, in order of preference. Chrome and Firefox
// record webm; Safari records mp4.
const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

function pickMimeType(): string {
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function microphoneError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return RECORDER_MESSAGES.denied;
    case "NotFoundError":
    case "OverconstrainedError":
      return RECORDER_MESSAGES.noMicrophone;
    case "NotReadableError":
      return RECORDER_MESSAGES.busy;
    default:
      return RECORDER_MESSAGES.failed;
  }
}

// Records one short clip from the microphone. Permission is only asked for
// when recording starts, the clip stays in memory, and the microphone is
// released as soon as recording stops.
export function useRecorder({ maxSeconds = 15 }: { maxSeconds?: number } = {}) {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState<Blob | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // Bumped by reset and by leaving the screen. A start that was waiting for
  // microphone permission checks it afterwards, so a late "Allow" can't
  // start recording for a passage that's gone.
  const generationRef = useRef(0);

  const releaseMicrophone = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  // Stops any recording in progress without keeping it, and turns the
  // microphone off.
  const discardRecording = useCallback(() => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder && recorder.state === "recording") {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
    }
    releaseMicrophone();
  }, [releaseMicrophone]);

  const start = useCallback(async () => {
    const generation = ++generationRef.current;
    setError("");
    setRecording(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      // Also the case on a page that isn't https or localhost.
      setStatus("error");
      setError(RECORDER_MESSAGES.unsupported);
      return;
    }

    setStatus("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      if (generation !== generationRef.current) return;
      setStatus("error");
      setError(microphoneError(err));
      return;
    }
    if (generation !== generationRef.current) {
      // Reset or left while the permission prompt was open.
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    streamRef.current = stream;

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      releaseMicrophone();
      const clip = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
      if (clip.size === 0) {
        setStatus("error");
        setError(RECORDER_MESSAGES.empty);
        return;
      }
      setRecording(clip);
      setStatus("recorded");
    };
    recorderRef.current = recorder;
    recorder.start();
    setElapsed(0);
    setStatus("recording");
  }, [releaseMicrophone]);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const reset = useCallback(() => {
    generationRef.current++;
    discardRecording();
    setRecording(null);
    setError("");
    setElapsed(0);
    setStatus("idle");
  }, [discardRecording]);

  // Elapsed seconds while recording.
  useEffect(() => {
    if (status !== "recording") return;
    const timer = setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => clearInterval(timer);
  }, [status]);

  // Stops on its own at the limit, far below the server's 1 MB cap.
  useEffect(() => {
    if (status === "recording" && elapsed >= maxSeconds) stop();
  }, [status, elapsed, maxSeconds, stop]);

  // Leaving the screen mid-recording must not leave the microphone on.
  useEffect(() => {
    const generation = generationRef;
    return () => {
      generation.current++;
      discardRecording();
    };
  }, [discardRecording]);

  return { status, error, elapsed, recording, start, stop, reset };
}
