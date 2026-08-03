<script lang="ts" setup>
import { useMessage } from 'naive-ui'
import loginLandscape from '@/assets/images/guilin-login-landscape.png'
import * as GlobalAPI from '@/api'

const form = reactive({ username: 'admin', password: '123456' })
const loading = ref(false)
const message = useMessage()
const router = useRouter()
const userStore = useUserStore()

onMounted(() => {
  if (userStore.isLoggedIn) {
    router.replace('/')
  }
})

async function handleLogin() {
  if (!form.username.trim() || !form.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const response = await GlobalAPI.login(form.username.trim(), form.password)
    const body = await response.json()
    if (body.code !== 200 || !body.data?.token) {
      message.error(body.msg || '登录失败，请检查用户名和密码')
      return
    }
    userStore.login({ token: body.data.token })
    await router.replace('/')
  } catch {
    message.error('服务暂时不可用，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page" :style="{ backgroundImage: `url(${loginLandscape})` }">
    <div class="login-shade"></div>
    <section class="login-intro">
      <div class="login-brand">
        <span class="brand-mark">漓</span>
        <div>
          <strong>漓观</strong>
          <small>GUILIN TOURISM INSIGHT</small>
        </div>
      </div>
      <h1>桂林旅游舆情<br>智能分析平台</h1>
      <p>汇聚多源舆情，关联景区事件，以可追溯证据支撑研判与处置。</p>
      <div class="capability-row" aria-label="系统能力">
        <span>多路召回</span>
        <span>事件聚合</span>
        <span>图谱关联</span>
        <span>证据溯源</span>
      </div>
    </section>

    <form class="login-form" @submit.prevent="handleLogin">
      <header>
        <p>ANALYSIS CONSOLE</p>
        <h2>进入研判工作台</h2>
        <span>使用平台账户登录</span>
      </header>

      <label for="username">用户名</label>
      <div class="field-wrap">
        <span class="i-lucide-user-round"></span>
        <input id="username" v-model="form.username" autocomplete="username" placeholder="请输入用户名">
      </div>

      <label for="password">密码</label>
      <div class="field-wrap">
        <span class="i-lucide-lock-keyhole"></span>
        <input
          id="password"
          v-model="form.password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        >
      </div>

      <button type="submit" :disabled="loading">
        <span v-if="loading" class="i-lucide-loader-circle loading-icon"></span>
        <span v-else class="i-lucide-log-in"></span>
        {{ loading ? '正在验证' : '登录平台' }}
      </button>

      <footer>
        <span class="status-dot"></span>
        本地中间件与分析服务就绪后可登录
      </footer>
    </form>
  </main>
</template>

<style lang="scss" scoped>
.login-page {
  position: relative;
  display: grid;
  width: 100%;
  min-height: 100%;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 440px);
  align-items: center;
  gap: 8vw;
  overflow: auto;
  background-position: center;
  background-size: cover;
  padding: 7vh 8vw;
}

.login-shade {
  position: absolute;
  inset: 0;
  background: rgb(5 27 25 / 47%);
}

.login-intro,
.login-form {
  position: relative;
  z-index: 1;
}

.login-intro {
  max-width: 640px;
  color: #fff;
  text-shadow: 0 2px 20px rgb(0 0 0 / 30%);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 13px;
}

.brand-mark {
  display: inline-flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(255 255 255 / 65%);
  font-family: STKaiti, KaiTi, serif;
  font-size: 27px;
}

.login-brand div {
  display: flex;
  flex-direction: column;
}

.login-brand strong {
  font-family: STKaiti, KaiTi, serif;
  font-size: 26px;
}

.login-brand small {
  margin-top: 1px;
  color: #d6ebe5;
  font-size: 9px;
  letter-spacing: 2px;
}

.login-intro h1 {
  margin: 44px 0 16px;
  font-size: clamp(38px, 4.6vw, 68px);
  font-weight: 600;
  line-height: 1.16;
}

.login-intro > p {
  max-width: 560px;
  margin: 0;
  color: #e2eeeb;
  font-size: 17px;
  line-height: 1.8;
}

.capability-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 34px;
  color: #e2eeeb;
  font-size: 12px;
}

.capability-row span::before {
  display: inline-block;
  width: 4px;
  height: 4px;
  margin: 0 8px 2px 0;
  border-radius: 50%;
  background: #64dbb6;
  content: '';
}

.login-form {
  border: 1px solid rgb(255 255 255 / 34%);
  border-radius: 6px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 24px 70px rgb(0 18 16 / 34%);
  padding: 36px 38px 30px;
  color: #172321;
  backdrop-filter: blur(12px);
}

.login-form header {
  margin-bottom: 28px;
}

.login-form header p {
  margin: 0 0 7px;
  color: #087f6a;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
}

.login-form h2 {
  margin: 0;
  font-size: 23px;
}

.login-form header span {
  display: block;
  margin-top: 7px;
  color: #71817d;
  font-size: 13px;
}

.login-form label {
  display: block;
  margin: 16px 0 7px;
  color: #354943;
  font-size: 13px;
  font-weight: 600;
}

.field-wrap {
  display: flex;
  height: 42px;
  align-items: center;
  gap: 9px;
  border: 1px solid #cbd9d5;
  border-radius: 5px;
  background: #fff;
  padding: 0 12px;
  color: #80918c;
}

.field-wrap:focus-within {
  border-color: #087f6a;
  box-shadow: 0 0 0 3px rgb(8 127 106 / 10%);
}

.field-wrap input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  color: #172321;
}

.login-form > button {
  display: flex;
  width: 100%;
  height: 42px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 24px;
  border: 1px solid #087f6a;
  border-radius: 5px;
  background: #087f6a;
  color: #fff;
  cursor: pointer;
  font-weight: 700;
}

.login-form > button:hover {
  background: #066c5a;
}

.loading-icon {
  animation: rotate 1s linear infinite;
}

.login-form footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 18px;
  color: #82908d;
  font-size: 11px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #18a476;
}

@keyframes rotate {
  to { transform: rotate(360deg); }
}

@media (max-width: 800px) {
  .login-page {
    grid-template-columns: 1fr;
    align-content: center;
    padding: 28px 18px;
  }

  .login-intro {
    display: none;
  }

  .login-form {
    width: min(100%, 420px);
    margin: auto;
    padding: 30px 24px 25px;
  }
}
</style>
