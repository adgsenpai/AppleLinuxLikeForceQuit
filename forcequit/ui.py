"""A pixel-for-pixel take on macOS's "Force Quit Applications" panel."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import apps  # noqa: E402

REFRESH_MS = 1500

CSS = """
.fq, .fq * {
  font-family: -apple-system, "SF Pro Text", "Inter", "Cantarell", sans-serif;
  font-size: 13px;
  -gtk-icon-shadow: none;
}
window.fq {
  background: #ececec;
  color: #1d1d1f;
  border-radius: 10px;
}
window.fq headerbar {
  background: #ececec;
  box-shadow: none;
  border: none;
  min-height: 28px;
  padding: 0 8px;
}
window.fq headerbar .title {
  font-weight: 600;
  color: #4d4d4d;
}
window.fq:backdrop headerbar .title { color: #a8a8a8; }

/* Traffic lights */
.lights { margin-left: 4px; }
.light {
  min-width: 12px; min-height: 12px;
  padding: 0; margin: 0 4px 0 0;
  border-radius: 999px;
  border: 0.5px solid rgba(0,0,0,0.12);
  box-shadow: none;
}
.light label { font-size: 9px; font-weight: 900; color: rgba(0,0,0,0.55); opacity: 0; }
.lights:hover .light label { opacity: 1; }
.light.close { background: #ff5f57; }
.light.minimize { background: #febc2e; }
.light.zoom, .light:disabled { background: #d0d0d0; }
window.fq:backdrop .light { background: #d0d0d0; }

.intro { color: #1d1d1f; }

.listframe {
  background: #ffffff;
  border: 1px solid #c8c8c8;
  border-radius: 0;
}
list.applist { background: #ffffff; }
list.applist row {
  min-height: 22px;
  padding: 1px 6px;
  border-radius: 0;
  outline: none;
  color: #1d1d1f;
}
list.applist row:hover { background: transparent; }
list.applist row:selected { background: #0064e1; color: #ffffff; }
window.fq:backdrop list.applist row:selected { background: #dcdcdc; color: #1d1d1f; }
list.applist row .not-responding { color: #e0291c; }
list.applist row:selected .not-responding { color: #ffffff; }

.hint { font-size: 11px; color: #6e6e73; }

button.mac {
  min-height: 20px;
  padding: 1px 16px;
  border-radius: 6px;
  background: #ffffff;
  color: #1d1d1f;
  border: 0.5px solid rgba(0,0,0,0.18);
  box-shadow: 0 0.5px 1px rgba(0,0,0,0.15);
}
button.mac.default {
  background: linear-gradient(#3b8cff, #0a6cff);
  color: #ffffff;
  border-color: rgba(0,0,0,0.05);
}
button.mac:active { filter: brightness(0.9); }
button.mac:disabled { background: #f6f6f6; color: #b5b5b5; box-shadow: none; }
window.fq:backdrop button.mac.default:not(:disabled) { background: #ffffff; color: #1d1d1f; }

/* Alert sheet */
window.alert { background: transparent; }
.alertbox {
  background: #ececec;
  border-radius: 12px;
  border: 0.5px solid rgba(0,0,0,0.25);
  padding: 20px 16px 16px 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}
.alert-title { font-weight: 700; }
.alert-msg { font-size: 11px; }
.alertbox button.mac { min-height: 24px; }

/* Dark appearance */
window.fq.dark, window.fq.dark headerbar, .dark .alertbox { background: #282828; color: #e5e5e5; }
window.fq.dark headerbar .title { color: #d0d0d0; }
.dark .intro { color: #e5e5e5; }
.dark .listframe { background: #1e1e1e; border-color: #3d3d3d; }
.dark list.applist { background: #1e1e1e; }
.dark list.applist row { color: #e5e5e5; }
.dark list.applist row:selected { background: #0058d0; color: #ffffff; }
window.fq.dark:backdrop list.applist row:selected { background: #464646; color: #e5e5e5; }
.dark .hint { color: #9a9a9a; }
.dark button.mac { background: #5a5a5a; color: #e5e5e5; border-color: rgba(255,255,255,0.08); }
.dark button.mac.default { background: linear-gradient(#3b8cff, #0a6cff); color: #ffffff; }
.dark button.mac:disabled { background: #3a3a3a; color: #6e6e6e; }
window.fq.dark .light.zoom, window.fq.dark .light:disabled, window.fq.dark:backdrop .light { background: #4d4d4d; }
"""


def _is_dark():
    try:
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        return settings.get_string("color-scheme") == "prefer-dark"
    except Exception:
        return False


def _light(kind, glyph, sensitive=True):
    btn = Gtk.Button()
    btn.add_css_class("light")
    btn.add_css_class(kind)
    btn.set_child(Gtk.Label(label=glyph))
    btn.set_sensitive(sensitive)
    btn.set_valign(Gtk.Align.CENTER)
    btn.set_focusable(False)
    btn.set_cursor(Gdk.Cursor.new_from_name("default"))
    return btn


def _mac_button(label, default=False):
    btn = Gtk.Button(label=label)
    btn.add_css_class("mac")
    if default:
        btn.add_css_class("default")
    return btn


class AppRow(Gtk.ListBoxRow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        box = Gtk.Box(spacing=6)
        icon = Gtk.Image.new_from_gicon(app.icon) if app.icon else Gtk.Image.new_from_icon_name("application-x-executable")
        icon.set_pixel_size(18)
        box.append(icon)
        name = Gtk.Label(label=app.name, xalign=0)
        name.set_ellipsize(3)  # Pango.EllipsizeMode.END
        box.append(name)
        if app.not_responding:
            nr = Gtk.Label(label="(Not Responding)", xalign=0)
            nr.add_css_class("not-responding")
            name.add_css_class("not-responding")
            box.append(nr)
        self.set_child(box)


class ConfirmAlert(Gtk.Window):
    """macOS-style alert: icon, bold question, note, Cancel / Force Quit."""

    def __init__(self, parent, targets, on_confirm):
        super().__init__(transient_for=parent, modal=True, decorated=False, resizable=False)
        self.add_css_class("alert")
        self.add_css_class("fq")
        if parent.has_css_class("dark"):
            self.add_css_class("dark")
        self.set_default_size(272, -1)

        relaunch = len(targets) == 1 and targets[0].is_finder
        if len(targets) == 1:
            question = (f"Do you want to relaunch “{targets[0].name}”?" if relaunch
                        else f"Do you want to force “{targets[0].name}” to quit?")
        else:
            question = f"Do you want to force the selected {len(targets)} applications to quit?"

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("alertbox")
        if len(targets) == 1 and targets[0].icon:
            icon = Gtk.Image.new_from_gicon(targets[0].icon)
        else:
            icon = Gtk.Image.new_from_icon_name("dialog-warning")
        icon.set_pixel_size(64)
        box.append(icon)

        title = Gtk.Label(label=question, wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=30)
        title.add_css_class("alert-title")
        box.append(title)
        msg = Gtk.Label(label="You will lose any unsaved changes.", wrap=True, justify=Gtk.Justification.CENTER)
        msg.add_css_class("alert-msg")
        box.append(msg)

        buttons = Gtk.Box(spacing=8, homogeneous=True)
        buttons.set_margin_top(6)
        cancel = _mac_button("Cancel")
        ok = _mac_button("Relaunch" if relaunch else "Force Quit", default=True)
        cancel.connect("clicked", lambda *_: self.close())

        def confirmed(*_):
            self.close()
            on_confirm(targets)

        ok.connect("clicked", confirmed)
        buttons.append(cancel)
        buttons.append(ok)
        box.append(buttons)
        self.set_child(box)
        self.set_default_widget(ok)
        ok.grab_focus()

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda c, kv, kc, st: (self.close(), True)[1] if kv == Gdk.KEY_Escape else False)
        self.add_controller(keys)


class ForceQuitWindow(Gtk.ApplicationWindow):
    def __init__(self, app, shortcut_label):
        super().__init__(application=app, title="Force Quit Applications")
        self.add_css_class("fq")
        self.set_default_size(420, 410)
        self._signature = None

        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        title = Gtk.Label(label="Force Quit Applications")
        title.add_css_class("title")
        header.set_title_widget(title)
        lights = Gtk.Box()
        lights.add_css_class("lights")
        close = _light("close", "×")
        close.connect("clicked", lambda *_: self.close())
        minimize = _light("minimize", "−")
        minimize.connect("clicked", lambda *_: self.minimize())
        lights.append(close)
        lights.append(minimize)
        lights.append(_light("zoom", "+", sensitive=False))
        header.pack_start(lights)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(6)
        root.set_margin_bottom(18)

        intro = Gtk.Label(
            label="If an app doesn’t respond for a while, select its name and click Force Quit.",
            wrap=True, xalign=0,
        )
        intro.add_css_class("intro")
        root.append(intro)

        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("applist")
        self.listbox.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.connect("selected-rows-changed", self._on_selection)
        self.listbox.connect("row-activated", lambda *_: self._on_force_quit())
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.listbox)
        frame = Gtk.Frame(child=scroller)
        frame.add_css_class("listframe")
        root.append(frame)

        bottom = Gtk.Box(spacing=12)
        hint = Gtk.Label(
            label=f"You can open this window by pressing {shortcut_label}.",
            wrap=True, xalign=0, hexpand=True,
        )
        hint.add_css_class("hint")
        bottom.append(hint)
        self.button = _mac_button("Force Quit", default=True)
        self.button.set_valign(Gtk.Align.CENTER)
        self.button.set_sensitive(False)
        self.button.connect("clicked", lambda *_: self._on_force_quit())
        bottom.append(self.button)
        root.append(bottom)
        self.set_child(root)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._apply_theme()
        try:
            self._iface = Gio.Settings.new("org.gnome.desktop.interface")
            self._iface.connect("changed::color-scheme", lambda *_: self._apply_theme())
        except Exception:
            self._iface = None

        self.refresh()
        self._timer = GLib.timeout_add(REFRESH_MS, self._tick)
        self.connect("close-request", self._on_close)

    # --- behaviour -------------------------------------------------------

    def _apply_theme(self):
        if _is_dark():
            self.add_css_class("dark")
        else:
            self.remove_css_class("dark")

    def _on_close(self, *_):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        return False

    def _tick(self):
        self.refresh()
        return True

    def _on_key(self, ctrl, keyval, keycode, state):
        mods = state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_Escape or (keyval in (Gdk.KEY_w, Gdk.KEY_q) and mods & Gdk.ModifierType.CONTROL_MASK):
            self.close()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.button.get_sensitive():
            self._on_force_quit()
            return True
        return False

    def refresh(self):
        running = apps.running_apps()
        signature = [(a.key, a.name, a.not_responding) for a in running]
        if signature == self._signature:
            # Same apps; just keep pid sets current for the kill.
            fresh = {a.key: a for a in running}
            row = self.listbox.get_first_child()
            while row:
                if isinstance(row, AppRow) and row.app.key in fresh:
                    row.app = fresh[row.app.key]
                row = row.get_next_sibling()
            return
        self._signature = signature

        selected = {r.app.key for r in self.listbox.get_selected_rows()}
        self.listbox.remove_all()
        for app in running:
            row = AppRow(app)
            self.listbox.append(row)
            if app.key in selected:
                self.listbox.select_row(row)
        if not self.listbox.get_selected_rows() and running:
            # macOS preselects the first app so Return works immediately.
            first = self.listbox.get_row_at_index(0)
            self.listbox.select_row(first)
            first.grab_focus()
        self._on_selection()

    def _selected_apps(self):
        return [r.app for r in self.listbox.get_selected_rows()]

    def _on_selection(self, *_):
        targets = self._selected_apps()
        self.button.set_sensitive(bool(targets))
        relaunch = len(targets) == 1 and targets[0].is_finder
        self.button.set_label("Relaunch" if relaunch else "Force Quit")

    def _on_force_quit(self):
        targets = self._selected_apps()
        if targets:
            ConfirmAlert(self, targets, self._kill).present()

    def _kill(self, targets):
        for app in targets:
            apps.force_quit(app)
            if app.is_finder:
                GLib.timeout_add(600, lambda a=app: (apps.relaunch(a), False)[1])
        GLib.timeout_add(250, lambda: (self.refresh(), False)[1])


class ForceQuitApplication(Gtk.Application):
    def __init__(self, shortcut_label):
        super().__init__(application_id=apps.SELF_APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.shortcut_label = shortcut_label
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # Above USER priority so ~/.config/gtk-4.0/gtk.css themes can't repaint us.
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
        )

    def do_activate(self):
        # Pressing the shortcut again just brings the existing panel forward.
        if self.window is None or not self.window.get_visible():
            self.window = ForceQuitWindow(self, self.shortcut_label)
        else:
            self.window.refresh()
        self.window.present()
