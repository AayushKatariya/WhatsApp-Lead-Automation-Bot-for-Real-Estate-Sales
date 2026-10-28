import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // a small self-contained server for the Docker image (see Dockerfile)
  // lib/db.ts reads the schema at run time; make sure it ships with every route
  outputFileTracingIncludes: { "/**": ["./db/schema.sql"] },
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
