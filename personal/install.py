#!/usr/bin/env python3
"""Install/update T3 Code Personal without sudo; retain the previous build."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

REPOSITORY = 'ghostarun/t3code-personal'
HOME = Path.home()
ROOT = HOME / '.local/opt/t3code-personal'
STATE = HOME / '.local/state/t3code-personal'
BIN = HOME / '.local/bin'
T3_HOME = Path(os.environ.get('T3CODE_HOME', str(HOME / '.t3'))).expanduser().resolve()
SCRIPT = HOME / '.local/share/t3code-personal/install.py'


def download(url, target):
    request = urllib.request.Request(url, headers={'User-Agent': 't3code-personal'})
    with urllib.request.urlopen(request, timeout=90) as response, target.open('wb') as output:
        shutil.copyfileobj(response, output)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as data:
        for chunk in iter(lambda: data.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def snapshot(version):
    destination = STATE / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + version + '-' + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True, mode=0o700)
    # sqlite backup is consistent while the current T3 instance is running.
    for source in (T3_HOME / 'userdata').glob('*.sqlite'):
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as live:
            with sqlite3.connect(destination / source.name) as backup:
                live.backup(backup)
        (destination / source.name).chmod(0o600)
    for name in ['settings.json', 'desktop-settings.json']:
        source = T3_HOME / name
        if source.is_file():
            shutil.copy2(source, destination / name)
            (destination / name).chmod(0o600)
    print(f'Data snapshot: {destination}')


def current_version():
    return (ROOT / 'current').resolve().name if (ROOT / 'current').exists() else None


def activate(version):
    target = ROOT / version / 'squashfs-root/AppRun'
    if not target.is_file():
        raise RuntimeError(f'Installed build is missing: {version}')
    previous = current_version()
    if previous == version:
        return
    snapshot(version)
    link = ROOT / 'current.new'
    link.unlink(missing_ok=True)
    link.symlink_to(ROOT / version)
    link.replace(ROOT / 'current')
    write_json(STATE / 'versions.json', {'current': version, 'previous': previous})


def install(version=None):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('This release requires Ubuntu/Linux x86_64.')
    if version is None:
        with tempfile.TemporaryDirectory(prefix='t3-release-') as temporary:
            release = Path(temporary) / 'latest.json'
            download(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', release)
            version = read_json(release)['tag_name'].removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('Version must be MAJOR.MINOR.PATCH.')
    destination = ROOT / version
    if not (destination / 'squashfs-root/AppRun').is_file():
        with tempfile.TemporaryDirectory(prefix='download-', dir=ROOT) as temporary:
            stage = Path(temporary)
            base = f'https://github.com/{REPOSITORY}/releases/download/v{version}'
            download(base + '/SHA256SUMS', stage / 'SHA256SUMS')
            archive = stage / f'T3-Code-{version}-x86_64.AppImage'
            checksums = dict((line.split('  ', 1)[1], line.split('  ', 1)[0])
                             for line in (stage / 'SHA256SUMS').read_text().splitlines())
            download(base + '/' + archive.name, archive)
            actual = sha256(archive)
            if actual != checksums.get(archive.name):
                raise RuntimeError('AppImage checksum verification failed.')
            archive.chmod(0o755)
            subprocess.run([str(archive), '--appimage-extract'], cwd=stage, check=True,
                           stdout=subprocess.DEVNULL)
            if not (stage / 'squashfs-root/AppRun').is_file():
                raise RuntimeError('AppImage extraction is incomplete.')
            write_json(stage / 'installed.json', {'version': version, 'sha256': actual})
            stage.rename(destination)
    activate(version)
    BIN.mkdir(parents=True, exist_ok=True)
    SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != SCRIPT.resolve():
        shutil.copy2(__file__, SCRIPT)
    SCRIPT.chmod(0o755)
    launcher = BIN / 't3code'
    if launcher.exists() and not (STATE / 'previous-launcher').exists():
        shutil.copy2(launcher, STATE / 'previous-launcher')
    launcher.write_text('#!/usr/bin/env python3\nimport os, pathlib, sys\n'
                        'script = pathlib.Path.home() / ".local/share/t3code-personal/install.py"\n'
                        'os.execv(sys.executable, [sys.executable, str(script), "--launch", *sys.argv[1:]])\n')
    launcher.chmod(0o755)
    applications = HOME / '.local/share/applications'
    applications.mkdir(parents=True, exist_ok=True)
    for name in ['com.t3tools.T3Code.desktop', 't3code.desktop']:
        entry = applications / name
        if entry.exists() and not (STATE / name).exists():
            shutil.copy2(entry, STATE / name)
        entry.write_text('[Desktop Entry]\nType=Application\nName=T3 Code Personal\n'
                         f'Exec="{launcher}" %U\nTerminal=false\nCategories=Development;\n'
                         f'Icon={ROOT}/current/squashfs-root/t3code.png\n'
                         'StartupWMClass=t3code\nMimeType=x-scheme-handler/t3code;\n')
    subprocess.run(['update-desktop-database', str(applications)], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f'T3 Code Personal {version} installed. Start with {launcher}')


def running_instance():
    status = read_json(T3_HOME / 'background-status.json')
    pid = status.get('pid')
    if not isinstance(pid, int) or pid <= 1:
        return None
    process = Path('/proc') / str(pid)
    try:
        executable = (process / 'exe').resolve(strict=True)
        allowed = [ROOT, HOME / '.local/opt/t3code-background', Path('/opt/T3 Code (Alpha)')]
        if process.stat().st_uid != os.getuid() or not any(executable.is_relative_to(p) for p in allowed):
            return None
        return pid, (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except OSError:
        return None


def stop(instance):
    if instance is None:
        return
    pid, started = instance

    def alive():
        try:
            return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19] == started
        except OSError:
            return False

    if alive():
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while alive() and time.monotonic() < deadline:
        time.sleep(0.2)
    if alive():
        raise RuntimeError('T3 did not finish shutting down. Installation is ready; quit from its tray before reopening.')


def restart():
    # The detached worker survives when T3 closes the terminal running this command.
    instance = running_instance()
    pending = STATE / 'restart.json'
    write_json(pending, {'instance': instance})
    with (STATE / 'restart.log').open('a') as output:
        subprocess.Popen([sys.executable, str(SCRIPT), '--restart-worker'],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=output, stderr=output)
    print(f'Restart queued; log: {STATE / "restart.log"}')


def launch(arguments):
    executable = ROOT / 'current/squashfs-root/AppRun'
    if not executable.is_file():
        raise RuntimeError('Install a release first.')
    os.execv(str(executable), [str(executable), *arguments])


def main():
    for directory in [ROOT, STATE]:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    arguments = sys.argv[1:]
    if arguments and arguments[0] == '--launch':
        arguments = arguments[1:]
        if not arguments or arguments[0] not in ['--update', '--rollback', '--status', '--quit', '--restart']:
            launch(arguments)
        arguments = [('--install' if arg == '--update' else arg) for arg in arguments]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--version')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--quit', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--restart-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(arguments)
    if args.restart_worker:
        stop(read_json(STATE / 'restart.json').get('instance'))
        subprocess.Popen([str(ROOT / 'current/squashfs-root/AppRun')],
                         start_new_session=True, stdin=subprocess.DEVNULL)
        return
    with (STATE / 'install.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.status:
            print(json.dumps({'installed': current_version(), 'running': running_instance(),
                              'releaseRepository': REPOSITORY}, indent=2))
            return
        if args.quit:
            stop(running_instance())
            return
        if args.rollback:
            previous = read_json(STATE / 'versions.json').get('previous')
            if not previous:
                raise RuntimeError('No previous custom release is installed.')
            activate(previous)
            print(f'Rolled back to {previous}. Data snapshots were retained; data was not restored.')
        elif args.install or not args.restart:
            install(args.version)
        if args.restart:
            restart()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
