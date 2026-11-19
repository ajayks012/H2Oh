"""XDG autostart entry for the daemon."""
import os
import shutil
import sys
from pathlib import Path

PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "waterreminder.desktop"


def is_enabled() -> bool:
    return PATH.exists()


def set_enabled(on: bool) -> None:
    if not on:
        PATH.unlink(missing_ok=True)
        return
    exe = shutil.which("waterreminderd") or f"{sys.executable} -m waterreminder.daemon"
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(
        "[Desktop Entry]\nType=Application\nName=H2Oh!\nComment=Drink-water reminders\n"
        f"Exec={exe}\nIcon=waterreminder\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n"
    )
