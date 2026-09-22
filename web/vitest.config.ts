import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Playwright owns e2e/ (separate runner, needs browsers).
    exclude: ["e2e/**", "node_modules/**"],
  },
});
