import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Forward the dashboard's prediction request to the FastAPI backend.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      { source: "/api/predict", destination: `${backendUrl}/api/predict` },
    ];
  },
};

export default nextConfig;
