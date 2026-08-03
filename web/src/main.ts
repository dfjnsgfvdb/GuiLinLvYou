import App from '@/App.vue'

import { setupRouter } from '@/router'

import { setupStore } from '@/store'

import 'virtual:uno.css'

const app = createApp(App)

async function setupApp() {
  setupStore(app)
  await setupRouter(app)
  app.mount('#app')
}

setupApp()

// 初始化用户状态
const userStore = useUserStore()
userStore.init()

export default app
