"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const { readStatus, probeProxy } = require("./status.cjs");

test("cached quotas are remaining percentages; credential fields never reach display state", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "t3-tray-status-"));
  try {
    fs.writeFileSync(
      path.join(home, "accounts.json"),
      JSON.stringify({
        current: "b",
        settings: { proxy_enabled: true, proxy_port: 23456, remote_shared_secret: "DO-NOT-EXPOSE" },
        accounts: {
          a: {
            id: "a",
            name: "Other",
            auth_json: { access_token: "DO-NOT-EXPOSE" },
            cached_quota: null,
          },
          b: {
            id: "b",
            name: "Active",
            refresh_token: "DO-NOT-EXPOSE",
            cached_quota: {
              five_hour_left: 67,
              weekly_left: 95,
              updated_at: new Date().toISOString(),
              plan_type: "plus",
            },
          },
        },
      }),
    );
    const status = readStatus(home);
    assert.equal(status.active, "Active");
    assert.equal(status.accounts[0].quota.fiveHour, "67%");
    assert.equal(status.accounts[0].quota.weekly, "95%");
    assert.equal(status.accounts[0].quota.stale, false);
    assert.equal(status.accounts[1].quota, null);
    assert.equal(JSON.stringify(status).includes("DO-NOT-EXPOSE"), false);
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});
test("missing, partially written, and stale caches are represented accurately", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "t3-tray-status-"));
  try {
    assert.equal(readStatus(home).available, false);
    fs.writeFileSync(path.join(home, "accounts.json"), "{");
    assert.equal(readStatus(home).available, false);
    fs.writeFileSync(
      path.join(home, "accounts.json"),
      JSON.stringify({
        current: "a",
        accounts: {
          a: {
            id: "a",
            name: "Old",
            cached_quota: { five_hour_left: 120, weekly_left: -5, updated_at: "2020-01-01" },
          },
        },
      }),
    );
    const quota = readStatus(home).accounts[0].quota;
    assert.equal(quota.stale, true);
    assert.equal(quota.fiveHour, "100%");
    assert.equal(quota.weekly, "0%");
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});
test("health probe rejects unrelated services and offline ports", async () => {
  let body = { status: "ok" };
  const server = http.createServer((request, response) => {
    assert.equal(request.url, "/health");
    response.end(JSON.stringify(body));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  try {
    assert.equal(await probeProxy(port), null);
    body = { status: "ok", auto_switches: 7 };
    assert.deepEqual(await probeProxy(port), { switches: 7 });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
  assert.equal(await probeProxy(port), null);
});
