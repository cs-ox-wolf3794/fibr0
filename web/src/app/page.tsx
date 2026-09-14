import { DigestView, EmptyState } from "@/components/DigestView";
import { PageShell } from "@/components/SiteChrome";
import { isConfigured } from "@/lib/db";
import { digestEvents, latestDigest } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function Home() {
  if (!isConfigured()) {
    return (
      <PageShell>
        <EmptyState
          title="Database not configured"
          body="Set DATABASE_URL in the environment to connect this dashboard to the fibr0 Postgres instance."
        />
      </PageShell>
    );
  }
  const digest = await latestDigest();
  if (!digest) {
    return (
      <PageShell>
        <EmptyState
          title="No digest published yet"
          body="The pipeline publishes three digests per US trading day: pre-open, midday, and post-close. The first one will appear here as soon as it is published."
        />
      </PageShell>
    );
  }
  const events = await digestEvents(digest.id);
  return (
    <PageShell>
      <DigestView digest={digest} events={events} isLatest />
    </PageShell>
  );
}
