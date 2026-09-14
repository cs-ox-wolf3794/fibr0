import { notFound } from "next/navigation";
import { DigestView } from "@/components/DigestView";
import { PageShell } from "@/components/SiteChrome";
import { digestEvents, getDigest, latestDigest } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function DigestPage({ params }: PageProps<"/digests/[id]">) {
  const { id } = await params;
  const digestId = Number(id);
  if (!Number.isInteger(digestId)) notFound();
  const [digest, latest] = await Promise.all([getDigest(digestId), latestDigest()]);
  if (!digest) notFound();
  const events = await digestEvents(digest.id);
  return (
    <PageShell>
      <DigestView digest={digest} events={events} isLatest={latest?.id === digest.id} />
    </PageShell>
  );
}
