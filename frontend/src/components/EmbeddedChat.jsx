import { useState, useRef, useEffect, useCallback, useSyncExternalStore } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Send, Square } from 'lucide-react'
import {
  subscribe,
  getState,
  ask as storeAsk,
  stopGenerating as storeStop,
  clearChat as storeClear,
  openPanel,
  closePanel,
  recoverIfNeeded,
} from '../embeddedChatStore.js'

const TOOL_LABELS = {
  major_search: '专业查询',
  download_search: '资料下载',
  contact_search: '联系方式',
  service_link_search: '服务入口',
  weather_search: '天气查询',
  map_route: '路线规划',
  academic_search: '学术搜索',
}

const CONFIDENCE_LABELS = {
  high: { text: '高可信', color: '#16a34a' },
  medium: { text: '中可信', color: '#ea580c' },
  low: { text: '低可信', color: '#dc2626' },
}

/**
 * 页面内嵌智能体对话组件
 * - 状态提升到 embeddedChatStore（模块级），切标签不丢失
 * - 流式请求在后台继续消费，回来即可看到进行中或已完成的回复
 * - 消息持久化到 localStorage
 * - props.title: 面板标题
 * - props.contextHint: 上下文提示（如 "资料智库"），也用作 store 实例 key
 * - props.suggestions: 初始建议标签
 */
export default function EmbeddedChat({ title = '智能体助手', contextHint = '', suggestions = [] }) {
  const key = contextHint || title

  // 订阅模块级 store：组件卸载后状态保留，重新挂载时拿回完整消息
  const storeSubscribe = useCallback(listener => subscribe(key, listener), [key])
  const state = useSyncExternalStore(storeSubscribe, () => getState(key), () => getState(key))
  const messages = state.messages
  const loading = state.loading
  const open = state.open

  // 输入框状态持久化，切标签不丢失正在输入的内容
  const [input, setInput] = useStickyInput(key)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const initRef = useRef(false)
  const panelRef = useRef(null)

  // 拖拽：鼠标在 header 上按下时开始
  const dragRef = useRef({ dragging: false, ox: 0, oy: 0 })

  function onDragStart(e) {
    // 忽略按钮点击
    if (e.target.closest('button')) return
    const panel = panelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    dragRef.current = { dragging: true, ox: e.clientX - rect.left, oy: e.clientY - rect.top }
    document.addEventListener('mousemove', onDragMove)
    document.addEventListener('mouseup', onDragEnd)
  }

  function onDragMove(e) {
    if (!dragRef.current.dragging) return
    const panel = panelRef.current
    if (!panel) return
    const x = Math.max(0, Math.min(e.clientX - dragRef.current.ox, window.innerWidth - panel.offsetWidth))
    const y = Math.max(0, Math.min(e.clientY - dragRef.current.oy, window.innerHeight - panel.offsetHeight))
    panel.style.left = x + 'px'
    panel.style.top = y + 'px'
    panel.style.right = 'auto'
    panel.style.bottom = 'auto'
  }

  function onDragEnd() {
    dragRef.current.dragging = false
    document.removeEventListener('mousemove', onDragMove)
    document.removeEventListener('mouseup', onDragEnd)
  }

  // 挂载时恢复残留 streaming 消息
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    recoverIfNeeded(key)
  }, [key])

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

  // ESC 关闭
  useEffect(() => {
    if (!open) return
    function handleKey(e) {
      if (e.key === 'Escape') closePanel(key)
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open])

  async function ask(q) {
    const text = (q || input).trim()
    if (!text || loading) return
    setInput('')
    await storeAsk(key, text)
  }

  return (
    <>
      {!open && (
        <button className="emb-chat-fab" onClick={() => openPanel(key)} title="打开智能体助手">
          <MessageCircle size={22} />
        </button>
      )}

      {open && (
        <div className="emb-chat-panel" ref={panelRef}>
          <div className="emb-chat-header" onMouseDown={onDragStart}>
            <div className="emb-chat-header-info">
              <span className="emb-chat-dot" />
              <span className="emb-chat-title">{title}</span>
            </div>
            <div className="emb-chat-header-actions">
              {messages.length > 0 && (
                <button className="emb-chat-header-btn" onClick={() => storeClear(key)} disabled={loading} title="清除对话">
                  清除
                </button>
              )}
              <button className="emb-chat-header-btn emb-chat-close-btn" onClick={() => closePanel(key)} title="关闭">
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="emb-chat-messages">
            {messages.length === 0 && (
              <div className="emb-chat-welcome">
                <div className="emb-chat-welcome-icon">🎓</div>
                <h3>{title}</h3>
                <p>有什么可以帮你的？直接描述你的需求</p>
                {suggestions.length > 0 && (
                  <div className="emb-chat-suggestions">
                    {suggestions.map(s => (
                      <button key={s} className="emb-chat-suggestion-chip" onClick={() => ask(s)} disabled={loading}>
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
              onClick={() => loading ? storeStop(key) : ask()}
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

// ---------- 持久化 hooks ----------

function useStickyInput(key) {
  const sk = 'zhku_emb_input_' + key
  const [value, setValueRaw] = useState(() => localStorage.getItem(sk) || '')
  function setValue(v) {
    try { localStorage.setItem(sk, v) } catch {}
    setValueRaw(v)
  }
  return [value, setValue]
}

// ---------- 消息气泡 ----------

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

            {data && !streaming && (data.tools_used?.length > 0 || data.agents_used?.length > 0) && (
              <div className="emb-tools">
                {data.route_mode === 'collab' && (
                  <span className="emb-tool-chip emb-tool-chip-collab">多 Agent 协作</span>
                )}
                {(data.agents_used || data.tools_used || []).map(t => (
                  <span key={t} className="emb-tool-chip">
                    {typeof t === 'string' && !t.includes('_') ? t : (TOOL_LABELS[t] || t)}
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
