from datetime import date

import pandas as pd
import pytest

from fibr0.stages import resolve, score
from fibr0.stages.score import CalibrationRow


def test_bucket_edges():
    assert score.bucket_of(0.5) == 0.5
    assert score.bucket_of(0.69) == 0.6
    assert score.bucket_of(0.7) == 0.7
    assert score.bucket_of(1.0) == 0.9


def test_uncalibrated_when_history_is_thin():
    rows = {("weather", "1d", 0.7): CalibrationRow("weather", "1d", 0.7, resolved=10, hits=9)}
    conf, calibrated = score.calibrate(0.72, "weather", "1d", rows, 50, False, 0.6)
    assert (conf, calibrated) == (0.72, False)


def test_calibrated_uses_observed_hit_rate():
    rows = {("weather", "1d", 0.7): CalibrationRow("weather", "1d", 0.7, resolved=80, hits=52)}
    conf, calibrated = score.calibrate(0.72, "weather", "1d", rows, 50, False, 0.6)
    assert calibrated
    assert conf == 0.65


def test_tier3_cap_applies_after_calibration():
    conf, _ = score.calibrate(0.9, "geopolitical", "1d", {}, 50, True, 0.6)
    assert conf == 0.6


def test_outcome_flat_and_direction():
    assert resolve.outcome(0.2, "up", 0.5) == "flat"
    assert resolve.outcome(1.4, "up", 0.5) == "hit"
    assert resolve.outcome(-1.4, "up", 0.5) == "miss"
    assert resolve.outcome(-1.4, "down", 0.5) == "hit"


def test_pct_change_and_window():
    closes = pd.Series({date(2026, 9, 11): 100.0, date(2026, 9, 14): 103.0})
    assert resolve.pct_change(closes, date(2026, 9, 11), date(2026, 9, 14)) == pytest.approx(3.0)
    assert resolve.pct_change(closes, date(2026, 9, 10), date(2026, 9, 14)) is None
    # Published on a Sunday: reference the prior Friday, 1d horizon lands on Monday.
    assert resolve.resolution_window(date(2026, 9, 13), "1d") == (
        date(2026, 9, 11),
        date(2026, 9, 14),
    )
