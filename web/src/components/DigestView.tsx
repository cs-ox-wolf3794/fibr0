import Link from "next/link";
import { EventCard } from "@/components/EventCard";
import { type Digest, type DigestEvent, SLOT_LABEL } from "@/lib/queries";

function formatEt(d: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

export function DigestView({
  digest,
  events,
  isLatest,
}: {
  digest: Digest;
  events: DigestEvent[];
  isLatest: boolean;
}) {
  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {SLOT_LABEL[digest.slot]} digest
          {!isLatest && <span className="ml-2 text-base font-normal text-zinc-500">#{digest.id}</span>}
        </h1>
        <p className="text-sm text-zinc-500">
          {formatEt(digest.published_at)} · {digest.prediction_count} prediction
          {digest.prediction_count === 1 ? "" : "s"} across {events.length} event
          {events.length === 1 ? "" : "s"}
        </p>
      </div>
      <p className="mt-2 text-sm text-zinc-500">
        Each line is the likelihood that the stock closes in the stated direction at the horizon, net of the
        XLE sector move. Percentages marked raw have not yet been through calibration.{" "}
        <Link href="/calibration" className="underline underline-offset-2">
          See the track record.
        </Link>
      </p>
      <div className="mt-8 flex flex-col gap-5">
        {events.map((e) => (
          <EventCard key={e.event_id} event={e} />
        ))}
      </div>
    </>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-500">{body}</p>
    </div>
  );
}
