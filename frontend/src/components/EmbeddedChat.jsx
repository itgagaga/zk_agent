import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Send, Square } from 'lucide-react'

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

/**
 * 页面内嵌智能体对话组件
 * - 独立消息状态，不与 /chat 共享
 * - 浮动按钮 + 右侧滑出面板
 * - props.title: 面板标题
 * - props.contextHint: 发送给后端的上下文提示（如 "资料智库"）
 * - props.suggestions: 初始建议标签
 */
export default function EmbeddedChat({ title = '智能体助手', contextHint = '', suggestions = [] }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => 'emb_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8))
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)
  const panelRef = useRef(null)

  // 打开面板时聚焦输入
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 300)
    }
  }, [open])

  // 消息变化时滚动到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 点击面板外关闭
  useEffect(() => {
    if (!open) return
    function handleClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        // 不关闭，只处理 ESC
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // ESC 关闭
  useEffect(() => {
    if (!open) return
    function handleKey(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open])

  async function ask(q) {
    const text = (q || input).trim()
    if (!text || loading) return
    setInput('')

    const userMsg = { role: 'user', content: text }
    const assistantMsg = { role: 'assistant', content: '', data: null, streaming: true }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setLoading(true)

    const history = messages
      .filter(m => !m.streaming && m.content)
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }))

    let idx = -1
    setMessages(prev => { idx = prev.length - 1; return prev })

    try {
      abortRef.current = new AbortController()
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: text,
          user_role: 'student',
          history,
          session_id: sessionId,
          context_hint: contextHint,
        }),
        signal: abortRef.current.signal,
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

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
              setMessages(prev => {
                if (idx < 0 || idx >= prev.length) return prev
                const next = [...prev]
                next[idx] = { ...next[idx], data }
                return next
              })
            } else if (data.type === 'token') {
              setMessages(prev => {
                if (idx < 0 || idx >= prev.length) return prev
                const next = [...prev]
                next[idx] = { ...next[idx], content: next[idx].content + data.content }
                return next
              })
            } else if (data.type === 'done') {
              setMessages(prev => {
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
      // 兜底
      setMessages(prev => {
        if (idx < 0 || idx >= prev.length) return prev
        if (!prev[idx].streaming) return prev
        const next = [...prev]
        next[idx] = { ...next[idx], streaming: false }
        return next
      })
    } catch (err) {
      if (err?.name === 'AbortError') {
        setMessages(prev => {
          const next = [...prev]
          if (next[idx]) next[idx] = { ...next[idx], content: next[idx].content || '（已停止生成）', streaming: false }
          return next
        })
      } else {
        setMessages(prev => {
          const next = [...prev]
          if (next[idx]) next[idx] = { ...next[idx], content: '请求失败：' + (err?.message || '未知错误'), streaming: false }
          return next
        })
      }
    } finally {
      abortRef.current = null
      setLoading(false)
    }
  }

  function stopGenerating() {
    abortRef.current?.abort()
  }

  function clearChat() {
    if (loading) return
    setMessages([])
  }

  return (
    <>
      {/* 浮动触发按钮 */}
      {!open && (
        <button
          className="emb-chat-fab"
          onClick={() => setOpen(true)}
          title="打开智能体助手"
        >
          <MessageCircle size={22} />
        </button>
      )}

      {/* 对话面板 */}
      {open && (
        <div className="emb-chat-panel" ref={panelRef}>
          {/* 头部 */}
          <div className="emb-chat-header">
            <div className="emb-chat-header-info">
              <span className="emb-chat-dot" />
              <span className="emb-chat-title">{title}</span>
            </div>
            <div className="emb-chat-header-actions">
              {messages.length > 0 && (
                <button className="emb-chat-header-btn" onClick={clearChat} disabled={loading} title="清除对话">
                  清除
                </button>
              )}
              <button className="emb-chat-header-btn emb-chat-close-btn" onClick={() => setOpen(false)} title="关闭">
                <X size={16} />
              </button>
            </div>
          </div>

          {/* 消息区 */}
          <div className="emb-chat-messages">
            {messages.length === 0 && (
              <div className="emb-chat-welcome">
                <div className="emb-chat-welcome-icon">🎓</div>
                <h3>{title}</h3>
                <p>有什么可以帮你的？直接描述你的需求</p>
                {suggestions.length > 0 && (
                  <div className="emb-chat-suggestions">
                    {suggestions.map(s => (
                      <button
                        key={s}
                        className="emb-chat-suggestion-chip"
                        onClick={() => ask(s)}
                        disabled={loading}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {messages.map((m, i) => (
              <EmbMessageBubble key={i} message={m} />
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* 输入栏 */}
          <div className="emb-chat-input-bar">
            <input
              ref={inputRef}
              className="emb-chat-input"
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  ask()
                }
              }}
              placeholder="输入你的问题..."
              disabled={loading}
            />
            <button
              className="emb-chat-send-btn"
              onClick={() => loading ? stopGenerating() : ask()}
              title={loading ? '停止生成' : '发送'}
            >
              {loading ? <Square size={16} /> : <Send size={16} />}
            </button>
          </div>
        </div>
      )}
    </>
  )
}

function EmbMessageBubble({ message }) {
  const isUser = message.role === 'user'
  const streaming = message.streaming
  const showThinking = !isUser && streaming && !message.content
  const data = message.data
  const conf = data ? CONFIDENCE_LABELS[data.confidence] : null

  if (isUser) {
    return (
      <div className="emb-msg emb-msg-user">
        <div className="emb-bubble emb-bubble-user">{message.content}</div>
      </div>
    )
  }

  return (
    <div className="emb-msg emb-msg-ai">
      <div className="emb-bubble emb-bubble-ai">
        {showThinking ? (
          <div className="emb-thinking">
            <span /><span /><span />
          </div>
        ) : (
          <>
            <div className="emb-msg-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              {streaming && <span className="emb-typing-cursor" />}
            </div>

            {data && !streaming && data.tools_used?.length > 0 && (
              <div className="emb-tools">
                {data.tools_used.map(t => (
                  <span key={t} className="emb-tool-chip">
                    {TOOL_LABELS[t] || t}
                  </span>
                ))}
              </div>
            )}

            {data && !streaming && conf && (
              <div className="emb-msg-footer">
                <span className="emb-confidence" style={{ background: conf.color + '18', color: conf.color }}>
                  ● {conf.text}
                </span>
                {data.sources?.length > 0 && (
                  <span className="emb-source-count">{data.sources.length} 个来源</span>
                )}
              </div>
            )}

            {data && !streaming && data.sources?.length > 0 && (
              <details className="emb-sources-details">
                <summary>查看来源引用</summary>
                <div className="emb-sources-list">
                  {data.sources.map((s, i) => (
                    <div key={i} className="emb-source-item">
                      <span className="emb-source-idx">{i + 1}</span>
                      <div className="emb-source-info">
                        <span className="emb-source-title">{s.title}</span>
                        <div className="emb-source-meta">
                          {s.department && <span>{s.department}</span>}
                          {s.url && (
                            <a href={s.url} target="_blank" rel="noreferrer" className="emb-source-link">
                              查看原文 ↗
                            </a>
                          )}
                        </div>
                        {s.snippet && <div className="emb-source-snippet">{s.snippet}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {data && !streaming && data.attachments?.length > 0 && (
              <div className="emb-attachments">
                {data.attachments.map((a, i) => (
                  <a
                    key={i}
                    href={a.file_url || a.source_page_url}
                    target="_blank"
                    rel="noreferrer"
                    className="emb-attachment-chip"
                  >
                    {a.file_type?.toUpperCase() || 'FILE'} · {a.name} ↗
                  </a>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
