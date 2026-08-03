<script lang="ts" setup>
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { v4 as uuidv4 } from 'uuid'
import * as GlobalAPI from '@/api'
import TourismEvidencePanel from './tourism/components/TourismEvidencePanel.vue'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  evidence?: any
  loading?: boolean
}

type HistoryItem = {
  uuid: string
  chat_id: string
  question: string
  create_time?: string
}

const router = useRouter()
const userStore = useUserStore()
const businessStore = useBusinessStore()
const messageApi = useMessage()

const messages = ref<ChatMessage[]>([])
const history = ref<HistoryItem[]>([])
const chatId = ref(uuidv4())
const input = ref('')
const loading = ref(false)
const historyLoading = ref(false)
const activeReader = ref<ReadableStreamDefaultReader<string> | null>(null)
const userRequestedStop = ref(false)
const messageViewport = ref<HTMLElement | null>(null)

const suggestions = [
  '象鼻山景区节假日排队情况怎么样？',
  '阳朔西街有哪些价格投诉？',
  '龙脊梯田近期有哪些安全风险？',
  '分析漓江景区舆情并给出处置建议',
]

const currentHistoryId = computed(() => chatId.value)

function renderMarkdown(content: string) {
  return DOMPurify.sanitize(String(marked.parse(content || '')))
}

function parseJson(value: any) {
  if (!value || typeof value !== 'string') {
    return value
  }
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function parseAnswer(value: any) {
  const parsed = parseJson(value)
  return parsed?.data?.content || parsed?.content || (typeof value === 'string' ? value : '')
}

function parseEvidence(value: any) {
  const parsed = parseJson(value)
  if (parsed?.template_code === 'TOURISM_EVIDENCE') {
    return parsed
  }
  if (parsed?.data?.template_code === 'TOURISM_EVIDENCE') {
    return parsed.data
  }
  return null
}

async function scrollToBottom() {
  await nextTick()
  if (messageViewport.value) {
    messageViewport.value.scrollTop = messageViewport.value.scrollHeight
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const response = await GlobalAPI.query_user_qa_record(1, 40, '', null)
    if (response.status === 401) {
      userStore.logout()
      router.replace('/login')
      return
    }
    const body = await response.json()
    history.value = (body.data?.records || [])
      .filter((item: any) => item.qa_type === 'TOURISM_QA')
      .map((item: any) => ({
        uuid: item.uuid,
        chat_id: item.chat_id,
        question: item.question,
        create_time: item.create_time,
      }))
  } finally {
    historyLoading.value = false
  }
}

async function openHistory(item: HistoryItem) {
  if (loading.value) {
    return
  }
  chatId.value = item.chat_id
  messages.value = []
  try {
    const response = await GlobalAPI.query_user_qa_record(1, 200, '', item.chat_id)
    const body = await response.json()
    const nextMessages: ChatMessage[] = []
    for (const record of body.data?.records || []) {
      nextMessages.push({
        id: `${record.uuid}-user`,
        role: 'user',
        content: record.question,
      })
      nextMessages.push({
        id: `${record.uuid}-assistant`,
        role: 'assistant',
        content: parseAnswer(record.to2_answer),
        evidence: parseEvidence(record.to4_answer),
      })
    }
    messages.value = nextMessages
    scrollToBottom()
  } catch {
    messageApi.error('加载历史研判记录失败')
  }
}

function newChat() {
  if (loading.value) {
    return
  }
  chatId.value = uuidv4()
  messages.value = []
  input.value = ''
}

async function deleteHistory(event: MouseEvent, item: HistoryItem) {
  event.stopPropagation()
  const response = await GlobalAPI.delete_user_record([item.chat_id])
  if (response.ok) {
    if (chatId.value === item.chat_id) {
      newChat()
    }
    await loadHistory()
  }
}

async function stopGeneration() {
  userRequestedStop.value = true
  if (businessStore.task_id) {
    await GlobalAPI.stop_chat(businessStore.task_id, 'TOURISM_QA')
  }
  await activeReader.value?.cancel()
  activeReader.value = null
  loading.value = false
  const assistant = messages.value.at(-1)
  if (assistant?.role === 'assistant') {
    assistant.loading = false
    if (userRequestedStop.value) {
      assistant.content = '这条消息已停止生成。'
    }
    if (!assistant.content) {
      assistant.content = '本次研判已停止。'
    }
  }
}

async function sendQuestion(preset?: string) {
  const question = (preset || input.value).trim()
  if (!question || loading.value) {
    return
  }
  input.value = ''
  const turnId = uuidv4()
  messages.value.push({ id: `${turnId}-user`, role: 'user', content: question })
  const assistant: ChatMessage = {
    id: `${turnId}-assistant`,
    role: 'assistant',
    content: '',
    loading: true,
  }
  messages.value.push(assistant)
  loading.value = true
  userRequestedStop.value = false
  await scrollToBottom()

  businessStore.update_qa_type('TOURISM_QA')
  const result = await businessStore.createAssistantWriterStylized(
    turnId,
    chatId.value,
    null,
    { text: question, file_list: [] },
  )

  if (result.needLogin) {
    userStore.logout()
    router.replace('/login')
    return
  }
  if (result.error || !result.reader) {
    assistant.content = '研判服务暂时不可用，请检查后端服务后重试。'
    assistant.loading = false
    loading.value = false
    return
  }

  activeReader.value = result.reader
  try {
    while (true) {
      const { value, done } = await result.reader.read()
      if (done) {
        break
      }
      const chunk = parseJson(value)
      assistant.content += chunk?.content || ''
      await scrollToBottom()
    }
    const envelope = businessStore.writerList
    assistant.evidence = envelope?.data?.template_code === 'TOURISM_EVIDENCE'
      ? envelope.data
      : envelope?.template_code === 'TOURISM_EVIDENCE'
        ? envelope
        : null
  } catch (error: any) {
    if (!assistant.content && userRequestedStop.value) {
      assistant.content = '这条消息已停止生成。'
    }
    if (!assistant.content) {
      assistant.content = error?.message || '回答读取失败，请重试。'
    }
  } finally {
    assistant.loading = false
    loading.value = false
    activeReader.value = null
    userRequestedStop.value = false
    await loadHistory()
    await scrollToBottom()
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendQuestion()
  }
}

onMounted(loadHistory)
onBeforeUnmount(() => activeReader.value?.cancel())
</script>

<template>
  <main class="chat-page">
    <aside class="history-panel">
      <header>
        <div>
          <span>研判记录</span>
          <small>{{ history.length }} 个会话</small>
        </div>
        <button type="button" title="新建研判" @click="newChat"><span class="i-lucide-square-pen"></span></button>
      </header>
      <div class="history-list">
        <button
          v-for="item in history"
          :key="item.chat_id"
          type="button"
          :class="['history-item', { active: currentHistoryId === item.chat_id }]"
          @click="openHistory(item)"
        >
          <span class="i-lucide-message-square history-icon"></span>
          <span class="history-copy">
            <strong>{{ item.question }}</strong>
            <small>{{ item.create_time || '旅游舆情研判' }}</small>
          </span>
          <span class="delete-history" title="删除记录" @click="deleteHistory($event, item)">
            <span class="i-lucide-trash-2"></span>
          </span>
        </button>
        <div v-if="!history.length && !historyLoading" class="history-empty">暂无研判记录</div>
      </div>
    </aside>

    <section class="chat-workspace">
      <header class="chat-header">
        <div>
          <span class="agent-mark"><span class="i-lucide-scan-search"></span></span>
          <div>
            <h2>桂林舆情研判 Agent</h2>
            <p>混合检索 · 事件查询 · 图谱扩展 · 证据充分性检查</p>
          </div>
        </div>
        <span class="agent-state"><i></i>可研判</span>
      </header>

      <div ref="messageViewport" class="message-viewport">
        <section v-if="!messages.length" class="chat-empty-state">
          <span class="empty-mark">漓</span>
          <h2>从证据出发，研判桂林旅游舆情</h2>
          <p>输入景区、事件、投诉或风险问题，系统将联合召回来源、事件和图谱关系。</p>
          <div class="suggestion-grid">
            <button v-for="suggestion in suggestions" :key="suggestion" type="button" @click="sendQuestion(suggestion)">
              <span class="i-lucide-arrow-up-right"></span>
              {{ suggestion }}
            </button>
          </div>
          <div class="evidence-flow">
            <span>FAISS 语义召回</span><i></i><span>BM25 关键词</span><i></i><span>事件库</span><i></i><span>Neo4j 图谱</span>
          </div>
        </section>

        <div v-else class="message-list">
          <article v-for="item in messages" :key="item.id" :class="['message-row', item.role]">
            <div class="message-avatar">
              <span v-if="item.role === 'assistant'" class="i-lucide-scan-search"></span>
              <span v-else class="i-lucide-user-round"></span>
            </div>
            <div class="message-content">
              <header>{{ item.role === 'assistant' ? '舆情研判 Agent' : '分析人员' }}</header>
              <div v-if="item.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(item.content)"></div>
              <p v-else>{{ item.content }}</p>
              <div v-if="item.loading && !item.content" class="thinking-line">
                <span></span><span></span><span></span>正在检索并融合多路证据
              </div>
              <TourismEvidencePanel
                v-if="item.role === 'assistant' && item.evidence"
                qa-type="TOURISM_QA"
                :evidence="item.evidence"
              />
            </div>
          </article>
        </div>
      </div>

      <footer class="composer-shell">
        <div class="composer">
          <textarea
            v-model="input"
            rows="2"
            :disabled="loading"
            placeholder="输入桂林旅游舆情问题，例如：阳朔西街近期有哪些价格投诉？"
            @keydown="handleKeydown"
          ></textarea>
          <button v-if="loading" class="stop-button" type="button" title="停止生成" @click="stopGeneration">
            <span class="i-lucide-square"></span>
          </button>
          <button v-else class="send-button" type="button" title="发送问题" :disabled="!input.trim()" @click="sendQuestion()">
            <span class="i-lucide-arrow-up"></span>
          </button>
        </div>
        <p>回答包含事实、推断和建议；涉及实时舆情时请以返回证据为准。</p>
      </footer>
    </section>
  </main>
</template>

<style lang="scss" scoped>
.chat-page { display: grid; width: 100%; height: 100%; grid-template-columns: 248px minmax(0, 1fr); overflow: hidden; background: #f4f7f6; }
.history-panel { min-width: 0; overflow: hidden; border-right: 1px solid #dfe8e5; background: #f9fbfa; }
.history-panel > header { display: flex; height: 58px; align-items: center; justify-content: space-between; border-bottom: 1px solid #dfe8e5; padding: 0 13px 0 16px; }
.history-panel > header div { display: flex; flex-direction: column; }
.history-panel > header span { font-size: 13px; font-weight: 700; }
.history-panel > header small { margin-top: 3px; color: #879692; font-size: 9px; }
.history-panel > header button { display: inline-flex; width: 32px; height: 32px; align-items: center; justify-content: center; border: 1px solid #d2dedb; border-radius: 4px; background: #fff; color: #087f6a; cursor: pointer; }
.history-list { height: calc(100% - 58px); overflow-y: auto; padding: 8px; }
.history-item { position: relative; display: grid; width: 100%; min-height: 56px; grid-template-columns: 17px minmax(0, 1fr) 22px; align-items: center; gap: 8px; border: 0; border-radius: 4px; background: transparent; padding: 8px; color: #52645f; cursor: pointer; text-align: left; }
.history-item:hover { background: #eff5f3; }
.history-item.active { background: #e4f1ed; color: #175c4e; }
.history-icon { width: 15px; height: 15px; align-self: start; margin-top: 2px; }
.history-copy { display: flex; min-width: 0; flex-direction: column; }
.history-copy strong { overflow: hidden; font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.history-copy small { margin-top: 5px; overflow: hidden; color: #8b9995; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.delete-history { display: none; width: 22px; height: 22px; align-items: center; justify-content: center; color: #8b9995; }
.history-item:hover .delete-history { display: inline-flex; }
.delete-history:hover { color: #c53b36; }
.history-empty { padding: 30px 10px; color: #8b9995; font-size: 11px; text-align: center; }

.chat-workspace { display: flex; min-width: 0; flex-direction: column; overflow: hidden; background: #fff; }
.chat-header { display: flex; height: 58px; flex: 0 0 58px; align-items: center; justify-content: space-between; border-bottom: 1px solid #dfe8e5; padding: 0 20px; }
.chat-header > div { display: flex; align-items: center; gap: 10px; }
.agent-mark { display: inline-flex; width: 32px; height: 32px; align-items: center; justify-content: center; border-radius: 4px; background: #e4f2ed; color: #087f6a; }
.agent-mark > span { width: 17px; height: 17px; }
.chat-header h2 { margin: 0; font-size: 14px; }
.chat-header p { margin: 3px 0 0; color: #82918d; font-size: 9px; }
.agent-state { display: flex; align-items: center; gap: 6px; color: #60726d; font-size: 10px; }
.agent-state i { width: 6px; height: 6px; border-radius: 50%; background: #15966f; }

.message-viewport { min-height: 0; flex: 1; overflow-y: auto; background: #fbfdfc; scroll-behavior: smooth; }
.chat-empty-state { display: flex; width: min(720px, calc(100% - 36px)); min-height: 100%; flex-direction: column; align-items: center; justify-content: center; margin: auto; padding: 38px 0; text-align: center; }
.empty-mark { display: inline-flex; width: 48px; height: 48px; align-items: center; justify-content: center; border: 1px solid #69a99a; color: #087f6a; font-family: STKaiti, KaiTi, serif; font-size: 27px; }
.chat-empty-state h2 { margin: 20px 0 7px; font-size: 21px; }
.chat-empty-state > p { max-width: 560px; margin: 0; color: #71817d; font-size: 12px; line-height: 1.7; }
.suggestion-grid { display: grid; width: 100%; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 28px; }
.suggestion-grid button { display: flex; min-height: 46px; align-items: center; gap: 9px; border: 1px solid #d8e4e1; border-radius: 5px; background: #fff; padding: 9px 12px; color: #435650; cursor: pointer; font-size: 11px; text-align: left; }
.suggestion-grid button:hover { border-color: #78aa9d; background: #f5faf8; color: #08745f; }
.suggestion-grid button span { width: 14px; height: 14px; flex: 0 0 14px; color: #087f6a; }
.evidence-flow { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px; margin-top: 24px; color: #8a9995; font-size: 9px; }
.evidence-flow i { width: 18px; height: 1px; background: #cad8d4; }

.message-list { width: min(900px, 100%); margin: 0 auto; padding: 16px 26px 40px; }
.message-row { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 11px; padding: 15px 0; }
.message-row + .message-row { border-top: 1px solid #edf2f0; }
.message-avatar { display: flex; width: 30px; height: 30px; align-items: center; justify-content: center; border-radius: 4px; background: #e7f2ef; color: #087f6a; }
.message-row.user .message-avatar { background: #edf1f5; color: #526778; }
.message-avatar span { width: 16px; height: 16px; }
.message-content { min-width: 0; }
.message-content > header { margin: 2px 0 8px; color: #435650; font-size: 10px; font-weight: 700; }
.message-content > p { margin: 0; color: #273a35; font-size: 13px; line-height: 1.75; white-space: pre-wrap; }
.markdown-body { color: #273a35; font-size: 13px; line-height: 1.8; }
.markdown-body :deep(p) { margin: 0 0 9px; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { margin: 14px 0 7px; font-size: 15px; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 7px 0; padding-left: 20px; }
.markdown-body :deep(blockquote) { margin: 9px 0; border-left: 3px solid #7fb6a9; background: #f2f7f5; padding: 7px 11px; color: #536762; }
.thinking-line { display: flex; align-items: center; gap: 4px; color: #71817d; font-size: 10px; }
.thinking-line span { width: 5px; height: 5px; border-radius: 50%; background: #32a786; animation: pulse 1.2s infinite; }
.thinking-line span:nth-child(2) { animation-delay: 0.18s; }
.thinking-line span:nth-child(3) { margin-right: 5px; animation-delay: 0.36s; }

.composer-shell { flex: 0 0 auto; border-top: 1px solid #dfe8e5; background: #fff; padding: 12px 20px 10px; }
.composer { position: relative; display: flex; width: min(860px, 100%); min-height: 58px; align-items: flex-end; margin: auto; border: 1px solid #bdcec9; border-radius: 6px; background: #fff; padding: 9px 48px 9px 12px; box-shadow: 0 4px 18px rgb(16 46 42 / 6%); }
.composer:focus-within { border-color: #087f6a; box-shadow: 0 0 0 3px rgb(8 127 106 / 8%); }
.composer textarea { width: 100%; min-height: 38px; max-height: 120px; resize: none; border: 0; outline: 0; color: #253833; font-size: 12px; line-height: 1.6; }
.send-button, .stop-button { position: absolute; right: 10px; bottom: 10px; display: inline-flex; width: 32px; height: 32px; align-items: center; justify-content: center; border: 0; border-radius: 4px; background: #087f6a; color: #fff; cursor: pointer; }
.send-button:disabled { background: #bccac6; }
.stop-button { background: #c1534d; }
.send-button span, .stop-button span { width: 15px; height: 15px; }
.composer-shell > p { margin: 6px 0 0; color: #92a09c; font-size: 9px; text-align: center; }

@keyframes pulse { 0%, 70%, 100% { opacity: 0.3; transform: translateY(0); } 35% { opacity: 1; transform: translateY(-2px); } }

@media (max-width: 900px) {
  .chat-page { grid-template-columns: 1fr; }
  .history-panel { display: none; }
}
@media (max-width: 600px) {
  .chat-header { padding: 0 12px; }
  .chat-header p, .agent-state { display: none; }
  .message-list { padding-inline: 14px; }
  .suggestion-grid { grid-template-columns: 1fr; }
  .composer-shell { padding-inline: 10px; }
}
</style>
