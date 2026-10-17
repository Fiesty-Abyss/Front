import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import pkg from './package.json' with { type: 'json' }

const backend = process.env.FRONT_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  build: { assetsDir: 'static', chunkSizeWarningLimit: 1600 },
  server: { proxy: { '/api': backend } },
})
