<script setup lang="ts">
import { DatabaseZap, LogIn, UserPlus } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const mode = ref<'login' | 'register'>('login')
const form = reactive({
  username: '',
  password: '',
  displayName: '',
})

async function submit(): Promise<void> {
  auth.clearError()
  try {
    if (mode.value === 'login') {
      await auth.login(form.username, form.password)
    } else {
      await auth.register(
        form.username,
        form.password,
        form.displayName || form.username,
      )
    }
    const redirect = typeof route.query.redirect === 'string'
      ? route.query.redirect
      : '/'
    await router.push(redirect.startsWith('/') ? redirect : '/')
  } catch {
    return
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-panel">
      <div class="auth-brand">
        <span class="auth-mark"><DatabaseZap :size="22" /></span>
        <div>
          <h1>DataPilot</h1>
          <p>Conversational Analytics</p>
        </div>
      </div>

      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-alert
        v-if="auth.error"
        type="error"
        :title="auth.error"
        :closable="false"
        show-icon
      />

      <el-form class="auth-form" label-position="top" @submit.prevent="submit">
        <el-form-item v-if="mode === 'register'" label="显示名称">
          <el-input
            v-model="form.displayName"
            maxlength="120"
            autocomplete="name"
            placeholder="例如：张三"
          />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            minlength="3"
            maxlength="64"
            autocomplete="username"
            placeholder="3-64 位用户名"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            minlength="8"
            maxlength="128"
            show-password
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            placeholder="至少 8 位"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          class="auth-submit"
          type="primary"
          :icon="mode === 'login' ? LogIn : UserPlus"
          :loading="auth.loading"
          native-type="submit"
        >
          {{ mode === 'login' ? '登录' : '创建账号' }}
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    linear-gradient(135deg, #eef6f5 0%, #f8fafc 52%, #f3f4f6 100%);
}

.auth-panel {
  width: min(420px, 100%);
  display: grid;
  gap: 18px;
  padding: 28px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-color);
  box-shadow: 0 18px 45px rgb(23 33 43 / 10%);
}

.auth-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.auth-mark {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #0f766e;
  background: #e7f6f3;
}

.auth-brand h1 {
  margin: 0;
  color: var(--heading-color);
  font-size: 22px;
  letter-spacing: 0;
}

.auth-brand p {
  margin: 3px 0 0;
  color: var(--muted-color);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.auth-form {
  display: grid;
  gap: 2px;
}

.auth-submit {
  width: 100%;
  margin-top: 6px;
}
</style>
