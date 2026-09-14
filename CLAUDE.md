# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What fibr0 is

Tagline: **Ground Zero for Finance Bros**. Repo: https://github.com/cs-ox-wolf3794/fibr0. Brand strings live in `web/src/lib/brand.ts`.

fibr0 (fibr0.com) is a news-to-stock-impact intelligence platform. It ingests news from trusted, non-paywalled open sources, identifies which US-listed stocks are likely affected, estimates the likelihood and direction of a price move, and attaches a calibrated confidence score. Every prediction is logged and later scored against actual price moves, and the full track record (right and wrong) is public.

**Founding constraints (never violate, even if asked in passing):**
- No BUY / SELL / HOLD language anywhere in output. Use "likelihood of rise/fall", "likely positive/negative pressure", "impact probability".
- No trade execution, no brokerage links, no portfolio tracking, no personalized recommendations. Output is identical for every user.
- Every prediction is stored before publication and is immutable afterward. Corrections are appended, never edited in place.
- Sources must be free to access. If a source moves behind a paywall, drop it rather than scrape around it.
- Every output carries a not-investment-advice disclaimer and links to the calibration page.

## Product decisions (locked 2026-09-14)

All decisions below are final unless the owner changes them here. Do not reopen them in conversation.

| Decision | Choice | Notes |
|---|---|---|
| Audience sequencing | Public digest + track record first, B2B (banks, trading desks) second, B2C retail as the ongoing free tier | B2B credibility depends on the public calibration record existing first. Data model is multi-tenant (orgs, users, API keys) from day one. |
| Market | US-listed equities and ETFs only | Single exchange calendar, single price feed. |
| News domain | Energy only for MVP | Oil & gas, refining, midstream, utilities, renewables, uranium, energy services. Second-order tickers (airlines, chemicals, shipping) are in the universe as *impact targets* but their own news is not ingested. |
| Latency | Periodic digest, three runs per trading day | Pre-open (07:30 ET), midday (12:30 ET), post-close (17:00 ET). Weekends and NYSE holidays: one run at 17:00 ET to capture weekend news for the pre-open digest. No streaming, no push on individual stories. The Batch API is used for the analysis step. |
| Delivery order | 1. Web dashboard, 2. Email digest, 3. Telegram bot, 4. Public read API | Items 3 and 4 read the same `digests` table as 1 and 2. Do not build them before 1 and 2 are live. |
| Email cadence | One email per subscriber per day, sent after the post-close run | The web dashboard shows all three daily digests. Email is post-close only. |
| Rationale visibility | Users see a summarized rationale; the verbatim model output is stored backend-only | `predictions.rationale_summary` is public. `predictions.rationale_raw` and the full structured response are stored in `llm_outputs`, never exposed through the web app or API. |
| Track record | Fully public, includes misses | Calibration page shows Brier score, calibration curve, hit rate by confidence bucket, by horizon, by source. |
| Repo visibility | Public | Methodology is transparent by design. Unlimited free GitHub Actions minutes. Consequence: nothing sensitive may ever be committed, and the source registry and prompts are public. Prompts are part of the methodology, so treat them as documentation, not secrets. |
| Cost | Free-tier infrastructure only; the LLM API is the single paid line item | Any new dependency that has no usable free tier needs explicit sign-off. |
| LLM budget | USD 100 of Claude API credit, no top-up assumed | Estimated burn at 40 events/day on Opus 5: about USD 70/month on standard calls, about USD 35/month on the Batch API. The Batch API is therefore the default for the scheduled analysis run, not an optimization for later. Log `response.usage` on every call to a `llm_usage` table. During development, run the analysis stage against a fixed fixture of 5 to 10 cached events, never against a live feed. |

## Architecture

Two codebases in one repo, split by responsibility:

```
pipeline/    Python. Ingestion, filtering, analysis, scoring. Runs on a schedule via GitHub Actions cron. Stateless between runs; all state lives in Postgres.
web/         Next.js (TypeScript). Dashboard, calibration page, email rendering, later the API routes and Telegram webhook. Deployed on Vercel.
supabase/    SQL migrations, row-level-security policies, seed data (ticker universe, source registry).
```

The pipeline never talks to the web app. The web app never calls the LLM. Postgres is the only contract between them.

### Pipeline stages (each is a separate module, each idempotent)

1. **Ingest** - pull RSS/Atom feeds and agency pages from the source registry. Store raw items with URL hash as the dedupe key.
2. **Filter** - cheap relevance gate (keyword and ticker-universe match) to drop the majority of items before any LLM call. Target: fewer than 60 items/day reach analysis.
3. **Cluster** - group items covering the same event so one event produces one analysis, not five.
4. **Analyze** - one LLM call per event cluster. Structured output only. Produces: event summary, event category, affected tickers with direction, magnitude bucket, horizon, a verbatim rationale, a two-sentence public summary of that rationale, and the model's confidence. Second-order effects are explicitly requested (suppliers, competitors, customers, sector ETFs). The full response is written to `llm_outputs`; only the summary reaches `predictions`.
5. **Score** - convert the model's raw confidence into a calibrated confidence using the historical calibration table for that (category, horizon) pair. Until enough history exists, publish the raw score and label it "uncalibrated".
6. **Publish** - write predictions and the digest to Postgres. This is the only stage with write access to the `predictions` table.
7. **Resolve** - separate scheduled job. For every prediction whose horizon has elapsed, fetch the close price, compute the realized move, mark hit/miss, and update the calibration table.

### Confidence score definition

A prediction is a tuple: `(ticker, direction ∈ {up, down}, horizon ∈ {1d, 5d}, confidence ∈ [0.5, 1.0])`.

- Confidence is the probability that the close at horizon end moves in the stated direction relative to the close before the news, after subtracting the move in the sector ETF (XLE for most energy names) so that broad-market days do not count as hits.
- A move smaller than 0.5% in either direction resolves as "flat" and counts as a miss for both directions.
- Calibration is measured by Brier score and by bucketed hit rate (0.5-0.6, 0.6-0.7, and so on). "Calibrated" means the hit rate in each bucket is within 10 points of the bucket midpoint over at least 50 resolved predictions.

### Data model (core tables)

`sources`, `raw_items`, `events`, `predictions`, `resolutions`, `calibration`, `digests`, `llm_outputs`, `llm_usage`, `orgs`, `users`, `api_keys`, `ticker_universe`.

`predictions` is append-only. Enforce this with a Postgres trigger, not application code.

`llm_outputs` and `llm_usage` have no public read policy. They are readable only by the service role used by the pipeline.

### Tech stack (free tiers)

| Concern | Choice | Why |
|---|---|---|
| Pipeline language | Python 3.12 | Feed parsing, pandas for price math, Anthropic SDK. |
| LLM | Claude Opus 5 (`claude-opus-5`) via the official `anthropic` SDK, structured outputs, Batch API for the scheduled analysis run | Analysis quality is the product. Adaptive thinking on. Do not downgrade the analysis model for cost without the owner's sign-off. |
| Scheduler | GitHub Actions cron | Free for public and small private repos, logs are visible, no server to maintain. |
| Database + auth | Supabase (Postgres, Auth, row-level security) | Free tier covers MVP. RLS enforces tenant isolation at the database layer. |
| Web | Next.js on Vercel | Free tier, edge-cached public pages. |
| Email | Resend | Free tier is 3,000 emails/month. |
| Telegram | Telegram Bot API | Free. Webhook handled by a Next.js route. |
| Price data | Stooq daily CSV (primary), Yahoo Finance via `yfinance` (fallback) | Free. Daily closes are sufficient for 1d and 5d horizons. |
| Secrets | GitHub Actions secrets and Vercel env vars only | Never in the repo, never in Supabase tables. |

### Source registry (initial, energy-focused, all free)

Tier 1 (primary, official):
- EIA (Weekly Petroleum Status Report, Short-Term Energy Outlook, Natural Gas Weekly)
- FERC, DOE, BSEE/BOEM, NRC, EPA, Texas Railroad Commission
- SEC EDGAR 8-K filings for tickers in the universe
- NOAA National Hurricane Center (Gulf of Mexico production disruptions)
- OPEC and IEA press releases
- Company press releases via GlobeNewswire and Business Wire energy feeds

Tier 2 (reputable wire, headline-level free):
- Reuters energy RSS, AP business RSS

Tier 3 (event detection, lower trust, never the sole basis for a prediction):
- GDELT for geopolitical events touching producing regions

Each source carries a trust weight in the `sources` table. A prediction based only on Tier 3 sources is capped at 0.6 confidence.

### Ticker universe

Seeded from constituents of XLE, XOP, OIH, ICLN, TAN, URA, XLU plus a hand-maintained second-order list (US airlines, major chemicals, tanker and LNG shipping). Stored in `supabase/seed/ticker_universe.csv` with columns: `ticker, name, sector, subsector, relationship_tags`. Update quarterly.

## Compliance rules for generated text

- Never output the words buy, sell, hold, accumulate, short, long, or target price.
- Never address the reader's own position or portfolio.
- Always state horizon and confidence together. A direction without both is not publishable.
- Always include at least one source URL per prediction.
- The disclaimer text lives in one place (`web/lib/disclaimer.ts`) and is rendered on every page, email, and API response.

## Repository layout

```
pipeline/src/fibr0/          Python package. cli.py is the entry point; stages/ holds one module per pipeline stage.
pipeline/src/fibr0/prompts/  The analysis system prompt. Part of the public methodology.
pipeline/tests/              pytest. fixtures/events.json is the development fixture for the analyze stage.
web/                         Next.js 16 (App Router, src/ layout, Tailwind). Routes: / (latest digest), /digests, /digests/[id], /calibration.
web/src/lib/db.ts            Server-only Postgres client (the `postgres` package) reading DATABASE_URL. next.config.ts loads the repo-root .env locally.
web/src/lib/queries.ts       Every SQL query the web app makes. Public tables only. Pages are force-dynamic; add caching here, not in pages.
web/src/lib/disclaimer.ts    The disclaimer source. web/src/lib/brand.ts holds name and tagline.
supabase/migrations/         Plain SQL, numbered. Applied by hand via the Supabase SQL editor or psql (no Supabase CLI in use).
supabase/seed/               sources.csv and ticker_universe.csv, loaded with \copy.
.github/workflows/           pipeline.yml (digest cron), resolve.yml (daily scoring), ci.yml (lint + tests + build).
```

The generated `web/CLAUDE.md` and `web/AGENTS.md` are re-created by `next dev` and carry Next.js version notes. Leave them in place; they do not override this file.

## Development commands

Pipeline (run from `pipeline/`, Python 3.12+; the local machine has 3.14):

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   # Windows path; use .venv/bin on Unix
```

```bash
.venv/Scripts/pytest -q                       # all tests
.venv/Scripts/pytest -q tests/test_score_resolve.py::test_calibrated_uses_observed_hit_rate   # one test
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
```

```bash
FIBR0_DRY_RUN=true .venv/Scripts/fibr0 run --slot pre_open               # every stage, no LLM calls, no writes (needs DATABASE_URL)
.venv/Scripts/fibr0 run --stage filter --slot midday                     # one stage
FIBR0_FIXTURE=tests/fixtures/events.json .venv/Scripts/fibr0 run          # analyze 5 fixture events synchronously, print JSON, write nothing. Costs money.
.venv/Scripts/fibr0 resolve                                              # score elapsed predictions
```

`fibr0 run --slot auto` maps the current US Eastern time to a slot and exits cleanly if none matches. This is what CI calls.

Web (run from `web/`):

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

Database (Supabase project `qfnjwhoizlxbigzdzbly`, URL `https://qfnjwhoizlxbigzdzbly.supabase.co`):

```bash
.venv/Scripts/fibr0 db migrate    # applies supabase/migrations/*.sql not yet in schema_migrations
.venv/Scripts/fibr0 db seed       # upserts sources.csv and ticker_universe.csv, safe to re-run
.venv/Scripts/fibr0 db status     # row counts
```

`DATABASE_URL` must be the **Session pooler** connection string: host `aws-1-eu-west-1.pooler.supabase.com`, port 5432, user `postgres.qfnjwhoizlxbigzdzbly`, database `postgres`. Not the direct `db.<ref>.supabase.co` host, which is IPv6-only on the free tier and unreachable from GitHub Actions runners and most corporate networks. If the pooler ever reports "tenant or user not found", the host or username is wrong, not the password. Set `DATABASE_URL` and `ANTHROPIC_API_KEY` as GitHub Actions secrets and the `NEXT_PUBLIC_SUPABASE_*` variables on Vercel. Locally both live in a git-ignored `.env` at the repo root, which the pipeline loads automatically.

## Things future sessions get wrong without being told

- `predictions` rejects UPDATE and DELETE by trigger. To correct a prediction, insert a new row.
- The Batches API does not accept the `fallbacks` parameter, so the analyze stage does not use refusal fallbacks. Check `stop_reason == "refusal"` instead.
- Structured-output schemas come from the pydantic models in `models.py`. Do not hand-write JSON schema, and do not add numeric `minimum`/`maximum` constraints to those models; ranges are enforced in `analyze._clamp`.
- The compliance filter is strict word-boundary matching, so `long-term` and `short-lived` are blocked. The prompt tells the model this. If a legitimate summary is blocked, rephrase the prompt guidance, do not loosen the filter without owner sign-off.
- Cron lines are duplicated for EDT and EST. The slot is decided in `market_calendar.slot_for`, not in the workflow. NYSE holidays are hard-coded there for 2026 and 2027.
- The `ticker_universe.csv` seed is a starter list, not the full ETF constituent set. Predictions on tickers outside the universe are blocked at publish time because of the foreign key.
- Every enabled feed in `sources.csv` was verified live on 2026-09-14. Rows with `enabled=false` are kept for the record: their name says why (Cloudflare bot challenge, discontinued, empty). Do not re-enable without re-verifying, and never work around a bot challenge; find a different source instead. Federal Register RSS is the substitute for agencies whose own sites block automation.
- The fixture run on 2026-09-14 (5 events, 55 impacts) passed the compliance filter with zero hits and named 17 tickers outside the starter universe, which were then added. Expect this to recur; when the analyze log shows "not in ticker universe" blocks, add the ticker rather than loosening the check.
- The ingest User-Agent includes a contact address because SEC EDGAR rejects generic agents.
- **Measured funnel, 2026-09-14, first ingest (a 36-hour backfill, so roughly 3x a steady-state run):** 708 raw items, 91 relevant after the filter rewrite (17 by company match, 34 by event phrase, 40 by two domain terms), 72 events. Before the rewrite the filter passed 382 of 708, almost all regulatory and NRC noise. Google News supplies most of what passes. Steady state should be roughly 25 to 30 events per run, above the 8-per-run cap, so the analyze stage's ordering (Tier 1 first, then most sources, then newest) decides what gets analyzed. If good events are being skipped, the fix is better clustering, not a higher cap.
- Per-event cost is about USD 0.11 on standard calls and USD 0.055 on Batch with Opus 5 at default effort, dominated by output tokens (thinking plus a long private rationale). The two untried levers, both owner decisions: `output_config.effort` at medium for the analysis call, and a single cheap LLM call per slot to cluster headlines before analysis.
