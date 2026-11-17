<script setup>
import { onMounted, ref } from 'vue'
import LoginButton from './components/LoginButton.vue'

// 控制台根组件：承载标题与事件列表（报告 §5.5 建议队列与控制台入口）
// TODO(M1-T5): 在控制台展示原始 Webhook 事件列表，步骤：
//   1. 请求 GET /api/events（相对路径，走 Vite 代理，不要写死 localhost:8000）
//   2. 把返回的 JSON 列表存起来（ref/响应式变量）
//   3. 失败时不要让整页白屏，至少在页面上能看出请求失败
// 事件列表需要登录后才能读，未登录后端返回 401，这里提示先登录（登录入口见 LoginButton）
const events = ref([])
const loading = ref(true)
const errorMessage = ref('')

async function loadEvents() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/events')
    // 401 表示还没登录，与后端不可用区分开，给用户可执行的提示
    if (response.status === 401) {
      events.value = []
      errorMessage.value = '请先登录后再查看事件'
      return
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    // 接口约定返回数组；非数组按空列表处理，避免 v-for 直接崩掉
    events.value = Array.isArray(data) ? data : []
  } catch (error) {
    // 具体原因留在控制台，页面只给一句中文提示，保证不白屏
    console.error('加载事件列表失败：', error)
    events.value = []
    errorMessage.value = '事件列表加载失败，请确认后端服务已启动后刷新重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadEvents)
</script>

<template>
  <main>
    <header class="app-header">
      <h1>RepoSteward 控制台</h1>
      <LoginButton />
    </header>
    <section class="event-list">
      <p v-if="loading">加载中…</p>
      <p v-else-if="errorMessage" class="error">{{ errorMessage }}</p>
      <p v-else-if="events.length === 0">暂无事件</p>
      <ul v-else>
        <!-- TODO(M1-T5): 遍历事件列表，每条至少展示 type、delivery_id、received_at -->
        <li v-for="event in events" :key="event.id ?? event.delivery_id">
          <span class="event-type">{{ event.type }}</span>
          <span class="event-delivery-id">{{ event.delivery_id }}</span>
          <span class="event-received-at">{{ event.received_at }}</span>
        </li>
      </ul>
    </section>
  </main>
</template>
