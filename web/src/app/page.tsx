import { TAGLINE } from "@/lib/brand";
import { CALIBRATION_PATH, DISCLAIMER } from "@/lib/disclaimer";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 px-6 py-24 font-sans dark:bg-black">
      <main className="w-full max-w-3xl">
        <p className="text-sm font-medium uppercase tracking-widest text-zinc-500">fibr0</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
          {TAGLINE}
        </h1>
        <p className="mt-3 text-xl text-zinc-700 dark:text-zinc-300">
          Energy news, mapped to the stocks it is likely to move.
        </p>
        <p className="mt-6 text-lg leading-8 text-zinc-600 dark:text-zinc-400">
          Three digests a day. Each names the US-listed energy stocks a story is likely to
          affect, the direction, the horizon, and a confidence score that is checked against
          real prices afterward. The full record, including misses, is public.
        </p>
        <p className="mt-8 text-sm text-zinc-500">
          Dashboard coming soon. Methodology and track record will live at{" "}
          <a className="underline" href={CALIBRATION_PATH}>
            {CALIBRATION_PATH}
          </a>
          .
        </p>
      </main>
      <footer className="mt-24 w-full max-w-3xl border-t border-zinc-200 pt-6 text-xs leading-5 text-zinc-500 dark:border-zinc-800">
        {DISCLAIMER}
      </footer>
    </div>
  );
}
