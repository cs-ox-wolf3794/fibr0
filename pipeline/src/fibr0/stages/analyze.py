"""Stage 4: one structured LLM call per event.

Two paths share one prompt and one schema:
- `analyze_batch`  Batch API, used by the scheduled run. Half price, results within the hour.
- `analyze_one`    Synchronous, used only for development against a fixture file.

Every call's usage is written to llm_usage and every full response to llm_outputs.
Server-side refusal fallbacks are not enabled: the Batches API rejects the parameter,
and the sync path exists only for development.
"""

from __future__ import annotations

import json
import logging
import time
from importlib import resources

import anthropic
import psycopg
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from fibr0.models import AnalysisResult, Event

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
POLL_SECONDS = 60

# USD per million tokens (input, output) at standard rates. Batch is half of these.
PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int, batch: bool = False
) -> float:
    inp, out = PRICES.get(model, (5.0, 25.0))
    cost = (input_tokens * inp + output_tokens * out) / 1_000_000
    return cost / 2 if batch else cost


def system_prompt() -> str:
    return resources.files("fibr0.prompts").joinpath("analyze_system.md").read_text("utf-8")


def output_format() -> dict:
    return {"type": "json_schema", "schema": AnalysisResult.model_json_schema()}


def user_message(event: Event) -> str:
    return f"# Event\n\n{event.title}\n\n# Source items\n\n{event.text_for_analysis}"


def _clamp(result: AnalysisResult) -> AnalysisResult:
    """Schema cannot express numeric bounds; enforce them here and drop no-view impacts."""
    kept = []
    for impact in result.impacts:
        c = max(0.0, min(1.0, impact.confidence))
        if c <= 0.5:
            continue
        impact.confidence = c
        impact.ticker = impact.ticker.upper().strip()
        kept.append(impact)
    result.impacts = kept
    return result


def _record_usage(
    conn: psycopg.Connection | None,
    event_id: int | None,
    model: str,
    usage: anthropic.types.Usage,
    mode: str,
) -> None:
    if conn is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into llm_usage (event_id, model, mode, input_tokens, output_tokens,
                                   cache_read_tokens, cache_write_tokens)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_id,
                model,
                mode,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_input_tokens or 0,
                usage.cache_creation_input_tokens or 0,
            ),
        )


def _record_output(
    conn: psycopg.Connection | None, event_id: int | None, model: str, raw: str, parsed: dict
) -> None:
    if conn is None or event_id is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "insert into llm_outputs (event_id, model, raw_text, parsed) values (%s, %s, %s, %s)",
            (event_id, model, raw, json.dumps(parsed)),
        )


def analyze_one(
    client: anthropic.Anthropic,
    event: Event,
    model: str,
    conn: psycopg.Connection | None = None,
) -> AnalysisResult:
    """Development path. One synchronous call, full price."""
    response = client.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_prompt(),
        messages=[{"role": "user", "content": user_message(event)}],
        output_format=AnalysisResult,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model refused event {event.id}: {response.stop_details}")
    result = _clamp(response.parsed_output)
    raw_text = next((b.text for b in response.content if b.type == "text"), "")
    u = response.usage
    log.info(
        "event=%s usage in=%d out=%d cache_read=%d est_usd=%.3f",
        event.id,
        u.input_tokens,
        u.output_tokens,
        u.cache_read_input_tokens or 0,
        estimate_cost_usd(model, u.input_tokens, u.output_tokens),
    )
    _record_usage(conn, event.id, model, response.usage, "sync")
    _record_output(conn, event.id, model, raw_text, result.model_dump())
    return result


def analyze_batch(
    client: anthropic.Anthropic,
    events: list[Event],
    model: str,
    conn: psycopg.Connection | None = None,
) -> dict[int, AnalysisResult]:
    """Scheduled path. Submits all events as one batch and blocks until it ends."""
    if not events:
        return {}
    system = [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
    requests = [
        Request(
            custom_id=f"event-{e.id}",
            params=MessageCreateParamsNonStreaming(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user_message(e)}],
                output_config={"format": output_format()},
            ),
        )
        for e in events
    ]
    batch = client.messages.batches.create(requests=requests)
    log.info("batch=%s submitted events=%d", batch.id, len(events))
    while batch.processing_status != "ended":
        time.sleep(POLL_SECONDS)
        batch = client.messages.batches.retrieve(batch.id)
        log.info("batch=%s status=%s", batch.id, batch.processing_status)

    results: dict[int, AnalysisResult] = {}
    for item in client.messages.batches.results(batch.id):
        event_id = int(item.custom_id.removeprefix("event-"))
        if item.result.type != "succeeded":
            log.warning("event=%s batch result %s", event_id, item.result.type)
            continue
        msg = item.result.message
        if msg.stop_reason == "refusal":
            log.warning("event=%s refused: %s", event_id, msg.stop_details)
            continue
        raw_text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            parsed = _clamp(AnalysisResult.model_validate_json(raw_text))
        except ValueError as exc:
            log.error("event=%s unparseable output: %s", event_id, exc)
            continue
        _record_usage(conn, event_id, model, msg.usage, "batch")
        _record_output(conn, event_id, model, raw_text, parsed.model_dump())
        results[event_id] = parsed
    return results


# Events older than this are never analyzed. A digest is about what just happened, and the
# per-run cap must go to the newest, best-sourced events rather than draining a backlog.
MAX_EVENT_AGE_HOURS = 18


def load_unanalyzed(conn: psycopg.Connection, limit: int) -> list[Event]:
    """Newest recent events first, preferring those with more sources and a Tier 1 source."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select e.id, e.slot, e.title, e.text_for_analysis, e.source_urls, e.source_tiers
            from events e left join llm_outputs o on o.event_id = e.id
            where o.id is null
              and e.created_at > now() - make_interval(hours => %s)
            order by (select min(t) from unnest(e.source_tiers) t) asc,
                     cardinality(e.source_urls) desc,
                     e.id desc
            limit %s
            """,
            (MAX_EVENT_AGE_HOURS, limit),
        )
        return [Event(**row) for row in cur.fetchall()]


def run(
    conn: psycopg.Connection, model: str, max_events: int, dry_run: bool = False
) -> dict[int, AnalysisResult]:
    events = load_unanalyzed(conn, max_events)
    log.info("analyze pending=%d model=%s", len(events), model)
    if dry_run or not events:
        return {}
    return analyze_batch(anthropic.Anthropic(), events, model, conn)
