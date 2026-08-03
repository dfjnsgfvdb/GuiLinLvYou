<script lang="ts" setup>
import * as GlobalAPI from '@/api'

type StepStatus = {
  status?: string
  success_count?: number
  failed_count?: number
  duration_ms?: number
  update_time?: string
  error_message?: string
}

const messageApi = useMessage()
const stages = [
  { key: 'import', title: '数据导入', note: '原始文件写入 MinIO，任务元数据写入 MySQL', icon: 'i-lucide-file-input' },
  { key: 'clean', title: '清洗去重', note: '文本标准化、内容去重与清洗结果持久化', icon: 'i-lucide-eraser' },
  { key: 'extract', sourceKeys: ['chunk', 'extract'], title: '切分与抽取', note: '切片、景区、地点、主题、事件与情感要素', icon: 'i-lucide-scan-text' },
  { key: 'cluster', title: '事件聚合', note: '跨来源文本聚合为可管理的舆情事件', icon: 'i-lucide-git-merge' },
  { key: 'graph', title: '图谱构建', note: '写入事件、景区、地点、来源和主题关系', icon: 'i-lucide-network' },
  { key: 'index', title: '索引构建', note: '发布 FAISS 向量索引与 BM25 关键词索引', icon: 'i-lucide-scan-search' },
]

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const sourceType = ref('news')
const taskRecords = ref<any[]>([])
const taskLoading = ref(false)
const uploadLoading = ref(false)
const graphLoading = ref(false)
const indexLoading = ref(false)
const retryingTaskNo = ref('')

const latestTask = computed(() => taskRecords.value[0] || null)
const failedTasks = computed(() => taskRecords.value.filter(item => item.status === 'failed'))

function parseStepStatus(task: any): Record<string, StepStatus> {
  if (!task?.step_status) {
    return {}
  }
  if (typeof task.step_status === 'object') {
    return task.step_status
  }
  try {
    return JSON.parse(task.step_status)
  } catch {
    return {}
  }
}

function stageStatus(def: any): StepStatus {
  if (!latestTask.value) {
    return { status: 'pending' }
  }
  const map = parseStepStatus(latestTask.value)
  const matched = (def.sourceKeys || [def.key]).map((key: string) => map[key]).filter(Boolean)
  if (!matched.length) {
    return { status: latestTask.value.status === 'success' ? 'success' : 'pending' }
  }
  const priority = ['failed', 'running', 'success', 'pending']
  return {
    status: priority.find(state => matched.some((item: any) => item.status === state)) || 'pending',
    success_count: matched.reduce((sum: number, item: any) => sum + Number(item.success_count || 0), 0),
    failed_count: matched.reduce((sum: number, item: any) => sum + Number(item.failed_count || 0), 0),
    duration_ms: matched.reduce((sum: number, item: any) => sum + Number(item.duration_ms || 0), 0),
    update_time: matched.at(-1)?.update_time,
    error_message: matched.find((item: any) => item.error_message)?.error_message,
  }
}

const stageRows = computed(() => stages.map(stage => ({ ...stage, state: stageStatus(stage) })))

const statusLabel = (status?: string) => ({
  pending: '待执行', running: '处理中', success: '成功', failed: '失败', skipped: '已跳过',
} as any)[status || 'pending'] || status

function formatDuration(duration?: number) {
  const value = Number(duration || 0)
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`
}

async function loadTasks() {
  taskLoading.value = true
  try {
    const response = await GlobalAPI.query_tourism_pipeline_tasks(1, 30)
    const body = await response.json()
    taskRecords.value = body.data?.records || []
  } finally {
    taskLoading.value = false
  }
}

function handleFileChange(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null
}

function clearFile() {
  selectedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function uploadFile() {
  if (!selectedFile.value) {
    messageApi.warning('请选择 CSV、JSON 或 JSONL 文件')
    return
  }
  const name = selectedFile.value.name.toLowerCase()
  if (!['.csv', '.json', '.jsonl'].some(ext => name.endsWith(ext))) {
    messageApi.warning('仅支持 CSV、JSON 和 JSONL 文件')
    return
  }
  uploadLoading.value = true
  try {
    const response = await GlobalAPI.upload_tourism_pipeline_file(selectedFile.value, sourceType.value)
    const body = await response.json()
    if (body.code !== 200) {
      throw new Error(body.msg)
    }
    messageApi.success('数据处理链路执行完成')
    clearFile()
    await loadTasks()
  } catch (error: any) {
    messageApi.error(error?.message || '数据处理失败')
  } finally {
    uploadLoading.value = false
  }
}

async function rebuildGraph() {
  graphLoading.value = true
  try {
    const body = await (await GlobalAPI.rebuild_tourism_graph(false)).json()
    body.code === 200 ? messageApi.success('Neo4j 图谱重建完成') : messageApi.error(body.msg)
    await loadTasks()
  } finally {
    graphLoading.value = false
  }
}

async function rebuildIndex() {
  indexLoading.value = true
  try {
    const body = await (await GlobalAPI.rebuild_tourism_index()).json()
    body.code === 200 ? messageApi.success('FAISS / BM25 索引重建完成') : messageApi.error(body.msg)
    await loadTasks()
  } finally {
    indexLoading.value = false
  }
}

async function retryTask(taskNo: string) {
  retryingTaskNo.value = taskNo
  try {
    const body = await (await GlobalAPI.retry_tourism_pipeline_task(taskNo)).json()
    body.code === 200 ? messageApi.success('失败任务重试完成') : messageApi.error(body.msg)
    await loadTasks()
  } finally {
    retryingTaskNo.value = ''
  }
}

onMounted(loadTasks)
</script>

<template>
  <main class="tourism-page pipeline-page">
    <header class="tourism-page-header">
      <div>
        <h2>旅游舆情数据管道</h2>
        <p>从原始新闻、评论与平台舆情数据开始，完成清洗、去重、抽取、聚合、图谱和混合检索索引构建。</p>
      </div>
      <button class="tourism-secondary-button" type="button" :disabled="taskLoading" @click="loadTasks">
        <span :class="taskLoading ? 'i-lucide-loader-circle spin' : 'i-lucide-refresh-cw'"></span>刷新任务
      </button>
    </header>

    <section class="operation-grid">
      <article class="tourism-panel upload-operation">
        <header class="operation-title">
          <span class="i-lucide-upload"></span>
          <div><h3>导入舆情数据</h3><p>支持 CSV、JSON、JSONL，单次导入将触发完整处理链路。</p></div>
        </header>
        <div class="upload-controls">
          <select v-model="sourceType" aria-label="数据来源类型">
            <option value="news">新闻资讯</option>
            <option value="comment">游客评论</option>
            <option value="complaint">投诉数据</option>
            <option value="social">社交平台</option>
            <option value="manual">手动导入</option>
          </select>
          <label class="file-select">
            <span class="i-lucide-file-plus-2"></span>
            <span>{{ selectedFile?.name || '选择数据文件' }}</span>
            <input ref="fileInput" type="file" accept=".csv,.json,.jsonl" @change="handleFileChange">
          </label>
          <button class="tourism-primary-button" type="button" :disabled="uploadLoading" @click="uploadFile">
            <span :class="uploadLoading ? 'i-lucide-loader-circle spin' : 'i-lucide-play'"></span>
            {{ uploadLoading ? '处理中' : '执行管道' }}
          </button>
        </div>
      </article>

      <article class="tourism-panel maintenance-operation">
        <header class="operation-title">
          <span class="i-lucide-wrench"></span>
          <div><h3>索引维护</h3><p>基于 MySQL 当前业务数据独立重建图谱或检索索引。</p></div>
        </header>
        <div class="maintenance-buttons">
          <button class="tourism-secondary-button" type="button" :disabled="graphLoading" @click="rebuildGraph">
            <span class="i-lucide-network"></span>{{ graphLoading ? '重建中' : '重建图谱' }}
          </button>
          <button class="tourism-secondary-button" type="button" :disabled="indexLoading" @click="rebuildIndex">
            <span class="i-lucide-scan-search"></span>{{ indexLoading ? '重建中' : '重建索引' }}
          </button>
        </div>
      </article>
    </section>

    <section class="tourism-panel stage-panel">
      <header class="tourism-panel-header">
        <h3>最新任务执行链路</h3>
        <span class="tourism-muted mono">{{ latestTask?.task_no || '暂无任务' }}</span>
      </header>
      <div class="stage-flow">
        <article v-for="(stage, index) in stageRows" :key="stage.key" :class="['stage-item', `stage-${stage.state.status || 'pending'}`]">
          <div class="stage-sequence">{{ String(index + 1).padStart(2, '0') }}</div>
          <span :class="['stage-icon', stage.icon]"></span>
          <div class="stage-copy">
            <strong>{{ stage.title }}</strong>
            <p>{{ stage.note }}</p>
            <small>成功 {{ stage.state.success_count || 0 }} · 失败 {{ stage.state.failed_count || 0 }} · {{ formatDuration(stage.state.duration_ms) }}</small>
          </div>
          <span class="stage-state">{{ statusLabel(stage.state.status) }}</span>
        </article>
      </div>
    </section>

    <section class="tourism-panel task-panel">
      <header class="tourism-panel-header">
        <h3>处理任务记录</h3>
        <span class="tourism-muted">失败任务 {{ failedTasks.length }} 条</span>
      </header>
      <div class="task-scroll">
        <div class="task-row task-head">
          <span>任务编号</span><span>类型</span><span>来源</span><span>状态</span><span>记录</span><span>耗时</span><span>完成时间</span><span>操作</span>
        </div>
        <div v-for="task in taskRecords" :key="task.task_no" class="task-row">
          <span class="mono">{{ task.task_no }}</span>
          <span>{{ task.task_type || '-' }}</span>
          <span>{{ task.source_type || '-' }}</span>
          <span :class="['task-status', `status-${task.status}`]">{{ statusLabel(task.status) }}</span>
          <span>{{ task.success_count || 0 }} / {{ task.failed_count || 0 }}</span>
          <span>{{ formatDuration(task.duration_ms) }}</span>
          <span>{{ task.finished_at || task.update_time || '-' }}</span>
          <button type="button" :disabled="task.status !== 'failed' || retryingTaskNo === task.task_no" @click="retryTask(task.task_no)">
            {{ retryingTaskNo === task.task_no ? '重试中' : '重试' }}
          </button>
        </div>
        <div v-if="!taskRecords.length" class="tourism-empty">暂无处理任务</div>
      </div>
    </section>
  </main>
</template>

<style lang="scss" scoped>
.operation-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr); gap: 12px; }
.operation-grid > article { padding: 15px; }
.operation-title { display: flex; align-items: flex-start; gap: 10px; }
.operation-title > span { width: 20px; height: 20px; margin-top: 1px; color: #087f6a; }
.operation-title h3 { margin: 0; font-size: 14px; }
.operation-title p { margin: 5px 0 0; color: #71817d; font-size: 10px; }
.upload-controls { display: grid; grid-template-columns: 130px minmax(180px, 1fr) 110px; gap: 8px; margin-top: 15px; }
.upload-controls select { height: 36px; border: 1px solid #ccd9d5; border-radius: 5px; background: #fff; padding: 0 9px; }
.file-select { display: flex; min-width: 0; height: 36px; align-items: center; gap: 7px; border: 1px solid #ccd9d5; border-radius: 5px; padding: 0 10px; color: #60726d; cursor: pointer; }
.file-select > span:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-select input { display: none; }
.maintenance-buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 15px; }
.stage-panel, .task-panel { margin-top: 12px; overflow: hidden; }
.stage-flow { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.stage-item { position: relative; display: grid; min-height: 112px; grid-template-columns: 28px minmax(0, 1fr); gap: 9px; border-right: 1px solid #edf2f0; border-top: 1px solid #edf2f0; padding: 14px; }
.stage-item:nth-child(-n+3) { border-top: 0; }
.stage-item:nth-child(3n) { border-right: 0; }
.stage-sequence { position: absolute; top: 9px; right: 10px; color: #d7e2df; font-family: ui-monospace, monospace; font-size: 16px; font-weight: 700; }
.stage-icon { width: 25px; height: 25px; color: #879692; }
.stage-copy { min-width: 0; }
.stage-copy strong { font-size: 12px; }
.stage-copy p { min-height: 32px; margin: 5px 0; color: #71817d; font-size: 9px; line-height: 1.5; }
.stage-copy small { color: #8b9995; font-size: 8px; }
.stage-state { position: absolute; right: 10px; bottom: 9px; border-radius: 3px; background: #eff3f2; padding: 2px 5px; color: #667873; font-size: 8px; }
.stage-success .stage-icon { color: #15966f; }
.stage-success .stage-state { background: #e9f5f1; color: #08745f; }
.stage-failed .stage-icon { color: #c53b36; }
.stage-failed .stage-state { background: #fff0ef; color: #b32f2a; }
.stage-running .stage-icon { color: #b26a17; }
.stage-running .stage-state { background: #fff6e8; color: #99601b; }
.task-scroll { overflow-x: auto; }
.task-row { display: grid; min-width: 1000px; grid-template-columns: minmax(225px, 1.5fr) 100px 90px 70px 75px 70px 145px 55px; gap: 10px; align-items: center; border-top: 1px solid #edf2f0; padding: 10px 15px; color: #52645f; font-size: 10px; }
.task-head { border-top: 0; background: #f7faf9; color: #71817d; font-weight: 700; }
.task-row button { border: 0; background: transparent; color: #087f6a; cursor: pointer; font-size: 10px; }
.task-row button:disabled { color: #a4afac; }
.task-status { justify-self: start; border-radius: 3px; padding: 3px 6px; }
.status-success { background: #e9f5f1; color: #08745f; }
.status-failed { background: #fff0ef; color: #b32f2a; }
.status-running { background: #fff6e8; color: #99601b; }
.mono { overflow: hidden; font-family: ui-monospace, monospace; text-overflow: ellipsis; white-space: nowrap; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1100px) { .operation-grid { grid-template-columns: 1fr; } .stage-flow { grid-template-columns: repeat(2, 1fr); } .stage-item:nth-child(3n) { border-right: 1px solid #edf2f0; } .stage-item:nth-child(2n) { border-right: 0; } .stage-item:nth-child(3) { border-top: 1px solid #edf2f0; } }
@media (max-width: 650px) { .upload-controls { grid-template-columns: 1fr; } .stage-flow { grid-template-columns: 1fr; } .stage-item { border-right: 0 !important; border-top: 1px solid #edf2f0 !important; } .stage-item:first-child { border-top: 0 !important; } }
</style>
