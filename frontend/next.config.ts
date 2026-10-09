import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone", poweredByHeader: false, devIndicators: false,
  distDir: process.env.AEGIS_BUILD_DIR || ".next",
  ...(process.env.AEGIS_IN_PROCESS_WEB === "true" ? { experimental: { workerThreads: true } } : {}),
};
export default nextConfig;
