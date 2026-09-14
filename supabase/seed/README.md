# Seed data

Preferred path, from `pipeline/` with `DATABASE_URL` set in the repo-root `.env`:

```bash
.venv/Scripts/fibr0 db migrate
```

```bash
.venv/Scripts/fibr0 db seed
```

Both are idempotent. Migrations are tracked in `schema_migrations`; seeds upsert on primary key.

Manual fallback with `psql`:

```bash
psql "$DATABASE_URL" -c "\copy sources from 'supabase/seed/sources.csv' csv header"
```

```bash
psql "$DATABASE_URL" -c "\copy ticker_universe(ticker,name,sector,subsector,relationship_tags) from 'supabase/seed/ticker_universe.csv' csv header"
```

`ticker_universe.csv` is a starter list, not the full constituent set of the seed ETFs. Expand it before launch and review quarterly. Feed URLs in `sources.csv` were chosen by hand and have not all been verified live; the ingest stage logs and skips any feed that fails to parse.
