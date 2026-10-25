import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // The prediction runs several Gemini calls and simulations, so allow
  // the proxied request up to five minutes.
  experimental: { proxyTimeout: 300_000 },
  // Forward the dashboard's prediction request to the FastAPI backend.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      { source: "/api/predict", destination: `${backendUrl}/api/predict` },
      {
        source: "/api/predict",
        destination: "http://127.0.0.1:8000/api/predict",
      },
      {
        source: "/auth/google",
        destination: "http://127.0.0.1:8000/auth/google",
      },
      {
        source: "/auth/google/callback",
        destination: "http://127.0.0.1:8000/auth/google/callback",
      },
      {
        source: "/api/calendar/:path*",
        destination: "http://127.0.0.1:8000/api/calendar/:path*",
      },
    ];
  },
};

export default nextConfig;
