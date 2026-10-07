import { describe, expect, it } from "vite-plus/test";
import { personalConnectConfig } from "./public-config.ts";

const defaults = {
  T3CODE_CLERK_PUBLISHABLE_KEY: "pk_live_fixture",
  T3CODE_CLERK_JWT_TEMPLATE: "t3-relay",
  T3CODE_CLERK_CLI_OAUTH_CLIENT_ID: "public-client-id",
  T3CODE_RELAY_URL: "https://relay.example.test",
};

describe("personal release Connect configuration", () => {
  it("enables Connect in a clean clone using only the upstream public identifiers", () => {
    expect(personalConnectConfig({ CLERK_SECRET_KEY: "do-not-export" }, defaults)).toEqual(
      defaults,
    );
  });
  it("preserves a complete custom deployment supplied through framework aliases", () => {
    expect(
      personalConnectConfig(
        {
          VITE_CLERK_PUBLISHABLE_KEY: "pk_test_other",
          VITE_CLERK_JWT_TEMPLATE: "custom-jwt",
          VITE_CLERK_CLI_OAUTH_CLIENT_ID: "custom-client",
          VITE_T3CODE_RELAY_URL: "https://custom.example.test",
        },
        defaults,
      ),
    ).toEqual({
      T3CODE_CLERK_PUBLISHABLE_KEY: "pk_test_other",
      T3CODE_CLERK_JWT_TEMPLATE: "custom-jwt",
      T3CODE_CLERK_CLI_OAUTH_CLIENT_ID: "custom-client",
      T3CODE_RELAY_URL: "https://custom.example.test",
    });
  });
  it("rejects partial overrides instead of mixing accounts and relay deployments", () => {
    expect(() =>
      personalConnectConfig({ T3CODE_RELAY_URL: "https://custom.example.test" }, defaults),
    ).toThrow("Incomplete T3 Connect configuration");
  });
  it("fails rather than publishing an unconfigured or insecure release", () => {
    expect(() => personalConnectConfig({}, {})).toThrow("Incomplete T3 Connect configuration");
    expect(() =>
      personalConnectConfig({ ...defaults, T3CODE_RELAY_URL: "http://relay.example.test" }, {}),
    ).toThrow("HTTPS relay URL");
  });
});
