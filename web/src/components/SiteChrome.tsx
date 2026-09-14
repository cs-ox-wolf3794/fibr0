import Link from "next/link";
import { APP_NAME, TAGLINE } from "@/lib/brand";
import { CALIBRATION_PATH, DISCLAIMER } from "@/lib/disclaimer";

export function SiteHeader() {
  return (
    <header className="w-full border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex w-full max-w-4xl flex-wrap items-baseline justify-between gap-x-6 gap-y-2 px-6 py-4">
        <Link href="/" className="flex items-baseline gap-3">
          <span className="text-lg font-semibold tracking-tight">{APP_NAME}</span>
          <span className="hidden text-sm text-zinc-500 sm:inline">{TAGLINE}</span>
        </Link>
        <nav className="flex gap-5 text-sm text-zinc-600 dark:text-zinc-400">
          <Link href="/" className="hover:text-zinc-900 dark:hover:text-zinc-100">
            Latest
          </Link>
          <Link href="/digests" className="hover:text-zinc-900 dark:hover:text-zinc-100">
            Digests
          </Link>
          <Link href={CALIBRATION_PATH} className="hover:text-zinc-900 dark:hover:text-zinc-100">
            Track record
          </Link>
          <a
            href="https://github.com/cs-ox-wolf3794/fibr0"
            className="hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            Methodology
          </a>
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-auto w-full border-t border-zinc-200 dark:border-zinc-800">
      <p className="mx-auto w-full max-w-4xl px-6 py-6 text-xs leading-5 text-zinc-500">
        {DISCLAIMER}
      </p>
    </footer>
  );
}

export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col bg-zinc-50 text-zinc-900 dark:bg-black dark:text-zinc-100">
      <SiteHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">{children}</main>
      <SiteFooter />
    </div>
  );
}
