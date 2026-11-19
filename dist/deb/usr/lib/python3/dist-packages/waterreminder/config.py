"""Config: TOML at ~/.config/waterreminder/config.toml. Stdlib only; load() never raises."""
import logging
import os
import tomllib
from dataclasses import dataclass, field, fields
from datetime import time
from pathlib import Path

log = logging.getLogger("waterreminder")

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "waterreminder"
CONFIG_PATH = Path(os.environ.get("WATERREMINDER_CONFIG", CONFIG_DIR / "config.toml"))
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "waterreminder"

SOUNDS = ("drop", "chime", "bell")
POSITIONS = ("center", "top-right", "bottom-right", "top-left", "bottom-left")


@dataclass
class Config:
    enabled: bool = True
    days: list = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon=0
    start: str = "09:00"
    end: str = "18:00"
    interval_min: int = 45
    first_at_start: bool = True  # False: first reminder at start+interval
    snooze_min: int = 5
    paused_until: str = ""  # ISO local datetime; empty = not paused
    sound_enabled: bool = True
    volume: int = 80
    sound: str = "drop"
    messages: list = field(default_factory=lambda: ["Time to drink some water!", "Stay hydrated - grab a glass of water."])
    popup_position: str = "center"
    popup_timeout_s: int = 30
    skip_when_locked: bool = True  # also defers when the user is idle (if detectable)
    idle_threshold_min: int = 0  # 0 = only screen lock is checked
    notify_fallback: bool = True
    tray: bool = True

    def start_time(self) -> time:
        return _parse_time(self.start, "09:00")

    def end_time(self) -> time:
        return _parse_time(self.end, "18:00")


def _parse_time(s, default):
    try:
        h, m = str(s).split(":")
        return time(int(h), int(m))
    except Exception:
        return time.fromisoformat(default)


def validate(c: Config) -> Config:
    """Clamp/repair values in place so downstream code can trust them."""
    d = Config()
    c.enabled = bool(c.enabled)
    c.days = sorted({int(x) for x in c.days if str(x).isdigit() or isinstance(x, int) if 0 <= int(x) <= 6}) if isinstance(c.days, list) else d.days
    for k in ("start", "end"):
        t = _parse_time(getattr(c, k), getattr(d, k))
        setattr(c, k, f"{t.hour:02d}:{t.minute:02d}")
    c.interval_min = max(1, min(int(c.interval_min), 24 * 60))
    c.snooze_min = max(1, min(int(c.snooze_min), 240))
    c.volume = max(0, min(int(c.volume), 100))
    c.popup_timeout_s = max(5, min(int(c.popup_timeout_s), 600))
    c.idle_threshold_min = max(0, min(int(c.idle_threshold_min), 240))
    if c.sound not in SOUNDS:
        c.sound = d.sound
    if c.popup_position not in POSITIONS:
        c.popup_position = d.popup_position
    if not isinstance(c.messages, list) or not [m for m in c.messages if str(m).strip()]:
        c.messages = d.messages
    c.messages = [str(m) for m in c.messages if str(m).strip()]
    c.paused_until = str(c.paused_until or "")
    return c


def from_dict(data: dict) -> Config:
    """Unknown keys ignored; a bad value falls back to the default for that key only."""
    c = Config()
    for f in fields(Config):
        if f.name in data:
            old = getattr(c, f.name)
            setattr(c, f.name, data[f.name])
            try:
                validate(Config(**{**c.__dict__}))
            except Exception:
                log.error("config: invalid value for %r, using default", f.name)
                setattr(c, f.name, old)
    try:
        return validate(c)
    except Exception:  # pragma: no cover - belt and braces
        return Config()


def _toml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_val(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def dumps(c: Config) -> str:
    return "".join(f"{k} = {_toml_val(v)}\n" for k, v in c.__dict__.items())


def save(c: Config, path: Path = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dumps(c))
    os.replace(tmp, path)  # atomic: the daemon's file monitor never sees a half-written file


def load(path: Path = None) -> Config:
    """Missing file -> write defaults. Invalid file -> log, keep file untouched, use defaults."""
    path = path or CONFIG_PATH
    try:
        with open(path, "rb") as f:
            return from_dict(tomllib.load(f))
    except FileNotFoundError:
        c = Config()
        try:
            save(c, path)
        except OSError as e:
            log.error("config: cannot write defaults to %s: %s", path, e)
        return c
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        log.error("config: cannot read %s (%s); using defaults", path, e)
        return Config()


# --- daily "drank" counter (state, not config) ---
def _stats_file() -> Path:
    return STATE_DIR / "stats.toml"


def read_count(today: str) -> int:
    try:
        with open(_stats_file(), "rb") as f:
            d = tomllib.load(f)
        return int(d["count"]) if d.get("date") == today else 0
    except Exception:
        return 0


def add_count(today: str) -> int:
    n = read_count(today) + 1
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _stats_file().write_text(f'date = "{today}"\ncount = {n}\n')
    except OSError as e:
        log.error("stats: cannot write: %s", e)
    return n
