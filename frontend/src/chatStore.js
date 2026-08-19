// 聊天状态与流式请求逻辑，独立于组件生命周期。
// 未登录：localStorage 临时存储；登录后：服务端会话为真源。

import axios from 'axios'
import {
  getAuthHeader,
  getAuthSnapshot,
  subscribeAuth,
} from './authStore.js'
import { mergeRetrievalMeta } from './retrievalSummary.js'

const STORAGE_KEY = 'zhku_chat_messages'
const SESSION_KEY = 'zhku_session_id'
const SERVER_SESSION_KEY = 'zhku_server_chat_session_id'

function getGuestSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = 's_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function loadLocalMessages() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch {
    // ignore
  }
  return []
}

let state = {
  messages: loadLocalMessages(),
  loading: false,
  serverSessionId: null,
  syncing: false,
  authMode: 'guest', // guest | user
}

let abortRef = null
let hasUnfinished = state.messages.some((m) => m.streaming)
const listeners = new Set()

function emit() {
  for (const l of listeners) l(state)
}

function setState(patch) {
  state = { ...state, ...patch }
  emit()
}

function persistLocal() {
  if (state.authMode === 'user') return
  const toSave = state.messages.filter((m) => !m.streaming)
  if (toSave.length === 0) {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {}
    return
  }
  const slim = toSave.map((m) => ({
    role: m.role,
    content: m.content,
    data: m.data,
  }))
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch {
    // ignore
  }
}

function setMessages(updater) {
  state = { ...state, messages: updater(state.messages) }
  hasUnfinished = state.messages.some((m) => m.streaming)
  persistLocal()
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
  return state.serverSessionId
    ? String(state.serverSessionId)
    : getGuestSessionId()
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

function authHeaders(extra = {}) {
  return { ...extra, ...getAuthHeader() }
}

async function ensureServerSession() {
  const auth = getAuthSnapshot()
  if (!auth.token || !auth.user) return null

  let sid = state.serverSessionId
  if (!sid) {
    try {
      const raw = localStorage.getItem(SERVER_SESSION_KEY)
      if (raw) sid = Number(raw) || null
    } catch {}
  }

  if (sid) {
    try {
      await axios.get(`/api/chat/sessions/${sid}/messages`, {
        headers: getAuthHeader(),
      })
      state = { ...state, serverSessionId: sid, authMode: 'user' }
      return sid
    } catch {
      sid = null
    }
  }

  // 取最近会话，没有则新建
  const list = await axios.get('/api/chat/sessions', { headers: getAuthHeader() })
  const sessions = list.data || []
  if (sessions.length > 0) {
    sid = sessions[0].id
  } else {
    const created = await axios.post(
      '/api/chat/sessions',
      { title: '新对话' },
      { headers: getAuthHeader() },
    )
    sid = created.data.id
  }

  try {
    localStorage.setItem(SERVER_SESSION_KEY, String(sid))
  } catch {}
  state = { ...state, serverSessionId: sid, authMode: 'user' }
  return sid
}

async function loadServerMessages(sessionId) {
  const resp = await axios.get(`/api/chat/sessions/${sessionId}/messages`, {
    headers: getAuthHeader(),
  })
  return (resp.data || []).map((m) => ({
    role: m.role,
    content: m.content || '',
    data: m.meta || null,
  }))
}

async function savePairToServer(userContent, assistantMsg) {
  const sid = state.serverSessionId
  if (!sid || !getAuthSnapshot().token) return
  try {
    await axios.post(
      `/api/chat/sessions/${sid}/messages`,
      {
        messages: [
          { role: 'user', content: userContent },
          {
            role: 'assistant',
            content: assistantMsg.content || '',
            meta: assistantMsg.data || null,
          },
        ],
      },
      { headers: getAuthHeader() },
    )
  } catch (err) {
    console.warn('[chatStore] 服务端保存失败', err?.message || err)
  }
}

/** 登录后：把本机临时聊天迁移到服务端（仅当服务端会话为空时）。 */
async function migrateLocalIfNeeded(sessionId, serverMessages) {
  if (serverMessages.length > 0) return serverMessages
  const local = loadLocalMessages().filter((m) => !m.streaming && m.content)
  if (local.length === 0) return serverMessages
  try {
    await axios.post(
      `/api/chat/sessions/${sessionId}/messages`,
      {
        messages: local.map((m) => ({
          role: m.role,
          content: m.content,
          meta: m.data || null,
        })),
      },
      { headers: getAuthHeader() },
    )
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {}
    return local
  } catch {
    return local
  }
}

export async function syncWithAuth() {
  const auth = getAuthSnapshot()
  if (!auth.token || !auth.user) {
    setState({
      authMode: 'guest',
      serverSessionId: null,
      messages: loadLocalMessages(),
    })
    return
  }
  if (state.syncing) return
  setState({ syncing: true, authMode: 'user' })
  try {
    const sid = await ensureServerSession()
    if (!sid) return
    let msgs = await loadServerMessages(sid)
    msgs = await migrateLocalIfNeeded(sid, msgs)
    hasUnfinished = false
    setState({ messages: msgs, serverSessionId: sid, authMode: 'user' })
  } catch (err) {
    console.warn('[chatStore] 同步失败', err?.message || err)
  } finally {
    setState({ syncing: false })
  }
}

// 鉴权变化时自动同步
subscribeAuth(() => {
  syncWithAuth()
})
// 启动时尝试同步
syncWithAuth()

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
        : m,
    ),
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
  const auth = getAuthSnapshot()
  const role = auth.user?.role || 'student'

  try {
    if (auth.token) {
      await ensureServerSession()
    }

    abortRef = new AbortController()
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        question: text,
        user_role: role,
        history,
        session_id: getSessionIdRef(),
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
              next[idx] = { ...next[idx], data: mergeRetrievalMeta(next[idx].data, data) }
              return next
            })
          } else if (data.type === 'retrieval') {
            setMessages((prev) => {
              if (idx < 0 || idx >= prev.length) return prev
              const next = [...prev]
              next[idx] = {
                ...next[idx],
                data: mergeRetrievalMeta(next[idx].data, { retrieval_summary: data }),
              }
              return next
            })
          } else if (data.type === 'agents') {
            setMessages((prev) => {
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
          // skip
        }
      }
    }
    setMessages((prev) => {
      if (idx < 0 || idx >= prev.length) return prev
      if (!prev[idx].streaming) return prev
      const next = [...prev]
      next[idx] = { ...next[idx], streaming: false }
      return next
    })

    // 登录用户：落库本轮问答
    if (getAuthSnapshot().token && state.serverSessionId) {
      const last = state.messages[state.messages.length - 1]
      if (last?.role === 'assistant') {
        await savePairToServer(text, last)
      }
    }
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

export async function clearChat() {
  if (state.loading) return
  if (state.messages.length > 0 && !confirm('确定要清除所有聊天记录吗？')) return

  if (state.authMode === 'user' && state.serverSessionId && getAuthSnapshot().token) {
    try {
      await axios.delete(`/api/chat/sessions/${state.serverSessionId}/messages`, {
        headers: getAuthHeader(),
      })
    } catch {
      // ignore
    }
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
  hasUnfinished = false
  setState({ messages: [] })
}

export function deleteMessage(index) {
  setMessages((prev) => prev.filter((_, i) => i !== index))
}
