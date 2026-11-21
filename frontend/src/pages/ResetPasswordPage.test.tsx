import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MESSAGES } from "../api/errors";
import { confirmPasswordReset, tokenFromHash } from "../api/passwordReset";
import { isSignedIn, startSession } from "../api/session";
import { forgetResetLinkToken, holdResetLinkToken } from "../resetLinkToken";
import { apiError, networkError } from "../test/apiError";
import { ResetPasswordPage } from "./ResetPasswordPage";

vi.mock("../api/passwordReset", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/passwordReset")>()),
  confirmPasswordReset: vi.fn(),
}));
const mockConfirm = vi.mocked(confirmPasswordReset);

const TOKEN = "Abc-123_xyzAbc-123_xyzAbc-123_xyzAbc-123_x";
const NEW_PASSWORD = "lantern orchard pebble";

// Shows the address the page is at, to check the token is tidied away.
function Address() {
  const { pathname, hash } = useLocation();
  return <p data-testid="address">{pathname + hash}</p>;
}

function SignInStandIn() {
  const changed = (useLocation().state as { passwordChanged?: boolean } | null)?.passwordChanged;
  return <p>sign in screen{changed ? " after a change" : ""}</p>;
}

function renderPage(hash = `#token=${TOKEN}`) {
  render(
    <MemoryRouter initialEntries={[`/reset-password${hash}`]}>
      <Routes>
        <Route
          path="/reset-password"
          element={
            <>
              <ResetPasswordPage />
              <Address />
            </>
          }
        />
        <Route path="/signin" element={<SignInStandIn />} />
        <Route path="/forgot-password" element={<p>forgot password screen</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function save(password = NEW_PASSWORD) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("New password"), password);
  await user.click(screen.getByRole("button", { name: /save new password/i }));
  return user;
}

beforeEach(() => {
  mockConfirm.mockReset().mockResolvedValue(undefined);
  sessionStorage.clear();
  forgetResetLinkToken();
});

describe("tokenFromHash", () => {
  it("reads the token after #token=", () => {
    expect(tokenFromHash(`#token=${TOKEN}`)).toBe(TOKEN);
  });

  it.each(["", "#", "#token=", "#other=1"])("finds none in %j", (hash) => {
    expect(tokenFromHash(hash)).toBeNull();
  });
});

describe("ResetPasswordPage", () => {
  it("shows the heading, the new password field and the note", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "A new password." })).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByText("Saving your new password signs your account out on every device")).toBeInTheDocument();
  });

  it("takes the token out of the address once read", () => {
    renderPage();

    expect(screen.getByTestId("address")).toHaveTextContent(/^\/reset-password$/);
  });

  it("saves the new password with the link's token, then goes to sign in", async () => {
    startSession({ id: "u1", full_name: "Sam Doe", email: "sam@example.com" });
    renderPage();
    await save();

    expect(mockConfirm).toHaveBeenCalledWith(TOKEN, NEW_PASSWORD);
    expect(await screen.findByText("sign in screen after a change")).toBeInTheDocument();
    // The reset ended every session, so this browser's is forgotten too.
    expect(isSignedIn()).toBe(false);
  });

  it("shows how strong the password looks while typing", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("New password"), "short");

    expect(screen.getByText(/password strength/i)).toBeInTheDocument();
  });

  it("checks the length before sending", async () => {
    renderPage();
    await save("too-short");

    expect(screen.getByText("Use at least 15 characters.")).toBeInTheDocument();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it("says why the server refused the password, and keeps the form", async () => {
    mockConfirm.mockRejectedValue(
      apiError(422, { detail: [{ type: "password_common", loc: ["body", "password"], msg: "" }] }),
    );
    renderPage();
    await save();

    expect(await screen.findByText(/too common or has appeared in a data breach/)).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toBeEnabled();
  });

  it("offers a new link when this one has expired or been used", async () => {
    mockConfirm.mockRejectedValue(apiError(400, { detail: "expired" }));
    renderPage();
    const user = await save();

    expect(await screen.findByRole("alert")).toHaveTextContent("This link can’t be used");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Ask for a new link" }));
    expect(screen.getByText("forgot password screen")).toBeInTheDocument();
  });

  it("offers a new link straight away when the address has no token", () => {
    renderPage("");

    expect(screen.getByRole("alert")).toHaveTextContent("This link can’t be used");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it.each([
    ["server is unavailable", apiError(503), MESSAGES.unavailable],
    ["server can't be reached", networkError(), MESSAGES.network],
  ])("says so when the %s, and the link can be tried again", async (_, error, message) => {
    mockConfirm.mockRejectedValueOnce(error);
    renderPage();
    const user = await save();

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    await user.click(screen.getByRole("button", { name: /save new password/i }));
    expect(mockConfirm).toHaveBeenLastCalledWith(TOKEN, NEW_PASSWORD);
  });

  it("locks the form while saving", async () => {
    mockConfirm.mockReturnValue(new Promise(() => {}));
    renderPage();
    await save();

    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
    expect(screen.getByLabelText("New password")).toBeDisabled();
  });

  it("uses the token taken out of the address before the app started", async () => {
    holdResetLinkToken(
      { pathname: "/reset-password", search: "", hash: `#token=${TOKEN}` } as Location,
      { state: null, replaceState: () => {} } as unknown as History,
    );
    renderPage("");
    await save();

    expect(mockConfirm).toHaveBeenCalledWith(TOKEN, NEW_PASSWORD);
  });

  it("forgets this browser's session after a reset even if the person has left the page", async () => {
    startSession({ id: "u1", full_name: "Sam Doe", email: "sam@example.com" });
    let finish: () => void = () => {};
    mockConfirm.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    renderPage();
    const user = await save();
    await user.click(screen.getByRole("link", { name: "Back to sign in" }));

    await act(async () => finish());

    expect(isSignedIn()).toBe(false);
  });

  it("suggests signing in when the link is refused on saving, in case an earlier save went through", async () => {
    mockConfirm.mockRejectedValue(apiError(400, { detail: "used" }));
    renderPage();
    await save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "If you’ve already set a new password with this link, sign in with it.",
    );
    expect(screen.getByRole("link", { name: "sign in" })).toHaveAttribute("href", "/signin");
  });

  it("doesn't suggest signing in when the link never had a token", () => {
    renderPage("");

    expect(screen.queryByText(/already set a new password/)).not.toBeInTheDocument();
  });
});
