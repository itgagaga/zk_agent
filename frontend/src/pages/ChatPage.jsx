import { useEffect, useRef, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SUGGESTIONS = [
  '仲恺农业工程学院有几个校区？',
  '学校有哪些教学机构？',
  '补办学生证申请表在哪里？',
  '2026年本科招生章程主要讲了什么？',
  '数学与数据科学学院电话是多少？',
  '就业协议书怎么申请？',
]

const TOOL_LABELS = {
  major_search: '专业查询',
  download_search: '资料下载',
  contact_search: '联系方式',
  service_link_search: '服务入口',
}

const CONFIDENCE_LABELS = {
  high: { text: '高可信', color: '#16a34a' },
  medium: { text: '中可信', color: '#ea580c' },
  low: { text: '低可信', color: '#dc2626' },
}

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

export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const messagesWrapRef = useRef(null)
  const inputRef = useRef(null)
  const sessionIdRef = useRef(getSessionId())
  const initRef = useRef(false)
  // 是否自动跟随滚动到底部。初始为 false，避免进入页面时强制滚到底；
  // 用户发送新问题、或已处于底部附近时才会置为 true。
  const autoStickRef = useRef(false)

  const scrollToBottom = useCallback((behavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior })
  }, [])

  // 滚动容器监听：用户主动上滑时停止自动跟随，重新回到底部附近时恢复
  useEffect(() => {
    const wrap = messagesWrapRef.current
    if (!wrap) return
    const handleScroll = () => {
      const threshold = 80
      const atBottom =
        wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight < threshold
      autoStickRef.current = atBottom
    }
    wrap.addEventListener('scroll', handleScroll, { passive: true })
    return () => wrap.removeEventListener('scroll', handleScroll)
  }, [])

  // 消息变化时，仅在用户已处于底部附近或刚发送问题时跟随滚动
  useEffect(() => {
    if (autoStickRef.current) {
      scrollToBottom()
    }
  }, [messages, scrollToBottom])

  // 加载时从 localStorage 恢复聊天记录
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed)
          // 恢复历史时不自动滚动，让用户从顶部开始阅读
          autoStickRef.current = false
          return
        }
      }
    } catch {
      // localStorage 读取失败，忽略
    }
    // 没有历史记录时，检查 URL 参数
    const q = searchParams.get('q')
    if (q && !initRef.current) {
      initRef.current = true
      // 通过 URL 参数发起提问时，自动跟随到底部
      autoStickRef.current = true
      ask(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 消息变化时保存到 localStorage（只保存已完成的非流式消息）
  useEffect(() => {
    if (messages.length === 0) return
    const toSave = messages.filter((m) => !m.streaming)
    if (toSave.length > 0) {
      // 只保存必要字段，减小存储体积
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
  }, [messages])

  function clearChat() {
    if (loading) return
    if (messages.length > 0 && !confirm('确定要清除所有聊天记录吗？')) return
    localStorage.removeItem(STORAGE_KEY)
    setMessages([])
  }

  // 构建历史对话（取最近 6 条 = 3 轮）
  function buildHistory() {
    return messages
      .filter((m) => !m.streaming && m.content)
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }))
  }

  async function ask(q) {
    const text = (q || question).trim()
    if (!text || loading) return

    setLoading(true)
    setQuestion('')
    // 用户主动发问时跟随到底部
    autoStickRef.current = true
    setMessages((prev) => [...prev, { role: 'user', content: text }])

    // 占位助手消息
    const assistantMsg = { role: 'assistant', content: '', data: null, streaming: true }
    setMessages((prev) => [...prev, assistantMsg])

    // 构建历史对话（在添加新消息之前）
    const history = buildHistory()

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, user_role: 'student', history, session_id: sessionIdRef.current }),
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
                const next = [...prev]
                next[idx] = { ...next[idx], data }
                return next
              })
            } else if (data.type === 'token') {
              setMessages((prev) => {
                const next = [...prev]
                next[idx] = { ...next[idx], content: next[idx].content + data.content }
                return next
              })
            } else if (data.type === 'done') {
              setMessages((prev) => {
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
    } catch (err) {
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
    } finally {
      setLoading(false)
    }
  }

  const hasMessages = messages.length > 0

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div className="chat-header-inner">
          <div className="chat-header-top">
            <div className="chat-logo">
              <span className="chat-logo-dot" />
              ZHKU Agent
            </div>
            {hasMessages && (
              <button className="chat-clear-btn" onClick={clearChat} disabled={loading} title="清除聊天记录">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                </svg>
                清除记录
              </button>
            )}
          </div>
          <h1 className="chat-title">仲恺校园智能问答</h1>
          <p className="chat-subtitle">
            基于官网真实资料的 AI 问答 · 来源可追溯
            {hasMessages && <span className="chat-saved-hint"> · 记录已本地保存</span>}
          </p>
        </div>
      </div>

      <div className="chat-messages-wrap" ref={messagesWrapRef}>
        <div className="chat-messages">
          {!hasMessages && (
            <div className="chat-welcome">
              <div className="chat-welcome-icon">🎓</div>
              <h2>你好，我是仲恺校园信息助手</h2>
              <p>可以问我学校概况、招生政策、教务资料、联系方式等问题</p>
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    className="suggestion-chip"
                    onClick={() => ask(s)}
                    disabled={loading}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
          ))}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="chat-input-bar">
        <div className="chat-input-inner">
          <input
            ref={inputRef}
            className="chat-input-field"
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                ask()
              }
            }}
            placeholder="输入你的问题..."
            disabled={loading}
          />
          <button
            className="chat-send-btn"
            onClick={() => ask()}
            disabled={loading || !question.trim()}
          >
            {loading ? (
              <span className="send-spinner" />
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M3 12L21 3L12 21L10 14L3 12Z"
                  fill="currentColor"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
        <div className="chat-input-hint">
          按 Enter 发送 · AI 基于仲恺官网资料与知识库文档回答，可能存在延迟
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const data = message.data
  const streaming = message.streaming
  const showThinking = !isUser && streaming && !message.content

  if (isUser) {
    return (
      <div className="msg-row msg-row-user">
        <div className="msg-avatar msg-avatar-user">你</div>
        <div className="msg-bubble msg-bubble-user">{message.content}</div>
      </div>
    )
  }

  const conf = data ? CONFIDENCE_LABELS[data.confidence] : null

  return (
    <div className="msg-row msg-row-ai">
      <div className="msg-avatar msg-avatar-ai">
        <span className="msg-avatar-dot" />
      </div>
      <div className="msg-bubble msg-bubble-ai">
        {showThinking ? (
          <div className="thinking-dots">
            <span />
            <span />
            <span />
          </div>
        ) : (
          <>
            <div className="msg-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              {streaming && <span className="typing-cursor" />}
            </div>

            {data && !streaming && (
              <AnswerDetails data={data} />
            )}

            {data && streaming && data.tools_used?.length > 0 && (
              <div className="msg-tools-inline">
                {data.tools_used.map((t) => (
                  <span key={t} className="tool-chip">
                    {TOOL_LABELS[t] || t}
                  </span>
                ))}
              </div>
            )}

            {data && !streaming && conf && (
              <div className="msg-footer">
                <span
                  className="confidence-badge"
                  style={{ background: conf.color + '18', color: conf.color }}
                >
                  ● {conf.text}
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function AnswerDetails({ data }) {
  const [showSources, setShowSources] = useState(true)
  const hasSources = data.sources?.length > 0
  const hasAttachments = data.attachments?.length > 0
  const hasTools = data.tools_used?.length > 0

  if (!hasSources && !hasAttachments && !hasTools) return null

  return (
    <div className="answer-details">
      {hasTools && (
        <div className="detail-tools">
          {data.tools_used.map((t) => (
            <span key={t} className="tool-chip">
              🔧 {TOOL_LABELS[t] || t}
            </span>
          ))}
        </div>
      )}

      {hasSources && (
        <div className="detail-sources">
          <button
            className="detail-toggle"
            onClick={() => setShowSources(!showSources)}
          >
            <span className="detail-toggle-icon">{showSources ? '▾' : '▸'}</span>
            来源引用（{data.sources.length}）
          </button>
          {showSources && (
            <div className="source-list">
              {data.sources.map((s, i) => (
                <div key={i} className="source-card">
                  <div className="source-card-header">
                    <span className="source-index">{i + 1}</span>
                    <span className="source-title">{s.title}</span>
                  </div>
                  <div className="source-card-meta">
                    {s.department && <span className="source-dept">{s.department}</span>}
                    {s.publish_date && <span className="source-date">{s.publish_date}</span>}
                    {s.url && (
                      <a href={s.url} target="_blank" rel="noreferrer" className="source-link">
                        查看原文 ↗
                      </a>
                    )}
                  </div>
                  {s.snippet && (
                    <div className="source-snippet">{s.snippet}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {hasAttachments && (
        <div className="detail-attachments">
          <div className="detail-label">📎 附件下载</div>
          <div className="attachment-list">
            {data.attachments.map((a, i) => (
              <a
                key={i}
                href={a.file_url || a.source_page_url}
                target="_blank"
                rel="noreferrer"
                className="attachment-chip"
              >
                {a.file_type?.toUpperCase() || 'FILE'} · {a.name} ↗
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
