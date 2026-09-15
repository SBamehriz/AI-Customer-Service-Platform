import path from 'node:path';
import { defineConfig } from 'vite';

/**
 * Build for the embeddable widget.
 *
 * A separate config, but the same toolchain and the same language as the rest
 * of the project, so the widget is not a second npm package to keep in sync.
 * It emits one self contained bundle with no dependencies, so a site that
 * embeds it loads a single file.
 */
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: path.resolve(__dirname, 'src/widget/index.ts'),
      name: 'SupportWidget',
      formats: ['iife'],
      fileName: () => 'widget.js',
    },
    rollupOptions: {
      output: { extend: true },
    },
    // The widget is loaded on pages we do not own, and every byte comes out of
    // somebody else's page load budget.
    minify: 'esbuild',
    target: 'es2020',
  },
});
