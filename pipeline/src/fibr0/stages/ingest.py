"""Stage 1: pull every enabled source and store new items. URL hash is the dedupe key."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from time import mktime

import feedparser
import psycopg

from fibr0.models import RawItem

log = logging.getLogger(__name__)

USER_AGENT = "fibr0-pipeline/0.1 (+https://fibr0.com; open-source methodology)"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            return datetime.fromtimestamp(mktime(struct), tz=UTC)
    return None


def fetch_feed(source_id: str, url: str, tier: int) -> list[RawItem]:
    """Parse one RSS/Atom feed into RawItems. Network errors are logged, not raised."""
    parsed = feedparser.parse(url, agent=USER_AGENT)
    if parsed.get("bozo") and not parsed.entries:
        log.warning("source=%s unreadable: %s", source_id, parsed.get("bozo_exception"))
        return []
    items: list[RawItem] = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        summary = entry.get("summary", "") or ""
        content = entry.get("content") or []
        body = content[0].get("value", "") if content else summary
        items.append(
            RawItem(
                source_id=source_id,
                url=link,
                url_hash=url_hash(link),
                title=(entry.get("title") or "").strip(),
                body=body.strip(),
                published_at=_published(entry),
                tier=tier,
            )
        )
    return items


def load_sources(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("select id, url, tier, kind from sources where enabled order by tier, id")
        return cur.fetchall()


def store(conn: psycopg.Connection, items: list[RawItem]) -> int:
    if not items:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into raw_items (source_id, url, url_hash, title, body, published_at)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (url_hash) do nothing
            """,
            [(i.source_id, i.url, i.url_hash, i.title, i.body, i.published_at) for i in items],
        )
        return cur.rowcount


def run(conn: psycopg.Connection, dry_run: bool = False) -> int:
    """Fetch all enabled RSS sources. Returns the number of new rows stored."""
    new_rows = 0
    for source in load_sources(conn):
        if source["kind"] != "rss":
            # EDGAR and agency pages need dedicated fetchers. Tracked as follow-up work.
            log.info("source=%s kind=%s skipped (no fetcher yet)", source["id"], source["kind"])
            continue
        items = fetch_feed(source["id"], source["url"], source["tier"])
        log.info("source=%s fetched=%d", source["id"], len(items))
        if not dry_run:
            new_rows += store(conn, items)
    return new_rows
