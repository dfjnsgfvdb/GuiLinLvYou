<script lang="ts" setup>
import * as echarts from 'echarts'

const props = defineProps<{
  option: Record<string, any>
}>()
const emit = defineEmits<{
  chartClick: [params: any]
}>()

const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function renderChart() {
  if (!chartEl.value) {
    return
  }
  chart ||= echarts.init(chartEl.value, undefined, { renderer: 'canvas' })
  chart.off('click')
  chart.on('click', params => emit('chartClick', params))
  chart.setOption(props.option || {}, true)
}

onMounted(() => {
  renderChart()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value!)
})

watch(() => props.option, renderChart, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="chartEl" class="tourism-chart"></div>
</template>

<style scoped>
.tourism-chart {
  width: 100%;
  height: 100%;
  min-height: 240px;
}
</style>
