"use strict";
const { app, Tray, Menu, nativeImage, autoUpdater } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { execFile } = require("node:child_process");
const { readStatus, probeProxy } = require("./status.cjs");
let mainWindow,
  tray,
  interval,
  quitting = false,
  refreshing = false,
  initialized = false;
const switcherHome = process.env.T3CODE_SWITCHER_HOME || path.join(os.homedir(), ".codex-switcher");
let t3Home = process.env.T3CODE_HOME || path.join(os.homedir(), ".t3");
let statusFile = path.join(t3Home, "background-status.json");
let switcherHelper;
let switcherStartupError = null;

function ensureSwitcher() {
  return new Promise((resolve) =>
    execFile("/usr/bin/python3", [switcherHelper, "--quiet"], { timeout: 25000 }, (error) => {
      switcherStartupError = error ? "auto-start failed; check switcher service" : null;
      if (error) console.error("[background-tray] Codex-switcher auto-start failed:", error.code);
      resolve();
    }),
  );
}

function allowQuit() {
  quitting = true;
}
function reveal() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}
function conceal() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  // Preserve a way back even if this desktop cannot create a system tray.
  if (tray) mainWindow.hide();
  else mainWindow.minimize();
  void refresh();
}
function forceQuit() {
  allowQuit();
  // T3's existing lifecycle shuts down its backend and providers first.
  app.quit();
}
function attachMainWindow(window) {
  if (!initialized) return;
  mainWindow = window;
  window.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      conceal();
    }
  });
  for (const event of ["show", "hide", "minimize", "restore"])
    window.on(event, () => void refresh());
}
function switcherRunning() {
  return new Promise((resolve) =>
    execFile("pgrep", ["-x", "codex-switcher"], { timeout: 1500 }, (error) => resolve(!error)),
  );
}
function info(label) {
  return { label, enabled: false };
}
async function refresh() {
  if (refreshing || quitting || !tray) return;
  refreshing = true;
  try {
    const status = readStatus(switcherHome);
    const [running, health] = await Promise.all([
      switcherRunning(),
      status.proxyEnabled ? probeProxy(status.port) : Promise.resolve(null),
    ]);
    if (quitting || tray.isDestroyed()) return;
    const hidden = !!mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible();
    const proxy = !status.proxyEnabled
      ? "disabled"
      : health
        ? `online · port ${status.port}`
        : `offline · port ${status.port}`;
    const active = status.accounts.find((account) => account.current);
    const quota = active?.quota;
    const menu = [
      { label: "Show T3 Code", click: reveal },
      { label: "Hide T3 Code", click: conceal },
      info(`T3 Code: ${hidden ? "running in background" : "running"}`),
      { type: "separator" },
      info(`Codex-switcher: ${running ? "running" : "stopped"}`),
      info(`Proxy: ${proxy}`),
      info(`Active switcher account: ${status.active}`),
    ];
    if (status.mode !== "off") menu.push(info(`Switcher mode: ${status.mode}`));
    if (switcherStartupError) menu.push(info(`Codex-switcher: ${switcherStartupError}`));
    if (health) menu.push(info(`Automatic switches: ${health.switches}`));
    if (!status.available) menu.push(info("Account status unavailable"));
    if (status.accounts.length)
      menu.push({
        label: "Account quotas (cached)",
        submenu: status.accounts.map((account) => ({
          label: `${account.current ? "● " : ""}${account.name}${account.problem ? ` · ${account.problem}` : ""}`,
          submenu: account.quota
            ? [
                info(`Plan: ${account.quota.plan}`),
                info(`5-hour remaining: ${account.quota.fiveHour}`),
                info(account.quota.fiveHourReset),
                info(`Weekly remaining: ${account.quota.weekly}`),
                info(account.quota.weeklyReset),
                info(`${account.quota.updated}${account.quota.stale ? " · stale" : ""}`),
              ]
            : [info("Quota unavailable — refresh in codex-switcher")],
        })),
      });
    if (status.usage)
      menu.push(
        info(`Proxy tokens: ${status.usage.tokens?.toLocaleString() ?? "unknown"}`),
        info(`Model requests: ${status.usage.requests?.toLocaleString() ?? "unknown"}`),
        info(`Usage totals since ${status.usage.since}`),
      );
    menu.push(
      {
        label: "Open codex-switcher",
        click: () =>
          execFile(
            process.env.T3CODE_SWITCHER_LAUNCHER || "/usr/bin/codex-switcher",
            [],
            (error) => {
              if (error)
                console.error("[background-tray] Unable to open codex-switcher:", error.code);
            },
          ),
      },
      { label: "Refresh tray status", click: () => void refresh() },
      { type: "separator" },
      { label: "Force Quit T3 Code", click: forceQuit },
    );
    tray.setContextMenu(Menu.buildFromTemplate(menu));
    tray.setToolTip(
      `T3 Code · ${hidden ? "background" : "running"}\nCodex-switcher: ${running ? "running" : "stopped"} · proxy ${proxy}\n${status.active}${quota ? `\n5h ${quota.fiveHour} · weekly ${quota.weekly} remaining${quota.stale ? " (stale)" : ""}` : ""}`,
    );
    fs.mkdirSync(t3Home, { recursive: true });
    const temporary = `${statusFile}.${process.pid}.tmp`;
    fs.writeFileSync(
      temporary,
      JSON.stringify(
        {
          pid: process.pid,
          updated: new Date().toISOString(),
          hidden,
          switcherRunning: running,
          proxy,
          ...status,
        },
        null,
        2,
      ),
      { mode: 0o600 },
    );
    fs.renameSync(temporary, statusFile);
  } catch (error) {
    console.error("[background-tray] Status refresh failed:", error.code || error.message);
  } finally {
    refreshing = false;
  }
}
async function initialize(options) {
  if (options.platform !== "linux" || initialized) return;
  initialized = true;
  for (const signal of ["SIGINT", "SIGTERM"]) process.prependListener(signal, allowQuit);
  autoUpdater.on("before-quit-for-update", allowQuit);
  app.on("will-quit", () => {
    clearInterval(interval);
    if (tray && !tray.isDestroyed()) tray.destroy();
    try {
      if (JSON.parse(fs.readFileSync(statusFile, "utf8")).pid === process.pid)
        fs.unlinkSync(statusFile);
    } catch {}
  });

  t3Home = options.baseDir;
  statusFile = path.join(t3Home, "background-status.json");
  switcherHelper = options.switcherHelper;
  void ensureSwitcher();
  try {
    const icon = options.iconPath
      ? nativeImage.createFromPath(options.iconPath).resize({ width: 32, height: 32 })
      : nativeImage.createEmpty();
    tray = new Tray(icon);
    tray.setTitle("T3");
    tray.on("click", reveal);
    tray.on("double-click", reveal);
    void refresh();
    interval = setInterval(() => void refresh(), 10000);
    interval.unref();
  } catch (error) {
    console.error("[background-tray] Tray unavailable; closing will minimize:", error.message);
  }
}
module.exports = { initialize, attachMainWindow, conceal, allowQuit, forceQuit };
