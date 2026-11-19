"""waterreminderd: no GTK. Wall-clock tick loop -> spawn popup -> handle result."""
import fcntl
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from gi.repository import Gio, GLib

from . import config, scheduler
from .audio import DATA

log = logging.getLogger("waterreminder")
TICK_S = 10  # alarm accuracy; wall clock is re-read every tick so suspend/clock jumps are harmless
NOTIFY = ("org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications")


class Daemon:
    def __init__(self):
        self.cfg = config.load()
        self.last_check = datetime.now()
        self.pending = None  # slot/snooze waiting to fire (deferred while locked/idle)
        self.snooze_until = None
        self.proc = None
        self.notif_id = 0
        self.loop = GLib.MainLoop()
        self.session = self.system = None
        self.tray = None

    # ---------- lifecycle ----------
    def run(self):
        self.reload()
        GLib.timeout_add_seconds(TICK_S, self.tick)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self._sighup)
        for s in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, s, self._quit)
        self._watch_config()
        self._connect_buses()
        log.info("started; next reminder: %s", scheduler.next_fire(self.cfg, datetime.now()))
        self.loop.run()

    def _quit(self):
        self.loop.quit()
        return False

    def _sighup(self):
        self.reload()
        return True

    def _watch_config(self):
        try:
            d = Gio.File.new_for_path(str(config.CONFIG_PATH.parent))
            d.get_path() and os.makedirs(d.get_path(), exist_ok=True)
            self.monitor = d.monitor_directory(Gio.FileMonitorFlags.NONE, None)  # dir, so atomic replace is seen
            self.monitor.connect("changed", self._cfg_changed)
        except GLib.Error as e:
            log.warning("config watch unavailable (%s); send SIGHUP to reload", e.message)
        self._debounce = 0

    def _cfg_changed(self, _m, f, _o, _ev):
        if f.get_basename() == config.CONFIG_PATH.name and not self._debounce:
            self._debounce = GLib.timeout_add(300, self._debounced)

    def _debounced(self):
        self._debounce = 0
        self.reload()
        return False

    def reload(self):
        self.cfg = config.load()
        log.info("config loaded")
        if self.tray:
            self.tray.refresh()

    def _connect_buses(self):
        try:
            self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            self.system.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
                                         "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, self._sleep_signal)
        except GLib.Error as e:
            log.info("logind unavailable (%s); relying on wall-clock ticks", e.message)
        try:
            self.session = Gio.bus_get_sync(Gio.BusType.SESSION)
        except GLib.Error as e:
            log.warning("no session bus (%s): no notifications/tray", e.message)
        if self.cfg.tray and self.session:
            from .tray import Tray
            self.tray = Tray(DATA / "icons", self.tray_items, self.tray_click)

    def _sleep_signal(self, _c, _s, _p, _i, _n, params):
        if not params.unpack()[0]:  # resumed
            GLib.timeout_add_seconds(3, lambda: self.tick() and False)

    # ---------- scheduling ----------
    def tick(self):
        time.tzset()  # pick up timezone changes
        now = datetime.now()
        try:
            slot = scheduler.due_slot(self.cfg, self.last_check, now)  # at most one, even after a long suspend
            if self.snooze_until and self.snooze_until <= now:
                if now - self.snooze_until <= scheduler.CATCHUP_GRACE:
                    slot = slot or self.snooze_until
                self.snooze_until = None
            self.last_check = now
            if slot:
                self.pending = slot  # a newer slot replaces a stale deferred one: no pile-up
            if self.pending and not self.proc:
                if not scheduler.in_work_hours(self.cfg, now) or scheduler.paused(self.cfg, now):
                    self.pending = None
                elif not self._blocked():
                    self.pending = None
                    self.fire()
        except Exception:
            log.exception("tick failed")  # never let the timer die
        return True

    def _blocked(self) -> bool:
        """Locked screen / idle user. Any failure to detect means 'not blocked'."""
        if not self.cfg.skip_when_locked or not self.system:
            return False
        try:
            r = self.system.call_sync("org.freedesktop.login1", "/org/freedesktop/login1/session/auto", "org.freedesktop.DBus.Properties",
                                      "Get", GLib.Variant("(ss)", ("org.freedesktop.login1.Session", "LockedHint")), None, Gio.DBusCallFlags.NONE, 1000, None)
            if r.unpack()[0]:
                return True
        except GLib.Error:
            pass
        if self.cfg.idle_threshold_min and self.session:
            try:
                r = self.session.call_sync("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core", "org.gnome.Mutter.IdleMonitor",
                                           "GetIdletime", None, None, Gio.DBusCallFlags.NONE, 1000, None)
                return r.unpack()[0] > self.cfg.idle_threshold_min * 60_000
            except GLib.Error:
                pass  # not GNOME: degrade gracefully
        return False

    # ---------- alert ----------
    def fire(self):
        log.info("firing reminder")
        if self.cfg.notify_fallback and self._popup_may_be_unreliable():
            self._notify()
        try:
            self.proc = Gio.Subprocess.new([sys.executable, "-m", "waterreminder.popup"], Gio.SubprocessFlags.STDOUT_PIPE)
            self.proc.communicate_utf8_async(None, None, self._popup_done)
        except GLib.Error as e:
            log.error("cannot start popup: %s", e.message)
            self.proc = None
            self._notify()  # alert must never be silently lost

    @staticmethod
    def _popup_may_be_unreliable() -> bool:
        # GNOME Wayland has no layer-shell and X11 has no guaranteed stacking -> also send a normal notification
        d = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        return "GNOME" in d or os.environ.get("XDG_SESSION_TYPE") == "x11"

    def _notify(self):
        if not self.session or self.notif_id:
            return
        try:
            r = self.session.call_sync(*NOTIFY[:3], "Notify", GLib.Variant("(susssasa{sv}i)", (
                "H2Oh!", 0, "waterreminder", "Time to drink water!", "Take a moment to drink some water.", [], {"urgency": GLib.Variant("y", 2)}, 20000)),
                None, Gio.DBusCallFlags.NONE, 2000, None)
            self.notif_id = r.unpack()[0]
        except GLib.Error as e:
            log.warning("notification failed: %s", e.message)

    def _close_notification(self):
        if self.notif_id and self.session:
            self.session.call(*NOTIFY[:3], "CloseNotification", GLib.Variant("(u)", (self.notif_id,)), None, Gio.DBusCallFlags.NONE, 1000, None, None)
        self.notif_id = 0

    def _popup_done(self, proc, res):
        try:
            _, out, _ = proc.communicate_utf8_finish(res)
            result = (out or "").strip().splitlines()[-1] if (out or "").strip() else "crashed"
        except GLib.Error:
            result = "crashed"
        self.proc = None
        self.last_check = datetime.now()  # the popup's own duration must not trigger a catch-up
        log.info("popup result: %s", result)
        if result == "crashed":
            self._notify()  # popup failed: keep the notification as the alert
        else:
            self._close_notification()
        if result == "done":
            config.add_count(datetime.now().date().isoformat())
            if self.tray:
                self.tray.refresh()
        elif result == "snooze":
            self.snooze_until = datetime.now() + timedelta(minutes=self.cfg.snooze_min)
        self.notif_id = 0

    # ---------- tray ----------
    def tray_items(self):
        n = config.read_count(datetime.now().date().isoformat())
        paused = scheduler.paused(self.cfg, datetime.now())
        return [(1, f"Drank today: {n}", False), (2, "Resume reminders" if paused else "Pause for 1 hour", True),
                (3, "Pause until tomorrow", True), (4, "Settings…", True), (5, "Quit", True)]

    def tray_click(self, ident):
        now = datetime.now()
        if ident in (2, 3):
            c = config.load()
            if ident == 2 and scheduler.paused(c, now):
                c.paused_until = ""
            elif ident == 2:
                c.paused_until = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            else:
                c.paused_until = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).isoformat()
            config.save(c)
        elif ident == 4:
            Gio.Subprocess.new([sys.executable, "-m", "waterreminder.settings"], Gio.SubprocessFlags.NONE)
        elif ident == 5:
            self.loop.quit()
        return False


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    lock = open(lock_dir / "waterreminder.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("waterreminderd is already running", file=sys.stderr)
        return 1
    Daemon().run()  # `lock` stays referenced (and locked) until process exit
    return 0


if __name__ == "__main__":
    sys.exit(main())
