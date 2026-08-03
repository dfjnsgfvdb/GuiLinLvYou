<script lang="ts" setup>
import * as GlobalAPI from '@/api'

const loading = ref(false)
const status = ref<any>({ services: [], indexes: [], latest_task: null })

const typeLabel = (value: string) => ({ faiss: 'FAISS 向量索引', bm25: 'BM25 关键词索引', graph: 'Neo4j 图谱版本' } as any)[value] || value

async function loadStatus() {
  loading.value = true
  try {
    const response = await GlobalAPI.query_tourism_system_status()
    const body = await response.json()
    if (body.code === 200) {
      status.value = body.data
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <main class="tourism-page system-page">
    <header class="tourism-page-header">
      <div>
        <h2>系统运行状态</h2>
        <p>查看旅游舆情数据存储、知识图谱、混合检索索引及最近管道任务状态。</p>
      </div>
      <button class="tourism-secondary-button" type="button" :disabled="loading" @click="loadStatus">
        <span :class="loading ? 'i-lucide-loader-circle spin' : 'i-lucide-refresh-cw'"></span>
        刷新状态
      </button>
    </header>

    <section class="service-grid">
      <article v-for="service in status.services" :key="service.name" class="service-item tourism-panel">
        <div class="service-icon">
          <span :class="service.name === 'Neo4j' ? 'i-lucide-network' : service.name === 'MinIO' ? 'i-lucide-hard-drive' : service.name === 'MySQL' ? 'i-lucide-database' : 'i-lucide-scan-search'"></span>
        </div>
        <div class="service-copy">
          <strong>{{ service.name }}</strong>
          <span>{{ service.role }}</span>
        </div>
        <span :class="['service-state', { online: service.available }]">
          <i></i>{{ service.available ? '运行正常' : '不可用' }}
        </span>
      </article>
    </section>

    <section class="status-layout">
      <article class="tourism-panel latest-task">
        <header class="tourism-panel-header"><h3>最近数据任务</h3></header>
        <div v-if="status.latest_task" class="task-content">
          <div class="task-status">
            <span :class="status.latest_task.status === 'success' ? 'i-lucide-circle-check-big success' : 'i-lucide-circle-alert failed'"></span>
            <div>
              <strong>{{ status.latest_task.status === 'success' ? '处理链路执行成功' : '处理链路需要检查' }}</strong>
              <small>{{ status.latest_task.task_no }}</small>
            </div>
          </div>
          <dl>
            <div><dt>成功记录</dt><dd>{{ status.latest_task.success_count || 0 }}</dd></div>
            <div><dt>失败记录</dt><dd>{{ status.latest_task.failed_count || 0 }}</dd></div>
            <div><dt>总耗时</dt><dd>{{ ((status.latest_task.duration_ms || 0) / 1000).toFixed(2) }} 秒</dd></div>
            <div><dt>完成时间</dt><dd>{{ status.latest_task.finished_at || '-' }}</dd></div>
          </dl>
        </div>
        <div v-else class="tourism-empty">暂无数据处理任务</div>
      </article>

      <article class="tourism-panel architecture-panel">
        <header class="tourism-panel-header"><h3>问答运行链路</h3></header>
        <ol class="runtime-flow">
          <li><span>01</span><div><strong>问题分析</strong><small>识别旅游舆情意图与筛选条件</small></div></li>
          <li><span>02</span><div><strong>多路召回</strong><small>FAISS、BM25、事件与图谱并行取证</small></div></li>
          <li><span>03</span><div><strong>证据检查</strong><small>阈值过滤并判断证据充分性</small></div></li>
          <li><span>04</span><div><strong>模型研判</strong><small>生成事实、推断和处置建议</small></div></li>
        </ol>
      </article>
    </section>

    <section class="tourism-panel index-panel">
      <header class="tourism-panel-header">
        <h3>索引版本记录</h3>
        <span class="tourism-muted">最近 {{ status.indexes.length }} 个版本</span>
      </header>
      <div class="index-scroll">
        <div class="index-row index-head">
          <span>索引类型</span><span>版本</span><span>模型</span><span>切片</span><span>文档</span><span>事件</span><span>状态</span><span>构建时间</span>
        </div>
        <div v-for="index in status.indexes" :key="`${index.index_version}-${index.index_type}`" class="index-row">
          <span><strong>{{ typeLabel(index.index_type) }}</strong></span>
          <span class="mono">{{ index.index_version }}</span>
          <span>{{ index.embedding_model || '-' }}</span>
          <span>{{ index.chunk_count || 0 }}</span>
          <span>{{ index.document_count || 0 }}</span>
          <span>{{ index.event_count || 0 }}</span>
          <span :class="['index-state', { active: index.status === 'active' }]">{{ index.status === 'active' ? '使用中' : '已归档' }}</span>
          <span>{{ index.build_finished_at || '-' }}</span>
        </div>
        <div v-if="!status.indexes.length" class="tourism-empty">暂无索引记录</div>
      </div>
    </section>
  </main>
</template>

<style lang="scss" scoped>
.service-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.service-item { display: grid; min-height: 86px; grid-template-columns: 38px minmax(0, 1fr); align-items: center; gap: 12px; padding: 14px; }
.service-icon { display: inline-flex; width: 38px; height: 38px; align-items: center; justify-content: center; border-radius: 4px; background: #e9f5f1; color: #087f6a; }
.service-icon span { width: 19px; height: 19px; }
.service-copy { display: flex; min-width: 0; flex-direction: column; }
.service-copy strong { font-size: 14px; }
.service-copy span { margin-top: 4px; overflow: hidden; color: #71817d; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.service-state { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; color: #b0403b; font-size: 10px; }
.service-state i { width: 6px; height: 6px; border-radius: 50%; background: currentcolor; }
.service-state.online { color: #08745f; }

.status-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(340px, 0.75fr); gap: 12px; margin-top: 12px; }
.task-content { padding: 16px; }
.task-status { display: flex; align-items: center; gap: 11px; }
.task-status > span { width: 30px; height: 30px; }
.task-status .success { color: #15966f; }
.task-status .failed { color: #c53b36; }
.task-status div { display: flex; flex-direction: column; }
.task-status small { margin-top: 4px; color: #81918d; font-family: ui-monospace, monospace; font-size: 10px; }
.task-content dl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 19px 0 0; }
.task-content dl div { border-left: 2px solid #c9dbd6; padding-left: 9px; }
.task-content dt { color: #81918d; font-size: 10px; }
.task-content dd { margin: 5px 0 0; font-size: 13px; font-weight: 700; }

.runtime-flow { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0; margin: 0; padding: 10px 16px 15px; list-style: none; }
.runtime-flow li { display: flex; gap: 9px; border-bottom: 1px solid #edf2f0; padding: 12px 5px; }
.runtime-flow li:nth-last-child(-n+2) { border-bottom: 0; }
.runtime-flow li > span { color: #087f6a; font-family: ui-monospace, monospace; font-size: 10px; font-weight: 700; }
.runtime-flow li div { display: flex; min-width: 0; flex-direction: column; }
.runtime-flow li strong { font-size: 12px; }
.runtime-flow li small { margin-top: 4px; color: #81918d; font-size: 9px; line-height: 1.4; }

.index-panel { margin-top: 12px; overflow: hidden; }
.index-scroll { overflow-x: auto; }
.index-row { display: grid; min-width: 1000px; grid-template-columns: 140px 205px minmax(150px, 1fr) 55px 55px 55px 65px 140px; gap: 10px; align-items: center; border-top: 1px solid #edf2f0; padding: 11px 16px; color: #52645f; font-size: 11px; }
.index-head { border-top: 0; background: #f7faf9; color: #71817d; font-weight: 700; }
.mono { overflow: hidden; font-family: ui-monospace, monospace; text-overflow: ellipsis; white-space: nowrap; }
.index-state { justify-self: start; border-radius: 3px; background: #f0f4f3; padding: 3px 6px; }
.index-state.active { background: #e9f5f1; color: #08745f; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .service-grid { grid-template-columns: repeat(2, 1fr); }
  .status-layout { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .service-grid { grid-template-columns: 1fr; }
  .task-content dl { grid-template-columns: repeat(2, 1fr); }
  .runtime-flow { grid-template-columns: 1fr; }
  .runtime-flow li:nth-last-child(2) { border-bottom: 1px solid #edf2f0; }
}
</style>
