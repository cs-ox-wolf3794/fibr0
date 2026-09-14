import type { DigestEvent, Prediction } from "@/lib/queries";

const CATEGORY_LABEL: Record<string, string> = {
  supply_disruption: "Supply disruption",
  infrastructure_outage: "Infrastructure outage",
  weather: "Weather",
  geopolitical: "Geopolitical",
  policy_regulation: "Policy and regulation",
  commodity_price: "Commodity price",
  demand_signal: "Demand signal",
  earnings_guidance: "Earnings and guidance",
  m_and_a: "M&A",
  corporate_action: "Corporate action",
  other: "Other",
};

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ConfidenceBar({ value }: { value: number }) {
  // Confidence lives in [0.5, 1.0]; map that range onto the full bar width.
  const pct = Math.round(((value - 0.5) / 0.5) * 100);
  return (
    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
      <div className="h-full rounded-full bg-zinc-700 dark:bg-zinc-300" style={{ width: `${pct}%` }} />
    </div>
  );
}

function OutcomeTag({ p }: { p: Prediction }) {
  if (!p.outcome) return <span className="text-xs text-zinc-400">pending</span>;
  const label =
    p.outcome === "hit" ? "hit" : p.outcome === "miss" ? "miss" : "flat";
  const tone =
    p.outcome === "hit"
      ? "text-emerald-700 dark:text-emerald-400"
      : "text-rose-700 dark:text-rose-400";
  const move = p.realized_move_pct == null ? "" : ` ${p.realized_move_pct >= 0 ? "+" : ""}${p.realized_move_pct.toFixed(1)}%`;
  return (
    <span className={`text-xs font-medium ${tone}`}>
      {label}
      {move}
    </span>
  );
}

function PredictionRow({ p }: { p: Prediction }) {
  const direction = p.direction === "up" ? "likely rise" : "likely fall";
  const dirTone =
    p.direction === "up"
      ? "text-emerald-700 dark:text-emerald-400"
      : "text-rose-700 dark:text-rose-400";
  return (
    <li className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[4.5rem_1fr_7rem_6rem_auto]">
      <span className="font-mono text-sm font-semibold">{p.ticker}</span>
      <span className="truncate text-sm text-zinc-600 dark:text-zinc-400" title={p.name}>
        {p.name}
        <span className="ml-2 text-xs text-zinc-400">
          {p.impact_order === "second" ? "second-order" : "direct"}
        </span>
      </span>
      <span className={`text-sm ${dirTone}`}>
        {direction} <span className="text-zinc-500">· {p.horizon}</span>
      </span>
      <span className="flex items-center gap-2 text-sm tabular-nums">
        <ConfidenceBar value={p.confidence} />
        {Math.round(p.confidence * 100)}%
        {!p.is_calibrated && (
          <span className="text-[10px] uppercase tracking-wide text-zinc-400" title="Not enough resolved history in this bucket yet">
            raw
          </span>
        )}
      </span>
      <span className="col-start-3 row-start-1 justify-self-end sm:col-start-5">
        <OutcomeTag p={p} />
      </span>
    </li>
  );
}

export function EventCard({ event }: { event: DigestEvent }) {
  const bestTier = Math.min(...event.source_tiers);
  return (
    <article className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-zinc-500">
        {event.category && <span>{CATEGORY_LABEL[event.category] ?? event.category}</span>}
        <span>Tier {bestTier} source{event.source_urls.length > 1 ? "s" : ""}</span>
      </div>
      <h2 className="mt-1 text-lg font-semibold leading-snug">{event.title}</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">{event.rationale_summary}</p>
      <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
        {event.predictions.map((p) => (
          <PredictionRow key={p.id} p={p} />
        ))}
      </ul>
      <p className="mt-3 flex flex-wrap gap-x-3 text-xs text-zinc-500">
        {event.source_urls.slice(0, 5).map((u) => (
          <a key={u} href={u} className="underline-offset-2 hover:underline" rel="noopener noreferrer">
            {hostname(u)}
          </a>
        ))}
      </p>
    </article>
  );
}
