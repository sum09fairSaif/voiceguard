import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { logOut } from "../api/auth";
import { isSignedIn } from "../api/session";
import { signInForTest } from "../test/session";
import { networkError } from "../test/apiError";
import { SignedInHeader } from "./SignedInHeader";

vi.mock("../api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/auth")>()),
  logOut: vi.fn(),
}));
const mockLogOut = vi.mocked(logOut);

function SignInStand() {
  const state = useLocation().state as { serverSignOutFailed?: boolean } | null;
  return <p>sign-in screen{state?.serverSignOutFailed ? " (server sign-out failed)" : ""}</p>;
}

function renderHeader() {
  render(
    <MemoryRouter initialEntries={["/verify"]}>
      <Routes>
        <Route path="/verify" element={<SignedInHeader />} />
        <Route path="/signin" element={<SignInStand />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  signInForTest();
  mockLogOut.mockReset();
});

describe("Sign out", () => {
  it("ends the session on the server, forgets the token and goes to sign in", async () => {
    mockLogOut.mockResolvedValue();
    renderHeader();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("sign-in screen")).toBeInTheDocument();
    expect(mockLogOut).toHaveBeenCalledTimes(1);
    expect(isSignedIn()).toBe(false);
  });

  it("still signs out on this device when the server can't be reached", async () => {
    mockLogOut.mockRejectedValue(networkError());
    renderHeader();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    // Signed out here, and sign-in is told the server didn't confirm it.
    expect(await screen.findByText("sign-in screen (server sign-out failed)")).toBeInTheDocument();
    expect(isSignedIn()).toBe(false);
  });

  it("can't be pressed twice while signing out", async () => {
    mockLogOut.mockReturnValue(new Promise(() => {}));
    renderHeader();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    expect(screen.getByRole("button", { name: "Signing out…" })).toBeDisabled();
    expect(mockLogOut).toHaveBeenCalledTimes(1);
  });
});
