import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

const devCerts = () => {
  try {
    const certDir = path.join(
      process.env.HOME || '',
      '.office-addin-dev-certs'
    );
    return {
      key: fs.readFileSync(path.join(certDir, 'localhost.key')),
      cert: fs.readFileSync(path.join(certDir, 'localhost.crt')),
      ca: fs.readFileSync(path.join(certDir, 'ca.crt')),
    };
  } catch {
    return undefined;
  }
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3100,
    https: devCerts(),
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
