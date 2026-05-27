import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Lovable's preset already registers TanStack Start, React, Tailwind and path aliases.
export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
  },
  vite: {
    server: {
      proxy: {
        "/api": "http://127.0.0.1:8765",
      },
    },
  },
});
