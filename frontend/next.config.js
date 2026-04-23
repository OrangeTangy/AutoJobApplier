/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export for desktop packaging — served by FastAPI at the same origin.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // No rewrites: with same-origin hosting, the frontend calls the backend via
  // the `/api/v1/*` prefix directly (see `src/lib/api.ts`).
};

module.exports = nextConfig;
