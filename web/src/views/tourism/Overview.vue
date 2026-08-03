<script lang="ts" setup>
import * as GlobalAPI from '@/api'
import TourismChart from './components/TourismChart.vue'

const loading = ref(true)
const errorText = ref('')
const overview = ref<any>({
  metrics: {},
  trend: [],
  source_distribution: [],
  scenic_distribution: [],
  sentiment_distribution: [],
  recent_events: [],
  active_indexes: [],
})

const metricCards = computed(() => [
  {
    label: '舆情文档',
    value: overview.value.metrics.document_count || 0,
    note: '已清洗并进入业务库',
    icon: 'i-lucide-files',
    tone: 'green',
  },
  {
    label: '聚合事件',
    value: overview.value.metrics.event_count || 0,
    note: '当前有效旅游事件',
    icon: 'i-lucide-radar',
    tone: 'blue',
  },
  {
    label: '负面事件',
    value: overview.value.metrics.negative_event_count || 0,
    note: '需持续关注情绪走势',
    icon: 'i-lucide-triangle-alert',
    tone: 'red',
  },
  {
    label: '研判问答',
    value: overview.value.metrics.qa_count || 0,
    note: '证据问答累计记录',
    icon: 'i-lucide-message-square-text',
    tone: 'amber',
  },
])

const trendOption = computed(() => ({
  color: ['#087f6a'],
  tooltip: { trigger: 'axis' },
  grid: { left: 42, right: 18, top: 28, bottom: 32 },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: overview.value.trend.map(item => item.day.slice(5)),
    axisLine: { lineStyle: { color: '#cfdad7' } },
    axisLabel: { color: '#71817d' },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: '#edf2f0' } },
    axisLabel: { color: '#71817d' },
  },
  series: [{
    name: '舆情数量',
    type: 'line',
    smooth: 0.28,
    symbolSize: 7,
    lineStyle: { width: 3 },
    areaStyle: { color: 'rgba(8, 127, 106, 0.10)' },
    data: overview.value.trend.map(item => item.value),
  }],
}))

const sourceOption = computed(() => ({
  color: ['#087f6a', '#3f78b5', '#b26a17', '#c1534d', '#657a75', '#6e8e3a', '#87639a', '#3e8e8b'],
  tooltip: { trigger: 'item' },
  legend: { bottom: 2, type: 'scroll', textStyle: { color: '#667873', fontSize: 11 } },
  series: [{
    type: 'pie',
    radius: ['45%', '68%'],
    center: ['50%', '44%'],
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
    label: { show: false },
    data: overview.value.source_distribution,
  }],
}))

const scenicOption = computed(() => ({
  color: ['#3f78b5'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 88, right: 22, top: 18, bottom: 24 },
  xAxis: {
    type: 'value',
    minInterval: 1,
    splitLine: { lineStyle: { color: '#edf2f0' } },
    axisLabel: { color: '#71817d' },
  },
  yAxis: {
    type: 'category',
    inverse: true,
    data: overview.value.scenic_distribution.map(item => item.name),
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#52645f', width: 76, overflow: 'truncate' },
  },
  series: [{
    type: 'bar',
    barWidth: 13,
    itemStyle: { borderRadius: [0, 3, 3, 0] },
    data: overview.value.scenic_distribution.map(item => item.value),
  }],
}))

function riskLabel(level: string) {
  return ({ critical: '严重', high: '高风险', medium: '中风险', low: '低风险' } as any)[level] || level || '未评级'
}

async function loadOverview() {
  loading.value = true
  errorText.value = ''
  try {
    const response = await GlobalAPI.query_tourism_overview()
    const body = await response.json()
    if (body.code !== 200) {
      throw new Error(body.msg || '获取舆情数据失败')
    }
    overview.value = body.data
  } catch (error: any) {
    errorText.value = error?.message || '获取舆情数据失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <main class="tourism-page overview-page">
    <header class="tourism-page-header">
      <div>
        <h2>全域舆情态势</h2>
        <p>汇总桂林重点景区、平台来源、事件风险与证据问答运行情况。</p>
      </div>
      <button class="tourism-secondary-button" type="button" :disabled="loading" @click="loadOverview">
        <span :class="loading ? 'i-lucide-loader-circle spin' : 'i-lucide-refresh-cw'"></span>
        刷新数据
      </button>
    </header>

    <div v-if="errorText" class="error-banner">
      <span class="i-lucide-circle-alert"></span>{{ errorText }}
    </div>

    <section class="metric-grid" aria-label="核心指标">
      <article v-for="item in metricCards" :key="item.label" :class="['metric-card', `tone-${item.tone}`]">
        <div class="metric-top">
          <span>{{ item.label }}</span>
          <span :class="['metric-icon', item.icon]"></span>
        </div>
        <strong>{{ item.value }}</strong>
        <p>{{ item.note }}</p>
      </article>
    </section>

    <section class="analysis-grid">
      <article class="tourism-panel trend-panel">
        <header class="tourism-panel-header">
          <h3>舆情收录趋势</h3>
          <span class="tourism-muted">按发布日期</span>
        </header>
        <div class="chart-wrap">
          <TourismChart v-if="overview.trend.length" :option="trendOption" />
          <div v-else class="tourism-empty">暂无趋势数据</div>
        </div>
      </article>

      <article class="tourism-panel source-panel">
        <header class="tourism-panel-header">
          <h3>平台来源构成</h3>
          <span class="tourism-muted">Top 8</span>
        </header>
        <div class="chart-wrap">
          <TourismChart v-if="overview.source_distribution.length" :option="sourceOption" />
          <div v-else class="tourism-empty">暂无来源数据</div>
        </div>
      </article>

      <article class="tourism-panel scenic-panel">
        <header class="tourism-panel-header">
          <h3>重点景区事件分布</h3>
          <span class="tourism-muted">按事件数</span>
        </header>
        <div class="chart-wrap">
          <TourismChart v-if="overview.scenic_distribution.length" :option="scenicOption" />
          <div v-else class="tourism-empty">暂无景区数据</div>
        </div>
      </article>

      <article class="tourism-panel event-panel">
        <header class="tourism-panel-header">
          <h3>近期重点事件</h3>
          <button type="button" @click="$router.push({ name: 'TourismEvents' })">
            查看全部<span class="i-lucide-arrow-right"></span>
          </button>
        </header>
        <div v-if="overview.recent_events.length" class="event-list">
          <button
            v-for="event in overview.recent_events"
            :key="event.event_id"
            type="button"
            @click="$router.push({ name: 'TourismEvents', query: { event: event.event_id } })"
          >
            <span class="event-main">
              <strong>{{ event.event_name }}</strong>
              <small>{{ event.main_scenic_spot || '桂林全域' }} · {{ event.topic || '综合舆情' }}</small>
            </span>
            <span :class="['risk-tag', `risk-${event.risk_level || 'low'}`]">{{ riskLabel(event.risk_level) }}</span>
            <span class="event-heat">热度 {{ Number(event.heat_score || 0).toFixed(0) }}</span>
          </button>
        </div>
        <div v-else class="tourism-empty">暂无聚合事件</div>
      </article>
    </section>
  </main>
</template>

<style lang="scss" scoped>
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  border: 1px solid #edc9c6;
  border-radius: 5px;
  background: #fff5f4;
  padding: 10px 12px;
  color: #a93631;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  min-width: 0;
  border: 1px solid var(--tourism-border);
  border-top: 3px solid #087f6a;
  border-radius: 5px;
  background: #fff;
  padding: 16px 17px 14px;
}

.metric-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #60726d;
  font-size: 13px;
}

.metric-icon {
  width: 18px;
  height: 18px;
  color: #087f6a;
}

.metric-card strong {
  display: block;
  margin-top: 10px;
  color: #172321;
  font-size: 29px;
  line-height: 1;
}

.metric-card p {
  margin: 9px 0 0;
  color: #81918d;
  font-size: 11px;
}

.tone-blue { border-top-color: #3f78b5; }
.tone-blue .metric-icon { color: #3f78b5; }
.tone-red { border-top-color: #c53b36; }
.tone-red .metric-icon { color: #c53b36; }
.tone-amber { border-top-color: #b26a17; }
.tone-amber .metric-icon { color: #b26a17; }

.analysis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.75fr);
  gap: 12px;
  margin-top: 12px;
}

.chart-wrap {
  height: 280px;
  padding: 8px 8px 2px;
}

.source-panel .chart-wrap,
.scenic-panel .chart-wrap {
  height: 280px;
}

.event-panel {
  grid-column: 1 / -1;
}

.tourism-panel-header > button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  background: transparent;
  color: #087f6a;
  cursor: pointer;
  font-size: 12px;
}

.event-list > button {
  display: grid;
  width: 100%;
  min-height: 57px;
  grid-template-columns: minmax(0, 1fr) 76px 84px;
  align-items: center;
  gap: 16px;
  border: 0;
  border-top: 1px solid #edf2f0;
  background: #fff;
  padding: 9px 16px;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.event-list > button:first-child { border-top: 0; }
.event-list > button:hover { background: #f7faf9; }

.event-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.event-main strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-main small {
  margin-top: 5px;
  color: #71817d;
  font-size: 11px;
}

.risk-tag {
  justify-self: start;
  border-radius: 3px;
  background: #edf5f2;
  padding: 3px 7px;
  color: #356257;
  font-size: 11px;
}

.risk-high,
.risk-critical {
  background: #fff0ef;
  color: #b32f2a;
}

.risk-medium {
  background: #fff6e8;
  color: #99601b;
}

.event-heat {
  color: #71817d;
  font-size: 11px;
  text-align: right;
}

.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analysis-grid { grid-template-columns: 1fr; }
  .event-panel { grid-column: auto; }
}

@media (max-width: 560px) {
  .metric-grid { grid-template-columns: 1fr; }
  .event-list > button { grid-template-columns: minmax(0, 1fr) auto; }
  .event-heat { display: none; }
}
</style>
