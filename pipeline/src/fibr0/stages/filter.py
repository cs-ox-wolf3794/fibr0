"""Stage 2: relevance gate. Every item that passes costs an LLM call downstream, so this
stage is deliberately strict. An item passes when it is recent and either names a company
in the ticker universe, describes a market-moving event type, or (for non-regulatory
sources only) mentions at least two distinct energy-market terms. Bureaucratic notices are
excluded outright.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from fibr0.models import RawItem

log = logging.getLogger(__name__)

# Items published longer ago than this are never relevant. Protects against the archive
# backfill on first ingest and against feeds that resurface old documents.
MAX_AGE = timedelta(hours=36)

# Sources whose feeds are dominated by procedural documents. For these, weak terms alone
# never pass; the item must name a universe company or a market-moving event.
STRICT_SOURCE_PREFIXES = ("fedreg_", "nrc_", "sec_edgar")

# Sources where only a universe company match counts. EDGAR lists every filer in the
# country, and words like "acquisition" appear in SPAC names.
COMPANY_ONLY_SOURCE_PREFIXES = ("sec_edgar",)

# Phrases that mark procedural or administrative items regardless of other content.
EXCLUDE_PHRASES: tuple[str, ...] = (
    r"information collection",
    r"comment request",
    r"paperwork reduction",
    r"notice of (open )?meeting",
    r"meeting notice",
    r"sunshine act",
    r"privacy act",
    r"sworn in",
    r"symposium",
    r"webinar",
    r"workshop",
    r"extension of (the )?comment period",
    r"notice of intent to prepare",
    r"agreement state",
    r"test methods",
    r"technical conference",
)

# Event types that move prices. Any single match passes the gate.
STRONG_PHRASES: tuple[str, ...] = (
    r"refiner(y|ies)\b.{0,60}\b(fire|explosion|blast|outage|shut|restart|flaring)",
    r"\b(fire|explosion|blast|outage)\b.{0,60}\brefiner(y|ies)",
    r"force majeure",
    r"shut[- ]ins?\b",
    r"evacuat",
    r"hurricane",
    r"tropical storm",
    r"\bexplosion\b",
    r"\bblast\b",
    r"\bfire at\b",
    r"\bspill\b",
    r"\bleak\b",
    r"\bruptur",
    r"\bsanction",
    r"\btariff",
    r"export (ban|curb|restriction|halt)",
    r"\bopec\b",
    r"(production|output|supply) (cut|curb|increase|hike|boost)",
    r"strategic petroleum reserve",
    r"\bspr\b",
    r"price cap",
    r"crude (draw|build)",
    r"inventor(y|ies)\b.{0,40}\b(fell|rose|drew|built|decline|increase)",
    r"rig count",
    r"final investment decision",
    r"\bfid\b",
    r"certificate of public convenience",
    r"(approve|grant|den|reject)\w*\b.{0,50}\b(certificate|pipeline|project|permit|licen[cs]e|lease)",
    r"lease sale",
    r"\bguidance\b",
    r"\bearnings\b",
    r"quarterly results",
    r"\bacqui(re|sition)",
    r"\bmerger\b",
    r"\btakeover\b",
    r"\bbankruptcy\b",
    r"\bchapter 11\b",
    r"\bdowngrade",
    r"\bdividend\b",
    r"\bbuyback\b",
    r"\blayoffs?\b",
    r"\bstrike\b",
    r"\battack",
    r"\bdrone",
    r"\bmissile",
    r"\bceasefire\b",
    r"\bembargo\b",
    r"\bblockade\b",
    r"pipeline\b.{0,40}\b(shut|outage|rupture|explosion|leak|halt)",
    r"power outage",
    r"\bblackout",
    r"grid emergency",
    r"heat ?wave",
    r"cold snap",
    r"polar vortex",
    r"\bfreeze\b",
    r"\bwildfire",
    r"\bflood",
)

# Domain vocabulary. Two distinct matches pass, but only for non-strict sources.
WEAK_TERMS: tuple[str, ...] = (
    "crude",
    "oil",
    "brent",
    "wti",
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
    "shale",
    "midstream",
    "utility",
    "utilities",
    "power grid",
    "nuclear",
    "uranium",
    "solar",
    "wind farm",
    "renewable",
    "gasoline",
    "diesel",
    "jet fuel",
    "ethanol",
    "hydrogen",
    "carbon capture",
    "barrel",
    "mmbtu",
    "bcf",
)

# First words of company names too generic to identify the company on their own.
_GENERIC_FIRST_WORDS = frozenset(
    "energy american united southern first global general national standard western eastern "
    "northern new the select spdr ishares invesco vaneck international".split()
)
_SUFFIX = re.compile(r"\b(corp|corporation|inc|plc|ltd|co|company|llc|lp|nv|holdings?)\.?$")


def _alternation(terms: list[str]) -> str:
    return "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True))


@dataclass(frozen=True)
class Matcher:
    company: re.Pattern[str]
    strong: re.Pattern[str]
    weak: re.Pattern[str]
    exclude: re.Pattern[str]


def build_matcher(universe: list[dict]) -> Matcher:
    company_terms: list[str] = []
    for row in universe:
        ticker = row["ticker"]
        # Short tickers are ordinary words (AR, ET, SO, DK, RIG, LNG). Match them only as
        # cashtags or in EDGAR-style "TICKER)" contexts by requiring upper case, handled in
        # is_relevant via a separate case-sensitive pass. Here we take the company name.
        if len(ticker) >= 4 and ticker not in {"FLNG", "TALO", "STNG", "INSW", "PRIM"}:
            company_terms.append(ticker.lower())
        name = _SUFFIX.sub("", row["name"].lower()).strip()
        if len(name) >= 4:
            company_terms.append(name)
        first = name.split()[0] if name else ""
        if len(first) >= 5 and first not in _GENERIC_FIRST_WORDS:
            company_terms.append(first)
    return Matcher(
        company=re.compile(r"\b(" + _alternation(company_terms) + r")\b", re.IGNORECASE),
        strong=re.compile("|".join(f"(?:{p})" for p in STRONG_PHRASES), re.IGNORECASE),
        weak=re.compile(r"\b(" + _alternation(list(WEAK_TERMS)) + r")\b", re.IGNORECASE),
        exclude=re.compile("|".join(f"(?:{p})" for p in EXCLUDE_PHRASES), re.IGNORECASE),
    )


def is_strict_source(source_id: str) -> bool:
    return source_id.startswith(STRICT_SOURCE_PREFIXES)


def classify(item: RawItem, m: Matcher, now: datetime | None = None) -> str | None:
    """Return the reason an item is relevant, or None if it is not."""
    now = now or datetime.now(tz=UTC)
    if item.published_at is not None and now - item.published_at > MAX_AGE:
        return None
    title = item.title
    text = f"{title}\n{item.body}"
    if m.exclude.search(title):
        return None
    if m.company.search(text):
        return "company"
    if item.source_id.startswith(COMPANY_ONLY_SOURCE_PREFIXES):
        return None
    if m.strong.search(text):
        return "event"
    if is_strict_source(item.source_id):
        return None
    weak_hits = {hit.lower() for hit in m.weak.findall(text)}
    if len(weak_hits) >= 2:
        return "domain"
    return None


def is_relevant(item: RawItem, m: Matcher, now: datetime | None = None) -> bool:
    return classify(item, m, now) is not None


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
    reasons: dict[str, int] = {}
    for row in rows:
        item = RawItem(**row)
        reason = classify(item, matcher)
        if reason:
            relevant_ids.append(item.id)
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            irrelevant_ids.append(item.id)
    log.info("filter total=%d relevant=%d by=%s", len(rows), len(relevant_ids), reasons)
    if not dry_run and rows:
        with conn.cursor() as cur:
            cur.execute("update raw_items set relevant = true where id = any(%s)", (relevant_ids,))
            cur.execute(
                "update raw_items set relevant = false where id = any(%s)", (irrelevant_ids,)
            )
    return len(relevant_ids), len(rows)
