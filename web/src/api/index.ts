function tokenHeader(contentType = true) {
  const token = useUserStore().getUserToken()
  return {
    ...(contentType ? { 'Content-Type': 'application/json' } : {}),
    'Authorization': `Bearer ${token}`,
  }
}

function jsonRequest(path: string, body: Record<string, any> = {}) {
  return fetch(new Request(new URL(`${location.origin}/sanic${path}`), {
    mode: 'cors',
    method: 'post',
    headers: tokenHeader(),
    body: JSON.stringify(body),
  }))
}

export function login(username: string, password: string) {
  return fetch(new Request(new URL(`${location.origin}/sanic/user/login`), {
    mode: 'cors',
    method: 'post',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  }))
}

export function createOllama3Stylized(text, qa_type, uuid, chat_id, file_list) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 10 * 60 * 1000)
  return fetch(new Request(new URL(`${location.origin}/sanic/dify/get_answer`), {
    mode: 'cors',
    method: 'post',
    headers: tokenHeader(),
    body: JSON.stringify({ query: text, qa_type, uuid, chat_id, file_list }),
    signal: controller.signal,
  })).finally(() => window.clearTimeout(timeoutId))
}

export function query_user_qa_record(page, limit, search_text, chat_id) {
  return jsonRequest('/user/query_user_record', { page, limit, search_text, chat_id })
}

export function delete_user_record(chat_ids) {
  return jsonRequest('/user/delete_user_record', { chat_ids })
}

export function stop_chat(task_id, qa_type) {
  return jsonRequest('/dify/stop_chat', { task_id, qa_type })
}

export function upload_tourism_pipeline_file(file, source_type = 'manual') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('source_type', source_type)
  return fetch(new Request(new URL(`${location.origin}/sanic/tourism/pipeline/upload`), {
    mode: 'cors',
    method: 'post',
    headers: tokenHeader(false),
    body: formData,
  }))
}

export function query_tourism_pipeline_tasks(page = 1, limit = 20) {
  return jsonRequest('/tourism/pipeline/task/list', { page, limit })
}

export function retry_tourism_pipeline_task(task_no) {
  return jsonRequest('/tourism/pipeline/task/retry', { task_no })
}

export function rebuild_tourism_graph(clear_existing = false) {
  return jsonRequest('/tourism/pipeline/rebuild_graph', { clear_existing })
}

export function rebuild_tourism_index() {
  return jsonRequest('/tourism/pipeline/rebuild_index')
}

export function query_tourism_overview() {
  return jsonRequest('/tourism/overview')
}

export function query_tourism_events(filters = {}) {
  return jsonRequest('/tourism/events/search', filters)
}

export function query_tourism_event_detail(event_id) {
  return jsonRequest('/tourism/events/detail', { event_id })
}

export function query_tourism_graph(limit = 80) {
  return jsonRequest('/tourism/graph/overview', { limit })
}

export function query_tourism_system_status() {
  return jsonRequest('/tourism/system/status')
}
