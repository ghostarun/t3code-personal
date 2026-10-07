#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
node --test apps/desktop/src/personal/*.test.cjs
python3 apps/desktop/resources/personal/codex_switcher_test.py
python3 -m unittest discover -s personal -p '*_test.py'
vp test run apps/desktop/src/window/DesktopWindow.test.ts apps/desktop/src/window/DesktopApplicationMenu.test.ts apps/desktop/src/app/DesktopLifecycle.test.ts packages/shared/src/cliRelease.test.ts
vp run --filter @t3tools/desktop typecheck
vp test run personal/public-config.test.ts scripts/lib/public-config.test.ts
vp test run apps/web/src/components/Sidebar.logic.test.ts apps/web/src/components/Sidebar.drag.test.ts apps/web/src/components/Sidebar.motion.test.ts apps/web/src/components/Sidebar.pointer.test.ts
vp run --filter @t3tools/web typecheck
vp lint apps/desktop/src/app/DesktopApp.ts apps/desktop/src/app/DesktopLifecycle.ts apps/desktop/src/main.ts apps/desktop/src/window/DesktopApplicationMenu.ts apps/desktop/src/window/DesktopWindow.ts apps/desktop/src/personal scripts/build-desktop-artifact.ts packages/shared/src/cliRelease.ts packages/shared/src/cliRelease.test.ts
