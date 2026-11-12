// Vite 构建配置：挂 Vue 插件，并把 /api 代理到本地后端，避免开发期跨域（报告 §4.1 接入层）
// TODO(M1-T5) 控制台接入事件接口后，/api 代理指向 backend 的 GET /api/events
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
