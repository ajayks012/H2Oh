# H2Oh!

**H2Oh!** is a lightweight drink-water reminder for Linux. During your work hours it shows a **large popup** and plays a **sound**.
Built with Python 3.11+, PyGObject (GTK4 + libadwaita), plain GLib timers. No other runtime dependencies.

| Process | Role |
|---|---|
| `waterreminderd` | Background daemon. **No GTK imports** (GLib/Gio only). Schedules, spawns the popup, optional tray. |
| `waterreminder-popup` | Short-lived alert window. Prints `done`/`snooze`/`skip`/`missed` on stdout and exits. |
| `waterreminder-settings` | Settings window. Saves instantly; the daemon reloads the file on change (or on `SIGHUP`). |

## Install

System packages (Ubuntu/Debian names): `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` plus `pipewire-bin` or `pulseaudio-utils`
(for `pw-play`/`paplay`). Optional: `gir1.2-gtk4layershell-1.0` (overlay popup on KDE/Sway/Hyprland), `wmctrl` (keep-above on X11).
Fedora: `python3-gobject gtk4 libadwaita`; Arch: `python-gobject gtk4 libadwaita`.

**pipx / pip** (PyGObject must come from the distro, so allow system site packages):
```
pipx install --system-site-packages .       # or: python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e .
```
**.deb**: `./tools/build-deb.sh && sudo apt install ./dist/waterreminder_0.1.0_all.deb`
**Flatpak**: `flatpak/io.github.waterreminder.WaterReminder.yml` (untested, see limitations).
**systemd user unit** (alternative to the in-app autostart): `data/waterreminder.service`.

## Quick install (script)

```
git clone https://github.com/ajayks012/H2Oh && cd H2Oh && ./install.sh     # installs distro deps with sudo, then pipx
./install.sh --uninstall                                                 # removes the app and autostart entry
```
`install.sh` supports the Debian/Ubuntu, Fedora, Arch and openSUSE families and stops with a clear message on others. It also works as
`curl -fsSL https://raw.githubusercontent.com/ajayks012/H2Oh/main/install.sh | sh`; read the script before piping anything into `sh`.

## Install per distro

Only PyGObject + GTK4 + libadwaita and a sound player (`pw-play` or `paplay`) are needed. Then install the app with pipx (below) or the `.deb`.

| Distro | Dependencies |
|---|---|
| Ubuntu / Debian / Mint | `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipewire-bin pipx` (optional: `gir1.2-gtk4layershell-1.0 wmctrl`) |
| Fedora | `sudo dnf install python3-gobject gtk4 libadwaita pipewire-utils pipx` (optional: `gtk4-layer-shell`) |
| Arch / Manjaro | `sudo pacman -S python-gobject gtk4 libadwaita libpipewire python-pipx` (optional: `gtk4-layer-shell`) |
| openSUSE | `sudo zypper install python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 pipewire-tools python3-pipx` |

```
git clone https://github.com/ajayks012/H2Oh && cd H2Oh
pipx install --system-site-packages .     # puts the 3 commands in ~/.local/bin
waterreminderd &                          # start now; or open Settings and turn on "Start at login"
```
Make sure `~/.local/bin` is on your `PATH`. Uninstall: `pipx uninstall waterreminder`, and delete `~/.config/autostart/waterreminder.desktop`.
Run as a service instead of autostart: `cp data/waterreminder.service ~/.config/systemd/user/ && systemctl --user enable --now waterreminder`.

## Test it locally (step by step, nothing installed system-wide)

Everything below runs from the checkout. Use a throwaway config so your real settings are never touched.

**Step 1: Create a virtualenv and install the project and pytest**
```
uv venv --system-site-packages .venv      # or: python3 -m venv --system-site-packages .venv   (needs python3-venv)
uv pip install -e . pytest                # or: .venv/bin/pip install -e . pytest
```
`--system-site-packages` lets the venv see the distro's PyGObject (GTK4 cannot be pip-installed easily). `-e` means edits to `src/` take effect immediately.
Expected: no errors; `.venv/bin/waterreminderd` now exists.

**Step 2: Run the unit tests**
```
.venv/bin/pytest
```
What it checks: the scheduler (outside hours, day boundaries, weekends, interval longer than the work window, pause, resume after a long suspend never bursts) and config handling (missing file, invalid TOML, bad values, round-trip).
Expected: `24 passed`. No GUI needed.

**Step 3: Point the app at a test config**
```
export WATERREMINDER_CONFIG=/tmp/wr-test.toml
```
All three commands now read/write this file instead of `~/.config/waterreminder/config.toml`. Set it again in each new terminal.

**Step 4: Try the popup and sound alone**
```
.venv/bin/waterreminder-popup --timeout 10
```
What it does: opens the big popup, plays the sound, and prints one word when it closes.
Try: click *I drank water* (prints `done`), press Enter (`done`), press Esc (`snooze`), click *Skip* (`skip`), or wait 10 s (`missed`).
Add `--no-sound` to silence it, `--message "Hi"` to change the text.

**Step 5: Try the settings window**
```
.venv/bin/waterreminder-settings
```
What it does: edits the test config. Every change is saved immediately. Use *Preview sound* and *Show now* to test the sound and popup. Then run `cat /tmp/wr-test.toml` to see the saved values.

**Step 6: Run the daemon on a 1-minute schedule**
Create the test config (or set the same values in the settings window):
```
cat > /tmp/wr-test.toml <<'EOT'
days = [0,1,2,3,4,5,6]
start = "00:00"
end = "23:59"
interval_min = 1
snooze_min = 1
EOT
.venv/bin/waterreminderd
```
What it does: starts the background daemon (it logs to the terminal). Within about a minute a popup and sound appear, and the log shows `firing reminder` then `popup result: ...`.
- *Snooze*: the popup returns after 1 minute (`snooze_min`).
- *Skip* or letting it time out: it waits for the next 1-minute slot.
- *I drank water*: the counter goes up (`cat ~/.local/state/waterreminder/stats.toml`).

**Step 7: Check live config reload** (while the daemon runs, in a second terminal)
```
sed -i 's/interval_min = 1/interval_min = 2/' /tmp/wr-test.toml     # or edit it in the settings window
```
Expected: the daemon log prints `config loaded` within a second, with no restart. `pkill -HUP -f waterreminderd` does the same.

**Step 8: Check single instance**
```
.venv/bin/waterreminderd
```
Expected (while the first is running): `waterreminderd is already running`, exit code 1.

**Step 9: Simulate suspend/resume** (no real suspend needed)
```
PID=$(pgrep -f bin/waterreminderd); kill -STOP $PID     # "sleep": the process freezes
# wait 3-4 minutes, then:
kill -CONT $PID                                          # "resume"
```
Expected: at most ONE alert right after resuming (only if a slot was missed less than 5 minutes ago), then the normal schedule; never one popup per missed slot.

**Step 10: Check nothing fires outside your schedule**
Set `days = []` (or `end` earlier than the current time) in `/tmp/wr-test.toml` and wait a few minutes. Expected: no `firing reminder` lines.

**Step 11: Measure memory**
```
grep -E '^(Rss|Pss):' /proc/$(pgrep -f bin/waterreminderd)/smaps_rollup
```
Expected: Rss around 30 MB, Pss around 17 MB (see Known limitations).

**Step 12: Clean up**
```
pkill -f waterreminderd; unset WATERREMINDER_CONFIG; rm -f /tmp/wr-test.toml
```

## Uninstall

1. **Stop it**: `pkill -f waterreminderd` (the tray menu's *Quit* also works).
2. **Remove the app**, using whichever way you installed it:
   - install script: `./install.sh --uninstall`
   - pipx: `pipx uninstall waterreminder`
   - `.deb`: `sudo apt remove waterreminder`
   - dev checkout: delete the folder (and its `.venv`)
   - Flatpak: `flatpak uninstall io.github.waterreminder.WaterReminder`
3. **Remove autostart** (if enabled): `rm -f ~/.config/autostart/waterreminder.desktop`, or turn off *Start at login* in settings before uninstalling.
   If you used the systemd unit: `systemctl --user disable --now waterreminder && rm ~/.config/systemd/user/waterreminder.service`.
4. **Optional, delete your data**: `rm -rf ~/.config/waterreminder ~/.local/state/waterreminder` (settings and the daily counter; uninstalling keeps them).
5. **Optional, remove the distro packages** the installer added (python3-gi, GTK4, libadwaita, pipx): only if nothing else uses them, e.g. `sudo apt autoremove`.

## After installing: launch and first-time setup

1. **Open Settings**: search for **H2Oh!** in your applications menu (the install script adds it; log out and in if it does not show up yet),
   or run `waterreminder-settings` in a terminal. If the command is not found, open a new terminal or run `export PATH="$HOME/.local/bin:$PATH"`.
   The `.deb` also adds the menu entry. A plain `pipx install` does not, so use `./install.sh` or the terminal command.
2. **Set your schedule**: work days, start/end time, interval, snooze and sound. Every change saves immediately.
3. **Check it works**: click *Show now* in Settings (or run `waterreminder-popup --test`). You should see the big popup and hear the sound.
4. **Start the reminders**: Settings does not run them, the background daemon does.
   - Easiest: turn on *Start at login* in Settings (or answer Y in the installer), then log out and back in.
   - Or right now: `waterreminderd &`
   - Check it is running: `pgrep -af waterreminderd`
5. **Wait for the next slot**: the first popup appears at your next scheduled time (default Mon-Fri, 09:00-18:00, every 45 min).
   To see one quickly, set the interval to 1 minute while testing.
6. **Pause or quit**: use the tray menu if your desktop shows it (Pause 1 h / until tomorrow, Settings, Quit), or the *Pause* buttons in Settings, or `pkill -f waterreminderd`.

If nothing appears, see *Known limitations* below. The most common causes are the daemon not running, being outside your work hours or days, or a paused/disabled setting.

## Use
```
waterreminderd &              # start the daemon (or enable "Start at login" in settings)
waterreminder-settings        # configure; also in the app launcher
waterreminder-popup --test    # show the popup now
```
Config: `~/.config/waterreminder/config.toml` (written with defaults if missing; an invalid file is logged and defaults are used,
the file is never overwritten). Override the path with `WATERREMINDER_CONFIG`. Daily counter: `~/.local/state/waterreminder/stats.toml`.
Popup keys: **Enter** = I drank water, **Esc** = snooze. Auto-dismiss counts as "missed". Reduced motion (`gtk-enable-animations=false`) disables the pulse.

## How scheduling is robust
`scheduler.py` is pure (config + `now` -> datetimes, unit-tested). The daemon re-reads the **wall clock every 10 s**
(not one long timer) and asks for the latest slot in `(last_check, now]`. After suspend/clock change this yields at most
**one** alert, and only if that slot is less than 5 min old; otherwise the missed slots are dropped. Nothing fires outside
work days/hours or while paused. Snooze re-fires after the snooze time; Skip/missed wait for the next slot.
Single instance via `flock` on `$XDG_RUNTIME_DIR/waterreminder.lock`. Skip-while-locked uses logind `LockedHint`; idle uses
GNOME's Mutter IdleMonitor; both degrade silently if unavailable. A deferred alert fires once when you return, if still in hours.

## Decisions / deviations
- Product name is **H2Oh!**; the technical names (package `waterreminder`, commands `waterreminderd`/`waterreminder-popup`/`waterreminder-settings`, config dir, icon name) are unchanged so existing installs and configs keep working.
- Own tiny TOML writer instead of `tomli-w` (zero extra deps).
- Sounds/icon live in `src/waterreminder/data/` (not top-level `data/`) so they ship inside the wheel; `data/` holds desktop/service files. Sounds are synthesised by `tools/gen_sounds.sh` (ffmpeg), public domain.
- Alerts on GNOME or X11 also send an `org.freedesktop.Notifications` notification (closed when the popup is answered), and any popup crash falls back to it.
- Overnight work windows (end earlier than start) are **not** supported; a window must lie within one day.
- Tray is a hand-rolled StatusNotifierItem + dbusmenu over Gio (no extra libs).

## Tested here / not tested
Tested on Ubuntu GNOME **Wayland** (Python 3.14): unit tests, daemon + popup + sound, config reload (monitor and SIGHUP), single instance, settings window starts, SIGSTOP/SIGCONT resume, `.deb` builds.
**Not tested**: layer-shell overlay and corner positions (typelib not installed here), X11 session, keep-above via `wmctrl`, Flatpak build, tray rendering on KDE, idle detection on non-GNOME, real suspend.

## Known limitations
- **GNOME Wayland**: no layer-shell, so the popup is a normal window: GNOME may open it without focus (Enter/Esc need a click first) and cannot be forced on top or positioned; that is why the notification fallback exists.
- **Tray**: GNOME needs the AppIndicator/KStatusNotifierItem extension; without a host the tray is silently skipped and everything else works. Tray setting needs a daemon restart.
- Flatpak: in-app autostart writes an XDG file only; the Background portal path is not wired up.
- Idle memory (measured, Python 3.14, GNOME): RSS ≈ 32 MB, of which ~17 MB is shared library file pages; PSS ≈ 17 MB, anonymous ≈ 15 MB. Importing `gi` alone costs ~15 MB of RSS, so the ~25 MB RSS target is not reachable with PyGObject; the daemon imports no GTK.

## Development
`uv venv --system-site-packages .venv && uv pip install -e . pytest && .venv/bin/pytest`
