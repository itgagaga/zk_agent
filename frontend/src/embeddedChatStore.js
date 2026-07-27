// 内嵌智能体聊天状态管理（多实例）
//
// EmbeddedChat 可在多个页面使用，每个实例
// 用 contextHint 区分。状态提到模块级，切标签不丢失；流式
// 请求在后台继续消费，回来即可看到进行中或已完成的回复。

const STORAGE_PREFIX = 'zhku_emb_chat_'
const OPEN_PREFIX = 'zhku_emb_open_'

// ---------- 实例存储 ----------

const instances = new Map()
// 每个 instance 结构：
// { state: { messages, loading, open }, abortRef, listeners: Set, hasUnfinished, sessionId }

function getInstance(key) {
  if (instances.has(key)) return instances.get(key)
  const sessionId = 'emb_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
  const saved = loadSaved(key)
  const inst = {
    state: {
      messages: saved || [],
      loading: false,
      open: localStorage.getItem(OPEN_PREFIX + key) === '1',
    },
    abortRef: null,
    listeners: new Set(),
    hasUnfinished: (saved || []).some(m => m.streaming),
    sessionId,
  }
  instances.set(key, inst)
  return inst
}

function loadSaved(key) {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch { /* ignore */ }
  return null
}

function persist(key, inst) {
  const toSave = inst.state.messages.filter(m => !m.streaming)
  if (toSave.length === 0) {
    localStorage.removeItem(STORAGE_PREFIX + key)
    return
  }
  const slim = toSave.map(m => ({ role: m.role, content: m.content, data: m.data }))
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(slim))
  } catch { /* storage full */ }
}

function emit(inst) {
  for (const l of inst.listeners) l(inst.state)
}

function setMessages(key, inst, updater) {
  inst.state = { ...inst.state, messages: updater(inst.state.messages) }
  inst.hasUnfinished = inst.state.messages.some(m => m.streaming)
  persist(key, inst)
  emit(inst)
}

// ---------- 公开 API ----------

export function subscribe(key, listener) {
  const inst = getInstance(key)
  inst.listeners.add(listener)
  listener(inst.state) // 立即推送当前快照
  return () => inst.listeners.delete(listener)
}

export function getState(key) {
  return getInstance(key).state
}

export function isLoading(key) {
  return getInstance(key).state.loading
}

export function recoverIfNeeded(key) {
  const inst = getInstance(key)
  if (!inst.hasUnfinished) return
  setMessages(key, inst, prev =>
    prev.map(m =>
      m.streaming
        ? { ...m, streaming: false, content: m.content || '（请求未完成，已中断）' }
        : m
    )
  )
}

export async function ask(key, question) {
  const text = (question || '').trim()
  const inst = getInstance(key)
  if (!text || inst.state.loading) return

  inst.state = { ...inst.state, loading: true }
  emit(inst)

  setMessages(key, inst, prev => [...prev, { role: 'user', content: text }])

  const assistantMsg = { role: 'assistant', content: '', data: null, streaming: true }
  setMessages(key, inst, prev => [...prev, assistantMsg])

  const history = inst.state.messages
    .filter(m => !m.streaming && m.content)
    .slice(-6)
    .map(m => ({ role: m.role, content: m.content }))

  try {
    inst.abortRef = new AbortController()
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: text,
        user_role: 'student',
        history,
        session_id: inst.sessionId,
        context_hint: key,
      }),
      signal: inst.abortRef.signal,
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let idx = -1

    setMessages(key, inst, prev => { idx = prev.length - 1; return prev })

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
            setMessages(key, inst, prev => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = { ...next[idx], data: { ...next[idx].data, ...data } }
              return next
            })
          } else if (data.type === 'supervisor') {
            setMessages(key, inst, prev => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = {
                ...next[idx],
                data: {
                  ...next[idx].data,
                  evidence_priority: data.priority,
                  supervisor_reason: data.reason,
                  supervisor_agents: data.agents,
                },
              }
              return next
            })
          } else if (data.type === 'agents') {
            setMessages(key, inst, prev => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = {
                ...next[idx],
                data: {
                  ...next[idx].data,
                  route_mode: data.mode,
                  agents_used: data.agents,
                  collab_reason: data.reason,
                },
              }
              return next
            })
          } else if (data.type === 'token') {
            setMessages(key, inst, prev => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = { ...next[idx], content: next[idx].content + data.content }
              return next
            })
          } else if (data.type === 'done') {
            setMessages(key, inst, prev => {
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
    // 流结束但后端没发 done：兜底
    setMessages(key, inst, prev => {
      if (idx < 0 || idx >= prev.length) return prev
      if (!prev[idx].streaming) return prev
      const next = [...prev]
      next[idx] = { ...next[idx], streaming: false }
      return next
    })
  } catch (err) {
    if (err?.name === 'AbortError') {
      setMessages(key, inst, prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, content: last.content || '（已停止生成）', streaming: false }
        }
        return next
      })
    } else {
      setMessages(key, inst, prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, content: '请求失败：' + (err?.message || '未知错误'), streaming: false }
        }
        return next
      })
    }
  } finally {
    inst.abortRef = null
    inst.state = { ...inst.state, loading: false }
    persist(key, inst)
    emit(inst)
  }
}

export function stopGenerating(key) {
  const inst = getInstance(key)
  if (inst.abortRef) inst.abortRef.abort()
}

export function openPanel(key) {
  const inst = getInstance(key)
  try { localStorage.setItem(OPEN_PREFIX + key, '1') } catch {}
  inst.state = { ...inst.state, open: true }
  emit(inst)
}

export function closePanel(key) {
  const inst = getInstance(key)
  try { localStorage.setItem(OPEN_PREFIX + key, '0') } catch {}
  inst.state = { ...inst.state, open: false }
  emit(inst)
}

/** 打开面板并发送问题（供页面功能卡片一键调用） */
export async function askAndOpen(key, question) {
  openPanel(key)
  await ask(key, question)
}

export function clearChat(key) {
  const inst = getInstance(key)
  if (inst.state.loading) return
  localStorage.removeItem(STORAGE_PREFIX + key)
  inst.hasUnfinished = false
  inst.state = { messages: [], loading: false }
  emit(inst)
}
