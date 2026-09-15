import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => ({
  plugins: [
    vue(),
    Components({
      dts: 'src/components.d.ts',
      resolvers: [
        ElementPlusResolver({
          importStyle: mode === 'test' ? false : 'css',
        }),
      ],
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/echarts/') || id.includes('/node_modules/zrender/')) {
            return 'charts'
          }
          if (
            id.includes('/node_modules/vue/') ||
            id.includes('/node_modules/@vue/') ||
            id.includes('/node_modules/pinia/') ||
            id.includes('/node_modules/vue-router/')
          ) {
            return 'vue-vendor'
          }
          if (id.includes('/node_modules/markdown-it/')) {
            return 'markdown'
          }
          return undefined
        },
      },
    },
  },
}))
