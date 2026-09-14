import type { NextConfig } from "next";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

// Local development: share the repo-root .env with the pipeline so DATABASE_URL is set once.
// On Vercel the variable comes from project settings and this block is a no-op.
if (!process.env.DATABASE_URL) {
  const rootEnv = resolve(__dirname, "..", ".env");
  if (existsSync(rootEnv)) {
    try {
      process.loadEnvFile(rootEnv);
    } catch {
      // Malformed file: fall through and let the page render its "not configured" state.
    }
  }
}

const nextConfig: NextConfig = {
  serverExternalPackages: ["postgres"],
};

export default nextConfig;
