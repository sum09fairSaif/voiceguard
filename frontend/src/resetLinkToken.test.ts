import { afterEach, describe, expect, it, vi } from "vitest";
import mainSource from "./main.tsx?raw";
import { stripUrlFragments } from "./posthog";
import { forgetResetLinkToken, heldResetLinkToken, holdResetLinkToken } from "./resetLinkToken";

const TOKEN = "Abc-123_xyzAbc-123_xyzAbc-123_xyzAbc-123_x";

function at(address: string) {
  const url = new URL(address, "https://app.example");
  const location = { pathname: url.pathname, search: url.search, hash: url.hash } as Location;
  const history = { state: { key: "k" }, replaceState: vi.fn() } as unknown as History;
  return { location, history };
}

afterEach(() => {
  forgetResetLinkToken();
});

describe("the reset link's token (#109)", () => {
  it("is taken out of the address and held for the reset page", () => {
    const { location, history } = at(`/reset-password?x=1#token=${TOKEN}`);

    holdResetLinkToken(location, history);

    expect(heldResetLinkToken()).toBe(TOKEN);
    expect(history.replaceState).toHaveBeenCalledWith({ key: "k" }, "", "/reset-password?x=1");
  });

  it("is left alone on any other page", () => {
    const { location, history } = at(`/signin#token=${TOKEN}`);

    holdResetLinkToken(location, history);

    expect(heldResetLinkToken()).toBeNull();
    expect(history.replaceState).not.toHaveBeenCalled();
  });

  it("leaves the address alone when there's nothing after #", () => {
    const { location, history } = at("/reset-password");

    holdResetLinkToken(location, history);

    expect(history.replaceState).not.toHaveBeenCalled();
  });

  it("is taken before analytics can start: main.tsx imports it first", () => {
    const imports = mainSource.split("\n").filter((line) => line.startsWith("import"));

    expect(imports[0]).toContain("./resetLinkToken");
    expect(mainSource.indexOf("./resetLinkToken")).toBeLessThan(mainSource.indexOf("./posthog"));
  });
});

describe("analytics never records what follows # in an address", () => {
  it("drops it from the addresses PostHog records", () => {
    const event = {
      uuid: "1",
      event: "$pageview",
      properties: {
        $current_url: `https://app.example/reset-password#token=${TOKEN}`,
        $referrer: `https://app.example/x#token=${TOKEN}`,
        other: "#kept",
      },
      $set: { $current_url: `https://app.example/a#token=${TOKEN}` },
      $set_once: { $initial_current_url: `https://app.example/reset-password#token=${TOKEN}` },
    };

    const sent = stripUrlFragments(event as never);

    expect(JSON.stringify(sent)).not.toContain(TOKEN);
    expect(sent?.properties.$current_url).toBe("https://app.example/reset-password");
    expect(sent?.properties.other).toBe("#kept");
  });

  it("passes a dropped event through", () => {
    expect(stripUrlFragments(null)).toBeNull();
  });
});
