<script setup>
import { onMounted, ref } from 'vue'

// 登录入口组件：未登录显示 GitHub 登录链接，已登录显示当前账号与退出（报告 §5.1 F1.2）
// 所有请求都走相对路径 /api，由 Vite 代理转到后端，不写死后端地址
const currentUser = ref(null)

async function loadCurrentUser() {
  try {
    const response = await fetch('/api/auth/me')
    // 401 就是没登录，属于正常状态，不要当失败处理
    if (!response.ok) {
      currentUser.value = null
      return
    }
    currentUser.value = await response.json()
  } catch (error) {
    console.error('读取登录状态失败：', error)
    currentUser.value = null
  }
}

async function logout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' })
  } finally {
    // 退出后整页刷新，让事件列表跟着回到未登录状态
    window.location.reload()
  }
}

onMounted(loadCurrentUser)
</script>

<template>
  <div class="login-button">
    <template v-if="currentUser">
      <span class="login-name">{{ currentUser.login }}</span>
      <button type="button" class="logout" @click="logout">退出</button>
    </template>
    <a v-else class="login-link" href="/api/auth/login">用 GitHub 登录</a>
  </div>
</template>
