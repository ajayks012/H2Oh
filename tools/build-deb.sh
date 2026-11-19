#!/bin/sh
# Builds dist/waterreminder_<ver>_all.deb with plain dpkg-deb (no pip needed).
set -e
cd "$(dirname "$0")/.."
ver=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
root=dist/deb; rm -rf "$root"
lib=$root/usr/lib/python3/dist-packages
mkdir -p "$lib" "$root/usr/bin" "$root/usr/share/applications" "$root/usr/share/icons/hicolor/scalable/apps" "$root/usr/lib/systemd/user" "$root/DEBIAN"
cp -r src/waterreminder "$lib/"; find "$lib" -name __pycache__ -prune -exec rm -rf {} +
for pair in waterreminderd:daemon waterreminder-popup:popup waterreminder-settings:settings; do
  printf '#!/usr/bin/python3\nfrom waterreminder.%s import main\nimport sys\nsys.exit(main())\n' "${pair#*:}" > "$root/usr/bin/${pair%%:*}"
  chmod 755 "$root/usr/bin/${pair%%:*}"
done
cp data/waterreminder.desktop "$root/usr/share/applications/"
cp data/waterreminder.svg "$root/usr/share/icons/hicolor/scalable/apps/"
sed 's#%h/.local/bin#/usr/bin#' data/waterreminder.service > "$root/usr/lib/systemd/user/waterreminder.service"
cat > "$root/DEBIAN/control" <<CTL
Package: waterreminder
Version: $ver
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pipewire-bin | pulseaudio-utils
Recommends: libgtk4-layer-shell0, gir1.2-gtk4layershell-1.0
Maintainer: H2Oh! <noreply@example.invalid>
Description: Drink-water reminder with a big popup and sound
 Reminds you to drink water during configured work hours.
CTL
dpkg-deb --root-owner-group --build "$root" "dist/waterreminder_${ver}_all.deb"
