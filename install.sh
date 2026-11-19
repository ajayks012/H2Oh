#!/bin/sh
# H2Oh! installer. Run from a checkout:  ./install.sh
# Or remotely (inspect it first!):  curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | REPO=https://github.com/OWNER/REPO sh
# Flags: --uninstall   remove the app and its autostart entry (config in ~/.config/waterreminder is kept)
set -eu

REPO="${REPO:-}"   # set when piping from curl; ignored when run inside a checkout

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

if [ "${1:-}" = "--uninstall" ]; then
  pipx uninstall waterreminder 2>/dev/null || true
  rm -f "$HOME/.config/autostart/waterreminder.desktop"
  say "removed (config kept in ~/.config/waterreminder)"; exit 0
fi

[ -r /etc/os-release ] || die "cannot detect distro (no /etc/os-release)"
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
  *" debian "*|*" ubuntu "*)  say "Debian/Ubuntu family"
    $SUDO apt-get update -qq
    $SUDO apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipewire-bin pipx
    $SUDO apt-get install -y gir1.2-gtk4layershell-1.0 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" fedora "*|*" rhel "*)    say "Fedora family"
    $SUDO dnf install -y python3-gobject gtk4 libadwaita pipewire-utils pipx
    $SUDO dnf install -y gtk4-layer-shell 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" arch "*)                 say "Arch family"
    $SUDO pacman -S --needed --noconfirm python-gobject gtk4 libadwaita libpipewire python-pipx
    $SUDO pacman -S --needed --noconfirm gtk4-layer-shell 2>/dev/null || say "optional gtk4-layer-shell not available, skipping" ;;
  *" suse "*|*" opensuse "*)  say "openSUSE family"
    $SUDO zypper --non-interactive install python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 pipewire-tools python3-pipx ;;
  *) die "unsupported distro '${ID:-?}': install PyGObject, GTK4, libadwaita, pw-play/paplay and pipx manually (see README)" ;;
esac

# Inside a checkout install that; otherwise install from $REPO.
if [ -f "$(dirname "$0")/pyproject.toml" ] 2>/dev/null; then SRC="$(cd "$(dirname "$0")" && pwd)"
elif [ -n "$REPO" ]; then SRC="git+$REPO"
else die "run from a checkout, or set REPO=https://github.com/OWNER/REPO"; fi

say "installing from $SRC"
pipx install --force --system-site-packages "$SRC"   # system site packages: PyGObject comes from the distro
pipx ensurepath >/dev/null 2>&1 || true

BIN="$HOME/.local/bin"
printf 'Start H2Oh! at login? [Y/n] '
read -r a </dev/tty 2>/dev/null || a=y
case "$a" in [nN]*) ;; *)
  mkdir -p "$HOME/.config/autostart"
  printf '[Desktop Entry]\nType=Application\nName=H2Oh!\nExec=%s/waterreminderd\nIcon=waterreminder\nNoDisplay=true\n' "$BIN" > "$HOME/.config/autostart/waterreminder.desktop"
  say "autostart enabled" ;;
esac

say "done. Start now with:  $BIN/waterreminderd &    Settings:  $BIN/waterreminder-settings"
say "if the commands are not found, open a new terminal (PATH updated for ~/.local/bin)"
