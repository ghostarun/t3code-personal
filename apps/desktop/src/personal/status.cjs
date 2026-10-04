"use strict";
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");

function readJson(file) {
  try {
    if (fs.statSync(file).size > 2 * 1024 * 1024) return null;
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}
function percent(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(Math.max(0, Math.min(100, value)))}%`
    : "unknown";
}
function age(value, now = Date.now()) {
  const date = Date.parse(value);
  if (!Number.isFinite(date)) return "update time unknown";
  const minutes = Math.max(0, Math.floor((now - date) / 60000));
  return minutes < 1 ? "updated just now" : `updated ${minutes}m ago`;
}
function reset(value) {
  if (!Number.isFinite(value)) return "reset unknown";
  return `resets ${new Date(value * 1000).toLocaleString()}`;
}
// Project only display fields. Authentication data never leaves this function.
function readStatus(directory) {
  const store = readJson(path.join(directory, "accounts.json"));
  const usage = readJson(path.join(directory, "proxy-usage.json"));
  const settings = store?.settings || {};
  const accounts = Object.values(store?.accounts || {})
    .map((account) => ({
      name: String(account.name || "Unnamed account")
        .replace(/[\r\n\t]/g, " ")
        .slice(0, 100),
      current: account.id === store.current,
      problem: account.is_banned
        ? "banned"
        : account.is_token_invalid
          ? "sign-in expired"
          : account.is_logged_out
            ? "signed out"
            : null,
      quota: account.cached_quota
        ? {
            fiveHour: percent(account.cached_quota.five_hour_left),
            weekly: percent(account.cached_quota.weekly_left),
            fiveHourReset: reset(account.cached_quota.five_hour_reset_at),
            weeklyReset: reset(account.cached_quota.weekly_reset_at),
            updated: age(account.cached_quota.updated_at),
            stale:
              !Number.isFinite(Date.parse(account.cached_quota.updated_at)) ||
              Date.now() - Date.parse(account.cached_quota.updated_at) > 15 * 60000,
            plan: String(account.cached_quota.plan_type || "unknown"),
          }
        : null,
    }))
    .sort((a, b) => Number(b.current) - Number(a.current) || a.name.localeCompare(b.name));
  return {
    available: !!store,
    accounts,
    active: accounts.find((account) => account.current)?.name || "No active account",
    proxyEnabled: settings.proxy_enabled === true,
    port:
      Number.isInteger(settings.proxy_port) &&
      settings.proxy_port > 0 &&
      settings.proxy_port <= 65535
        ? settings.proxy_port
        : 18080,
    mode: ["off", "server", "client"].includes(settings.remote_mode) ? settings.remote_mode : "off",
    usage: usage
      ? {
          tokens: Number.isFinite(usage.total_tokens) ? usage.total_tokens : null,
          requests: Number.isFinite(usage.total_requests) ? usage.total_requests : null,
          since: Number.isFinite(Date.parse(usage.since))
            ? new Date(usage.since).toLocaleString()
            : "unknown",
        }
      : null,
  };
}
function probeProxy(port) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    const request = http.get(
      { hostname: "127.0.0.1", port, path: "/health", timeout: 1500 },
      (response) => {
        let body = "";
        response.on("data", (chunk) => {
          body += chunk;
          if (body.length > 8192) {
            finish(null);
            request.destroy();
          }
        });
        response.on("error", () => finish(null));
        response.on("end", () => {
          try {
            const data = JSON.parse(body);
            finish(
              response.statusCode === 200 &&
                data.status === "ok" &&
                Number.isFinite(data.auto_switches)
                ? { switches: data.auto_switches }
                : null,
            );
          } catch {
            finish(null);
          }
        });
      },
    );
    request.on("timeout", () => {
      finish(null);
      request.destroy();
    });
    request.on("error", () => finish(null));
  });
}
module.exports = { readStatus, probeProxy, percent, age };
