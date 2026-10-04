#!/usr/bin/env python3
"""Build the same Linux release for both PCs, using the official packagers."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from install import sha256

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ['apps/server/package.json', 'apps/desktop/package.json',
             'apps/web/package.json', 'packages/contracts/package.json']


def release_version(metadata):
    major, minor, patch = map(int, metadata['upstreamTag'].removeprefix('v').split('.'))
    revision = metadata['revision']
    if not isinstance(revision, int) or not 1 <= revision <= 99:
        raise ValueError('revision must be between 1 and 99')
    # Stable semver lets Electron's existing stable updater accept custom builds.
    return f'{major}.{minor}.{patch * 100 + revision}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='release-personal')
    parser.add_argument('--version-only', action='store_true')
    args = parser.parse_args()
    metadata = json.loads((ROOT / 'personal/release.json').read_text())
    version = release_version(metadata)
    if args.version_only:
        print(version)
        return
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise SystemExit('Commit or stash changes before building a release.')
    output = (ROOT / args.output).resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f'Output directory must be empty: {output}')
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, T3CODE_DESKTOP_UPDATE_REPOSITORY=metadata['repository'])
    originals = {ROOT / name: (ROOT / name).read_bytes() for name in MANIFESTS}

    def run(*command, extra=None):
        subprocess.run(command, cwd=ROOT, env=environment | (extra or {}), check=True)

    try:
        run('node', 'scripts/update-release-package-versions.ts', version)
        run('node', 'scripts/build-desktop-artifact.ts', '--platform', 'linux',
            '--target', 'AppImage', '--arch', 'x64', '--build-version', version,
            '--output-dir', str(output), '--verbose')
        # Node 26 is needed only by SEA; the normal desktop build uses Node 24.
        run('vp', 'env', 'exec', '--node', '26.8.2', 'node',
            'apps/server/scripts/cli.ts', 'build-exe', '--target', 'linux-x64', '--verbose')
        with tempfile.TemporaryDirectory(prefix='t3-personal-monitor-') as temporary:
            monitor = Path(temporary)
            shutil.copy2(ROOT / 'native/resource-monitor/target/x86_64-unknown-linux-gnu/release/t3-resource-monitor',
                         monitor / 't3-resource-monitor')
            run('node', 'scripts/build-cli-archive.ts', '--platform', 'linux', '--arch',
                'x64', '--version', version, '--output-dir', str(output),
                '--resource-monitor-dir', str(monitor))
    finally:
        for file, original in originals.items():
            file.write_bytes(original)
    metadata |= {'version': version, 'sourceCommit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    (output / 'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    shutil.copy2(ROOT / 'personal/install.py', output / 'install.py')
    (output / 'builder-debug.yml').unlink(missing_ok=True)
    files = sorted(p for p in output.iterdir() if p.is_file() and not p.name.endswith('.blockmap'))
    (output / 'SHA256SUMS').write_text(''.join(
        f'{sha256(file)}  {file.name}\n'
        for file in files))
    print(f'Release {version} ready in {output}')


if __name__ == '__main__':
    main()
