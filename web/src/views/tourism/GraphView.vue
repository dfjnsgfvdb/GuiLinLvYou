<script lang="ts" setup>
import * as GlobalAPI from '@/api'
import TourismChart from './components/TourismChart.vue'

const loading = ref(false)
const query = ref('')
const graph = ref<any>({ nodes: [], relationships: [], paths: [], available: true })
const selectedNode = ref<any | null>(null)

const categories = [
  { name: '事件', label: 'Event', color: '#c1534d' },
  { name: '景区', label: 'ScenicSpot', color: '#087f6a' },
  { name: '地点', label: 'Location', color: '#3f78b5' },
  { name: '文档', label: 'Document', color: '#6d7f7a' },
  { name: '来源', label: 'Source', color: '#b26a17' },
  { name: '主题', label: 'Topic', color: '#87639a' },
]

function nodeLabel(node: any) {
  const props = node.properties || {}
  return props.name || props.title || props.event_id || props.doc_id || node.id
}

function nodeCategory(node: any) {
  const label = node.labels?.[0]
  const index = categories.findIndex(item => item.label === label)
  return index < 0 ? 0 : index
}

const graphOption = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  const nodes = graph.value.nodes.map((node: any) => {
    const label = nodeLabel(node)
    const category = nodeCategory(node)
    const matched = !keyword || label.toLowerCase().includes(keyword)
    return {
      ...node,
      name: label,
      value: label,
      category,
      symbolSize: node.labels?.includes('Event') ? 34 : node.labels?.includes('Document') ? 17 : 25,
      itemStyle: { opacity: matched ? 1 : 0.18 },
      label: { show: matched && (node.labels?.includes('Event') || node.labels?.includes('ScenicSpot')) },
    }
  })
  const links = graph.value.relationships.map((relation: any) => ({
    source: relation.start_node,
    target: relation.end_node,
    name: relation.type,
    lineStyle: { opacity: keyword ? 0.16 : 0.48 },
  }))
  return {
    color: categories.map(item => item.color),
    tooltip: {
      formatter(params: any) {
        if (params.dataType === 'edge') {
          return params.data.name
        }
        const labels = params.data.labels?.join(' / ') || '节点'
        return `<strong>${params.name}</strong><br>${labels}`
      },
    },
    legend: [{
      data: categories.map(item => item.name),
      bottom: 12,
      textStyle: { color: '#52645f' },
    }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: nodes,
      links,
      categories: categories.map(item => ({ name: item.name })),
      force: { repulsion: 250, edgeLength: [55, 130], gravity: 0.08 },
      label: {
        position: 'right',
        color: '#354943',
        fontSize: 10,
        formatter: '{b}',
      },
      lineStyle: { color: '#9bb0aa', curveness: 0.08, width: 1 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2, opacity: 0.9 } },
    }],
  }
})

async function loadGraph() {
  loading.value = true
  try {
    const response = await GlobalAPI.query_tourism_graph(100)
    const body = await response.json()
    if (body.code === 200) {
      graph.value = body.data
    }
  } finally {
    loading.value = false
  }
}

function handleChartClick(params: any) {
  if (params.dataType === 'node') {
    selectedNode.value = params.data
  }
}

onMounted(loadGraph)
</script>

<template>
  <main class="tourism-page graph-page">
    <header class="tourism-page-header">
      <div>
        <h2>旅游舆情知识图谱</h2>
        <p>观察事件、景区、地点、来源、文档和主题之间的关联，支持拖拽、缩放与节点聚焦。</p>
      </div>
      <button class="tourism-secondary-button" type="button" :disabled="loading" @click="loadGraph">
        <span :class="loading ? 'i-lucide-loader-circle spin' : 'i-lucide-refresh-cw'"></span>
        刷新图谱
      </button>
    </header>

    <section class="graph-workbench tourism-panel">
      <header class="graph-toolbar">
        <label>
          <span class="i-lucide-search"></span>
          <input v-model="query" placeholder="搜索事件、景区或来源节点">
        </label>
        <div class="graph-stat">
          <span><strong>{{ graph.nodes.length }}</strong> 节点</span>
          <span><strong>{{ graph.relationships.length }}</strong> 关系</span>
        </div>
      </header>

      <div class="graph-layout">
        <div class="graph-canvas">
          <TourismChart
            v-if="graph.available && graph.nodes.length"
            :option="graphOption"
            @chart-click="handleChartClick"
          />
          <div v-else class="tourism-empty">
            {{ graph.available === false ? 'Neo4j 当前不可用' : '暂无图谱数据，请先执行数据管道' }}
          </div>
        </div>

        <aside class="node-inspector">
          <header>
            <h3>节点详情</h3>
            <button v-if="selectedNode" type="button" title="清除选择" @click="selectedNode = null">
              <span class="i-lucide-x"></span>
            </button>
          </header>
          <div v-if="selectedNode" class="node-detail">
            <span :class="['node-type', `type-${selectedNode.labels?.[0]}`]">
              {{ categories.find(item => item.label === selectedNode.labels?.[0])?.name || '节点' }}
            </span>
            <h4>{{ selectedNode.name }}</h4>
            <dl>
              <template v-for="(value, key) in selectedNode.properties" :key="key">
                <dt>{{ key }}</dt>
                <dd>{{ Array.isArray(value) ? value.join('、') : value || '-' }}</dd>
              </template>
            </dl>
          </div>
          <div v-else class="inspector-empty">
            <span class="i-lucide-mouse-pointer-click"></span>
            <p>点击图中的节点查看属性</p>
          </div>
        </aside>
      </div>
    </section>
  </main>
</template>

<style lang="scss" scoped>
.graph-workbench { height: calc(100% - 86px); min-height: 560px; overflow: hidden; }

.graph-toolbar {
  display: flex;
  height: 52px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--tourism-border);
  padding: 0 14px;
}

.graph-toolbar label {
  display: flex;
  width: min(360px, 55%);
  height: 34px;
  align-items: center;
  gap: 7px;
  border: 1px solid #ccd9d5;
  border-radius: 5px;
  padding: 0 10px;
  color: #71817d;
}

.graph-toolbar input { min-width: 0; flex: 1; border: 0; outline: 0; }
.graph-stat { display: flex; gap: 18px; color: #71817d; font-size: 11px; }
.graph-stat strong { color: #172321; font-size: 14px; }

.graph-layout { display: grid; height: calc(100% - 52px); grid-template-columns: minmax(0, 1fr) 270px; }
.graph-canvas { min-width: 0; height: 100%; background: #fbfdfc; }
.graph-canvas :deep(.tourism-chart) { min-height: 500px; height: 100%; }

.node-inspector { overflow-y: auto; border-left: 1px solid var(--tourism-border); background: #fff; }
.node-inspector > header { display: flex; height: 46px; align-items: center; justify-content: space-between; border-bottom: 1px solid #edf2f0; padding: 0 14px; }
.node-inspector h3 { margin: 0; font-size: 13px; }
.node-inspector header button { display: inline-flex; width: 28px; height: 28px; align-items: center; justify-content: center; border: 0; background: transparent; cursor: pointer; }
.node-detail { padding: 16px 14px; }
.node-type { display: inline-block; border-radius: 3px; background: #e9f5f1; padding: 3px 7px; color: #08745f; font-size: 10px; }
.node-detail h4 { margin: 10px 0 16px; font-size: 15px; line-height: 1.5; }
.node-detail dl { margin: 0; }
.node-detail dt { margin-top: 10px; color: #81918d; font-size: 10px; word-break: break-all; }
.node-detail dd { margin: 3px 0 0; color: #435650; font-size: 11px; line-height: 1.55; word-break: break-word; }
.inspector-empty { display: flex; min-height: 300px; flex-direction: column; align-items: center; justify-content: center; color: #93a19d; }
.inspector-empty span { width: 24px; height: 24px; }
.inspector-empty p { margin: 10px 0 0; font-size: 11px; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .graph-layout { grid-template-columns: 1fr; }
  .node-inspector { display: none; }
}
</style>
