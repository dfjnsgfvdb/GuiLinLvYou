<script lang="ts" setup>
const props = withDefaults(defineProps<{
  qaType?: string
  evidence?: any
}>(), {
  qaType: '',
  evidence: null,
})

const businessStore = useBusinessStore()
const evidenceData = computed(() => {
  if (props.evidence?.template_code === 'TOURISM_EVIDENCE') {
    return props.evidence
  }
  const envelope = businessStore.writerList || {}
  return envelope.data?.template_code === 'TOURISM_EVIDENCE' ? envelope.data : null
})
const visible = computed(() => props.qaType === 'TOURISM_QA' && evidenceData.value)
const sources = computed(() => evidenceData.value?.sources || [])
const events = computed(() => evidenceData.value?.events || [])
const graphRelations = computed(() => evidenceData.value?.graph?.relationships || [])
const retrieval = computed(() => evidenceData.value?.retrieval || {})

const policyLabel = computed(() => ({
  evidence_grounded: '证据支撑回答',
  general_fallback: '通识模型回答',
  evidence_required: '证据不足',
} as any)[evidenceData.value?.answer_policy] || '证据状态')

const isFallback = computed(() => evidenceData.value?.answer_policy === 'general_fallback')
</script>

<template>
  <details v-if="visible" class="evidence-panel" open>
    <summary>
      <span class="summary-title"><span class="i-lucide-shield-check"></span>回答证据</span>
      <span :class="['policy-tag', { fallback: isFallback }]">{{ policyLabel }}</span>
      <span class="evidence-count">来源 {{ sources.length }} · 事件 {{ events.length }} · 关系 {{ graphRelations.length }}</span>
      <span class="i-lucide-chevron-down chevron"></span>
    </summary>

    <div class="evidence-body">
      <div v-if="isFallback" class="fallback-note">
        <span class="i-lucide-info"></span>
        本地知识库未召回相关证据，本回答由通用模型知识生成，不代表实时舆情事实。
      </div>

      <div v-else class="retrieval-strip">
        <span>检索模式 <strong>{{ retrieval.mode || 'hybrid_graph' }}</strong></span>
        <span>向量版本 <strong>{{ retrieval.vector_version || '-' }}</strong></span>
        <span>关键词版本 <strong>{{ retrieval.bm25_version || '-' }}</strong></span>
        <span>耗时 <strong>{{ retrieval.latency_ms || 0 }}ms</strong></span>
      </div>

      <div class="evidence-columns">
        <section>
          <header><span class="i-lucide-file-text"></span>来源片段</header>
          <div v-if="sources.length" class="evidence-list">
            <a
              v-for="source in sources.slice(0, 6)"
              :key="`${source.doc_id}-${source.chunk_id || ''}`"
              :href="source.source_url || undefined"
              :target="source.source_url ? '_blank' : undefined"
              rel="noreferrer"
            >
              <strong>{{ source.title || source.doc_id }}</strong>
              <small>{{ source.source_name || '未知来源' }}<template v-if="source.publish_time"> · {{ source.publish_time }}</template></small>
              <p>{{ source.quote_text || source.content_preview }}</p>
            </a>
          </div>
          <div v-else class="empty-tip">无本地来源</div>
        </section>

        <section>
          <header><span class="i-lucide-radar"></span>关联事件</header>
          <div v-if="events.length" class="evidence-list">
            <div v-for="event in events.slice(0, 6)" :key="event.event_id" class="event-evidence">
              <strong>{{ event.event_name || event.event_id }}</strong>
              <small>{{ event.main_scenic_spot || '桂林全域' }} · {{ event.risk_level || '未评级' }}</small>
              <p>{{ event.event_summary }}</p>
            </div>
          </div>
          <div v-else class="empty-tip">无关联事件</div>
        </section>

        <section>
          <header><span class="i-lucide-network"></span>图谱关系</header>
          <div v-if="graphRelations.length" class="relation-list">
            <span v-for="relation in graphRelations.slice(0, 12)" :key="relation.id">
              {{ relation.type }}
            </span>
          </div>
          <div v-else class="empty-tip">无图谱关系</div>
        </section>
      </div>
    </div>
  </details>
</template>

<style lang="scss" scoped>
.evidence-panel { margin-top: 13px; border: 1px solid #cfded9; border-radius: 5px; background: #fff; overflow: hidden; }
.evidence-panel summary { display: flex; min-height: 40px; align-items: center; gap: 9px; padding: 0 11px; background: #f3f8f6; color: #52645f; cursor: pointer; list-style: none; font-size: 10px; }
.evidence-panel summary::-webkit-details-marker { display: none; }
.summary-title { display: flex; align-items: center; gap: 6px; color: #245e51; font-weight: 700; }
.summary-title span { width: 14px; height: 14px; }
.policy-tag { border-radius: 3px; background: #dcefe9; padding: 3px 6px; color: #08745f; }
.policy-tag.fallback { background: #fff4e4; color: #97611f; }
.evidence-count { margin-left: auto; color: #71817d; }
.chevron { width: 13px; height: 13px; transition: transform 160ms; }
.evidence-panel[open] .chevron { transform: rotate(180deg); }
.evidence-body { border-top: 1px solid #dfe8e5; padding: 10px; }
.fallback-note { display: flex; align-items: flex-start; gap: 7px; border: 1px solid #ead8b8; border-radius: 4px; background: #fffbf2; padding: 8px 10px; color: #7f5c27; font-size: 10px; line-height: 1.6; }
.fallback-note span { width: 14px; height: 14px; flex: 0 0 14px; margin-top: 1px; }
.retrieval-strip { display: flex; flex-wrap: wrap; gap: 8px 18px; border-bottom: 1px solid #edf2f0; padding: 0 2px 9px; color: #81918d; font-size: 9px; }
.retrieval-strip strong { color: #52645f; font-weight: 600; }
.evidence-columns { display: grid; grid-template-columns: 1.2fr 1fr 0.72fr; gap: 10px; margin-top: 10px; }
.evidence-columns > section { min-width: 0; border: 1px solid #e2eae8; border-radius: 4px; overflow: hidden; }
.evidence-columns > section > header { display: flex; height: 34px; align-items: center; gap: 6px; border-bottom: 1px solid #e7eeec; background: #fafcfb; padding: 0 9px; color: #435650; font-size: 10px; font-weight: 700; }
.evidence-columns > section > header span { width: 13px; height: 13px; color: #087f6a; }
.evidence-list > a,
.event-evidence { display: flex; min-width: 0; flex-direction: column; border-top: 1px solid #edf2f0; padding: 8px 9px; color: #273a35; }
.evidence-list > :first-child { border-top: 0; }
.evidence-list a:hover { background: #f7faf9; }
.evidence-list strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-list small { margin-top: 3px; color: #81918d; font-size: 8px; }
.evidence-list p { display: -webkit-box; margin: 5px 0 0; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; color: #667873; font-size: 9px; line-height: 1.55; }
.relation-list { display: flex; flex-wrap: wrap; gap: 5px; padding: 9px; }
.relation-list span { border-radius: 3px; background: #eaf5f1; padding: 4px 6px; color: #27695a; font-size: 8px; }
.empty-tip { padding: 22px 9px; color: #8b9995; font-size: 9px; text-align: center; }
@media (max-width: 900px) { .evidence-columns { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .evidence-count { display: none; } }
</style>
