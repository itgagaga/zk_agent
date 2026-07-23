import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function DocumentsPage() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  // 上传相关
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [department, setDepartment] = useState('文档库')
  const fileInputRef = useRef(null)

  // 加载已上传文档列表
  async function loadDocs() {
    try {
      const resp = await axios.get('/api/upload/docs')
      setDocs(resp.data.docs || [])
    } catch {}
  }

  useEffect(() => {
    loadDocs()
  }, [])

  async function handleUpload(file) {
    if (!file || uploading) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('department', department || '文档库')
      const resp = await axios.post('/api/upload', form)
      setDocs((prev) => [
        ...prev,
        {
          doc_id: resp.data.doc_id,
          filename: resp.data.filename,
          title: resp.data.title,
          department: resp.data.department,
          chunk_count: resp.data.chunk_count,
          page_count: resp.data.page_count,
        },
      ])
    } catch (err) {
      alert(err?.response?.data?.detail || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  async function removeDoc(docId) {
    if (!confirm('确定从知识库中删除该文档？')) return
    try {
      await axios.delete(`/api/upload/docs/${docId}`)
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

      <p style={{ color: 'var(--color-slate)', maxWidth: 720, marginBottom: 32, lineHeight: 1.6 }}>
        上传培养方案、章程、手册等文档到永久知识库，系统自动解析并向量化。
        以后任何用户提问涉及这些文档内容时，RAG 会自动检索并基于文档内容回答——
        无关问题不会命中，不影响日常问答。
      </p>

      {/* 上传区 */}
      <div className="doc-upload-zone">
        <div className="doc-upload-header">
          <strong>上传文档到永久知识库</strong>
          <span className="doc-upload-hint">支持 PDF / Word / TXT / MD，单个不超过 20MB</span>
        </div>
        <div className="doc-upload-row">
          <input
            className="doc-dept-input"
            type="text"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            placeholder="来源标签（如：教务部 / 招生办）"
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
            disabled={uploading}
          >
            {uploading ? '解析入库中...' : '选择文件上传'}
          </button>
        </div>
      </div>

      {/* 已上传文档列表 */}
      {docs.length > 0 && (
        <div className="doc-list-section">
          <div className="eyebrow" style={{ fontSize: 12, marginBottom: 12 }}>
            知识库文档 · {docs.length} 份
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

      {/* 检索测试区 */}
      <div style={{ marginTop: 40, borderTop: '1px solid var(--color-dust-taupe)', paddingTop: 32 }}>
        <div className="eyebrow">TEST SEARCH</div>
        <h3 style={{ marginTop: 12, marginBottom: 16 }}>检索测试</h3>
        <p style={{ color: 'var(--color-slate)', maxWidth: 720, marginBottom: 24, fontSize: 14 }}>
          输入问题测试知识库文档的检索效果。命中说明该问题可以基于上传文档回答。
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
