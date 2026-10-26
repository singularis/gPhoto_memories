import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// `npm run dev` proxies the API to Flask. Point API_ORIGIN at the cluster to use real photos.
const api = process.env.API_ORIGIN ?? 'http://localhost:5000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/get_photos': api,
      '/photos': api,
      '/rotate': api,
      '/api': api,
    },
  },
  build: {
    target: 'es2022',
    assetsDir: 'assets',
  },
});
