import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://192.168.1.99',
        changeOrigin: true,
      },
    },
  },
})

/*
./easytier-core -d --network-name macheng --network-secret gsmart@2021 \
  -p tcp://turn.bj.629957.xyz:11010 -p tcp://turn.js.629957.xyz:11012 \
  -l 11050
*/
