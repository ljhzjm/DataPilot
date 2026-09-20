import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  getCurrentSession,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
} from '../api/auth'
import type { AuthSession } from '../types/auth'

export const useAuthStore = defineStore('auth', () => {
  const session = ref<AuthSession | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => session.value !== null)
  const user = computed(() => session.value?.user ?? null)
  const workspace = computed(() => session.value?.workspace ?? null)

  async function loadSession(): Promise<void> {
    if (initialized.value) {
      return
    }
    loading.value = true
    try {
      session.value = await getCurrentSession()
    } catch {
      session.value = null
    } finally {
      initialized.value = true
      loading.value = false
    }
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      session.value = await loginRequest(username, password)
      initialized.value = true
    } catch (cause) {
      error.value = toErrorMessage(cause)
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function register(
    username: string,
    password: string,
    displayName: string,
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      session.value = await registerRequest(username, password, displayName)
      initialized.value = true
    } catch (cause) {
      error.value = toErrorMessage(cause)
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await logoutRequest()
    } finally {
      clearSession()
    }
  }

  function clearSession(): void {
    session.value = null
    initialized.value = true
  }

  function clearError(): void {
    error.value = null
  }

  return {
    session,
    initialized,
    loading,
    error,
    isAuthenticated,
    user,
    workspace,
    loadSession,
    login,
    register,
    logout,
    clearSession,
    clearError,
  }
})

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
