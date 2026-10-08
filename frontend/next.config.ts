import type { NextConfig } from "next";
const nextConfig: NextConfig = { output: "standalone", poweredByHeader: false, devIndicators: false, distDir: process.env.AEGIS_BUILD_DIR || ".next" };
export default nextConfig;
