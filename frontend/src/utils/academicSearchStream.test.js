import test from 'node:test'
import assert from 'node:assert/strict'
import { streamAcademicSearch } from './academicSearchStream.js'

const encoder = new TextEncoder()
const frame = event => `data: ${JSON.stringify(event)}\n\n`

function response(chunks) {
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}

test('emits verified snapshots before the final response arrives', async () => {
  let controller
  const events = []
  const body = new ReadableStream({ start(value) { controller = value } })
  const operation = streamAcademicSearch({ keyword: '深度学习', top_k: 8 }, {
    onEvent: event => events.push(event),
    fetcher: async (url, options) => {
      assert.equal(new URL(url, 'http://local').searchParams.get('keyword'), '深度学习')
      assert.equal(options.headers.Accept, 'text/event-stream')
      return new Response(body)
    },
  })
  controller.enqueue(encoder.encode(frame({ type: 'results', result: { items: [{ link_verified: true }] } })))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(events.length, 1)
  assert.equal(events[0].type, 'results')
  controller.enqueue(encoder.encode(frame({ type: 'done', result: { search_status: 'complete' } })))
  controller.close()
  await operation
  assert.equal(events.at(-1).type, 'done')
})

test('handles split UTF-8 characters and CRLF SSE frames', async () => {
  const bytes = encoder.encode(`: heartbeat\r\n\r\ndata: ${JSON.stringify({ type: 'results', result: { title: '中文论文' } })}\r\n\r\n${frame({ type: 'done' })}`)
  const events = []
  await streamAcademicSearch({ keyword: '中文' }, {
    onEvent: event => events.push(event),
    fetcher: async () => response(Array.from(bytes, byte => Uint8Array.of(byte))),
  })
  assert.equal(events[0].result.title, '中文论文')
  assert.equal(events.length, 2)
})

test('reports interrupted streams after delivering partial results', async () => {
  const events = []
  await assert.rejects(streamAcademicSearch({ keyword: 'topic' }, {
    onEvent: event => events.push(event),
    fetcher: async () => response([encoder.encode(frame({ type: 'results', result: { total: 1 } }))]),
  }), /连接已中断/)
  assert.equal(events[0].result.total, 1)
})

test('passes continuation cursor and abort signal to the request', async () => {
  const controller = new AbortController()
  await streamAcademicSearch({ keyword: 'topic', cursor: 'resume-token' }, {
    signal: controller.signal,
    onEvent() {},
    fetcher: async (url, options) => {
      assert.equal(new URL(url, 'http://local').searchParams.get('cursor'), 'resume-token')
      assert.equal(options.signal, controller.signal)
      return response([encoder.encode(frame({ type: 'done' }))])
    },
  })
})

test('shows server errors such as expired continuation records', async () => {
  await assert.rejects(streamAcademicSearch({ keyword: 'topic' }, {
    onEvent() {},
    fetcher: async () => response([encoder.encode(frame({ type: 'error', message: '搜索记录已过期，请重新搜索。' }))]),
  }), /记录已过期/)
})
