import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
import { resolve } from 'path';
import type { Plugin } from 'vite';

// Plugin to resolve ws optional native dependencies to JS shims
function wsShimsPlugin(): Plugin {
  const shimDir = resolve(__dirname, 'src/shims');
  return {
    name: 'ws-shims',
    enforce: 'pre',
    resolveId(id) {
      if (id === 'bufferutil') {
        return resolve(shimDir, 'bufferutil.ts');
      }
      if (id === 'utf-8-validate') {
        return resolve(shimDir, 'utf-8-validate.ts');
      }
      return null;
    },
  };
}

export default defineConfig({
  build: {
    outDir: 'dist',
  },
  main: {
    plugins: [wsShimsPlugin(), externalizeDepsPlugin({ exclude: ['ws'] })],
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/main/index.ts'),
        },
      },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
        },
      },
    },
  },
  renderer: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/renderer/index.html'),
        },
      },
    },
  },
});
