"""Command-line entry point. `fibr0 run` for digest slots, `fibr0 resolve` for scoring."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from fibr0 import market_calendar
from fibr0.config import Settings
from fibr0.db import connect
from fibr0.models import Event, Slot
from fibr0.stages import analyze, cluster, filter, ingest, publish, resolve

STAGES = ("ingest", "filter", "cluster", "analyze", "publish")

log = logging.getLogger("fibr0")


def _resolve_slot(arg: str) -> Slot | None:
    if arg == "auto":
        return market_calendar.slot_for()
    return Slot(arg)


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    if settings.fixture:
        return run_fixture(settings)
    slot = _resolve_slot(args.slot)
    if slot is None:
        log.info("no digest slot at this time; exiting cleanly")
        return 0
    stages = STAGES if args.stage == "all" else (args.stage,)
    log.info("slot=%s stages=%s dry_run=%s", slot.value, ",".join(stages), settings.dry_run)

    with connect(settings.require_database()) as conn:
        results = {}
        if "ingest" in stages:
            log.info("ingest new_rows=%d", ingest.run(conn, settings.dry_run))
        if "filter" in stages:
            relevant, total = filter.run(conn, settings.dry_run)
            log.info("filter relevant=%d total=%d", relevant, total)
        if "cluster" in stages:
            log.info("cluster events=%d", cluster.run(conn, slot, settings.dry_run))
        if "analyze" in stages:
            results = analyze.run(
                conn, settings.model, settings.max_events_per_run, settings.dry_run
            )
            log.info("analyze results=%d", len(results))
        if "publish" in stages:
            log.info("publish predictions=%d", publish.run(conn, slot, results, settings))
    return 0


def run_fixture(settings: Settings) -> int:
    """Development path: analyze fixture events synchronously, print results, write nothing."""
    import anthropic

    events = [Event(**e) for e in json.loads(settings.fixture.read_text("utf-8"))]
    log.info("fixture=%s events=%d model=%s", settings.fixture, len(events), settings.model)
    if settings.dry_run:
        for e in events:
            print(f"[dry run] would analyze: {e.title}")
        return 0
    client = anthropic.Anthropic()
    for event in events:
        result = analyze.analyze_one(client, event, settings.model)
        print(json.dumps({"event": event.title, **result.model_dump()}, indent=2))
    return 0


def cmd_resolve(args: argparse.Namespace, settings: Settings) -> int:
    with connect(settings.require_database()) as conn:
        log.info("resolved=%d", resolve.run(conn, settings))
    return 0


def cmd_db(args: argparse.Namespace, settings: Settings) -> int:
    from fibr0 import admin

    with connect(settings.require_database()) as conn:
        if args.action == "migrate":
            applied = admin.migrate(conn)
            print("applied:", ", ".join(applied) if applied else "nothing pending")
        elif args.action == "seed":
            print("seeded:", admin.seed(conn))
        elif args.action == "status":
            for table, n in admin.status(conn).items():
                print(f"{table:<18}{n:>8}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fibr0")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run digest pipeline stages")
    run_p.add_argument("--stage", choices=("all", *STAGES), default="all")
    run_p.add_argument("--slot", choices=("auto", *[s.value for s in Slot]), default="auto")
    run_p.set_defaults(func=cmd_run)

    res_p = sub.add_parser("resolve", help="score elapsed predictions")
    res_p.set_defaults(func=cmd_resolve)

    db_p = sub.add_parser("db", help="apply migrations, load seeds, show row counts")
    db_p.add_argument("action", choices=("migrate", "seed", "status"))
    db_p.set_defaults(func=cmd_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return args.func(args, Settings.from_env())


if __name__ == "__main__":
    sys.exit(main())
