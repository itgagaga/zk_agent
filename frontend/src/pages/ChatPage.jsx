import { useEffect, useRef, useState, useCallback, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  subscribe,
  getState,
  ask as storeAsk,
  stopGenerating as storeStop,
  clearChat as storeClear,
  deleteMessage as storeDelete,
  recoverIfNeeded,
} from '../chatStore.js'

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
  weather_search: '天气查询',
  academic_search: '学术搜索',
}

const CONFIDENCE_LABELS = {
  high: { text: '高可信', color: '#16a34a' },
  medium: { text: '中可信', color: '#ea580c' },
  low: { text: '低可信', color: '#dc2626' },
}

function generateFollowUps(question) {
  if (!question) return []
  if (/电话|联系/.test(question))
    return ['其他部门的联系方式', '办公时间是什么时候？', '如何线下咨询？']
  if (/招生|录取|报考/.test(question))
    return ['招生计划是多少？', '有哪些专业可以选？', '录取分数线是多少？']
  if (/培养方案|学分|课程/.test(question))
    return ['有哪些必修课？', '毕业要求是什么？', '可以转专业吗？']
  if (/下载|表格|申请表/.test(question))
    return ['还有哪些表格可以下载？', '申请流程是什么？', '需要哪些材料？']
  if (/天气|气温|温度|下雨/.test(question))
    return ['明天天气怎么样？', '需要带伞吗？', '这周有台风吗？']
  if (/论文|文献|学术|研究/.test(question))
    return ['有哪些高引用的论文？', '能推荐相关方向的前沿论文吗？', '这些论文的DOI是什么？']
  if (/校区|地址|在哪/.test(question))
    return ['怎么去学校？', '校区之间有校车吗？', '周边有什么？']
  if (/就业|实习|毕业/.test(question))
    return ['就业率怎么样？', '有校园招聘吗？', '实习怎么安排？']
  return ['能详细说明一下吗？', '还有其他相关要求吗？', '这个信息的来源是什么？']
}

export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const [question, setQuestion] = useState('')
  // 订阅模块级 store：组件卸载后状态保留，重新挂载时拿回完整消息
  const state = useSyncExternalStore(subscribe, getState, getState)
  const messages = state.messages
  const loading = state.loading
  const messagesEndRef = useRef(null)
  const messagesWrapRef = useRef(null)
  const inputRef = useRef(null)
  const initRef = useRef(false)
  // 是否自动跟随滚动到底部。初始为 false，避免进入页面时强制滚到底；
  // 用户发送新问题、或已处于底部附近时才会置为 true。
  const autoStickRef = useRef(false)

  const scrollToBottom = useCallback((behavior = 'smooth') => {
    const wrap = messagesWrapRef.current
    if (wrap) {
      wrap.scrollTo({ top: wrap.scrollHeight, behavior })
    }
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

  // 挂载时恢复：若有残留的 streaming 消息（页面刷新前请求未完成），
  // 标记为已中断；否则检查 URL 参数发起提问
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    recoverIfNeeded()
    if (messages.length === 0 || !messages.some((m) => m.streaming)) {
      const q = searchParams.get('q')
      if (q) {
        // 通过 URL 参数发起提问时，自动跟随到底部
        autoStickRef.current = true
        storeAsk(q, () => { autoStickRef.current = true })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function exportChat() {
    const lines = messages
      .filter((m) => !m.streaming && m.content)
      .map((m) =>
        m.role === 'user'
          ? `## 🧑 用户\n\n${m.content}`
          : `## 🤖 助手\n\n${m.content}`
      )
    if (lines.length === 0) return
    const md = `# 仲恺校园智能问答记录\n\n> 导出时间：${new Date().toLocaleString('zh-CN')}\n\n${lines.join('\n\n---\n\n')}`
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `zhku_chat_${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function ask(q) {
    const text = (q || question).trim()
    if (!text || loading) return
    setQuestion('')
    // 用户主动发问时跟随到底部
    autoStickRef.current = true
    await storeAsk(text, () => { autoStickRef.current = true })
  }

  const hasMessages = messages.length > 0

  const clearChat = storeClear
  const deleteMessage = storeDelete
  const stopGenerating = storeStop

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
              <div className="chat-header-actions">
                <button className="chat-header-btn" onClick={exportChat} disabled={loading} title="导出对话为 Markdown">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
                  </svg>
                  导出
                </button>
                <button className="chat-header-btn" onClick={clearChat} disabled={loading} title="清除聊天记录">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                  </svg>
                  清除
                </button>
              </div>
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
            <MessageBubble
              key={i}
              message={m}
              index={i}
              onDelete={deleteMessage}
              onAsk={ask}
              loading={loading}
              prevQuestion={i > 0 && messages[i - 1].role === 'user' ? messages[i - 1].content : ''}
            />
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
            onClick={() => (loading ? stopGenerating() : ask())}
            disabled={!loading && !question.trim()}
            title={loading ? '停止生成' : '发送'}
          >
            {loading ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
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

function MessageBubble({ message, index, onDelete, onAsk, loading, prevQuestion }) {
  const isUser = message.role === 'user'
  const data = message.data
  const streaming = message.streaming
  const showThinking = !isUser && streaming && !message.content
  const [copied, setCopied] = useState(false)
  const followUps = !isUser && !streaming && prevQuestion ? generateFollowUps(prevQuestion) : []

  function handleCopy() {
    navigator.clipboard.writeText(message.content || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isUser) {
    return (
      <div className="msg-row msg-row-user">
        <div className="msg-avatar msg-avatar-user">你</div>
        <div className="msg-bubble msg-bubble-user">
          {message.content}
          {!streaming && (
            <button className="msg-action-btn msg-action-user" onClick={() => onDelete(index)} title="删除此条">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          )}
        </div>
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
                <div className="msg-actions">
                  <button className="msg-action-btn" onClick={handleCopy} title="复制回答">
                    {copied ? '✓ 已复制' : (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                    )}
                  </button>
                  <button className="msg-action-btn" onClick={() => onDelete(index)} title="删除此条">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
                  </button>
                </div>
              </div>
            )}

            {followUps.length > 0 && !loading && (
              <div className="msg-followups">
                <div className="msg-followups-label">相关问题</div>
                <div className="msg-followups-chips">
                  {followUps.map((fq) => (
                    <button
                      key={fq}
                      className="followup-chip"
                      onClick={() => onAsk(fq)}
                    >
                      {fq}
                    </button>
                  ))}
                </div>
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
