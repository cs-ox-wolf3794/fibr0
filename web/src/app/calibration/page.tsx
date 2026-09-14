import { EmptyState } from "@/components/DigestView";
import { PageShell } from "@/components/SiteChrome";
import { trackRecord } from "@/lib/queries";

export const dynamic = "force-dynamic";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

export default async function CalibrationPage() {
  const t = await trackRecord();
  const hitRate = t.resolved ? Math.round((t.hits / t.resolved) * 100) : null;

  return (
    <PageShell>
      <h1 className="text-2xl font-semibold tracking-tight">Track record</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
        Every prediction is stored before publication and scored after its horizon elapses against the
        actual close, net of the XLE sector move. A move under 0.5% counts as flat, and flat counts as a
        miss. Nothing here is edited after the fact.
      </p>

      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Resolved" value={String(t.resolved)} hint={`${t.pending} pending`} />
        <Stat label="Hit rate" value={hitRate == null ? "—" : `${hitRate}%`} hint={`${t.hits} hits, ${t.misses} misses, ${t.flats} flat`} />
        <Stat
          label="Brier score"
          value={t.brier == null ? "—" : t.brier.toFixed(3)}
          hint="Lower is better. 0.25 is a coin flip."
        />
        <Stat
          label="Calibrated"
          value={t.buckets.filter((b) => b.resolved >= 50).length + " / " + t.buckets.length}
          hint="Buckets with 50+ resolved predictions"
        />
      </div>

      {t.resolved === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No predictions have resolved yet"
            body="The first 1-day predictions resolve one trading day after publication and 5-day predictions after five. Calibration needs at least 50 resolved predictions per bucket before it replaces the raw score."
          />
        </div>
      ) : (
        <>
          <h2 className="mt-10 text-lg font-semibold">By horizon</h2>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="py-2">Horizon</th>
                <th className="py-2">Resolved</th>
                <th className="py-2">Hit rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {t.byHorizon.map((h) => (
                <tr key={h.horizon}>
                  <td className="py-2 font-mono">{h.horizon}</td>
                  <td className="py-2 tabular-nums">{h.resolved}</td>
                  <td className="py-2 tabular-nums">{Math.round((h.hits / h.resolved) * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 className="mt-10 text-lg font-semibold">Calibration by confidence bucket</h2>
          <p className="mt-1 text-sm text-zinc-500">
            A well-calibrated system has a hit rate close to the bucket midpoint in every row.
          </p>
          <div className="overflow-x-auto">
            <table className="mt-3 w-full min-w-[32rem] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="py-2">Category</th>
                  <th className="py-2">Horizon</th>
                  <th className="py-2">Bucket</th>
                  <th className="py-2">Resolved</th>
                  <th className="py-2">Hit rate</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {t.buckets.map((b) => (
                  <tr key={`${b.category}-${b.horizon}-${b.bucket}`}>
                    <td className="py-2">{b.category.replace(/_/g, " ")}</td>
                    <td className="py-2 font-mono">{b.horizon}</td>
                    <td className="py-2 tabular-nums">
                      {Math.round(b.bucket * 100)}–{Math.round((b.bucket + 0.1) * 100)}%
                    </td>
                    <td className="py-2 tabular-nums">{b.resolved}</td>
                    <td className="py-2 tabular-nums">{b.resolved ? Math.round((b.hits / b.resolved) * 100) : 0}%</td>
                    <td className="py-2 text-xs text-zinc-500">{b.resolved >= 50 ? "calibrated" : "collecting"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </PageShell>
  );
}
