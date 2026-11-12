// 前端入口：创建并挂载 Vue 应用根实例到 #app（报告 §5.5 对人交互的控制台载体）
// TODO(M1-T5) 控制台事件列表页面在此挂载后接入
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
