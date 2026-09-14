"""Stage 2: cheap relevance gate. Drops most items before anything costs money."""

from __future__ import annotations

import logging
import re

import psycopg

from fibr0.models import RawItem

log = logging.getLogger(__name__)

# Energy-domain vocabulary. Matching any term OR any universe ticker/name passes the gate.
# Deliberately broad: the LLM stage is the precise filter, this one only has to be cheap.
ENERGY_KEYWORDS: tuple[str, ...] = (
    "crude",
    "oil",
    "brent",
    "wti",
    "opec",
    "refinery",
    "refining",
    "pipeline",
    "natural gas",
    "lng",
    "henry hub",
    "permian",
    "gulf of mexico",
    "offshore",
    "drilling",
    "rig count",
    "shale",
    "midstream",
    "utility",
    "utilities",
    "grid",
    "ferc",
    "eia",
    "doe",
    "nrc",
    "nuclear",
    "uranium",
    "solar",
    "wind farm",
    "renewable",
    "hurricane",
    "tropical storm",
    "outage",
    "force majeure",
    "spr",
    "strategic petroleum",
    "sanction",
    "tariff",
    "export ban",
    "barrel",
    "mmbtu",
    "gasoline",
    "diesel",
    "jet fuel",
    "ethanol",
    "hydrogen",
    "carbon capture",
)


# First words of company names that are too generic to identify the company on their own.
_GENERIC_FIRST_WORDS = frozenset(
    "energy american united southern first global general national standard western eastern "
    "northern new the select spdr ishares invesco vaneck".split()
)

_SUFFIX = re.compile(r"\b(corp|corporation|inc|plc|ltd|co|company|llc|lp|nv)\.?$")


def build_matcher(universe: list[dict]) -> re.Pattern[str]:
    """One compiled regex over keywords, tickers, and company names."""
    terms = set(ENERGY_KEYWORDS)
    for row in universe:
        terms.add(row["ticker"].lower())
        name = _SUFFIX.sub("", row["name"].lower()).strip()
        if len(name) >= 4:
            terms.add(name)
        # "Exxon Mobil" should also match a headline that only says "Exxon".
        first = name.split()[0] if name else ""
        if len(first) >= 5 and first not in _GENERIC_FIRST_WORDS:
            terms.add(first)
    alternation = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(r"\b(" + alternation + r")\b", flags=re.IGNORECASE)


def is_relevant(item: RawItem, matcher: re.Pattern[str]) -> bool:
    return bool(matcher.search(f"{item.title}\n{item.body}"))


def load_universe(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("select ticker, name from ticker_universe where active")
        return cur.fetchall()


def run(conn: psycopg.Connection, dry_run: bool = False) -> tuple[int, int]:
    """Mark unfiltered raw_items as relevant or not. Returns (relevant, total)."""
    matcher = build_matcher(load_universe(conn))
    with conn.cursor() as cur:
        cur.execute(
            "select id, source_id, url, url_hash, title, body, published_at "
            "from raw_items where relevant is null"
        )
        rows = cur.fetchall()
    relevant_ids: list[int] = []
    irrelevant_ids: list[int] = []
    for row in rows:
        item = RawItem(**row)
        (relevant_ids if is_relevant(item, matcher) else irrelevant_ids).append(item.id)
    log.info("filter total=%d relevant=%d", len(rows), len(relevant_ids))
    if not dry_run and rows:
        with conn.cursor() as cur:
            cur.execute("update raw_items set relevant = true where id = any(%s)", (relevant_ids,))
            cur.execute(
                "update raw_items set relevant = false where id = any(%s)", (irrelevant_ids,)
            )
    return len(relevant_ids), len(rows)
