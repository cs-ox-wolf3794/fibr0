import "server-only";
import { sql } from "@/lib/db";

export type Slot = "pre_open" | "midday" | "post_close";

export interface Digest {
  id: number;
  slot: Slot;
  published_at: Date;
  prediction_count: number;
}

export interface Prediction {
  id: number;
  ticker: string;
  name: string;
  direction: "up" | "down";
  horizon: "1d" | "5d";
  magnitude: "small" | "medium" | "large";
  impact_order: "first" | "second";
  confidence: number;
  is_calibrated: boolean;
  outcome: "hit" | "miss" | "flat" | null;
  realized_move_pct: number | null;
}

export interface DigestEvent {
  event_id: number;
  title: string;
  category: string | null;
  rationale_summary: string;
  source_urls: string[];
  source_tiers: number[];
  predictions: Prediction[];
}

export interface CalibrationBucket {
  category: string;
  horizon: string;
  bucket: number;
  resolved: number;
  hits: number;
}

export interface TrackRecord {
  resolved: number;
  hits: number;
  misses: number;
  flats: number;
  brier: number | null;
  pending: number;
  byHorizon: { horizon: string; resolved: number; hits: number }[];
  buckets: CalibrationBucket[];
}

export const SLOT_LABEL: Record<Slot, string> = {
  pre_open: "Pre-open",
  midday: "Midday",
  post_close: "Post-close",
};

export async function listDigests(limit = 30): Promise<Digest[]> {
  const rows = await sql()<Digest[]>`
    select d.id, d.slot, d.published_at, count(p.id)::int as prediction_count
    from digests d left join predictions p on p.digest_id = d.id
    group by d.id order by d.id desc limit ${limit}
  `;
  return rows;
}

export async function latestDigest(): Promise<Digest | null> {
  const rows = await listDigests(1);
  return rows[0] ?? null;
}

export async function getDigest(id: number): Promise<Digest | null> {
  const rows = await sql()<Digest[]>`
    select d.id, d.slot, d.published_at, count(p.id)::int as prediction_count
    from digests d left join predictions p on p.digest_id = d.id
    where d.id = ${id} group by d.id
  `;
  return rows[0] ?? null;
}

export async function digestEvents(digestId: number): Promise<DigestEvent[]> {
  type Row = Omit<DigestEvent, "predictions"> & Prediction;
  const rows = await sql()<Row[]>`
    select e.id as event_id, e.title, e.category, e.source_urls, e.source_tiers,
           p.id, p.ticker, t.name, p.direction, p.horizon, p.magnitude, p.impact_order,
           p.calibrated_confidence::float as confidence, p.is_calibrated, p.rationale_summary,
           r.outcome, r.realized_move_pct::float as realized_move_pct
    from predictions p
    join events e on e.id = p.event_id
    join ticker_universe t on t.ticker = p.ticker
    left join resolutions r on r.prediction_id = p.id
    where p.digest_id = ${digestId}
    order by e.id, p.calibrated_confidence desc, p.ticker
  `;
  const byEvent = new Map<number, DigestEvent>();
  for (const r of rows) {
    let ev = byEvent.get(r.event_id);
    if (!ev) {
      ev = {
        event_id: r.event_id,
        title: r.title,
        category: r.category,
        rationale_summary: r.rationale_summary,
        source_urls: r.source_urls,
        source_tiers: r.source_tiers,
        predictions: [],
      };
      byEvent.set(r.event_id, ev);
    }
    ev.predictions.push({
      id: r.id,
      ticker: r.ticker,
      name: r.name,
      direction: r.direction,
      horizon: r.horizon,
      magnitude: r.magnitude,
      impact_order: r.impact_order,
      confidence: r.confidence,
      is_calibrated: r.is_calibrated,
      outcome: r.outcome,
      realized_move_pct: r.realized_move_pct,
    });
  }
  // Events with the most predictions first; ties keep database order.
  return [...byEvent.values()].sort((a, b) => b.predictions.length - a.predictions.length);
}

export async function trackRecord(): Promise<TrackRecord> {
  const [totals] = await sql()<
    { resolved: number; hits: number; misses: number; flats: number; brier: number | null }[]
  >`
    select count(r.id)::int as resolved,
           count(r.id) filter (where r.outcome = 'hit')::int as hits,
           count(r.id) filter (where r.outcome = 'miss')::int as misses,
           count(r.id) filter (where r.outcome = 'flat')::int as flats,
           avg(power(p.calibrated_confidence - (r.outcome = 'hit')::int, 2))::float as brier
    from resolutions r join predictions p on p.id = r.prediction_id
  `;
  const [{ pending }] = await sql()<{ pending: number }[]>`
    select count(*)::int as pending
    from predictions p left join resolutions r on r.prediction_id = p.id
    where r.id is null
  `;
  const byHorizon = await sql()<{ horizon: string; resolved: number; hits: number }[]>`
    select p.horizon, count(*)::int as resolved,
           count(*) filter (where r.outcome = 'hit')::int as hits
    from resolutions r join predictions p on p.id = r.prediction_id
    group by p.horizon order by p.horizon
  `;
  const buckets = await sql()<CalibrationBucket[]>`
    select category, horizon, bucket::float as bucket, resolved, hits
    from calibration order by horizon, bucket, category
  `;
  return { ...totals, pending, byHorizon, buckets };
}
