export async function streamAcademicSearch(params, { signal, onEvent, fetcher = fetch }) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value != null) query.set(key, String(value))
  }
  const response = await fetcher(`/api/resources/academic/stream?${query}`, {
    signal,
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.ok || !response.body) throw new Error('论文搜索请求失败，请稍后重试。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let complete = false
  try {
    while (!complete) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const records = buffer.split(/\r?\n\r?\n/)
      buffer = records.pop() || ''
      for (const record of records) {
        const data = record.split(/\r?\n/).filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n')
        if (!data) continue
        const event = JSON.parse(data)
        if (event.type === 'error') {
          const error = new Error(event.message || '搜索暂时中断，请重试。')
          error.code = event.code
          throw error
        }
        onEvent(event)
        if (event.type === 'done') {
          complete = true
          break
        }
      }
      if (done) break
    }
    if (!complete) throw new Error('搜索连接已中断，已保留收到的结果，请重试。')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
