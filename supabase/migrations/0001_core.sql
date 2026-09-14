-- fibr0 core schema. Apply with the Supabase SQL editor or psql against the project database.
-- Conventions: pipeline writes with the service role; the web app and anonymous visitors read
-- through row-level security. predictions is append-only, enforced by trigger.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------------

create table sources (
  id            text primary key,                 -- short slug, e.g. eia_wpsr
  name          text not null,
  tier          smallint not null check (tier between 1 and 3),
  trust_weight  numeric(3,2) not null check (trust_weight between 0 and 1),
  kind          text not null check (kind in ('rss', 'edgar', 'page')),
  url           text not null,
  enabled       boolean not null default true,
  created_at    timestamptz not null default now()
);

create table ticker_universe (
  ticker            text primary key,
  name              text not null,
  sector            text not null,
  subsector         text not null,
  relationship_tags text[] not null default '{}',   -- e.g. {refiner, gulf_coast, jet_fuel_consumer}
  active            boolean not null default true,
  updated_at        timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Pipeline state
-- ---------------------------------------------------------------------------

create table events (
  id                bigint generated always as identity primary key,
  slot              text not null check (slot in ('pre_open', 'midday', 'post_close')),
  title             text not null,
  text_for_analysis text not null,
  source_urls       text[] not null default '{}',
  source_tiers      smallint[] not null default '{}',
  category          text,                           -- filled from the analysis
  event_summary     text,
  created_at        timestamptz not null default now()
);

create table raw_items (
  id            bigint generated always as identity primary key,
  source_id     text not null references sources(id),
  url           text not null,
  url_hash      text not null unique,
  title         text not null,
  body          text not null default '',
  published_at  timestamptz,
  fetched_at    timestamptz not null default now(),
  relevant      boolean,                            -- null = not yet filtered
  event_id      bigint references events(id)
);
create index raw_items_pending_filter on raw_items (id) where relevant is null;
create index raw_items_pending_cluster on raw_items (id) where relevant and event_id is null;

create table llm_outputs (
  id          bigint generated always as identity primary key,
  event_id    bigint not null references events(id),
  model       text not null,
  raw_text    text not null,
  parsed      jsonb not null,
  created_at  timestamptz not null default now()
);
create index llm_outputs_event on llm_outputs (event_id);

create table llm_usage (
  id                 bigint generated always as identity primary key,
  event_id           bigint references events(id),
  model              text not null,
  mode               text not null check (mode in ('sync', 'batch')),
  input_tokens       integer not null,
  output_tokens      integer not null,
  cache_read_tokens  integer not null default 0,
  cache_write_tokens integer not null default 0,
  created_at         timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Published output
-- ---------------------------------------------------------------------------

create table digests (
  id            bigint generated always as identity primary key,
  slot          text not null check (slot in ('pre_open', 'midday', 'post_close')),
  published_at  timestamptz not null default now()
);

create table predictions (
  id                    bigint generated always as identity primary key,
  digest_id             bigint not null references digests(id),
  event_id              bigint not null references events(id),
  ticker                text not null references ticker_universe(ticker),
  direction             text not null check (direction in ('up', 'down')),
  horizon               text not null check (horizon in ('1d', '5d')),
  magnitude             text not null check (magnitude in ('small', 'medium', 'large')),
  impact_order          text not null check (impact_order in ('first', 'second')),
  raw_confidence        numeric(4,3) not null check (raw_confidence between 0.5 and 1),
  calibrated_confidence numeric(4,3) not null check (calibrated_confidence between 0.5 and 1),
  is_calibrated         boolean not null,
  rationale_summary     text not null,
  source_urls           text[] not null,
  published_at          timestamptz not null default now()
);
create index predictions_digest on predictions (digest_id);
create index predictions_ticker on predictions (ticker, published_at desc);

-- Append-only: corrections are new rows, never edits.
create or replace function predictions_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'predictions is append-only (attempted %)', tg_op;
end;
$$;
create trigger predictions_no_update_delete
  before update or delete on predictions
  for each row execute function predictions_immutable();

create table resolutions (
  id                  bigint generated always as identity primary key,
  prediction_id       bigint not null unique references predictions(id),
  reference_date      date not null,
  horizon_date        date not null,
  stock_move_pct      numeric(8,4) not null,
  benchmark_move_pct  numeric(8,4) not null,
  realized_move_pct   numeric(8,4) not null,
  outcome             text not null check (outcome in ('hit', 'miss', 'flat')),
  resolved_at         timestamptz not null default now()
);

create table calibration (
  category    text not null,
  horizon     text not null check (horizon in ('1d', '5d')),
  bucket      numeric(2,1) not null,             -- lower edge: 0.5, 0.6, 0.7, 0.8, 0.9
  resolved    integer not null default 0,
  hits        integer not null default 0,
  updated_at  timestamptz not null default now(),
  primary key (category, horizon, bucket)
);

-- ---------------------------------------------------------------------------
-- Tenancy (multi-tenant from day one; unused by the public MVP)
-- ---------------------------------------------------------------------------

create table orgs (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  plan        text not null default 'free' check (plan in ('free', 'b2b')),
  created_at  timestamptz not null default now()
);

create table users (
  id                 uuid primary key references auth.users(id) on delete cascade,
  org_id             uuid references orgs(id),
  email              text not null,
  email_digest_optin boolean not null default false,
  created_at         timestamptz not null default now()
);

create table api_keys (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id),
  key_hash    text not null unique,               -- sha256 of the key; the key itself is never stored
  label       text,
  created_at  timestamptz not null default now(),
  revoked_at  timestamptz
);

-- ---------------------------------------------------------------------------
-- Row-level security
-- Public read for everything a visitor sees. No policy at all on backend-only tables,
-- so anon and authenticated roles get nothing; the service role bypasses RLS.
-- ---------------------------------------------------------------------------

alter table sources          enable row level security;
alter table ticker_universe  enable row level security;
alter table events           enable row level security;
alter table raw_items        enable row level security;
alter table llm_outputs      enable row level security;
alter table llm_usage        enable row level security;
alter table digests          enable row level security;
alter table predictions      enable row level security;
alter table resolutions      enable row level security;
alter table calibration      enable row level security;
alter table orgs             enable row level security;
alter table users            enable row level security;
alter table api_keys         enable row level security;

create policy public_read on sources         for select using (true);
create policy public_read on ticker_universe for select using (true);
create policy public_read on events          for select using (true);
create policy public_read on digests         for select using (true);
create policy public_read on predictions     for select using (true);
create policy public_read on resolutions     for select using (true);
create policy public_read on calibration     for select using (true);

create policy own_row on users for select using (auth.uid() = id);
create policy own_row_update on users for update using (auth.uid() = id);
create policy own_org on orgs for select
  using (id in (select org_id from users where users.id = auth.uid()));
create policy own_org_keys on api_keys for select
  using (org_id in (select org_id from users where users.id = auth.uid()));

-- raw_items, llm_outputs, llm_usage: intentionally no policies.
