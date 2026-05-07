import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Strict Mode double-mounts components; Clerk + Cloudflare Turnstile in modals often break (widget 300010 / "Cannot find Widget").
  reactStrictMode: false,
  output: 'export',
  images: {
    unoptimized: true
  },
  // Disable automatic trailing slash redirect for API routes
  trailingSlash: false,
};

export default nextConfig;
