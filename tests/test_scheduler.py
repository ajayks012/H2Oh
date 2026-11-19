from datetime import datetime as D, timedelta

from waterreminder.config import Config
from waterreminder.scheduler import due_slot, in_work_hours, next_fire, slots_for_day

MON = D(2026, 11, 16)  # a Monday
cfg = lambda **k: Config(**{"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00", "interval_min": 45, **k})


def test_slots_first_at_start():
    s = slots_for_day(cfg(), MON.date())
    assert s[0] == MON.replace(hour=9) and s[1] == MON.replace(hour=9, minute=45)
    assert all(x <= MON.replace(hour=18) for x in s)


def test_slots_first_after_interval():
    assert slots_for_day(cfg(first_at_start=False), MON.date())[0] == MON.replace(hour=9, minute=45)


def test_end_is_inclusive():
    s = slots_for_day(cfg(interval_min=60), MON.date())
    assert s[-1] == MON.replace(hour=18)


def test_non_work_day_has_no_slots():
    assert slots_for_day(cfg(), D(2026, 11, 21).date()) == []  # Saturday


def test_next_outside_hours_before_start():
    assert next_fire(cfg(), MON.replace(hour=7)) == MON.replace(hour=9)


def test_next_after_end_rolls_to_next_day():
    assert next_fire(cfg(), MON.replace(hour=19)) == D(2026, 11, 17, 9)


def test_friday_evening_rolls_to_monday():
    assert next_fire(cfg(), D(2026, 11, 20, 19)) == D(2026, 11, 23, 9)


def test_strictly_after_now():
    assert next_fire(cfg(), MON.replace(hour=9)) == MON.replace(hour=9, minute=45)


def test_interval_longer_than_window():
    c = cfg(interval_min=600)
    assert slots_for_day(c, MON.date()) == [MON.replace(hour=9)]
    assert next_fire(c, MON.replace(hour=10)) == D(2026, 11, 17, 9)
    assert slots_for_day(cfg(interval_min=600, first_at_start=False), MON.date()) == []


def test_disabled_or_no_days():
    assert next_fire(cfg(enabled=False), MON) is None
    assert next_fire(cfg(days=[]), MON) is None


def test_pause_until_tomorrow():
    c = cfg(paused_until="2026-11-17T00:00:00")
    assert next_fire(c, MON.replace(hour=10)) == D(2026, 11, 17, 9)


def test_in_work_hours():
    assert in_work_hours(cfg(), MON.replace(hour=12))
    assert not in_work_hours(cfg(), MON.replace(hour=20))
    assert not in_work_hours(cfg(), D(2026, 11, 21, 12))


def test_due_normal_tick():
    assert due_slot(cfg(), MON.replace(hour=9, minute=44, second=55), MON.replace(hour=9, minute=45, second=5)) == MON.replace(hour=9, minute=45)


def test_due_nothing_between_slots():
    assert due_slot(cfg(), MON.replace(hour=10), MON.replace(hour=10, minute=1)) is None


def test_resume_after_long_suspend_no_burst():
    # asleep 09:00 -> 17:00: 12 slots missed; stale ones are dropped, not replayed
    assert due_slot(cfg(), MON.replace(hour=9, minute=1), MON.replace(hour=17)) is None


def test_resume_shortly_after_missed_slot_fires_once():
    last, now = MON.replace(hour=9, minute=40), MON.replace(hour=12, minute=2)  # slot 12:00 was 2 min ago
    assert due_slot(cfg(), last, now) == MON.replace(hour=12)


def test_resume_overnight_outside_hours():
    assert due_slot(cfg(), MON.replace(hour=17), D(2026, 11, 17, 7)) is None


def test_clock_goes_backwards():
    assert due_slot(cfg(), MON.replace(hour=12), MON.replace(hour=9)) is None


def test_due_respects_pause_and_disabled():
    last, now = MON.replace(hour=9, minute=44), MON.replace(hour=9, minute=45, second=3)
    assert due_slot(cfg(enabled=False), last, now) is None
    assert due_slot(cfg(paused_until="2026-11-16T12:00:00"), last, now) is None
