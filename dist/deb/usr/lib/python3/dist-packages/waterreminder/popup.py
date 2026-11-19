"""Short-lived alert window. Prints one of: done | snooze | skip | missed on stdout, then exits."""
import argparse
import os
import random
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import audio, config  # noqa: E402

try:  # optional: only on Wayland compositors with wlr-layer-shell
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LS
except (ValueError, ImportError):
    LS = None

ICON = audio.DATA / "icons" / "waterreminder.svg"
CSS = b"""
window.wr { background: #0d47a1; color: #ffffff; border-radius: 28px; }
.wr-head { font-size: 40px; font-weight: 800; }
.wr-msg { font-size: 22px; }
.wr-count { font-size: 14px; opacity: 0.85; }
.wr-btn { font-size: 20px; padding: 12px 24px; border-radius: 14px; min-height: 36px; }
.wr-done { background: #ffffff; color: #0d47a1; font-weight: 700; }
.wr-other { background: rgba(255,255,255,0.18); color: #ffffff; }
@keyframes wr-pulse { from { opacity: 1; } 50% { opacity: 0.65; } to { opacity: 1; } }
.wr-pulse { animation: wr-pulse 2s ease-in-out infinite; }
"""
ANCHORS = {  # position -> (top, bottom, left, right); all False = centred
    "center": (0, 0, 0, 0), "top-right": (1, 0, 0, 1), "bottom-right": (0, 1, 0, 1),
    "top-left": (1, 0, 1, 0), "bottom-left": (0, 1, 1, 0),
}


class Popup(Gtk.Window):
    def __init__(self, app, cfg, message, timeout):
        super().__init__(application=app, title="H2Oh!", decorated=False, resizable=False)
        self.result, self.remaining = "missed", timeout
        self.add_css_class("wr")
        self.set_default_size(560, 460)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=32, margin_bottom=28, margin_start=36, margin_end=36)
        pic = Gtk.Picture.new_for_file(Gio.File.new_for_path(str(ICON)))
        pic.set_size_request(160, 160)
        pic.set_can_shrink(True)
        pic.set_accessible_role(Gtk.AccessibleRole.IMG)
        if Gtk.Settings.get_default().props.gtk_enable_animations:  # honour reduced-motion
            pic.add_css_class("wr-pulse")
        box.append(pic)
        head = Gtk.Label(label="Time to drink water!", wrap=True, justify=Gtk.Justification.CENTER)
        head.add_css_class("wr-head")
        msg = Gtk.Label(label=message, wrap=True, justify=Gtk.Justification.CENTER)
        msg.add_css_class("wr-msg")
        self.count = Gtk.Label()
        self.count.add_css_class("wr-count")
        box.append(head), box.append(msg)

        row = Gtk.Box(spacing=12, homogeneous=False, halign=Gtk.Align.CENTER, margin_top=8)
        for label, res, css in (("I drank water", "done", "wr-done"), ("Snooze", "snooze", "wr-other"), ("Skip", "skip", "wr-other")):
            b = Gtk.Button(label=label)
            b.add_css_class("wr-btn"), b.add_css_class(css)
            b.connect("clicked", lambda _b, r=res: self.finish(r))
            row.append(b)
            if res == "done":
                self.set_default_widget(b)
                b.grab_focus()
        box.append(row), box.append(self.count)
        self.set_child(box)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.tick()
        GLib.timeout_add_seconds(1, self.tick)
        self.setup_layer(cfg)

    def setup_layer(self, cfg):
        if LS is None or not LS.is_supported():
            return
        LS.init_for_window(self)
        LS.set_layer(self, LS.Layer.OVERLAY)
        LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)  # EXCLUSIVE would swallow the user's typing
        LS.set_namespace(self, "waterreminder")
        for edge, on in zip((LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT), ANCHORS[cfg.popup_position]):
            LS.set_anchor(self, edge, bool(on))
            LS.set_margin(self, edge, 24)

    def on_key(self, _c, keyval, _code, _state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.finish("done")
        elif keyval == Gdk.KEY_Escape:
            self.finish("snooze")
        else:
            return False
        return True

    def tick(self):
        self.count.set_label(f"Closing in {self.remaining}s")
        if self.remaining <= 0:
            self.finish("missed")
            return False
        self.remaining -= 1
        return True

    def finish(self, result):
        if self.result == "missed":  # first answer wins
            self.result = result
        self.get_application().quit()


def keep_above_x11():
    """GTK4 has no keep-above; on X11 ask the WM via wmctrl if it is installed."""
    if os.environ.get("XDG_SESSION_TYPE") == "x11" and shutil.which("wmctrl"):
        subprocess.run(["wmctrl", "-F", "-r", "H2Oh!", "-b", "add,above"], check=False, timeout=2)
    return False  # one-shot GLib timeout


def main(argv=None):
    ap = argparse.ArgumentParser(prog="waterreminder-popup")
    ap.add_argument("--message")
    ap.add_argument("--timeout", type=int, help="seconds before auto-dismiss (default: config)")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--test", action="store_true", help="manual trigger; same as running with no args")
    args = ap.parse_args(argv)

    cfg = config.load()
    message = args.message or random.choice(cfg.messages)
    timeout = args.timeout or cfg.popup_timeout_s
    app = Adw.Application(application_id="io.github.waterreminder.Popup", flags=Gio.ApplicationFlags.NON_UNIQUE)
    holder = {}

    def activate(a):
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        holder["w"] = w = Popup(a, cfg, message, timeout)
        w.present()
        GLib.timeout_add(300, keep_above_x11)
        if not args.no_sound:
            audio.play(cfg)  # non-blocking subprocess

    app.connect("activate", activate)
    app.run([])
    result = holder["w"].result if "w" in holder else "missed"
    print(result, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
