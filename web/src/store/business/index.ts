import { defineStore } from 'pinia'
import * as GlobalAPI from '@/api'

function parseSseFrame(frame: string) {
  const data = frame
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).replace(/^ /, ''))
    .join('\n')
  return !data || data === '[DONE]' ? null : JSON.parse(data)
}

function createAssistantReader(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: any, controller: ReadableStreamDefaultController<string>) => void,
) {
  const sourceReader = body.pipeThrough(new TextDecoderStream()).getReader()
  const stream = new ReadableStream<string>({
    async start(controller) {
      let buffer = ''
      const processFrame = (frame: string) => {
        if (!frame.trim()) {
          return
        }
        try {
          const event = parseSseFrame(frame)
          if (event) {
            onEvent(event, controller)
          }
        } catch (error) {
          console.error('SSE event parsing failed', error)
        }
      }
      try {
        while (true) {
          const { value, done } = await sourceReader.read()
          if (done) {
            break
          }
          buffer += value
          const frames = buffer.split(/\r?\n\r?\n/)
          buffer = frames.pop() || ''
          frames.forEach(processFrame)
        }
        processFrame(buffer)
        controller.close()
      } catch (error) {
        controller.error(error)
      } finally {
        sourceReader.releaseLock()
      }
    },
    cancel(reason) {
      return sourceReader.cancel(reason)
    },
  })
  return stream.getReader()
}

export const useBusinessStore = defineStore('business-store', {
  state: () => ({
    writerList: {} as any,
    qa_type: 'TOURISM_QA',
    task_id: '',
  }),
  actions: {
    update_qa_type(qaType: string) {
      this.qa_type = qaType
    },
    async createAssistantWriterStylized(uuid, chatId, _writerOid, data) {
      this.writerList = {}
      this.task_id = ''
      try {
        const response = await GlobalAPI.createOllama3Stylized(
          data.text,
          this.qa_type,
          uuid,
          chatId,
          data.file_list || [],
        )
        if (response.status === 401) {
          return { error: 1, reader: null, needLogin: true }
        }
        if (!response.ok || !response.body) {
          return { error: 1, reader: null, needLogin: false }
        }
        const reader = createAssistantReader(response.body, (event, controller) => {
          if (event.task_id) {
            this.task_id = event.task_id
          }
          if (event.dataType === 't02' && event.data?.content) {
            controller.enqueue(JSON.stringify(event.data))
          } else if (event.dataType === 't04') {
            this.writerList = event
          }
        })
        return { error: 0, reader, needLogin: false }
      } catch (error) {
        console.error('Tourism answer request failed', error)
        return { error: 1, reader: null, needLogin: false }
      }
    },
  },
})
