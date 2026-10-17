import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backend = process.env.FRONT_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  build: { assetsDir: 'static' },
  server: { proxy: { '/api': backend } },
})
