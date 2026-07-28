import { useState, useEffect, useRef, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { getAuthHeader, getAuthSnapshot, subscribeAuth } from '../authStore.js'

export default function DocumentsPage() {
  const auth = useSyncExternalStore(subscribeAuth, getAuthSnapshot)
  const loggedIn = Boolean(auth.user && auth.token)

  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [department, setDepartment] = useState('文档库')
  const [stats, setStats] = useState(null)
  const fileInputRef = useRef(null)

  async function loadDocs() {
    if (!loggedIn) {
      setDocs([])
      return
    }
    try {
      const resp = await axios.get('/api/upload/docs', { headers: getAuthHeader() })
      setDocs(resp.data.docs || [])
    } catch {
      setDocs([])
    }
  }

  useEffect(() => {
    loadDocs()
    axios.get('/api/stats').then((r) => setStats(r.data)).catch(() => {})
  }, [loggedIn])

  async function handleUpload(file) {
    if (!file || uploading || !loggedIn) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('department', department || '文档库')
      const resp = await axios.post('/api/upload', form, { headers: getAuthHeader() })
      setDocs((prev) => [
        {
          doc_id: resp.data.doc_id,
          filename: resp.data.filename,
          title: resp.data.title,
          department: resp.data.department,
          chunk_count: resp.data.chunk_count,
          page_count: resp.data.page_count,
        },
        ...prev,
      ])
    } catch (err) {
      const detail = err?.response?.data?.detail
      alert(typeof detail === 'string' ? detail : '上传失败，请先登录')
    } finally {
      setUploading(false)
    }
  }

  async function removeDoc(docId) {
    if (!confirm('确定从你的知识库中删除该文档？')) return
    try {
      await axios.delete(`/api/upload/docs/${docId}`, { headers: getAuthHeader() })
      setDocs((prev) => prev.filter((d) => d.doc_id !== docId))
    } catch {
      alert('删除失败')
    }
  }

  async function search() {
    if (!question.trim()) return
    setLoading(true)
    try {
      const resp = await axios.get('/api/search/documents', {
        params: { q: question, top_k: 5 },
        headers: getAuthHeader(),
      })
      setResult(resp.data)
    } catch (err) {
      setResult({ error: err.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container section">
      <div className="eyebrow">DOCUMENTS</div>
      <h2 style={{ marginTop: 16, marginBottom: 16 }}>智能文档中心</h2>

      <p style={{ color: 'var(--color-slate)', maxWidth: 720, marginBottom: 24, lineHeight: 1.6 }}>
        上传培养方案、章程、手册等文档到<strong>你的私有知识库</strong>，系统自动解析并向量化。
        仅你本人可检索这些文档；校园公共资料仍走官网知识库。
      </p>

      {!loggedIn && (
        <div className="auth-gate-banner">
          <span>上传与管理文档需要登录账号。</span>
          <Link to="/login" className="btn-primary" style={{ textDecoration: 'none' }}>
            去登录
          </Link>
        </div>
      )}

      {stats && (
        <div className="doc-stats-row">
          <div className="doc-stat-item">
            <div className="doc-stat-num">{stats.document_chunks}</div>
            <div className="doc-stat-label">文档库片段</div>
          </div>
          <div className="doc-stat-item">
            <div className="doc-stat-num">{stats.campus_chunks}</div>
            <div className="doc-stat-label">官网资料片段</div>
          </div>
          <div className="doc-stat-item">
            <div className="doc-stat-num">{loggedIn ? docs.length : stats.uploaded_docs}</div>
            <div className="doc-stat-label">{loggedIn ? '我的文档' : '已上传文档'}</div>
          </div>
          <div className="doc-stat-item">
            <div className="doc-stat-num">{stats.total_chunks}</div>
            <div className="doc-stat-label">知识库总量</div>
          </div>
        </div>
      )}

      <div className={`doc-upload-zone ${!loggedIn ? 'is-disabled' : ''}`}>
        <div className="doc-upload-header">
          <strong>上传文档到我的知识库</strong>
          <span className="doc-upload-hint">支持 PDF / Word / TXT / MD，单个不超过 20MB</span>
        </div>
        <div className="doc-upload-row">
          <input
            className="doc-dept-input"
            type="text"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            placeholder="来源标签（如：教务部 / 招生办）"
            disabled={!loggedIn || uploading}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleUpload(f)
              e.target.value = ''
            }}
          />
          <button
            className="btn-primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={!loggedIn || uploading}
          >
            {uploading ? '解析入库中...' : '选择文件上传'}
          </button>
        </div>
      </div>

      {loggedIn && docs.length > 0 && (
        <div className="doc-list-section">
          <div className="eyebrow" style={{ fontSize: 12, marginBottom: 12 }}>
            我的文档 · {docs.length} 份
          </div>
          <div className="doc-list">
            {docs.map((d) => (
              <div key={d.doc_id} className="doc-list-item">
                <div className="doc-list-icon">📄</div>
                <div className="doc-list-info">
                  <div className="doc-list-title">{d.title || d.filename}</div>
                  <div className="doc-list-meta">
                    <span>{d.department}</span>
                    {d.chunk_count > 0 && <span> · {d.chunk_count} 片段</span>}
                    {d.page_count > 0 && <span> · {d.page_count} 页</span>}
                  </div>
                </div>
                <button
                  className="doc-list-remove"
                  onClick={() => removeDoc(d.doc_id)}
                  title="从知识库删除"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 40, borderTop: '1px solid var(--color-dust-taupe)', paddingTop: 32 }}>
        <div className="eyebrow">TEST SEARCH</div>
        <h3 style={{ marginTop: 12, marginBottom: 16 }}>检索测试</h3>
        <p style={{ color: 'var(--color-slate)', maxWidth: 720, marginBottom: 24, fontSize: 14 }}>
          登录后可检索你的私有文档；未登录仅检索校园公共知识库。
        </p>
        <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
          <input
            className="chat-input"
            placeholder="例如：计算机专业培养方案的学分要求是什么？"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <button className="btn-primary" onClick={search} disabled={loading}>
            检索文档
          </button>
        </div>

        {result && !result.error && (
          <div>
            <div className="eyebrow" style={{ fontSize: 12 }}>
              RESULTS · {result.total}
            </div>
            {result.hits?.length > 0 ? (
              result.hits.map((h, i) => (
                <div key={i} className="source-card">
                  <div className="source-title">{h.title}</div>
                  <div className="source-meta">
                    {h.department && <span>{h.department} · </span>}
                    {h.publish_date && <span>{h.publish_date}</span>}
                  </div>
                  {h.snippet && (
                    <div style={{ marginTop: 8, fontSize: 13, color: 'var(--color-granite)' }}>
                      {h.snippet}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="chat-bubble" style={{ color: 'var(--color-slate)' }}>
                暂无文档命中。
              </div>
            )}
          </div>
        )}

        {result?.error && (
          <div className="fallback-note">检索失败：{result.error}</div>
        )}
      </div>
    </div>
  )
}
