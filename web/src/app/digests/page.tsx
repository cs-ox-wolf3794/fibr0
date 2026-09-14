import Link from "next/link";
import { EmptyState } from "@/components/DigestView";
import { PageShell } from "@/components/SiteChrome";
import { listDigests, SLOT_LABEL } from "@/lib/queries";

export const dynamic = "force-dynamic";

const fmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  dateStyle: "medium",
  timeStyle: "short",
});

export default async function DigestsPage() {
  const digests = await listDigests(60);
  return (
    <PageShell>
      <h1 className="text-2xl font-semibold tracking-tight">Digests</h1>
      <p className="mt-2 text-sm text-zinc-500">Every digest ever published, newest first. Nothing is edited after publication.</p>
      {digests.length === 0 ? (
        <div className="mt-8">
          <EmptyState title="Nothing published yet" body="Digests will be listed here once the pipeline runs." />
        </div>
      ) : (
        <ul className="mt-6 divide-y divide-zinc-200 dark:divide-zinc-800">
          {digests.map((d) => (
            <li key={d.id}>
              <Link
                href={`/digests/${d.id}`}
                className="flex flex-wrap items-baseline justify-between gap-2 py-3 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                <span className="font-medium">
                  {SLOT_LABEL[d.slot]} <span className="text-zinc-400">#{d.id}</span>
                </span>
                <span className="text-sm text-zinc-500">
                  {fmt.format(d.published_at)} ET · {d.prediction_count} prediction{d.prediction_count === 1 ? "" : "s"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
