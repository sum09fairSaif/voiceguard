import { vi } from "vitest";

// A stand-in for the browser's MediaRecorder: stop() hands over the clip and
// fires onstop, like the real one.
export class FakeMediaRecorder {
  static supported = new Set(["audio/webm;codecs=opus", "audio/webm"]);
  static instances: FakeMediaRecorder[] = [];
  static clip: Blob = new Blob(["fake audio"], { type: "audio/webm;codecs=opus" });

  static isTypeSupported(type: string) {
    return FakeMediaRecorder.supported.has(type);
  }

  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  stream: MediaStream;

  constructor(stream: MediaStream, options?: { mimeType?: string }) {
    this.stream = stream;
    this.mimeType = options?.mimeType ?? "";
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: FakeMediaRecorder.clip });
    this.onstop?.();
  }
}

// Installs a fake microphone. Returns the track's stop() spy (to check the
// microphone is released) and the getUserMedia mock (to make it fail).
export function installFakeMicrophone() {
  const stopTrack = vi.fn();
  const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  FakeMediaRecorder.instances = [];
  FakeMediaRecorder.clip = new Blob(["fake audio"], { type: "audio/webm;codecs=opus" });
  return { stopTrack, getUserMedia };
}

export function removeFakeMicrophone() {
  Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
  vi.unstubAllGlobals();
}
