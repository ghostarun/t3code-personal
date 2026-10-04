# Maintaining T3 Code Personal on two Ubuntu PCs

The `personal` branch in [ghostarun/t3code-personal](https://github.com/ghostarun/t3code-personal)
is the source of truth. `upstream` points to `pingdotgg/t3code`. Both PCs install
the same published release; build and maintain it on one PC. Machine credentials,
T3 sessions, and codex-switcher accounts stay local and are never committed.

## Install on either PC

These releases support Ubuntu x86_64. Install codex-switcher separately and sign
in on each PC. Its normal launcher must be `/usr/bin/codex-switcher`; custom
locations can use `T3CODE_SWITCHER_LAUNCHER` and `T3CODE_SWITCHER_BINARY`.
The startup helper needs a systemd user session, Python 3, `xdotool`, and X11
or XWayland. Ubuntu GNOME needs AppIndicator support to display the tray.

```bash
sudo apt install python3 xdotool gnome-shell-extension-appindicator
curl -fL https://github.com/ghostarun/t3code-personal/releases/latest/download/install.py -o /tmp/t3code-install.py
python3 /tmp/t3code-install.py --install --restart
```

The installer verifies the release checksum, extracts the AppImage without FUSE
or sudo, snapshots the live SQLite database using its backup API, and installs a
user launcher and desktop entry. It retains earlier builds and backs up prior
launcher overrides. It uses the existing T3 home. A running instance is replaced
only when `--restart` is requested; the detached worker survives its terminal
closing. Wait for active agent work to finish before restarting.

```bash
~/.local/bin/t3code --status
~/.local/bin/t3code --update --restart
~/.local/bin/t3code --rollback --restart
~/.local/bin/t3code --quit
```

Run the update command on both PCs after publishing. `--version 0.0.4501`
selects a particular release. Backups live in `~/.local/state/t3code-personal/backups`;
rollback changes the executable and does not restore data automatically, because
doing so could discard newer conversations. Restoring a database snapshot requires
T3 to be completely stopped. Codex-switcher remains running when T3 quits.

The close button, File menu, and quit shortcut hide T3 in the background. The tray
can show it again or Force Quit. Without a usable tray, close minimizes the window.
Quota information comes from codex-switcher's cache and shows its freshness;
refresh quotas in codex-switcher when stale.

## Develop and publish

```bash
git clone https://github.com/ghostarun/t3code-personal.git
cd t3code-personal
git switch personal
git remote add upstream https://github.com/pingdotgg/t3code.git
```

Install Vite+ using the upstream README, Node 24, Rust stable, and Ubuntu build
dependencies `build-essential pkg-config libsecret-1-dev imagemagick`.

```bash
vp i --filter @t3tools/desktop... --filter t3... --filter @t3tools/scripts... --filter @t3tools/oxlint-plugin-t3code... --frozen-lockfile
bash personal/check.sh
python3 personal/build.py
```

`personal/release.json` records the official stable tag and custom revision.
Increase `revision` for custom fixes on the same official base. Revisions are
1–99. The stable version encodes `official patch * 100 + revision`: base
`v0.0.45`, revision 1 becomes `0.0.4501`. This keeps stable Electron updates
ordered within the fork. Desktop updates and SSH CLI downloads use the fork's
release repository. Only Linux x64 artifacts are published.

Commit and push to `personal`, then run **Personal Linux Release** under GitHub
Actions. It builds the .deb, AppImage, matching standalone SSH CLI, update metadata,
installer, checksums, and source/base metadata before publishing. Builds restore
package manifest versions after stamping release versions. Build from a clean
checkout when publishing. Imported upstream workflows are disabled on this fork;
keep them disabled when adding new upstream workflows.

## Incorporate official updates

```bash
git switch personal
git pull --ff-only origin personal
python3 personal/sync-upstream.py
```

The script fetches the latest official stable release and merges it into an
`update/v…` branch. Conflicts stay there for review; `personal` remains intact.
Check the tray, background startup, shutdown, and updater integration after the
merge. Run `personal/check.sh`, commit the refreshed release metadata, fast-forward
`personal` to the checked update branch, push, and publish a new custom release.
Pass an explicit stable tag to the script to choose an older official base.

For custom changes on the second PC, pull before editing and commit/push through
the same branch. Do not copy installed binaries or sync live T3/codex-switcher
data folders between PCs.
