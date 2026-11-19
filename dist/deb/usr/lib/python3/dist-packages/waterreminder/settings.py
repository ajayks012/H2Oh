"""Settings window. Every change is saved at once; the daemon picks it up via its file monitor."""
import subprocess
import sys
from datetime import datetime, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from . import audio, autostart, config  # noqa: E402

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class Settings(Adw.PreferencesWindow):
    def __init__(self, app):
        super().__init__(application=app, title="H2Oh!", default_width=640, default_height=780)
        self.cfg = config.load()
        page = Adw.PreferencesPage()
        self.add(page)
        self.today = Gtk.Label(xalign=0)
        self._refresh_today()

        g = self.group(page, "Schedule", "Changes apply immediately, no restart needed.")
        self.switch(g, "Reminders enabled", "enabled")
        row = Adw.ActionRow(title="Work days")
        box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
        for i, d in enumerate(DAYS):
            b = Gtk.ToggleButton(label=d[0], tooltip_text=d, active=i in self.cfg.days)
            b.update_property([Gtk.AccessibleProperty.LABEL], [d])
            b.connect("toggled", self._day, i)
            box.append(b)
        row.add_suffix(box)
        g.add(row)
        self.time_entry(g, "Work starts (HH:MM)", "start")
        self.time_entry(g, "Work ends (HH:MM)", "end")
        self.spin(g, "Interval (minutes)", "interval_min", 1, 1440)
        self.switch(g, "First reminder at start time", "first_at_start", "Off: first reminder at start + interval")
        self.spin(g, "Snooze (minutes)", "snooze_min", 1, 240)
        pr = Adw.ActionRow(title="Pause")
        for label, fn in (("1 hour", lambda: datetime.now() + timedelta(hours=1)),
                          ("Until tomorrow", lambda: datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())),
                          ("Resume", None)):
            b = Gtk.Button(label=label, valign=Gtk.Align.CENTER, margin_start=6)
            b.connect("clicked", self._pause, fn)
            pr.add_suffix(b)
        g.add(pr)

        g = self.group(page, "Sound")
        self.switch(g, "Play sound", "sound_enabled")
        self.spin(g, "Volume (%)", "volume", 0, 100)
        self.combo(g, "Sound", "sound", config.SOUNDS)
        r = Adw.ActionRow(title="Preview sound")
        b = Gtk.Button(label="Play", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda _b: audio.play(self.cfg))
        r.add_suffix(b)
        g.add(r)

        g = self.group(page, "Popup", "Corner positions need a compositor with layer-shell (KDE, Sway, Hyprland).")
        self.combo(g, "Position", "popup_position", config.POSITIONS)
        self.spin(g, "Auto-dismiss after (seconds)", "popup_timeout_s", 5, 600)
        self.switch(g, "Also send a desktop notification", "notify_fallback", "Used on GNOME and X11 so alerts are never lost")
        r = Adw.ActionRow(title="Messages", subtitle="One per line; one is picked at random")
        g.add(r)
        self.msgs = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, top_margin=8, bottom_margin=8, left_margin=8, right_margin=8, height_request=90)
        self.msgs.get_buffer().set_text("\n".join(self.cfg.messages))
        self.msgs.get_buffer().connect("changed", self._msgs)
        self.msgs.update_property([Gtk.AccessibleProperty.LABEL], ["Reminder messages"])
        fr = Gtk.Frame(child=self.msgs)
        g.add(fr)
        r = Adw.ActionRow(title="Test popup")
        b = Gtk.Button(label="Show now", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda _b: subprocess.Popen([sys.executable, "-m", "waterreminder.popup", "--test"], stdout=subprocess.DEVNULL))
        r.add_suffix(b)
        g.add(r)

        g = self.group(page, "Behaviour")
        self.switch(g, "Skip while screen is locked", "skip_when_locked", "Uses logind; ignored if unavailable")
        self.spin(g, "Skip when idle for (minutes, 0 = off)", "idle_threshold_min", 0, 240, "GNOME only")
        self.switch(g, "Show tray icon (needs restart)", "tray", "Requires a StatusNotifier host (KDE; GNOME AppIndicator extension)")
        r = Adw.SwitchRow(title="Start at login", active=autostart.is_enabled())
        r.connect("notify::active", lambda w, _p: autostart.set_enabled(w.get_active()))
        g.add(r)

        g = self.group(page, "Today")
        r = Adw.ActionRow(title="Glasses confirmed today")
        r.add_suffix(self.today)
        g.add(r)

    # --- helpers ---
    def group(self, page, title, desc=""):
        g = Adw.PreferencesGroup(title=title, description=desc)
        page.add(g)
        return g

    def _save(self):
        config.validate(self.cfg)
        config.save(self.cfg)

    def _refresh_today(self):
        self.today.set_label(str(config.read_count(datetime.now().date().isoformat())))

    def switch(self, g, title, key, sub=""):
        r = Adw.SwitchRow(title=title, subtitle=sub, active=getattr(self.cfg, key))
        r.connect("notify::active", lambda w, _p: (setattr(self.cfg, key, w.get_active()), self._save()))
        g.add(r)

    def spin(self, g, title, key, lo, hi, sub=""):
        r = Adw.SpinRow.new_with_range(lo, hi, 1)
        r.set_title(title), r.set_subtitle(sub), r.set_value(getattr(self.cfg, key))
        r.connect("notify::value", lambda w, _p: (setattr(self.cfg, key, int(w.get_value())), self._save()))
        g.add(r)

    def combo(self, g, title, key, options):
        r = Adw.ComboRow(title=title, model=Gtk.StringList.new(list(options)), selected=options.index(getattr(self.cfg, key)))
        r.connect("notify::selected", lambda w, _p: (setattr(self.cfg, key, options[w.get_selected()]), self._save()))
        g.add(r)

    def time_entry(self, g, title, key):
        r = Adw.EntryRow(title=title, text=getattr(self.cfg, key))

        def changed(w):
            try:
                h, m = w.get_text().split(":")
                assert 0 <= int(h) < 24 and 0 <= int(m) < 60
            except Exception:
                w.add_css_class("error")
                return
            w.remove_css_class("error")
            setattr(self.cfg, key, f"{int(h):02d}:{int(m):02d}")
            self._save()
        r.connect("changed", changed)
        g.add(r)

    def _day(self, btn, i):
        days = set(self.cfg.days)
        (days.add if btn.get_active() else days.discard)(i)
        self.cfg.days = sorted(days)
        self._save()

    def _pause(self, _b, fn):
        self.cfg.paused_until = fn().isoformat(timespec="seconds") if fn else ""
        self._save()

    def _msgs(self, buf):
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        self.cfg.messages = [m for m in text.splitlines() if m.strip()]
        self._save()


def main():
    app = Adw.Application(application_id="io.github.waterreminder.Settings", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    app.connect("activate", lambda a: (a.props.active_window or Settings(a)).present())
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
