import { existsSync } from "node:fs";
import path from "node:path";

import type { NextConfig } from "next";

// One .env at the repo root is shared with fastapi-backend. Variables already
// set (the shell, or a frontend/.env* file Next loaded) take precedence.
const rootEnv = path.join(__dirname, "..", ".env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
