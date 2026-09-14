"""Stage 6: the only code path that writes to `predictions`. Compliance is enforced here.

Publish reads analyses from `llm_outputs`, not from the analyze stage's return value, so the
two stages can run in separate processes and nothing analyzed is ever lost. Every event it
handles gets `published_at` set, even when it yields no predictions.
"""

from __future__ import annotations

import logging

import psycopg

from fibr0 import compliance
from fibr0.config import Settings
from fibr0.models import AnalysisResult, Event, Prediction, Slot
from fibr0.stages import score

log = logging.getLogger(__name__)


def build_predictions(
    event: Event,
    result: AnalysisResult,
    calibration: dict,
    settings: Settings,
    universe: set[str] | None = None,
) -> tuple[list[Prediction], list[str]]:
    """Convert one analysis into publishable predictions. Returns (kept, blocked_reasons).

    `universe` is the set of active tickers. Impacts on unknown tickers are blocked because
    predictions.ticker is a foreign key. None skips the check (tests only).
    """
    kept: list[Prediction] = []
    blocked: list[str] = []
    banned_in_summary = compliance.find_banned(result.rationale_summary)
    if banned_in_summary:
        blocked.append(f"event {event.id}: summary contains {banned_in_summary}")
        return kept, blocked
    for impact in result.impacts:
        ticker = impact.ticker.upper().strip()
        if ticker == settings.benchmark_ticker:
            # Confidence is defined net of the benchmark; a prediction on it is circular.
            blocked.append(f"event {event.id} {ticker}: benchmark ticker is never a target")
            continue
        if universe is not None and ticker not in universe:
            blocked.append(f"event {event.id} {ticker}: not in ticker universe")
            continue
        banned = compliance.find_banned(impact.rationale)
        if banned:
            blocked.append(f"event {event.id} {ticker}: rationale contains {banned}")
            continue
        confidence, is_calibrated = score.calibrate(
            impact.confidence,
            result.category,
            impact.horizon,
            calibration,
            settings.min_resolved_for_calibration,
            event.tier3_only,
            settings.tier3_confidence_cap,
        )
        kept.append(
            Prediction(
                event_id=event.id,
                ticker=ticker,
                direction=impact.direction,
                horizon=impact.horizon,
                magnitude=impact.magnitude,
                order=impact.order,
                raw_confidence=round(impact.confidence, 3),
                calibrated_confidence=confidence,
                is_calibrated=is_calibrated,
                rationale_summary=result.rationale_summary,
                source_urls=event.source_urls,
                slot=event.slot,
            )
        )
    return kept, blocked


def load_unpublished(conn: psycopg.Connection) -> list[tuple[Event, AnalysisResult]]:
    """Analyzed events that publish has not yet handled. Latest output per event wins."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (e.id)
                   e.id, e.slot, e.title, e.text_for_analysis, e.source_urls, e.source_tiers,
                   o.parsed
            from events e join llm_outputs o on o.event_id = e.id
            where e.published_at is null
            order by e.id, o.id desc
            """
        )
        rows = cur.fetchall()
    pairs: list[tuple[Event, AnalysisResult]] = []
    for row in rows:
        parsed = row.pop("parsed")
        pairs.append((Event(**row), AnalysisResult.model_validate(parsed)))
    return pairs


def store(
    conn: psycopg.Connection,
    slot: Slot,
    predictions: list[Prediction],
    handled: list[tuple[Event, AnalysisResult]],
) -> int:
    with conn.cursor() as cur:
        for event, result in handled:
            cur.execute(
                "update events set category = %s, event_summary = %s, published_at = now() "
                "where id = %s",
                (result.category, result.event_summary, event.id),
            )
        if not predictions:
            return 0
        cur.execute("insert into digests (slot) values (%s) returning id", (slot.value,))
        digest_id = cur.fetchone()["id"]
        cur.executemany(
            """
            insert into predictions (digest_id, event_id, ticker, direction, horizon, magnitude,
                impact_order, raw_confidence, calibrated_confidence, is_calibrated,
                rationale_summary, source_urls)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    digest_id,
                    p.event_id,
                    p.ticker,
                    p.direction,
                    p.horizon,
                    p.magnitude,
                    p.order,
                    p.raw_confidence,
                    p.calibrated_confidence,
                    p.is_calibrated,
                    p.rationale_summary,
                    p.source_urls,
                )
                for p in predictions
            ],
        )
        return cur.rowcount


def run(conn: psycopg.Connection, slot: Slot, settings: Settings) -> int:
    pending = load_unpublished(conn)
    if not pending:
        log.info("publish: nothing analyzed and unpublished")
        return 0
    calibration = score.load_calibration(conn)
    with conn.cursor() as cur:
        cur.execute("select ticker from ticker_universe where active")
        universe = {row["ticker"] for row in cur.fetchall()}
    all_kept: list[Prediction] = []
    for event, result in pending:
        kept, blocked = build_predictions(event, result, calibration, settings, universe)
        for reason in blocked:
            log.warning("blocked: %s", reason)
        all_kept.extend(kept)
    log.info("publish: events=%d predictions=%d", len(pending), len(all_kept))
    if settings.dry_run:
        return 0
    return store(conn, slot, all_kept, pending)
