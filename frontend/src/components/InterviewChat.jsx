import { useState, useRef, useEffect, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { getAuthHeader, getAuthSnapshot, subscribeAuth } from '../authStore.js'

const CATEGORY_LABELS = {
  tech: '技术基础',
  project: '项目深挖',
  design: '场景设计',
  behavior: '行为面试',
}

const SCORE_COLORS = {
  low: '#dc2626',
  mid: '#ea580c',
  high: '#16a34a',
}

function getScoreColor(score) {
  if (score <= 4) return SCORE_COLORS.low
  if (score <= 7) return SCORE_COLORS.mid
  return SCORE_COLORS.high
}

const STORAGE_KEY = 'interview_state'

export default function InterviewChat({ onBack }) {
  const auth = useSyncExternalStore(subscribeAuth, getAuthSnapshot)
  const loggedIn = Boolean(auth.user && auth.token)

  // 从 localStorage 恢复面试状态
  const saved = useRef(null)
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) saved.current = JSON.parse(raw)
  } catch { /* ignore */ }

  // 恢复时，如果存在 stream_interrupted 消息，将 phase 修正为 questioning 以便重试
  if (saved.current?.messages?.some(m => m.role === 'stream_interrupted')) {
    if (saved.current.phase === 'answered' || saved.current.phase === 'skipped') {
      saved.current.phase = 'questioning'
    }
  }

  // 面试状态：upload → ready → questioning → answered/skipped → finished
  const [phase, setPhase] = useState(saved.current?.phase || 'upload')
  const [resumeData, setResumeData] = useState(null)
  const [resumeFilename, setResumeFilename] = useState('')
  const [uploading, setUploading] = useState(false)
  const [questions, setQuestions] = useState(saved.current?.questions || [])
  const [currentIdx, setCurrentIdx] = useState(saved.current?.currentIdx || 0)
  const [sessionId, setSessionId] = useState(saved.current?.sessionId || '')
  const [messages, setMessages] = useState(saved.current?.messages || [])
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesWrapRef = useRef(null)
  const fileInputRef = useRef(null)

  // 持久化面试状态到 localStorage
  // 将中断的流式消息转为 stream_interrupted，以便恢复后可重试
  useEffect(() => {
    const safeMessages = messages.map(m => {
      if (m.role === 'streaming') {
        return {
          ...m,
          role: 'stream_interrupted',
          _questionIndex: currentIdx,
          _sessionId: sessionId,
        }
      }
      return m
    })
    const state = { phase, questions, currentIdx, sessionId, messages: safeMessages }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  }, [phase, questions, currentIdx, sessionId, messages])

  // 滚动消息容器到底部（不影响整个页面）
  useEffect(() => {
    const wrap = messagesWrapRef.current
    if (wrap) {
      wrap.scrollTop = wrap.scrollHeight
    }
  }, [messages])

  // 初始化时检查是否已有持久化的简历（需登录）
  useEffect(() => {
    if (!loggedIn) return
    async function checkResume() {
      try {
        const resp = await axios.get('/api/interview/resume', {
          headers: getAuthHeader(),
        })
        if (resp.data.ok && resp.data.resume) {
          setResumeData(resp.data.resume)
          setResumeFilename(resp.data.resume.filename || '')
          if (!saved.current?.phase || saved.current.phase === 'upload') {
            setPhase('ready')
          }
        }
      } catch {
        // ignore
      }
    }
    checkResume()
  }, [loggedIn])

  function buildResumeContext() {
    if (!resumeData) {
      return {
        basic: {}, education: [], skills: [], projects: [],
        target_position: '', intro_keywords: '', intro: '',
      }
    }
    return {
      basic: resumeData.basic || {},
      education: resumeData.education || [],
      skills: resumeData.skills || [],
      projects: resumeData.projects || [],
      target_position: resumeData.target_position || '',
      intro_keywords: resumeData.intro_keywords || '',
      intro: resumeData.intro || '',
    }
  }

  // 上传简历（不覆盖已有面试对话）
  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!loggedIn) {
      alert('请先登录后再上传简历')
      return
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await axios.post('/api/interview/upload-resume', formData, {
        headers: { ...getAuthHeader(), 'Content-Type': 'multipart/form-data' },
      })
      if (resp.data.ok) {
        setResumeData(resp.data.resume)
        setResumeFilename(file.name)
        if (phase === 'upload') {
          setPhase('ready')
        }
      } else {
        alert(resp.data.message || '上传失败')
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || '上传失败'
      alert('简历上传失败：' + detail)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function handleReupload() {
    if (fileInputRef.current) fileInputRef.current.click()
  }

  // 开始面试（清除旧对话，开始新的）
  async function handleStart() {
    setLoading(true)
    try {
      const resp = await axios.post('/api/interview/start', {
        resume: buildResumeContext(),
        question_count: 8,
      })
      const data = resp.data
      setSessionId(data.session_id)
      setQuestions(data.questions)
      setCurrentIdx(0)
      setMessages([
        { role: 'system', content: `模拟面试开始！共 ${data.questions.length} 个问题，加油！` },
        { role: 'interviewer', content: data.questions[0].question, category: data.questions[0].category, index: 0 },
      ])
      setPhase('questioning')
    } catch (e) {
      console.error('启动面试失败:', e)
      alert('启动面试失败，请检查后端服务是否正常运行。')
    } finally {
      setLoading(false)
    }
  }

  // 通用 SSE 流式请求
  async function fetchStream(url, body, onToken, onResult) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
          if (data.type === 'token') {
            onToken(data.content)
          } else if (data.type === 'result') {
            onResult(data)
          }
        } catch {
          // skip malformed
        }
      }
    }
  }

  // 提交回答（流式）
  async function handleSubmitAnswer() {
    const text = answer.trim()
    if (!text) return
    setLoading(true)
    setMessages(prev => [...prev, { role: 'candidate', content: text }])
    setAnswer('')

    // 添加一个流式占位消息
    const streamMsg = { role: 'streaming', content: '', streamType: 'score' }
    setMessages(prev => [...prev, streamMsg])
    let streamIdx = -1
    setMessages(prev => { streamIdx = prev.length - 1; return prev })

    try {
      await fetchStream(
        '/api/interview/answer/stream',
        {
          session_id: sessionId,
          question_index: currentIdx,
          question: questions[currentIdx].question,
          answer: text,
          resume: buildResumeContext(),
        },
        // onToken: 逐字追加到流式消息
        (token) => {
          setMessages(prev => {
            if (streamIdx < 0 || streamIdx >= prev.length) return prev
            const next = [...prev]
            next[streamIdx] = { ...next[streamIdx], content: next[streamIdx].content + token }
            return next
          })
        },
        // onResult: 替换为结构化消息
        (result) => {
          setMessages(prev => {
            if (streamIdx < 0 || streamIdx >= prev.length) return prev
            const next = [...prev]
            next[streamIdx] = {
              role: 'score',
              score: result.score,
              feedback: result.feedback,
              reference_answer: result.reference_answer,
            }
            return next
          })
        },
      )
      setPhase('answered')
    } catch (e) {
      console.error('提交回答失败:', e)
      setMessages(prev => {
        if (streamIdx < 0 || streamIdx >= prev.length) return prev
        const next = [...prev]
        next[streamIdx] = { role: 'error', content: '评分请求失败，请重试' }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  // 跳过问题（流式）
  async function handleSkip() {
    setLoading(true)
    setMessages(prev => [...prev, { role: 'candidate', content: '（跳过此题）' }])

    const streamMsg = { role: 'streaming', content: '', streamType: 'skip' }
    setMessages(prev => [...prev, streamMsg])
    let streamIdx = -1
    setMessages(prev => { streamIdx = prev.length - 1; return prev })

    try {
      await fetchStream(
        '/api/interview/skip/stream',
        {
          session_id: sessionId,
          question_index: currentIdx,
          question: questions[currentIdx].question,
          resume: buildResumeContext(),
        },
        (token) => {
          setMessages(prev => {
            if (streamIdx < 0 || streamIdx >= prev.length) return prev
            const next = [...prev]
            next[streamIdx] = { ...next[streamIdx], content: next[streamIdx].content + token }
            return next
          })
        },
        (result) => {
          setMessages(prev => {
            if (streamIdx < 0 || streamIdx >= prev.length) return prev
            const next = [...prev]
            next[streamIdx] = {
              role: 'skip_result',
              reference_answer: result.reference_answer,
              tips: result.tips,
            }
            return next
          })
        },
      )
      setPhase('skipped')
    } catch (e) {
      console.error('跳过失败:', e)
      setMessages(prev => {
        if (streamIdx < 0 || streamIdx >= prev.length) return prev
        const next = [...prev]
        next[streamIdx] = { role: 'error', content: '获取参考答案失败' }
        return next
      })
    } finally {
      setLoading(false)
    }
  }

  // 重试中断的流式请求
  async function handleRetryStream(interruptedMsg) {
    const qIdx = interruptedMsg._questionIndex ?? currentIdx
    const sId = interruptedMsg._sessionId ?? sessionId

    // 找到 messages 中该 interrupted 消息的索引
    const interruptedIdx = messages.findIndex(m => m === interruptedMsg)
    if (interruptedIdx < 0) return

    // 将 interrupted 消息替换为 streaming 消息
    const streamMsg = { role: 'streaming', content: '', streamType: interruptedMsg.streamType }
    setMessages(prev => {
      const next = [...prev]
      next[interruptedIdx] = streamMsg
      return next
    })
    setLoading(true)

    const streamIdx = interruptedIdx

    if (interruptedMsg.streamType === 'score') {
      const candidateMsg = messages[interruptedIdx - 1]
      const answerText = candidateMsg?.role === 'candidate' ? candidateMsg.content : ''

      try {
        await fetchStream(
          '/api/interview/answer/stream',
          {
            session_id: sId,
            question_index: qIdx,
            question: questions[qIdx]?.question || '',
            answer: answerText,
            resume: buildResumeContext(),
          },
          (token) => {
            setMessages(prev => {
              if (streamIdx < 0 || streamIdx >= prev.length) return prev
              const next = [...prev]
              next[streamIdx] = { ...next[streamIdx], content: next[streamIdx].content + token }
              return next
            })
          },
          (result) => {
            setMessages(prev => {
              if (streamIdx < 0 || streamIdx >= prev.length) return prev
              const next = [...prev]
              next[streamIdx] = {
                role: 'score',
                score: result.score,
                feedback: result.feedback,
                reference_answer: result.reference_answer,
              }
              return next
            })
          },
        )
        setPhase('answered')
      } catch (e) {
        console.error('重试评分失败:', e)
        setMessages(prev => {
          if (streamIdx < 0 || streamIdx >= prev.length) return prev
          const next = [...prev]
          next[streamIdx] = { role: 'error', content: '评分请求失败，请重试' }
          return next
        })
      }
    } else {
      try {
        await fetchStream(
          '/api/interview/skip/stream',
          {
            session_id: sId,
            question_index: qIdx,
            question: questions[qIdx]?.question || '',
            resume: buildResumeContext(),
          },
          (token) => {
            setMessages(prev => {
              if (streamIdx < 0 || streamIdx >= prev.length) return prev
              const next = [...prev]
              next[streamIdx] = { ...next[streamIdx], content: next[streamIdx].content + token }
              return next
            })
          },
          (result) => {
            setMessages(prev => {
              if (streamIdx < 0 || streamIdx >= prev.length) return prev
              const next = [...prev]
              next[streamIdx] = {
                role: 'skip_result',
                reference_answer: result.reference_answer,
                tips: result.tips,
              }
              return next
            })
          },
        )
        setPhase('skipped')
      } catch (e) {
        console.error('重试跳过失败:', e)
        setMessages(prev => {
          if (streamIdx < 0 || streamIdx >= prev.length) return prev
          const next = [...prev]
          next[streamIdx] = { role: 'error', content: '获取参考答案失败' }
          return next
        })
      }
    }
    setLoading(false)
  }

  // 下一题
  function handleNext() {
    const nextIdx = currentIdx + 1
    if (nextIdx >= questions.length) {
      setPhase('finished')
      const scoreMsgs = messages.filter(m => m.role === 'score')
      if (scoreMsgs.length > 0) {
        const avg = (scoreMsgs.reduce((s, m) => s + m.score, 0) / scoreMsgs.length).toFixed(1)
        setMessages(prev => [
          ...prev,
          { role: 'summary', total: questions.length, answered: scoreMsgs.length, avg_score: avg },
        ])
      } else {
        setMessages(prev => [
          ...prev,
          { role: 'system', content: '面试结束！你没有回答任何问题。' },
        ])
      }
      return
    }
    setCurrentIdx(nextIdx)
    setMessages(prev => [
      ...prev,
      { role: 'interviewer', content: questions[nextIdx].question, category: questions[nextIdx].category, index: nextIdx },
    ])
    setPhase('questioning')
  }

  // 重新开始（回到简历就绪状态，保留简历数据）
  function handleRestart() {
    setPhase('ready')
    setQuestions([])
    setCurrentIdx(0)
    setSessionId('')
    setMessages([])
    setAnswer('')
    localStorage.removeItem(STORAGE_KEY)
  }

  function renderResumeSummary() {
    if (!resumeData) return null
    const name = resumeData.basic?.name || ''
    const position = resumeData.target_position || ''
    const skills = (resumeData.skills || []).map(s => s.items).filter(Boolean).join('、')
    return (
      <div className="iv-resume-summary">
        <div className="iv-resume-summary-title">当前简历</div>
        <div className="iv-resume-summary-row">
          {name && <span className="iv-resume-name">{name}</span>}
          {position && <span className="iv-resume-position">{position}</span>}
        </div>
        {skills && <div className="iv-resume-skills">{skills}</div>}
      </div>
    )
  }

  return (
    <div className="interview-chat">
      {/* 全局隐藏 file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md"
        onChange={handleUpload}
        hidden
      />

      {!loggedIn && (
        <div className="auth-gate-banner">
          <span>上传简历并绑定到账号需要先登录。</span>
          <Link to="/login" className="btn-primary" style={{ textDecoration: 'none' }}>
            去登录
          </Link>
        </div>
      )}

      {/* 顶部栏 */}
      <div className="interview-header">
        <div className="interview-header-top">
          <button className="interview-back-btn" onClick={onBack}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            返回简历
          </button>
          <div className="interview-logo">
            <span className="interview-logo-dot" />
            模拟面试
          </div>
          {resumeData && phase !== 'upload' && (
            <button
              className="iv-header-reupload"
              onClick={handleReupload}
              disabled={uploading}
              title="重新上传简历"
            >
              {uploading ? <><span className="rf-spinner" /> 分析中</> : '换简历'}
            </button>
          )}
          {messages.length > 0 && phase !== 'upload' && phase !== 'ready' && (
            <button
              className="iv-header-clear"
              onClick={handleRestart}
              disabled={loading}
              title="清除对话，重新开始"
            >
              清除
            </button>
          )}
        </div>
        <h1 className="interview-title">AI 模拟面试</h1>
        <p className="interview-subtitle">
          上传简历后，AI 面试官将进行对话式面试
          {questions.length > 0 && (
            <span className="interview-progress">
              {' '}· {Math.min(currentIdx + 1, questions.length)} / {questions.length}
            </span>
          )}
        </p>
      </div>

      {/* 上传简历阶段 */}
      {phase === 'upload' && (
        <div className="interview-messages-wrap">
          <div className="interview-welcome">
            {uploading ? (
              <>
                <div className="iv-analyzing-icon">
                  <span className="rf-spinner iv-analyzing-spinner" />
                </div>
                <h2>智能体分析中</h2>
                <p>正在解析简历内容并提取关键信息，请稍候...</p>
              </>
            ) : (
              <>
                <div className="interview-welcome-icon">📄</div>
                <h2>请先上传简历</h2>
                <p>上传你的简历文件（PDF / DOCX / TXT），AI 将解析简历内容并生成针对性的面试问题</p>
              </>
            )}
            <div className="iv-upload-zone">
              {!uploading && (
                <button
                  className="iv-upload-btn"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                  </svg>
                  选择简历文件
                </button>
              )}
              {!uploading && <div className="iv-upload-hint">支持 PDF、DOCX、TXT、MD 格式，最大 10MB</div>}
            </div>
          </div>
        </div>
      )}

      {/* 简历已上传，准备开始面试 */}
      {(phase === 'ready' || phase === 'questioning' || phase === 'answered' || phase === 'skipped' || phase === 'finished') && (
        <div className="interview-messages-wrap" ref={messagesWrapRef}>
          <div className="interview-messages">
            {phase === 'ready' && (
              <div className="interview-welcome">
                <div className="interview-welcome-icon">💼</div>
                <h2>准备好面试了吗？</h2>
                {renderResumeSummary()}
                <div className="iv-ready-actions">
                  <button
                    className="interview-start-btn"
                    onClick={handleStart}
                    disabled={loading || uploading}
                  >
                    {loading ? <><span className="rf-spinner" /> 准备中...</> : '开始面试'}
                  </button>
                  <button className="iv-reupload-btn" onClick={handleReupload} disabled={uploading}>
                    {uploading ? <><span className="rf-spinner" /> 智能体分析中...</> : '重新上传简历'}
                  </button>
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <MessageItem key={i} message={m} onRetry={handleRetryStream} />
            ))}

            {/* 当前问题输入 */}
            {phase === 'questioning' && (
              <div className="interview-action-area">
                <div className="interview-answer-row">
                  <textarea
                    className="interview-answer-input"
                    value={answer}
                    onChange={e => setAnswer(e.target.value)}
                    placeholder="输入你的回答..."
                    rows={4}
                    disabled={loading}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && e.ctrlKey) {
                        e.preventDefault()
                        handleSubmitAnswer()
                      }
                    }}
                  />
                </div>
                <div className="interview-btn-row">
                  <button
                    className="interview-submit-btn"
                    onClick={handleSubmitAnswer}
                    disabled={loading || !answer.trim()}
                  >
                    {loading ? <><span className="rf-spinner" /> 提交中...</> : '提交回答'}
                  </button>
                  <button
                    className="interview-skip-btn"
                    onClick={handleSkip}
                    disabled={loading}
                  >
                    跳过，查看答案
                  </button>
                </div>
                <div className="interview-input-hint">Ctrl + Enter 快速提交</div>
              </div>
            )}

            {/* 下一题 */}
            {(phase === 'answered' || phase === 'skipped') && currentIdx < questions.length - 1 && (
              <div className="interview-next-area">
                <button className="interview-next-btn" onClick={handleNext}>下一题 →</button>
              </div>
            )}
            {(phase === 'answered' || phase === 'skipped') && currentIdx >= questions.length - 1 && (
              <div className="interview-next-area">
                <button className="interview-next-btn" onClick={handleNext}>查看面试总结</button>
              </div>
            )}

            {/* 面试结束 */}
            {phase === 'finished' && (
              <div className="interview-finished-area">
                <button className="interview-restart-btn" onClick={handleRestart}>重新面试</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MessageItem({ message, onRetry }) {
  const m = message

  if (m.role === 'system') {
    return (
      <div className="iv-msg iv-msg-system">
        <div className="iv-system-bubble">{m.content}</div>
      </div>
    )
  }

  if (m.role === 'interviewer') {
    const catLabel = CATEGORY_LABELS[m.category] || m.category
    return (
      <div className="iv-msg iv-msg-interviewer">
        <div className="iv-avatar iv-avatar-interviewer">
          <span className="iv-avatar-dot" />
        </div>
        <div className="iv-bubble iv-bubble-interviewer">
          <div className="iv-question-header">
            <span className="iv-question-index">Q{m.index + 1}</span>
            <span className="iv-question-cat">{catLabel}</span>
          </div>
          <div className="iv-question-text">{m.content}</div>
        </div>
      </div>
    )
  }

  if (m.role === 'candidate') {
    return (
      <div className="iv-msg iv-msg-candidate">
        <div className="iv-avatar iv-avatar-candidate">你</div>
        <div className="iv-bubble iv-bubble-candidate">{m.content}</div>
      </div>
    )
  }

  // 流式输出中的临时消息
  if (m.role === 'streaming') {
    return (
      <div className="iv-msg iv-msg-result">
        <div className="iv-avatar iv-avatar-interviewer">
          <span className="iv-avatar-dot" />
        </div>
        <div className="iv-bubble iv-bubble-result iv-bubble-streaming">
          <div className="iv-streaming-header">
            <span className="rf-spinner" /> AI 正在思考...
          </div>
          {m.content && <div className="iv-result-text iv-streaming-text">{m.content}</div>}
        </div>
      </div>
    )
  }

  // 流式中断（切换标签导致）— 显示已有内容 + 重新生成按钮
  if (m.role === 'stream_interrupted') {
    return (
      <div className="iv-msg iv-msg-result">
        <div className="iv-avatar iv-avatar-interviewer">
          <span className="iv-avatar-dot" />
        </div>
        <div className="iv-bubble iv-bubble-result iv-bubble-streaming">
          {m.content && <div className="iv-result-text iv-streaming-text">{m.content}</div>}
          <div className="iv-interrupted-hint">
            输出中断（切换页面导致）
            <button className="iv-retry-btn" onClick={() => onRetry?.(m)}>
              重新生成
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (m.role === 'score') {
    const color = getScoreColor(m.score)
    return (
      <div className="iv-msg iv-msg-result">
        <div className="iv-avatar iv-avatar-interviewer">
          <span className="iv-avatar-dot" />
        </div>
        <div className="iv-bubble iv-bubble-result">
          <div className="iv-score-header">
            <span className="iv-score-badge" style={{ background: color + '18', color }}>
              {m.score} / 10
            </span>
            <span className="iv-score-label">评分</span>
          </div>
          {m.feedback && (
            <div className="iv-feedback">
              <div className="iv-result-section-title">点评</div>
              <div className="iv-result-text">{m.feedback}</div>
            </div>
          )}
          {m.reference_answer && (
            <div className="iv-reference">
              <div className="iv-result-section-title">参考答案</div>
              <div className="iv-result-text">{m.reference_answer}</div>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (m.role === 'skip_result') {
    return (
      <div className="iv-msg iv-msg-result">
        <div className="iv-avatar iv-avatar-interviewer">
          <span className="iv-avatar-dot" />
        </div>
        <div className="iv-bubble iv-bubble-result">
          <div className="iv-skip-badge">已跳过</div>
          {m.reference_answer && (
            <div className="iv-reference">
              <div className="iv-result-section-title">参考答案</div>
              <div className="iv-result-text">{m.reference_answer}</div>
            </div>
          )}
          {m.tips && (
            <div className="iv-tips">
              <div className="iv-result-section-title">回答建议</div>
              <div className="iv-result-text">{m.tips}</div>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (m.role === 'summary') {
    return (
      <div className="iv-msg iv-msg-summary">
        <div className="iv-summary-card">
          <div className="iv-summary-icon">🎉</div>
          <h3>面试结束</h3>
          <div className="iv-summary-stats">
            <div className="iv-summary-stat">
              <span className="iv-summary-num">{m.total}</span>
              <span className="iv-summary-label">总题数</span>
            </div>
            <div className="iv-summary-stat">
              <span className="iv-summary-num">{m.answered}</span>
              <span className="iv-summary-label">已回答</span>
            </div>
            <div className="iv-summary-stat">
              <span className="iv-summary-num">{m.avg_score}</span>
              <span className="iv-summary-label">平均分</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (m.role === 'error') {
    return (
      <div className="iv-msg iv-msg-system">
        <div className="iv-error-bubble">{m.content}</div>
      </div>
    )
  }

  return null
}
