<script lang="ts" setup>
const route = useRoute()

const pageTitle = computed(() => String(route.meta.title || '舆情工作台'))
const dateText = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'short',
}).format(new Date())
</script>

<template>
  <div class="app-shell">
    <NavigationSideBar />
    <section class="workspace">
      <header class="workspace-header">
        <div>
          <p class="workspace-kicker">桂林旅游舆情智能分析平台</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="workspace-status">
          <span class="online-dot"></span>
          <span>分析服务在线</span>
          <time>{{ dateText }}</time>
        </div>
      </header>
      <main class="workspace-content">
        <LayoutDefault />
      </main>
    </section>
  </div>
</template>

<style lang="scss" scoped>
.app-shell {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #f4f7f6;
  color: #172321;
}

.workspace {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.workspace-header {
  display: flex;
  min-height: 72px;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid #dfe8e5;
  background: rgb(255 255 255 / 94%);
  padding: 0 28px;
}

.workspace-kicker {
  margin: 0 0 3px;
  color: #6a7d78;
  font-size: 12px;
}

.workspace-header h1 {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
}

.workspace-status {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #52645f;
  font-size: 12px;
}

.workspace-status time {
  margin-left: 10px;
  border-left: 1px solid #dfe8e5;
  padding-left: 18px;
}

.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #15966f;
  box-shadow: 0 0 0 3px #def4ec;
}

.workspace-content {
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

@media (max-width: 700px) {
  .app-shell {
    flex-direction: column;
  }

  .workspace-header {
    min-height: 62px;
    padding: 0 16px;
  }

  .workspace-status time,
  .workspace-kicker {
    display: none;
  }
}
</style>
