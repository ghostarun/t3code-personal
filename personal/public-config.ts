// @effect-diagnostics nodeBuiltinImport:off - Release bootstrap runs before the application runtime.
import * as NodeFS from "node:fs";
import * as NodeUtil from "node:util";
import { loadRepoEnv, resolvePublicConfig } from "../scripts/lib/public-config.ts";

const names = [
  "T3CODE_CLERK_PUBLISHABLE_KEY",
  "T3CODE_CLERK_JWT_TEMPLATE",
  "T3CODE_CLERK_CLI_OAUTH_CLIENT_ID",
  "T3CODE_RELAY_URL",
] as const;

export function personalConnectConfig(
  configured: Readonly<Record<string, string | undefined>>,
  defaults: Readonly<Record<string, string | undefined>>,
): Record<string, string> {
  const explicit = resolvePublicConfig(configured);
  const source = [
    explicit.clerkPublishableKey,
    explicit.clerkJwtTemplate,
    explicit.clerkCliOAuthClientId,
    explicit.relayUrl,
  ].some(Boolean)
    ? configured
    : defaults;
  const config = resolvePublicConfig(source);
  const values = [
    config.clerkPublishableKey,
    config.clerkJwtTemplate,
    config.clerkCliOAuthClientId,
    config.relayUrl,
  ];
  const missing = names.filter((_, index) => !values[index]);
  if (missing.length) throw new Error(`Incomplete T3 Connect configuration: ${missing.join(", ")}`);
  if (!/^pk_(live|test)_/.test(config.clerkPublishableKey!)) {
    throw new Error("T3 Connect requires a Clerk publishable key.");
  }
  const relay = new URL(config.relayUrl!);
  if (relay.protocol !== "https:" || relay.username || relay.password) {
    throw new Error("T3 Connect requires an HTTPS relay URL without credentials.");
  }
  return Object.fromEntries(names.map((name, index) => [name, values[index]!]));
}

if (import.meta.main) {
  const defaults = NodeUtil.parseEnv(
    NodeFS.readFileSync(new URL("../.env.example", import.meta.url), "utf8"),
  );
  process.stdout.write(JSON.stringify(personalConnectConfig(loadRepoEnv(), defaults)) + "\n");
}
