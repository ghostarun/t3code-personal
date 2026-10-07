// @effect-diagnostics nodeBuiltinImport:off - Artifact verification reads immutable release files.
import * as NodeFS from "node:fs";
import * as NodePath from "node:path";
import { extractFile, listPackage } from "@electron/asar";

const archive = process.argv[2];
const metadataPath = process.argv[3];
if (!archive || !metadataPath)
  throw new Error("Usage: verify-personal-connect.ts app.asar release.json");
const metadata = JSON.parse(NodeFS.readFileSync(metadataPath, "utf8"));
const config: Record<string, string> = metadata.connectPublicConfig;
if (
  !config ||
  Object.values(config).length !== 4 ||
  Object.values(config).some((value) => !value)
) {
  throw new Error("Release metadata must include all four Connect public identifiers.");
}
const files = listPackage(archive, { isPack: false }).map((file) => file.replace(/^\//, ""));
const read = (file: string) => extractFile(archive, file).toString("utf8");
const desktop = read("apps/desktop/dist-electron/main.cjs");
if (!desktop.includes(JSON.stringify(config.T3CODE_CLERK_PUBLISHABLE_KEY))) {
  throw new Error("Desktop Clerk configuration was omitted from the artifact.");
}
const web = files
  .filter((file) => file.includes("/client/assets/") && file.endsWith(".js"))
  .map(read)
  .join("\n");
const server = read("apps/server/dist/bin.mjs");
for (const [name, value] of Object.entries(config)) {
  if (!web.includes(value)) throw new Error(`Web client is missing ${name}.`);
  if (name !== "T3CODE_CLERK_JWT_TEMPLATE" && !server.includes(value)) {
    throw new Error(`Bundled server is missing ${name}.`);
  }
}
process.stdout.write(`Verified T3 Connect configuration in ${NodePath.basename(archive)}\n`);
