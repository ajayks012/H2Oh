"""Pure scheduling logic: config + wall-clock `now` in, datetimes out. No GTK/GLib."""
from datetime import datetime, timedelta

from .config import Config

CATCHUP_GRACE = timedelta(minutes=5)


def slots_for_day(cfg: Config, day) -> list:
    """All reminder datetimes (naive local) on `day`, or [] if not a work day."""
    if day.weekday() not in cfg.days:
        return []
    first = datetime.combine(day, cfg.start_time())
    end = datetime.combine(day, cfg.end_time())
    step = timedelta(minutes=cfg.interval_min)
    t = first if cfg.first_at_start else first + step
    out = []
    while t <= end:  # end < start (wrap past midnight) yields no slots: unsupported, see README
        out.append(t)
        t += step
    return out


def _pause_floor(cfg: Config):
    try:
        return datetime.fromisoformat(cfg.paused_until) if cfg.paused_until else None
    except ValueError:
        return None


def next_fire(cfg: Config, now: datetime):
    """First slot strictly after `now` (and after any pause), or None."""
    if not cfg.enabled or not cfg.days:
        return None
    floor = _pause_floor(cfg)
    for i in range(8):
        for s in slots_for_day(cfg, now.date() + timedelta(days=i)):
            if s > now and (floor is None or s >= floor):
                return s
    return None


def due_slot(cfg: Config, last_check: datetime, now: datetime):
    """Slot to fire now, given the previous check time. At most ONE, never a burst.

    Returns the latest slot in (last_check, now], but only if it is fresh
    (within CATCHUP_GRACE); a stale one after a long suspend is dropped.
    A clock that went backwards (now <= last_check) yields None.
    """
    if not cfg.enabled or now <= last_check:
        return None
    floor = _pause_floor(cfg)
    best = None
    for d in {last_check.date(), now.date()}:
        for s in slots_for_day(cfg, d):
            if last_check < s <= now and (floor is None or s >= floor):
                best = max(best, s) if best else s
    if best and now - best <= CATCHUP_GRACE:
        return best
    return None


def in_work_hours(cfg: Config, now: datetime) -> bool:
    if not cfg.enabled or now.weekday() not in cfg.days:
        return False
    return cfg.start_time() <= now.time() <= cfg.end_time()


def paused(cfg: Config, now: datetime) -> bool:
    floor = _pause_floor(cfg)
    return floor is not None and now < floor
