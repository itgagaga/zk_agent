// 聊天状态与流式请求逻辑，独立于组件生命周期。
//
// ChatPage 是路由组件，切到其他标签时会被卸载。若状态与 fetch
// 放在组件内，卸载后流式回调无法更新组件，回来就只剩用户发的
// 话。把状态提到模块级，组件只订阅，请求在后台继续，回来即可
// 看到进行中或已完成的回复。

const STORAGE_KEY = 'zhku_chat_messages'
const SESSION_KEY = 'zhku_session_id'

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = 's_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function loadSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch {
    // localStorage 读取失败，忽略
  }
  return null
}

let state = {
  messages: loadSaved() || [],
  loading: false,
}
// 进行中的流式请求；切走标签时保留，回来继续消费
let abortRef = null
// 标志：是否还有未完成（streaming:true）的助手消息。组件重新挂载时
// 据此判断是否需要恢复一次后台请求。
let hasUnfinished = state.messages.some((m) => m.streaming)

const listeners = new Set()

function emit() {
  for (const l of listeners) l(state)
}

function setState(patch) {
  state = { ...state, ...patch }
  emit()
}

function persist() {
  const toSave = state.messages.filter((m) => !m.streaming)
  if (toSave.length === 0) return
  const slim = toSave.map((m) => ({
    role: m.role,
    content: m.content,
    data: m.data,
  }))
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch {
    // 存储空间不足，忽略
  }
}

function setMessages(updater) {
  state = { ...state, messages: updater(state.messages) }
  hasUnfinished = state.messages.some((m) => m.streaming)
  persist()
  emit()
}

export function subscribe(listener) {
  listeners.add(listener)
  listener(state)
  return () => listeners.delete(listener)
}

export function getState() {
  return state
}

export function getSessionIdRef() {
  return getSessionId()
}

export function isLoading() {
  return state.loading
}

export function hasUnfinishedStream() {
  return hasUnfinished
}

function buildHistory() {
  return state.messages
    .filter((m) => !m.streaming && m.content)
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content }))
}

// 恢复进行中的流式请求：若存在 streaming:true 的助手消息但 loading
// 已为 false（比如页面刷新前请求未完成），尝试重连。当前后端不支
// 持断点续传，这里直接把残留的 streaming 消息标记为已中断。
export function recoverIfNeeded() {
  if (!hasUnfinished) return
  setMessages((prev) =>
    prev.map((m) =>
      m.streaming
        ? {
            ...m,
            streaming: false,
            content: m.content || '（请求未完成，已中断）',
          }
        : m
    )
  )
}

export async function ask(question, autoStick) {
  const text = (question || '').trim()
  if (!text || state.loading) return

  setState({ loading: true })
  if (autoStick) autoStick()

  setMessages((prev) => [...prev, { role: 'user', content: text }])

  const assistantMsg = { role: 'assistant', content: '', data: null, streaming: true }
  setMessages((prev) => [...prev, assistantMsg])

  const history = buildHistory()

  try {
    abortRef = new AbortController()
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: text,
        user_role: 'student',
        history,
        session_id: getSessionId(),
      }),
      signal: abortRef.signal,
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let idx = -1

    setMessages((prev) => {
      idx = prev.length - 1
      return prev
    })

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'meta') {
            setMessages((prev) => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = { ...next[idx], data }
              return next
            })
          } else if (data.type === 'token') {
            setMessages((prev) => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = { ...next[idx], content: next[idx].content + data.content }
              return next
            })
          } else if (data.type === 'done') {
            setMessages((prev) => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = { ...next[idx], streaming: false }
              return next
            })
          }
        } catch {
          // skip malformed
        }
      }
    }
    // 流结束但后端没发 done：兜底置为已完成
    setMessages((prev) => {
      if (idx < 0 || idx >= prev.length) return prev
      if (!prev[idx].streaming) return prev
      const next = [...prev]
      next[idx] = { ...next[idx], streaming: false }
      return next
    })
  } catch (err) {
    if (err?.name === 'AbortError') {
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            content: last.content || '（已停止生成）',
            streaming: false,
          }
        }
        return next
      })
    } else {
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            content: '⚠️ 请求失败：' + (err?.message || '未知错误'),
            streaming: false,
          }
        }
        return next
      })
    }
  } finally {
    abortRef = null
    setState({ loading: false })
  }
}

export function stopGenerating() {
  if (abortRef) abortRef.abort()
}

export function clearChat() {
  if (state.loading) return
  if (state.messages.length > 0 && !confirm('确定要清除所有聊天记录吗？')) return
  localStorage.removeItem(STORAGE_KEY)
  hasUnfinished = false
  setState({ messages: [] })
}

export function deleteMessage(index) {
  setMessages((prev) => prev.filter((_, i) => i !== index))
}
