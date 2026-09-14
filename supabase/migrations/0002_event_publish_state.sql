-- Publish reads stored model outputs rather than in-memory results, so it needs to know
-- which analyzed events it has already handled (including ones that yielded zero predictions).
alter table events add column published_at timestamptz;
create index events_unpublished on events (id) where published_at is null;
