import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";

afterEach(() => {
  window.history.pushState({}, "", "/");
});

describe("App routes", () => {
  it("opens sign in at the root address", () => {
    window.history.pushState({}, "", "/");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });

  it("sends unknown addresses to sign in", () => {
    window.history.pushState({}, "", "/no-such-page");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
  });

  it("still serves signup at /signup", () => {
    window.history.pushState({}, "", "/signup");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Your security starts here." })).toBeInTheDocument();
  });
});
