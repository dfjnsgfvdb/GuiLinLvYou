<script lang="ts" setup>
import * as GlobalAPI from '@/api'

const route = useRoute()
const filters = reactive({
  keyword: '',
  scenic_spot: '',
  sentiment: '',
  risk_level: '',
  limit: 50,
})
const loading = ref(false)
const detailLoading = ref(false)
const records = ref<any[]>([])
const selected = ref<any | null>(null)

const sentimentLabel = (value: string) => ({ positive: '正面', neutral: '中性', negative: '负面' } as any)[value] || '未知'
const riskLabel = (value: string) => ({ critical: '严重', high: '高风险', medium: '中风险', low: '低风险' } as any)[value] || '未评级'

async function loadEvents() {
  loading.value = true
  try {
    const response = await GlobalAPI.query_tourism_events(filters)
    const body = await response.json()
    records.value = body.code === 200 ? body.data || [] : []
  } finally {
    loading.value = false
  }
}

async function openDetail(eventId: string) {
  detailLoading.value = true
  selected.value = { event: records.value.find(item => item.event_id === eventId) }
  try {
    const response = await GlobalAPI.query_tourism_event_detail(eventId)
    const body = await response.json()
    if (body.code === 200) {
      selected.value = body.data
    }
  } finally {
    detailLoading.value = false
  }
}

function clearFilters() {
  Object.assign(filters, { keyword: '', scenic_spot: '', sentiment: '', risk_level: '', limit: 50 })
  loadEvents()
}

onMounted(async () => {
  await loadEvents()
  if (typeof route.query.event === 'string') {
    openDetail(route.query.event)
  }
})
</script>

<template>
  <main class="tourism-page events-page">
    <header class="tourism-page-header">
      <div>
        <h2>旅游舆情事件监测</h2>
        <p>按景区、情感和风险等级筛选聚合事件，查看关联文档与图谱证据。</p>
      </div>
      <button class="tourism-secondary-button" type="button" :disabled="loading" @click="loadEvents">
        <span :class="loading ? 'i-lucide-loader-circle spin' : 'i-lucide-refresh-cw'"></span>
        刷新
      </button>
    </header>

    <section class="filter-bar tourism-panel">
      <label class="search-field">
        <span class="i-lucide-search"></span>
        <input v-model="filters.keyword" placeholder="搜索事件名称、摘要或主题" @keyup.enter="loadEvents">
      </label>
      <input v-model="filters.scenic_spot" placeholder="景区名称" @keyup.enter="loadEvents">
      <select v-model="filters.sentiment">
        <option value="">全部情感</option>
        <option value="negative">负面</option>
        <option value="neutral">中性</option>
        <option value="positive">正面</option>
      </select>
      <select v-model="filters.risk_level">
        <option value="">全部风险</option>
        <option value="critical">严重</option>
        <option value="high">高风险</option>
        <option value="medium">中风险</option>
        <option value="low">低风险</option>
      </select>
      <button class="tourism-primary-button" type="button" @click="loadEvents">
        <span class="i-lucide-list-filter"></span>筛选
      </button>
      <button class="tourism-icon-button" type="button" title="清空筛选" @click="clearFilters">
        <span class="i-lucide-rotate-ccw"></span>
      </button>
    </section>

    <section class="event-table tourism-panel">
      <header class="table-summary">
        <strong>事件清单</strong>
        <span>共 {{ records.length }} 条聚合事件</span>
      </header>
      <div class="table-scroll">
        <div class="table-row table-head">
          <span>事件</span>
          <span>景区 / 地点</span>
          <span>主题</span>
          <span>情感</span>
          <span>风险</span>
          <span>热度</span>
          <span>最近出现</span>
          <span></span>
        </div>
        <button
          v-for="event in records"
          :key="event.event_id"
          class="table-row event-row"
          type="button"
          @click="openDetail(event.event_id)"
        >
          <span class="event-title">
            <strong>{{ event.event_name }}</strong>
            <small>{{ event.event_summary || '暂无事件摘要' }}</small>
          </span>
          <span>{{ event.main_scenic_spot || '桂林全域' }}<small>{{ event.main_location || '-' }}</small></span>
          <span>{{ event.topic || '综合舆情' }}</span>
          <span :class="['sentiment', `sentiment-${event.sentiment}`]">{{ sentimentLabel(event.sentiment) }}</span>
          <span :class="['risk', `risk-${event.risk_level}`]">{{ riskLabel(event.risk_level) }}</span>
          <span>{{ Number(event.heat_score || 0).toFixed(0) }}</span>
          <span>{{ event.last_seen_at || '-' }}</span>
          <span class="i-lucide-chevron-right row-arrow"></span>
        </button>
        <div v-if="!records.length && !loading" class="tourism-empty">没有符合条件的事件</div>
      </div>
    </section>

    <div v-if="selected" class="drawer-mask" @click.self="selected = null">
      <aside class="event-drawer">
        <header class="drawer-header">
          <div>
            <span>EVENT INTELLIGENCE</span>
            <h3>{{ selected.event?.event_name || '事件详情' }}</h3>
          </div>
          <button type="button" title="关闭" @click="selected = null"><span class="i-lucide-x"></span></button>
        </header>
        <div v-if="detailLoading" class="tourism-empty">正在加载事件证据...</div>
        <div v-else class="drawer-content">
          <section class="event-summary">
            <p>{{ selected.event?.event_summary || '暂无事件摘要' }}</p>
            <dl>
              <div><dt>涉及景区</dt><dd>{{ selected.event?.main_scenic_spot || '-' }}</dd></div>
              <div><dt>事件主题</dt><dd>{{ selected.event?.topic || '-' }}</dd></div>
              <div><dt>风险等级</dt><dd>{{ riskLabel(selected.event?.risk_level) }}</dd></div>
              <div><dt>负面比例</dt><dd>{{ Math.round(Number(selected.event?.negative_ratio || 0) * 100) }}%</dd></div>
              <div><dt>来源数量</dt><dd>{{ selected.event?.source_count || 0 }}</dd></div>
              <div><dt>关联文档</dt><dd>{{ selected.documents?.length || 0 }}</dd></div>
            </dl>
          </section>

          <section class="drawer-section">
            <header><h4>来源证据</h4><span>{{ selected.documents?.length || 0 }} 条</span></header>
            <div v-if="selected.documents?.length" class="document-list">
              <a
                v-for="doc in selected.documents"
                :key="doc.doc_id"
                :href="doc.source_url || undefined"
                :target="doc.source_url ? '_blank' : undefined"
                rel="noreferrer"
              >
                <strong>{{ doc.title }}</strong>
                <span>{{ doc.source_name || '未知来源' }} · {{ doc.publish_time || '-' }}</span>
              </a>
            </div>
            <div v-else class="drawer-empty">暂无关联来源</div>
          </section>

          <section class="drawer-section">
            <header><h4>图谱关系</h4><span>{{ selected.graph?.relationships?.length || 0 }} 条</span></header>
            <div class="relation-list">
              <span v-for="relation in selected.graph?.relationships?.slice(0, 12)" :key="relation.id">
                {{ relation.type }}
              </span>
            </div>
            <div v-if="!selected.graph?.relationships?.length" class="drawer-empty">暂无图谱关系</div>
          </section>
        </div>
      </aside>
    </div>
  </main>
</template>

<style lang="scss" scoped>
.filter-bar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 150px 120px 120px auto 36px;
  gap: 9px;
  padding: 12px;
}

.filter-bar input,
.filter-bar select {
  width: 100%;
  height: 36px;
  min-width: 0;
  border: 1px solid #ccd9d5;
  border-radius: 5px;
  background: #fff;
  padding: 0 10px;
  color: #354943;
  outline: 0;
}

.filter-bar input:focus,
.filter-bar select:focus { border-color: #087f6a; }

.search-field {
  display: flex;
  height: 36px;
  align-items: center;
  gap: 7px;
  border: 1px solid #ccd9d5;
  border-radius: 5px;
  padding-left: 10px;
  color: #71817d;
}

.search-field:focus-within { border-color: #087f6a; }
.search-field input { border: 0; padding-left: 0; }

.event-table { margin-top: 12px; overflow: hidden; }

.table-summary {
  display: flex;
  height: 48px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--tourism-border);
  padding: 0 16px;
}

.table-summary span { color: #71817d; font-size: 12px; }
.table-scroll { overflow-x: auto; }

.table-row {
  display: grid;
  min-width: 1050px;
  grid-template-columns: minmax(280px, 1.8fr) 1fr 0.8fr 65px 75px 55px 130px 24px;
  gap: 12px;
  align-items: center;
  padding: 11px 16px;
  text-align: left;
}

.table-head {
  background: #f7faf9;
  color: #60726d;
  font-size: 11px;
  font-weight: 700;
}

.event-row {
  width: 100%;
  border: 0;
  border-top: 1px solid #edf2f0;
  background: #fff;
  color: #435650;
  cursor: pointer;
  font-size: 12px;
}

.event-row:hover { background: #f7faf9; }
.event-row > span { min-width: 0; }
.event-row > span small { display: block; margin-top: 4px; color: #899793; }

.event-title { display: flex; flex-direction: column; }
.event-title strong { overflow: hidden; color: #172321; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.event-title small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.sentiment,
.risk {
  justify-self: start;
  border-radius: 3px;
  padding: 3px 6px;
}

.sentiment-negative,
.risk-high,
.risk-critical { background: #fff0ef; color: #b32f2a; }
.sentiment-positive { background: #eaf7f2; color: #08745f; }
.sentiment-neutral,
.risk-low { background: #f0f4f3; color: #536762; }
.risk-medium { background: #fff6e8; color: #99601b; }
.row-arrow { color: #8a9995; }

.drawer-mask {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgb(9 29 26 / 32%);
}

.event-drawer {
  width: min(560px, 94vw);
  height: 100%;
  overflow-y: auto;
  background: #f4f7f6;
  box-shadow: -12px 0 40px rgb(6 34 30 / 18%);
}

.drawer-header {
  position: sticky;
  z-index: 2;
  top: 0;
  display: flex;
  min-height: 78px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #dfe8e5;
  background: #fff;
  padding: 14px 18px;
}

.drawer-header > div > span { color: #087f6a; font-size: 9px; font-weight: 700; letter-spacing: 1.3px; }
.drawer-header h3 { margin: 5px 0 0; font-size: 17px; }
.drawer-header button { display: inline-flex; width: 34px; height: 34px; align-items: center; justify-content: center; border: 0; background: transparent; cursor: pointer; }
.drawer-content { padding: 14px; }

.event-summary,
.drawer-section { border: 1px solid #dfe8e5; border-radius: 5px; background: #fff; }
.event-summary { padding: 16px; }
.event-summary > p { margin: 0; color: #52645f; line-height: 1.7; }
.event-summary dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 13px; margin: 16px 0 0; }
.event-summary dl div { min-width: 0; }
.event-summary dt { color: #81918d; font-size: 10px; }
.event-summary dd { margin: 4px 0 0; overflow: hidden; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }

.drawer-section { margin-top: 12px; overflow: hidden; }
.drawer-section > header { display: flex; height: 43px; align-items: center; justify-content: space-between; border-bottom: 1px solid #edf2f0; padding: 0 14px; }
.drawer-section h4 { margin: 0; }
.drawer-section header span { color: #81918d; font-size: 11px; }
.document-list a { display: flex; flex-direction: column; border-top: 1px solid #edf2f0; padding: 10px 14px; color: #172321; }
.document-list a:first-child { border-top: 0; }
.document-list a:hover { background: #f7faf9; }
.document-list a span { margin-top: 4px; color: #71817d; font-size: 11px; }
.relation-list { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 14px; }
.relation-list span { border-radius: 3px; background: #eaf5f1; padding: 4px 7px; color: #246959; font-size: 10px; }
.drawer-empty { padding: 22px; color: #81918d; text-align: center; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .filter-bar { grid-template-columns: 1fr 1fr 1fr; }
}

@media (max-width: 600px) {
  .filter-bar { grid-template-columns: 1fr 1fr; }
  .search-field { grid-column: 1 / -1; }
  .event-summary dl { grid-template-columns: repeat(2, 1fr); }
}
</style>
