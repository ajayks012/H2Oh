"""Non-blocking sound playback via pw-play / paplay (libcanberra as last resort). No GStreamer."""
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("waterreminder")
DATA = Path(__file__).parent / "data"


def sound_path(name: str) -> Path:
    return DATA / "sounds" / f"{name}.ogg"


def is_muted() -> bool:
    """True if the default sink is muted. Unknown (no tools) counts as not muted."""
    for cmd in (["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], ["pactl", "get-sink-mute", "@DEFAULT_SINK@"]):
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            return "MUTED" in out or "yes" in out.lower()
    return False


def play(cfg) -> bool:
    """Start playing the configured sound; returns immediately. True if a player was started."""
    if not cfg.sound_enabled or cfg.volume <= 0 or is_muted():
        return False
    f = str(sound_path(cfg.sound))
    v = cfg.volume / 100
    for cmd in (
        ["pw-play", f"--volume={v:.2f}", f],
        ["paplay", f"--volume={int(v * 65536)}", f],
        ["canberra-gtk-play", "-f", f],
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True
            except OSError as e:
                log.error("audio: %s failed: %s", cmd[0], e)
    log.error("audio: no player found (pw-play, paplay, canberra-gtk-play)")
    return False
