import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev-only API proxy. When DEV_API_PROXY_TARGET is set (e.g. in .env.local),
  // requests to /api/v1/* on localhost are forwarded server-side to that host,
  // so the browser never makes a cross-origin call and CORS doesn't apply.
  // Unset in production, where this does nothing.
  async rewrites() {
    const target = process.env.DEV_API_PROXY_TARGET;
    if (!target) return [];
    return [
      {
        source: "/api/v1/:path*",
        destination: target.replace(/\/$/, "") + "/api/v1/:path*",
      },
    ];
  },
};

export default nextConfig;
