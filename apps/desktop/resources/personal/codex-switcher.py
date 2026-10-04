#!/usr/bin/env python3
"""Start codex-switcher once, independently of T3, and hide its new window."""
import argparse
import ctypes
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

BINARY = Path(os.environ.get('T3CODE_SWITCHER_BINARY', '/opt/codex-switcher/usr/bin/codex-switcher')).expanduser().resolve()
LAUNCHER = Path(os.environ.get('T3CODE_SWITCHER_LAUNCHER', '/usr/bin/codex-switcher')).expanduser()
UNIT = 't3-codex-switcher.service'
STATE = Path.home() / '.local/state/t3-background'


def running_pids():
    result = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid == os.getuid() and ((process / 'exe').resolve() == BINARY or (process / 'exe').resolve().name == 'codex-switcher'):
                result.append(int(process.name))
        except OSError:
            continue
    return result


def request_window_hide(window):
    # WM_DELETE_WINDOW invokes Tauri's CloseRequested handler, which hides the
    # window and prevents exit. Do not destroy or merely unmap its X11 window.
    class Data(ctypes.Union):
        _fields_ = [('b', ctypes.c_char * 20), ('s', ctypes.c_short * 10), ('l', ctypes.c_long * 5)]

    class ClientMessage(ctypes.Structure):
        _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                    ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                    ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                    ('format', ctypes.c_int), ('data', Data)]

    class Event(ctypes.Union):
        _fields_ = [('client', ClientMessage), ('pad', ctypes.c_long * 24)]

    x11 = ctypes.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(Event)]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('Cannot connect to the X11 desktop to hide codex-switcher')
    try:
        event = Event()
        event.client.type = 33  # ClientMessage
        event.client.display = display
        event.client.window = window
        event.client.message_type = x11.XInternAtom(display, b'WM_PROTOCOLS', 0)
        event.client.format = 32
        event.client.data.l[0] = x11.XInternAtom(display, b'WM_DELETE_WINDOW', 0)
        if not x11.XSendEvent(display, window, 0, 0, ctypes.byref(event)):
            raise RuntimeError('Could not request background mode for codex-switcher')
        x11.XFlush(display)
    finally:
        x11.XCloseDisplay(display)


def visible_windows(pid):
    result = subprocess.run(['xdotool', 'search', '--all', '--onlyvisible', '--pid', str(pid),
                             '--name', '^Codex Switcher$'], capture_output=True, text=True, timeout=2)
    return [int(line) for line in result.stdout.splitlines() if line.isdigit()]


def start_service():
    if not os.access(LAUNCHER, os.X_OK):
        raise RuntimeError('The installed codex-switcher Linux launcher is missing')
    command = ['systemd-run', '--user', '--quiet', '--collect', '--unit=' + UNIT,
               '--property=Type=exec']
    for name in ['DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR',
                 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE']:
        if os.environ.get(name):
            command.append(f'--setenv={name}={os.environ[name]}')
    if os.environ.get('DISPLAY'):
        # Also works on GNOME Wayland through XWayland; its window can then
        # receive the app's normal close-to-background request over X11.
        command.append('--setenv=GDK_BACKEND=x11')
    command.append(str(LAUNCHER))
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    if result.returncode:
        # A prior startup can already own the service while GTK is initializing.
        active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', UNIT], timeout=3)
        if active.returncode:
            raise RuntimeError('Could not start codex-switcher user service: ' + result.stderr.strip())


def ensure_running():
    existing = running_pids()
    if existing:
        return 'already running', existing
    start_service()
    deadline = time.monotonic() + 15
    pids = []
    hidden = set()
    first_hidden = None
    while time.monotonic() < deadline:
        pids = running_pids()
        for pid in pids:
            for window in visible_windows(pid):
                if window not in hidden:
                    request_window_hide(window)
                    hidden.add(window)
                    first_hidden = first_hidden or time.monotonic()
        if first_hidden is not None and time.monotonic() - first_hidden > 0.5:
            if all(not visible_windows(pid) for pid in pids):
                return 'started in background', pids
        time.sleep(0.2)
    if not pids:
        raise RuntimeError(f'Codex-switcher did not start; inspect journalctl --user -u {UNIT}')
    raise RuntimeError('Codex-switcher started, but its background window state could not be verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(STATE / 'switcher-start.lock', os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            action, pids = ensure_running()
            if not args.quiet:
                print(f'Codex-switcher {action} (PIDs: {", ".join(map(str, pids))})')
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            sys.exit(f'Codex-switcher auto-start failed: {error}')


if __name__ == '__main__':
    main()
