import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearToken, saveToken } from "./api/session";
import App from "./App";

vi.mock("./api/enroll", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/enroll")>()),
  getEnrollment: vi.fn().mockResolvedValue({
    status: "not_started",
    samples_accepted: 0,
    samples_required: 3,
    prompt: "a fresh six word phrase here",
  }),
}));

afterEach(() => {
  clearToken();
  window.history.pushState({}, "", "/");
});

describe("App routes", () => {
  it("opens the welcome screen at the root address", () => {
    window.history.pushState({}, "", "/");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Be yourself. Stay protected." })).toBeInTheDocument();
  });

  it("sends unknown addresses to the welcome screen", () => {
    window.history.pushState({}, "", "/no-such-page");
    render(<App />);
    expect(window.location.pathname).toBe("/");
    expect(screen.getByRole("heading", { name: "Be yourself. Stay protected." })).toBeInTheDocument();
  });

  it("takes new visitors from the welcome screen to signup", async () => {
    window.history.pushState({}, "", "/");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Get started" }));
    expect(screen.getByRole("heading", { name: "Your security starts here." })).toBeInTheDocument();
  });

  it("takes returning visitors from the welcome screen to sign in", async () => {
    window.history.pushState({}, "", "/");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "I already have an account" }));
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });

  it("skips the welcome screen for someone already signed in", async () => {
    saveToken("a-token");
    window.history.pushState({}, "", "/");
    render(<App />);
    expect(window.location.pathname).toBe("/enroll");
    expect(screen.queryByRole("heading", { name: "Be yourself. Stay protected." })).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Meet your new key." })).toBeInTheDocument();
  });

  it("sends someone already signed in from an unknown address to enrollment", async () => {
    saveToken("a-token");
    window.history.pushState({}, "", "/no-such-page");
    render(<App />);
    expect(window.location.pathname).toBe("/enroll");
    expect(await screen.findByRole("heading", { name: "Meet your new key." })).toBeInTheDocument();
  });

  it("still serves signup at /signup", () => {
    window.history.pushState({}, "", "/signup");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Your security starts here." })).toBeInTheDocument();
  });

  it("needs a session for the enrollment page", () => {
    window.history.pushState({}, "", "/enroll");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });
});
