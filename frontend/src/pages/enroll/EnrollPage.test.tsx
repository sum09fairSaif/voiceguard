import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ENROLL_MESSAGES, addSample, getEnrollment, startOver, type Enrollment } from "../../api/enroll";
import { MESSAGES } from "../../api/errors";
import { getToken, saveToken } from "../../api/session";
import { apiError } from "../../test/apiError";
import { installFakeMicrophone, removeFakeMicrophone } from "../../test/fakeMicrophone";
import { EnrollPage } from "./EnrollPage";

// Never talk to a real server in tests; keep the real error wording.
vi.mock("../../api/enroll", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/enroll")>()),
  getEnrollment: vi.fn(),
  addSample: vi.fn(),
  startOver: vi.fn(),
}));
const mockGet = vi.mocked(getEnrollment);
const mockAdd = vi.mocked(addSample);
const mockStartOver = vi.mocked(startOver);

function status(accepted: number, prompt = `amber lantern river ${accepted}`): Enrollment {
  return {
    status: accepted >= 3 ? "enrolled" : accepted > 0 ? "in_progress" : "not_started",
    samples_accepted: Math.min(accepted, 3),
    samples_required: 3,
    prompt: accepted >= 3 ? null : prompt,
  };
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/enroll"]}>
      <Routes>
        <Route path="/enroll" element={<EnrollPage />} />
        <Route path="/signin" element={<p>sign-in screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function record(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Start recording" }));
  await user.click(await screen.findByRole("button", { name: "Stop recording" }));
  await screen.findByText("Recording ready");
}

async function startFromIntro(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("checkbox", { name: /i agree/i }));
  await user.click(screen.getByRole("button", { name: /set up my voice id/i }));
}

beforeEach(() => {
  installFakeMicrophone();
  saveToken("token");
  mockGet.mockReset();
  mockAdd.mockReset();
  mockStartOver.mockReset();
});

afterEach(() => {
  removeFakeMicrophone();
});

describe("EnrollPage: where it starts", () => {
  it("starts a new account at the intro, then shows the first phrase", async () => {
    mockGet.mockResolvedValue(status(0));
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "Meet your new key." })).toBeInTheDocument();
    await startFromIntro(user);

    expect(screen.getByRole("heading", { name: "Let’s hear you." })).toBeInTheDocument();
    expect(screen.getByText("“Amber lantern river 0”")).toBeInTheDocument();
    expect(screen.getByText(/sample 1 of 3/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start over" })).not.toBeInTheDocument();
  });

  it("takes someone part-way through straight back to recording", async () => {
    mockGet.mockResolvedValue(status(1));
    renderPage();

    expect(await screen.findByRole("heading", { name: "Let’s hear you." })).toBeInTheDocument();
    expect(screen.getByText(/sample 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start over" })).toBeInTheDocument();
  });

  it("goes straight to the end for an enrolled account", async () => {
    mockGet.mockResolvedValue(status(3));
    renderPage();
    expect(await screen.findByRole("status")).toHaveTextContent("Your Voice ID is ready.");
  });

  it("sends a signed-out user to sign in", async () => {
    mockGet.mockRejectedValue(apiError(401));
    renderPage();

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("explains when it can't load, and tries again", async () => {
    mockGet.mockRejectedValueOnce(apiError(503)).mockResolvedValue(status(0));
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByRole("alert")).toHaveTextContent(MESSAGES.unavailable);
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: "Meet your new key." })).toBeInTheDocument();
  });
});

describe("EnrollPage: recording samples", () => {
  it("saves a sample, moves on to the next phrase and says it was saved", async () => {
    mockGet.mockResolvedValue(status(0));
    mockAdd.mockResolvedValue(status(1, "copper meadow falcon"));
    renderPage();
    const user = userEvent.setup();
    await startFromIntro(user);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(mockAdd).toHaveBeenCalledWith(expect.any(Blob));
    expect(await screen.findByText("“Copper meadow falcon”")).toBeInTheDocument();
    expect(screen.getByText(/sample 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByText("Sample 1 saved.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeEnabled();
  });

  it("finishes when the last sample completes the voiceprint", async () => {
    mockGet.mockResolvedValue(status(2));
    mockAdd.mockResolvedValue(status(3));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 3 of 3/i);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Your Voice ID is ready.");
  });

  it("explains a rejected sample in our own words and lets the user try again", async () => {
    mockGet.mockResolvedValue(status(1));
    const detail = "That recording was too short or too quiet. Please read the whole sentence clearly, close to your microphone.";
    mockAdd.mockRejectedValue(apiError(422, { detail }));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 2 of 3/i);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(ENROLL_MESSAGES.tooShort);
    expect(screen.queryByText(detail)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(/sample 2 of 3/i)).toBeInTheDocument();
  });

  it("treats an account that's already enrolled as done", async () => {
    mockGet.mockResolvedValue(status(2));
    mockAdd.mockRejectedValue(apiError(409));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 3 of 3/i);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Your Voice ID is ready.");
  });

  it("locks the buttons while a sample is being saved", async () => {
    mockGet.mockResolvedValue(status(1));
    mockAdd.mockReturnValue(new Promise(() => {}));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 2 of 3/i);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(screen.getByRole("button", { name: /saving your sample/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /new phrase/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start over" })).toBeDisabled();
  });

  it("gets a new phrase on request", async () => {
    mockGet.mockResolvedValueOnce(status(1)).mockResolvedValue(status(1, "violet harbour pebble"));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 2 of 3/i);

    await user.click(screen.getByRole("button", { name: /new phrase/i }));

    expect(await screen.findByText("“Violet harbour pebble”")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it("starts over from the first sample", async () => {
    mockGet.mockResolvedValue(status(2));
    mockStartOver.mockResolvedValue(status(0, "silver orchard kite"));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 3 of 3/i);

    await user.click(screen.getByRole("button", { name: "Start over" }));

    expect(await screen.findByText("“Silver orchard kite”")).toBeInTheDocument();
    expect(screen.getByText(/sample 1 of 3/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start over" })).not.toBeInTheDocument();
  });

  it("sends a user whose session ended while recording to sign in", async () => {
    mockGet.mockResolvedValue(status(1));
    mockAdd.mockRejectedValue(apiError(401));
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/sample 2 of 3/i);

    await record(user);
    await user.click(screen.getByRole("button", { name: /save sample/i }));

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});
