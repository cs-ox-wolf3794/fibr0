"""Stage 5: turn the model's raw confidence into a calibrated one.

Calibration rows hold, per (category, horizon, bucket), how often past predictions in that
bucket were right. With enough history the published confidence is that observed hit rate.
Without it the raw score is published and labelled uncalibrated.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import psycopg

log = logging.getLogger(__name__)

BUCKET_WIDTH = 0.1


@dataclass(frozen=True)
class CalibrationRow:
    category: str
    horizon: str
    bucket: float  # lower edge, e.g. 0.6 for [0.6, 0.7)
    resolved: int
    hits: int

    @property
    def hit_rate(self) -> float:
        return self.hits / self.resolved if self.resolved else 0.0


def bucket_of(confidence: float) -> float:
    """Lower edge of the confidence bucket. 1.0 folds into the top bucket."""
    # The epsilon keeps 0.7 in the 0.7 bucket; 0.7 / 0.1 is 6.999... in binary floating point.
    tenths = math.floor(min(confidence, 0.999) * 10 + 1e-9)
    return round(tenths * BUCKET_WIDTH, 1)


def calibrate(
    raw_confidence: float,
    category: str,
    horizon: str,
    rows: dict[tuple[str, str, float], CalibrationRow],
    min_resolved: int,
    tier3_only: bool,
    tier3_cap: float,
) -> tuple[float, bool]:
    """Return (published_confidence, is_calibrated)."""
    key = (category, horizon, bucket_of(raw_confidence))
    row = rows.get(key)
    if row and row.resolved >= min_resolved:
        confidence, calibrated = max(0.5, min(1.0, row.hit_rate)), True
    else:
        confidence, calibrated = raw_confidence, False
    if tier3_only:
        confidence = min(confidence, tier3_cap)
    return round(confidence, 3), calibrated


def load_calibration(conn: psycopg.Connection) -> dict[tuple[str, str, float], CalibrationRow]:
    with conn.cursor() as cur:
        cur.execute("select category, horizon, bucket, resolved, hits from calibration")
        rows = [CalibrationRow(**r) for r in cur.fetchall()]
    return {(r.category, r.horizon, r.bucket): r for r in rows}
