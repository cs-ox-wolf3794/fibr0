# fibr0

**Ground Zero for Finance Bros.** News-to-stock-impact intelligence for the US energy sector.

fibr0 reads free, open news sources, identifies which US-listed energy stocks a story is likely to affect, and publishes a direction, a horizon, and a calibrated confidence for each. Every prediction is logged before publication, scored against actual prices afterward, and the full track record, including misses, is public.

fibr0 is not investment advice. It never says buy or sell, never executes trades, and never personalizes output.

## Layout

| Path | What |
|---|---|
| `pipeline/` | Python. Ingest, filter, cluster, analyze, score, publish, resolve. Runs on GitHub Actions cron. |
| `web/` | Next.js. Public dashboard, calibration page, email rendering. Deployed on Vercel. |
| `supabase/` | SQL migrations, row-level-security policies, seed data. |
| `CLAUDE.md` | Product decisions, architecture, and constraints. Read this first. |

## Methodology

The pipeline, prompts, source list, and scoring rules in this repository are the methodology. They are public on purpose.
