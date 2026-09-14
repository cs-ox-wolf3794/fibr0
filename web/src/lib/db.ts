import "server-only";
import postgres from "postgres";

/**
 * Server-side Postgres access. Reads DATABASE_URL (the Supabase session pooler string).
 * Only public tables are queried from the web app; see CLAUDE.md for the contract.
 * The client is cached on globalThis so dev hot-reloads do not exhaust pooler connections.
 */
declare global {
  var __fibr0_sql: ReturnType<typeof postgres> | undefined;
}

export function isConfigured(): boolean {
  return Boolean(process.env.DATABASE_URL);
}

export function sql(): ReturnType<typeof postgres> {
  if (!globalThis.__fibr0_sql) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set");
    globalThis.__fibr0_sql = postgres(url, {
      max: 3,
      ssl: "require",
      idle_timeout: 20,
      connect_timeout: 10,
    });
  }
  return globalThis.__fibr0_sql;
}
