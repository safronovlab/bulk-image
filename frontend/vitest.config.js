import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react({ jsxRuntime: 'automatic' })],
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
    include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    // The worker tests read source files via fs.readFileSync(new URL(...))
    // and require Node's URL behavior (file:// scheme honored). Use the
    // node environment for that suite; everything else stays in jsdom.
    environmentMatchGlobs: [
      ['src/workers/**', 'node'],
      ['src/lib/**', 'node'],
    ],
  },
});
