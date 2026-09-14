"""Stage 3: group items about the same event so one event costs one LLM call."""

from __future__ import annotations

import logging
import re

import psycopg

from fibr0.models import Event, RawItem, Slot

log = logging.getLogger(__name__)

_STOP = frozenset(
    "a an the of in on at to for and or with by from as is are was were be been "
    "after amid over under into its it this that these those says said say".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")

JACCARD_THRESHOLD = 0.5


def tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(items: list[RawItem], threshold: float = JACCARD_THRESHOLD) -> list[list[RawItem]]:
    """Greedy single-pass clustering on title token overlap. Good enough for a few dozen items."""
    groups: list[tuple[frozenset[str], list[RawItem]]] = []
    for item in items:
        toks = tokens(item.title)
        for group_tokens, members in groups:
            if jaccard(toks, group_tokens) >= threshold:
                members.append(item)
                break
        else:
            groups.append((toks, [item]))
    return [members for _, members in groups]


def to_event(members: list[RawItem], slot: Slot) -> Event:
    """Highest-trust item (lowest tier) supplies the title; every body is included."""
    members = sorted(members, key=lambda m: (m.tier, m.published_at or 0))
    lead = members[0]
    parts = []
    for m in members:
        parts.append(f"[{m.source_id} | tier {m.tier}] {m.title}\n{m.body}\n{m.url}")
    return Event(
        slot=slot,
        title=lead.title,
        text_for_analysis="\n\n---\n\n".join(parts),
        item_ids=[m.id for m in members if m.id is not None],
        source_urls=[m.url for m in members],
        source_tiers=[m.tier for m in members],
    )


def run(conn: psycopg.Connection, slot: Slot, dry_run: bool = False) -> int:
    """Turn relevant, unclustered items into events for this slot. Returns events created."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select r.id, r.source_id, r.url, r.url_hash, r.title, r.body, r.published_at, s.tier
            from raw_items r join sources s on s.id = r.source_id
            where r.relevant and r.event_id is null
            order by r.published_at nulls last
            """
        )
        items = [RawItem(**row) for row in cur.fetchall()]
    groups = cluster(items)
    log.info("cluster items=%d events=%d", len(items), len(groups))
    if dry_run:
        return len(groups)
    created = 0
    with conn.cursor() as cur:
        for members in groups:
            event = to_event(members, slot)
            cur.execute(
                """
                insert into events (slot, title, text_for_analysis, source_urls, source_tiers)
                values (%s, %s, %s, %s, %s) returning id
                """,
                (
                    event.slot.value,
                    event.title,
                    event.text_for_analysis,
                    event.source_urls,
                    event.source_tiers,
                ),
            )
            event_id = cur.fetchone()["id"]
            cur.execute(
                "update raw_items set event_id = %s where id = any(%s)", (event_id, event.item_ids)
            )
            created += 1
    return created
