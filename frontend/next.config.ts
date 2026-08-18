import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Traces exactly which node_modules files the server actually needs into
  // .next/standalone. frontend/Dockerfile.prod (BASE-DESIGN.md §8.1) copies that
  // directory instead of the whole node_modules tree — do not remove this, Phase 5's
  // production image depends on it existing.
  output: "standalone",
};

export default nextConfig;
