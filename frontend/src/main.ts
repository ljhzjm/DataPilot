import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './styles.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
window.addEventListener('datapilot:unauthorized', () => {
  const auth = useAuthStore()
  auth.clearSession()
  if (router.currentRoute.value.name !== 'login') {
    void router.push({
      name: 'login',
      query: { redirect: router.currentRoute.value.fullPath },
    })
  }
})
app.mount('#app')
