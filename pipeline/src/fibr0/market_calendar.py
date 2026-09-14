"""US Eastern time slots and a minimal NYSE calendar.

The scheduler fires at both EDT and EST offsets for every slot (see pipeline.yml).
This module decides whether a given instant falls inside a slot window and, on
weekends and holidays, allows only the post-close slot.

Holidays are hard-coded for 2026 and 2027. Extend the set each year or replace with
pandas-market-calendars once the project is past MVP.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fibr0.models import Slot

ET = ZoneInfo("America/New_York")

SLOT_TIMES: dict[Slot, time] = {
    Slot.PRE_OPEN: time(7, 30),
    Slot.MIDDAY: time(12, 30),
    Slot.POST_CLOSE: time(17, 0),
}

# Cron drift plus the one-hour DST double-schedule means a trigger can land up to
# an hour from the target. Anything inside this window counts as that slot.
SLOT_TOLERANCE = timedelta(minutes=70)

NYSE_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
        # 2027
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 3, 26),
        date(2027, 5, 31),
        date(2027, 6, 18),
        date(2027, 7, 5),
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),
    }
)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def next_trading_day(d: date, n: int = 1) -> date:
    """The n-th trading day strictly after d."""
    current = d
    remaining = n
    while remaining > 0:
        current += timedelta(days=1)
        if is_trading_day(current):
            remaining -= 1
    return current


def previous_trading_day(d: date) -> date:
    current = d - timedelta(days=1)
    while not is_trading_day(current):
        current -= timedelta(days=1)
    return current


def slot_for(now: datetime | None = None) -> Slot | None:
    """Which slot, if any, the instant `now` belongs to. None means do nothing."""
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    today = now_et.date()
    candidates = list(SLOT_TIMES) if is_trading_day(today) else [Slot.POST_CLOSE]
    for slot in candidates:
        target = datetime.combine(today, SLOT_TIMES[slot], tzinfo=ET)
        if abs(now_et - target) <= SLOT_TOLERANCE:
            return slot
    return None
