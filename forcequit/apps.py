"""Discover running GUI applications and force-quit them.

Wayland gives clients no way to enumerate other clients' windows, so we work
from processes instead:

1. GNOME (and most modern launchers) start every app inside its own systemd
   scope named after its desktop-file id, e.g.
   ``app-gnome-org.gnome.Nautilus-1234.scope``.  We read ``/proc/<pid>/cgroup``
   and map that id back to a ``.desktop`` file.
2. D-Bus activated apps (Ptyxis, GNOME Terminal, ...) and apps started from a
   terminal live outside such scopes, so as a fallback any process that is
   connected to the display (``WAYLAND_DISPLAY``/``DISPLAY`` in its environment)
   and whose executable matches a desktop file is treated as that app.

Only desktop files that would be shown in the app grid count, which mirrors
macOS listing only "Dock" applications.
"""

import os
import re
import signal
from dataclasses import dataclass, field

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

SELF_APP_ID = "io.github.adgsenpai.ForceQuit"

# macOS always lists Finder and offers "Relaunch" instead of "Force Quit".
FINDER_IDS = {"org.gnome.Nautilus.desktop", "nautilus.desktop"}

IGNORED_COMMS = {"gnome-shell", "Xwayland", "gnome-session-b", "systemd"}

_SCOPE_RE = re.compile(r"^app-(.+?)(?:-\d+\.scope|@[^.]*\.service|\.service|\.scope)$")
_SNAP_RE = re.compile(r"^snap\.([^.]+)\.([^.]+)[-.]")


@dataclass
class RunningApp:
    key: str
    name: str
    app_info: Gio.DesktopAppInfo
    pids: set = field(default_factory=set)
    not_responding: bool = False

    @property
    def is_finder(self):
        return self.app_info.get_id() in FINDER_IDS

    @property
    def icon(self):
        return self.app_info.get_icon()


@dataclass
class _Proc:
    pid: int
    ppid: int
    state: str
    comm: str
    exe: str
    argv: list
    cgroup_unit: str


def _read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except OSError:
        return None


def _unescape(s):
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)


class _DesktopIndex:
    """Lookup tables from various process identifiers to desktop files."""

    def __init__(self):
        self.by_id = {}
        self.by_key = {}
        for info in Gio.AppInfo.get_all():
            if not isinstance(info, Gio.DesktopAppInfo):
                continue
            app_id = info.get_id()
            if not app_id or app_id.removesuffix(".desktop") == SELF_APP_ID:
                continue
            # Hidden desktop files still identify scopes (Chrome's main process
            # runs in a NoDisplay "com.google.Chrome" scope); they are only
            # dropped from the final list if no visible app absorbs them.
            self.by_id[app_id.lower()] = info
            if not info.should_show():
                continue
            stem = app_id.removesuffix(".desktop")
            keys = {stem, stem.rsplit(".", 1)[-1]}
            wm_class = info.get_startup_wm_class()
            if wm_class:
                keys.add(wm_class)
            executable = info.get_executable()
            if executable:
                keys.add(os.path.basename(executable))
            for k in keys:
                self.by_key.setdefault(k.lower(), info)

    def from_unit_id(self, unit_id):
        """Resolve the id part of an ``app-[launcher-]<id>`` unit name."""
        parts = unit_id.split("-")
        candidates = [parts[-1], unit_id] if len(parts) > 1 else [unit_id]
        for c in candidates:
            c = _unescape(c).lower()
            info = self.by_id.get(c + ".desktop") or self.by_id.get(c)
            if info:
                return info
        return None

    def from_names(self, names):
        for n in names:
            if n:
                info = self.by_key.get(n.lower())
                if info:
                    return info
        return None


def _list_procs():
    uid = os.getuid()
    procs = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
        except OSError:
            continue
        stat = _read(f"/proc/{pid}/stat")
        if not stat:
            continue
        # comm may contain spaces/parens; it is bounded by the first "(" and last ")".
        comm = stat[stat.find("(") + 1 : stat.rfind(")")]
        rest = stat[stat.rfind(")") + 2 :].split()
        cmdline = _read(f"/proc/{pid}/cmdline", "rb") or b""
        argv = [a.decode(errors="replace") for a in cmdline.split(b"\0") if a]
        if not argv:  # kernel threads / zombies
            continue
        try:
            exe = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            exe = ""
        cgroup = _read(f"/proc/{pid}/cgroup") or ""
        unit = cgroup.strip().rsplit("/", 1)[-1]
        procs[pid] = _Proc(pid, int(rest[1]), rest[0], comm, exe, argv, unit)
    return procs


def _has_display(pid):
    env = _read(f"/proc/{pid}/environ", "rb")
    return bool(env) and (b"WAYLAND_DISPLAY=" in env or b"\0DISPLAY=" in env or env.startswith(b"DISPLAY="))


def _app_for_proc(proc, index):
    if proc.comm in IGNORED_COMMS:
        return None
    m = _SCOPE_RE.match(proc.cgroup_unit)
    if m:
        info = index.from_unit_id(m.group(1))
        if info:
            return info
    m = _SNAP_RE.match(proc.cgroup_unit)
    if m:
        snap, app = m.groups()
        info = index.by_id.get(f"{snap}_{app}.desktop".lower()) or index.from_names([app, snap])
        if info:
            return info
    names = [proc.exe, proc.comm, os.path.basename(proc.argv[0])]
    # Interpreted apps: "python3 /usr/bin/foo"
    if len(proc.argv) > 1 and proc.exe.startswith(("python", "perl", "ruby", "node", "gjs", "java")):
        names.append(os.path.basename(proc.argv[1]))
    info = index.from_names(names)
    if info and _has_display(proc.pid):
        return info
    return None


def running_apps():
    """Return the list of running GUI applications, sorted by name."""
    index = _DesktopIndex()
    procs = _list_procs()
    me = os.getpid()

    groups = {}
    owner = {}
    for proc in procs.values():
        if proc.pid == me:
            continue
        info = _app_for_proc(proc, index)
        if not info:
            continue
        key = info.get_id()
        app = groups.get(key)
        if app is None:
            app = groups[key] = RunningApp(key, info.get_name() or key, info)
        app.pids.add(proc.pid)
        owner[proc.pid] = key

    # One app may spread over several desktop ids (Chrome spawns helpers in a
    # second scope). Fold a group into another if its processes descend from it.
    def ancestor_group(pid, own_key):
        seen = set()
        pid = procs[pid].ppid if pid in procs else 0
        while pid > 1 and pid in procs and pid not in seen:
            seen.add(pid)
            k = owner.get(pid)
            if k and k != own_key:
                return k
            pid = procs[pid].ppid
        return None

    changed = True
    while changed:
        changed = False
        for key, app in list(groups.items()):
            parents = {ancestor_group(p, key) for p in app.pids} - {None}
            if parents:
                parent = groups[sorted(parents)[0]]
                parent.pids |= app.pids
                if not parent.app_info.should_show() and app.app_info.should_show():
                    parent.app_info, parent.name = app.app_info, app.name
                for p in app.pids:
                    owner[p] = parent.key
                del groups[key]
                changed = True
                break

    groups = {k: a for k, a in groups.items() if a.app_info.should_show()}
    for app in groups.values():
        # A stopped/traced process will never answer its compositor pings.
        app.not_responding = any(procs[p].state in ("T", "t") for p in app.pids if p in procs)

    return sorted(groups.values(), key=lambda a: (a.is_finder, a.name.lower()))


def _descendants(roots):
    children = {}
    for proc in _list_procs().values():
        children.setdefault(proc.ppid, []).append(proc.pid)
    out, stack = set(), list(roots)
    while stack:
        pid = stack.pop()
        if pid in out:
            continue
        out.add(pid)
        stack.extend(children.get(pid, ()))
    return out


def force_quit(app):
    """SIGKILL every process belonging to *app*, like macOS Force Quit."""
    me = os.getpid()
    for pid in _descendants(app.pids) - {me, os.getppid()}:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def relaunch(app):
    app.app_info.launch([], None)
