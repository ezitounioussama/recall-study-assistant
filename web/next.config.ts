import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The design language forbids decorative imagery beyond product photography,
  // so there is no remote image host to allow. Kept explicit so adding one is a
  // deliberate act.
  images: { remotePatterns: [] },
  // Type errors fail the build. There is no `eslint` key in Next 16's config —
  // linting runs as its own script and its own CI job.
  typescript: { ignoreBuildErrors: false },
};

export default config;
