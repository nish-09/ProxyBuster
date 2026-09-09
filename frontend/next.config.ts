import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this directory — a stray package-lock.json under the
  // user's home directory would otherwise make Turbopack mis-detect the monorepo root.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
