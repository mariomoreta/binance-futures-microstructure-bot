import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // DASH-V2-00: static foundation only. No API routes, no rewrites to the
  // Python backend, no external fetch. BFF arrives in a later slice.
};

export default nextConfig;
