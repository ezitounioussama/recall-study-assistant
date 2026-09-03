import nextConfig from "eslint-config-next";
import nextTs from "eslint-config-next/typescript";

/**
 * ESLint 10 flat config: Next's rules plus its TypeScript set. Generated
 * output and dependencies are ignored; everything under src/ and scripts/ is
 * linted.
 */
const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...nextConfig,
  ...nextTs,
];

export default config;
