// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  build: {
    // The site renders thousands of pages from large JSON datasets; keep static
    // rendering conservative so local builds do not get killed on 16 GB machines.
    concurrency: 1
  },
  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: ['minisearch'],
    },
  },
});
