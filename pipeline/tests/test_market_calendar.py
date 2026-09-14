from datetime import date, datetime

from fibr0 import market_calendar as cal
from fibr0.models import Slot


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=cal.ET)


def test_trading_day_rules():
    assert cal.is_trading_day(date(2026, 9, 14))  # Monday
    assert not cal.is_trading_day(date(2026, 9, 13))  # Sunday
    assert not cal.is_trading_day(date(2026, 11, 26))  # Thanksgiving


def test_next_and_previous_trading_day_skip_weekends_and_holidays():
    assert cal.next_trading_day(date(2026, 9, 11)) == date(2026, 9, 14)
    assert cal.next_trading_day(date(2026, 11, 25), 1) == date(2026, 11, 27)
    assert cal.next_trading_day(date(2026, 9, 14), 5) == date(2026, 9, 21)
    assert cal.previous_trading_day(date(2026, 9, 14)) == date(2026, 9, 11)


def test_slots_on_a_trading_day():
    assert cal.slot_for(et(2026, 9, 14, 7, 30)) == Slot.PRE_OPEN
    assert cal.slot_for(et(2026, 9, 14, 12, 35)) == Slot.MIDDAY
    assert cal.slot_for(et(2026, 9, 14, 17, 0)) == Slot.POST_CLOSE


def test_dst_double_schedule_lands_inside_tolerance():
    # The EST cron line fires an hour late during EDT; it must still map to the slot.
    assert cal.slot_for(et(2026, 9, 14, 8, 30)) == Slot.PRE_OPEN
    assert cal.slot_for(et(2026, 9, 14, 18, 0)) == Slot.POST_CLOSE


def test_no_slot_between_windows():
    assert cal.slot_for(et(2026, 9, 14, 10, 0)) is None


def test_weekend_only_post_close():
    assert cal.slot_for(et(2026, 9, 13, 7, 30)) is None
    assert cal.slot_for(et(2026, 9, 13, 17, 0)) == Slot.POST_CLOSE
