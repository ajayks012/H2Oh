#!/bin/sh
# H2Oh! installer. Run from a checkout:  ./install.sh
# Or remotely (inspect it first!):  curl -fsSL https://raw.githubusercontent.com/ajayks012/H2Oh/main/install.sh | sh
# Flags: --uninstall   remove the app and its autostart entry (config in ~/.config/waterreminder is kept)
set -eu

REPO="${REPO:-https://github.com/ajayks012/H2Oh}"   # used when run outside a checkout (e.g. via curl)

say() { printf '    %s\n' "$*"; }
N=0; TOTAL=7
step() { N=$((N+1)); printf '\n[%s/%s] %s\n' "$N" "$TOTAL" "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
SUDO=""
if [ "$(id -u)" -ne 0 ]; then command -v sudo >/dev/null || die "sudo not found: run as root or install sudo"; SUDO="sudo"; fi

if [ "${1:-}" = "--uninstall" ]; then
  pipx uninstall waterreminder 2>/dev/null || true
  rm -f "$HOME/.config/autostart/waterreminder.desktop"
  say "removed (config kept in ~/.config/waterreminder)"; exit 0
fi

step "Detecting your Linux distribution"
[ -r /etc/os-release ] || die "cannot detect distro (no /etc/os-release)"
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
  *" debian "*|*" ubuntu "*)  say "Found: Debian/Ubuntu family"
    step "Installing system packages (GTK4, libadwaita, PyGObject, sound player, pipx); sudo may ask for your password"
    $SUDO apt-get update -qq || say "apt-get update failed, continuing"
    $SUDO apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipewire-bin pipx
    $SUDO apt-get install -y gir1.2-gtk4layershell-1.0 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" fedora "*|*" rhel "*)    say "Found: Fedora family"
    step "Installing system packages (GTK4, libadwaita, PyGObject, sound player, pipx); sudo may ask for your password"
    $SUDO dnf install -y python3-gobject gtk4 libadwaita pipewire-utils pipx
    $SUDO dnf install -y gtk4-layer-shell 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" arch "*)                 say "Found: Arch family"
    step "Installing system packages (GTK4, libadwaita, PyGObject, sound player, pipx); sudo may ask for your password"
    $SUDO pacman -S --needed --noconfirm python-gobject gtk4 libadwaita libpipewire python-pipx
    $SUDO pacman -S --needed --noconfirm gtk4-layer-shell 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" suse "*|*" opensuse "*)  say "Found: openSUSE family"
    step "Installing system packages (GTK4, libadwaita, PyGObject, sound player, pipx); sudo may ask for your password"
    $SUDO zypper --non-interactive install python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 pipewire-tools python3-pipx ;;
  *) die "unsupported distro '${ID:-?}': install PyGObject, GTK4, libadwaita, pw-play/paplay and pipx manually (see README)" ;;
esac
say "OK: system packages installed"

# Inside a checkout install that; otherwise install from $REPO.
if [ -f "$0" ] && [ -f "$(dirname "$0")/pyproject.toml" ]; then SRC="$(cd "$(dirname "$0")" && pwd)"
elif [ -n "$REPO" ]; then SRC="git+$REPO"
else die "no REPO set"; fi

step "Installing H2Oh! with pipx from $SRC"
pipx install --force --system-site-packages "$SRC"   # system site packages: PyGObject comes from the distro
step "Making sure ~/.local/bin is on your PATH"
pipx ensurepath || true

step "Verifying the install"
BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || true)"; BIN="${BIN:-$HOME/.local/bin}"
[ -x "$BIN/waterreminderd" ] || die "install finished but $BIN/waterreminderd is missing; see the pipx output above"
say "OK: commands found in $BIN"

step "Autostart at login"
printf '    Start H2Oh! at login? [Y/n] '
{ read -r a </dev/tty; } 2>/dev/null || a=y
case "$a" in [nN]*) ;; *)
  mkdir -p "$HOME/.config/autostart"
  printf '[Desktop Entry]\nType=Application\nName=H2Oh!\nExec=%s/waterreminderd\nIcon=waterreminder\nNoDisplay=true\n' "$BIN" > "$HOME/.config/autostart/waterreminder.desktop"
  say "OK: wrote ~/.config/autostart/waterreminder.desktop" ;;
esac
[ -f "$HOME/.config/autostart/waterreminder.desktop" ] || say "Skipped autostart (turn it on later in Settings)"

step "Done. Summary"
say "Installed commands : $BIN/waterreminderd  $BIN/waterreminder-popup  $BIN/waterreminder-settings"
say "Config (created on first run): ~/.config/waterreminder/config.toml"
say "Start now            : $BIN/waterreminderd &"
say "Settings             : $BIN/waterreminder-settings"
say "Test the popup       : $BIN/waterreminder-popup --test"
say "Uninstall            : ./install.sh --uninstall   (or: pipx uninstall waterreminder)"
say "If a command is not found, open a new terminal so the updated PATH applies."
