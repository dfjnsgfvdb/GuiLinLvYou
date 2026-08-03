<script lang="ts" setup>
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const items = [
  { label: '舆情总览', name: 'TourismOverview', icon: 'i-lucide-layout-dashboard' },
  { label: '智能研判', name: 'ChatIndex', icon: 'i-lucide-message-square-text' },
  { label: '事件监测', name: 'TourismEvents', icon: 'i-lucide-radar' },
  { label: '知识图谱', name: 'TourismGraph', icon: 'i-lucide-network' },
  { label: '数据管道', name: 'TourismPipeline', icon: 'i-lucide-workflow' },
  { label: '系统状态', name: 'TourismSystem', icon: 'i-lucide-server-cog' },
]

function logout() {
  userStore.logout()
  router.replace('/login')
}
</script>

<template>
  <aside class="sidebar">
    <button class="brand" type="button" title="返回舆情总览" @click="router.push({ name: 'TourismOverview' })">
      <span class="brand-mark">漓</span>
      <span class="brand-copy">
        <strong>漓观</strong>
        <small>GUILIN INSIGHT</small>
      </span>
    </button>

    <nav class="nav-list" aria-label="主导航">
      <button
        v-for="item in items"
        :key="item.name"
        type="button"
        :title="item.label"
        :class="['nav-item', { active: route.name === item.name }]"
        @click="router.push({ name: item.name })"
      >
        <span :class="['nav-icon', item.icon]"></span>
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <div class="user-summary">
        <span class="user-avatar">管</span>
        <span class="user-copy">
          <strong>舆情管理员</strong>
          <small>数据研判中心</small>
        </span>
      </div>
      <button class="logout-button" type="button" title="退出登录" @click="logout">
        <span class="i-lucide-log-out"></span>
      </button>
    </div>
  </aside>
</template>

<style lang="scss" scoped>
.sidebar {
  display: flex;
  width: 232px;
  flex: 0 0 232px;
  flex-direction: column;
  overflow: hidden;
  background: #102e2a;
  color: #e9f4f1;
}

.brand {
  display: flex;
  height: 72px;
  flex: 0 0 72px;
  align-items: center;
  gap: 11px;
  border: 0;
  border-bottom: 1px solid rgb(255 255 255 / 9%);
  background: transparent;
  padding: 0 20px;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.brand-mark {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border: 1px solid #75bca9;
  color: #d9f5ec;
  font-family: STKaiti, KaiTi, serif;
  font-size: 21px;
}

.brand-copy,
.user-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.brand-copy strong {
  font-family: STKaiti, KaiTi, serif;
  font-size: 21px;
  font-weight: 600;
}

.brand-copy small {
  margin-top: 1px;
  color: #8fb3aa;
  font-size: 9px;
  letter-spacing: 1.6px;
}

.nav-list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  padding: 18px 12px;
}

.nav-item {
  display: flex;
  width: 100%;
  height: 42px;
  flex: 0 0 42px;
  align-items: center;
  gap: 12px;
  border: 0;
  border-left: 3px solid transparent;
  border-radius: 4px;
  background: transparent;
  padding: 0 13px;
  color: #aac1bb;
  cursor: pointer;
  font-size: 14px;
  text-align: left;
  transition: 160ms ease;
}

.nav-item:hover {
  background: rgb(255 255 255 / 6%);
  color: #fff;
}

.nav-item.active {
  border-left-color: #42c49d;
  background: #1a443c;
  color: #fff;
}

.nav-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
}

.sidebar-footer {
  display: flex;
  min-height: 70px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid rgb(255 255 255 / 9%);
  padding: 12px 14px;
}

.user-summary {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
}

.user-avatar {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #d7eee7;
  color: #125e50;
  font-size: 12px;
  font-weight: 700;
}

.user-copy strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-copy small {
  margin-top: 3px;
  color: #829e97;
  font-size: 10px;
}

.logout-button {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #8fb3aa;
  cursor: pointer;
}

.logout-button:hover {
  background: rgb(255 255 255 / 7%);
  color: #fff;
}

@media (max-width: 960px) {
  .sidebar {
    width: 76px;
    flex-basis: 76px;
  }

  .brand,
  .nav-item {
    justify-content: center;
    padding-inline: 0;
  }

  .brand-copy,
  .nav-label,
  .user-copy {
    display: none;
  }

  .sidebar-footer {
    justify-content: center;
  }

  .logout-button {
    display: none;
  }
}

@media (max-width: 700px) {
  .sidebar {
    width: 100%;
    height: 62px;
    flex: 0 0 62px;
    flex-direction: row;
    overflow-x: auto;
  }

  .brand {
    width: 58px;
    height: 62px;
    flex: 0 0 58px;
    border-right: 1px solid rgb(255 255 255 / 9%);
    border-bottom: 0;
  }

  .brand-mark {
    width: 30px;
    height: 30px;
  }

  .nav-list {
    flex-direction: row;
    gap: 2px;
    overflow: visible;
    padding: 7px 4px;
  }

  .nav-item {
    width: 48px;
    height: 48px;
    flex: 0 0 48px;
    border-bottom: 3px solid transparent;
    border-left: 0;
  }

  .nav-item.active {
    border-bottom-color: #42c49d;
  }

  .sidebar-footer {
    display: none;
  }
}
</style>
