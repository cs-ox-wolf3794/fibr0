"""Stage 7: score elapsed predictions against daily closes and refresh calibration.

Realized move = ticker % change minus benchmark (XLE) % change over the horizon,
from the close before the digest to the close on the horizon's trading day.
"""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
import psycopg
import requests

from fibr0 import market_calendar as cal
from fibr0.config import Settings
from fibr0.stages.score import bucket_of

log = logging.getLogger(__name__)

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
HORIZON_DAYS = {"1d": 1, "5d": 5}


def fetch_closes(ticker: str) -> pd.Series:
    """Daily closes indexed by date. Empty series on any failure so callers can skip."""
    try:
        resp = requests.get(STOOQ_URL.format(symbol=ticker.lower()), timeout=20)
        resp.raise_for_status()
        frame = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"])
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("ticker=%s price fetch failed: %s", ticker, exc)
        return pd.Series(dtype=float)
    if "Close" not in frame:
        return pd.Series(dtype=float)
    return frame.set_index(frame["Date"].dt.date)["Close"].astype(float)


def pct_change(closes: pd.Series, start: date, end: date) -> float | None:
    if start not in closes.index or end not in closes.index:
        return None
    return (closes[end] / closes[start] - 1.0) * 100.0


def outcome(realized_pct: float, direction: str, flat_threshold: float) -> str:
    """hit, miss, or flat. Flat counts as a miss for calibration."""
    if abs(realized_pct) < flat_threshold:
        return "flat"
    went_up = realized_pct > 0
    return "hit" if went_up == (direction == "up") else "miss"


def resolution_window(published: date, horizon: str) -> tuple[date, date]:
    """(reference close date, horizon close date) for a prediction published on `published`.

    Pre-open and midday digests reference the previous close; post-close references
    that day's close. The distinction is applied by the caller through `published`.
    """
    start = published if cal.is_trading_day(published) else cal.previous_trading_day(published)
    end = cal.next_trading_day(start, HORIZON_DAYS[horizon])
    return start, end


def run(conn: psycopg.Connection, settings: Settings) -> int:
    today = date.today()
    with conn.cursor() as cur:
        cur.execute(
            """
            select p.id, p.ticker, p.direction, p.horizon, p.calibrated_confidence,
                   d.slot, (p.published_at at time zone 'America/New_York')::date as published_date,
                   e.category
            from predictions p
            join digests d on d.id = p.digest_id
            join events e on e.id = p.event_id
            left join resolutions r on r.prediction_id = p.id
            where r.id is null
            """
        )
        pending = cur.fetchall()
    if not pending:
        log.info("resolve: nothing pending")
        return 0

    benchmark = fetch_closes(settings.benchmark_ticker)
    closes_cache: dict[str, pd.Series] = {}
    resolved = 0
    for row in pending:
        published = row["published_date"]
        if row["slot"] != "post_close":
            published = cal.previous_trading_day(published)
        start, end = resolution_window(published, row["horizon"])
        if end >= today:
            continue  # horizon not yet elapsed
        closes = closes_cache.setdefault(row["ticker"], fetch_closes(row["ticker"]))
        stock_move = pct_change(closes, start, end)
        bench_move = pct_change(benchmark, start, end)
        if stock_move is None or bench_move is None:
            log.warning("prediction=%s missing prices for %s..%s", row["id"], start, end)
            continue
        realized = stock_move - bench_move
        result = outcome(realized, row["direction"], settings.flat_threshold_pct)
        if settings.dry_run:
            log.info("dry run: prediction=%s %s realized=%.2f", row["id"], result, realized)
            continue
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into resolutions (prediction_id, reference_date, horizon_date,
                    stock_move_pct, benchmark_move_pct, realized_move_pct, outcome)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (row["id"], start, end, stock_move, bench_move, realized, result),
            )
            cur.execute(
                """
                insert into calibration (category, horizon, bucket, resolved, hits)
                values (%s, %s, %s, 1, %s)
                on conflict (category, horizon, bucket) do update
                set resolved = calibration.resolved + 1,
                    hits = calibration.hits + excluded.hits,
                    updated_at = now()
                """,
                (
                    row["category"],
                    row["horizon"],
                    bucket_of(float(row["calibrated_confidence"])),
                    1 if result == "hit" else 0,
                ),
            )
        resolved += 1
    log.info("resolve: pending=%d resolved=%d", len(pending), resolved)
    return resolved
