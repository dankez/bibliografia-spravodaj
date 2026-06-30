// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  build: {
    // The site renders thousands of pages, so keep generation conservative.
    concurrency: 1
  },
  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: ['minisearch'],
    },
  },
});
