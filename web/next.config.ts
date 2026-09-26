import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API origin (FastAPI) is configured at runtime via
  // NEXT_PUBLIC_ASTRAEUS_API_URL. No rewrites: the browser speaks to the
  // API directly so the wire contract stays explicit and testable.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
