import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": here("./"),
      "server-only": here("./tests/server-only-stub.ts"), // the real package throws outside Next.js
    },
  },
  test: { include: ["tests/**/*.test.ts"], environment: "node", testTimeout: 20_000 },
});
