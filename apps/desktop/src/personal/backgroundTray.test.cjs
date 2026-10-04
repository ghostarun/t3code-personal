"use strict";
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

async function fixture(t, trayAvailable = true) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "t3-tray-test-"));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const app = new EventEmitter();
  const updater = new EventEmitter();
  const processStub = Object.assign(new EventEmitter(), { env: {}, pid: process.pid });
  class Window extends EventEmitter {
    visible = true;
    minimized = false;
    destroyed = false;
    isDestroyed() {
      return this.destroyed;
    }
    isVisible() {
      return this.visible;
    }
    isMinimized() {
      return this.minimized;
    }
    hide() {
      this.visible = false;
    }
    minimize() {
      this.minimized = true;
    }
    show() {
      this.visible = true;
    }
    restore() {
      this.minimized = false;
    }
    focus() {}
    close() {
      let cancelled = false;
      this.emit("close", {
        preventDefault() {
          cancelled = true;
        },
      });
      if (!cancelled) this.destroyed = true;
    }
  }
  const window = new Window();
  let tray;
  class Tray extends EventEmitter {
    constructor() {
      super();
      if (!trayAvailable) throw new Error("no tray");
      tray = this;
    }
    isDestroyed() {
      return false;
    }
    setContextMenu(menu) {
      this.menu = menu;
    }
    setTitle() {}
    setToolTip() {}
    destroy() {}
  }
  let quits = 0;
  app.quit = () => {
    quits++;
    window.close();
    app.emit("will-quit");
  };
  const electron = {
    app,
    Tray,
    Menu: { buildFromTemplate: (menu) => menu },
    autoUpdater: updater,
    nativeImage: { createEmpty: () => ({}) },
  };
  const dependencies = {
    electron,
    "./status.cjs": {
      readStatus: () => ({ active: "Account", accounts: [], mode: "off", available: true }),
      probeProxy: async () => null,
    },
    "node:child_process": { execFile: (_file, _args, options, callback) => callback?.(null) },
  };
  const context = {
    module: { exports: {} },
    process: processStub,
    console,
    setInterval: () => ({ unref() {} }),
    clearInterval() {},
    require: (id) => dependencies[id] || require(id),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "backgroundTray.cjs"), "utf8"), context);
  const adapter = context.module.exports;
  await adapter.initialize({ platform: "linux", baseDir: home, switcherHelper: "/fixture.py" });
  adapter.attachMainWindow(window);
  await new Promise((resolve) => setImmediate(resolve));
  return { adapter, window, tray, updater, process: processStub, quits: () => quits };
}

test("close keeps the window alive; tray restores it and Force Quit permits shutdown", async (t) => {
  const f = await fixture(t);
  f.window.close();
  assert.equal(f.window.destroyed, false);
  assert.equal(f.window.visible, false);
  f.tray.menu.find((item) => item.label === "Show T3 Code").click();
  assert.equal(f.window.visible, true);
  f.tray.menu.find((item) => item.label === "Force Quit T3 Code").click();
  assert.equal(f.quits(), 1);
  assert.equal(f.window.destroyed, true);
});

test("unavailable tray leaves a minimized window that can be restored", async (t) => {
  const f = await fixture(t, false);
  f.window.close();
  assert.equal(f.window.destroyed, false);
  assert.equal(f.window.minimized, true);
  assert.equal(f.window.visible, true);
});

test("terminal signals and updater shutdown release the close interception", async (t) => {
  for (const action of ["SIGTERM", "SIGINT", "update"]) {
    const f = await fixture(t);
    if (action === "update") f.updater.emit("before-quit-for-update");
    else f.process.emit(action);
    f.window.close();
    assert.equal(f.window.destroyed, true);
  }
});
