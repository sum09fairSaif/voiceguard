import { afterEach, describe, expect, it, vi } from "vitest";

// Analytics on, so who it's told the person is can be checked.
vi.mock("../posthog", () => ({
  default: { identify: vi.fn(), reset: vi.fn() },
  isPostHogConfigured: true,
}));

// The test setup has already loaded ./session with the real analytics, so
// load it again with the stand-in above.
vi.resetModules();
const { default: posthog } = await import("../posthog");
const { clearToken, saveToken } = await import("./session");

const USER = { id: "64b000000000000000000001", full_name: "Sam Lee", email: "sam@example.com" };

afterEach(() => {
  clearToken();
  vi.mocked(posthog.identify).mockClear();
  vi.mocked(posthog.reset).mockClear();
});

describe("who analytics knows a signed-in person as (#170)", () => {
  it("is the server's keyed stand-in, never the account id", () => {
    saveToken("a-token", { ...USER, analytics_id: "9f2c4e1ab37d6f05" });

    expect(posthog.identify).toHaveBeenCalledWith("9f2c4e1ab37d6f05");
    expect(posthog.identify).not.toHaveBeenCalledWith(USER.id);
  });

  it("is nobody when the server sent no stand-in", () => {
    saveToken("a-token", USER);

    expect(posthog.identify).not.toHaveBeenCalled();
  });

  it("is forgotten on sign-out", () => {
    saveToken("a-token", { ...USER, analytics_id: "9f2c4e1ab37d6f05" });
    clearToken();

    expect(posthog.reset).toHaveBeenCalled();
  });
});
