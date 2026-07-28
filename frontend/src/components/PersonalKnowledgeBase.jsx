import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  CloudUpload,
  FileText,
  Layers,
  MessageCircleMore,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { getAuthHeader } from '../authStore.js'

function fileExt(name) {
  const m = (name || '').match(/\.([^.]+)$/)
  return m ? m[1].toUpperCase() : 'DOC'
}

function extTone(ext) {
  if (ext === 'PDF') return 'pdf'
  if (ext === 'DOC' || ext === 'DOCX') return 'word'
  if (ext === 'MD') return 'md'
  return 'txt'
}

export default function PersonalKnowledgeBase() {
  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [department, setDepartment] = useState('文档库')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  async function loadDoc() {
    setLoading(true)
    try {
      const resp = await axios.get('/api/upload/docs', { headers: getAuthHeader() })
      const docs = resp.data.docs || []
      setDoc(docs[0] || null)
    } catch {
      setDoc(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDoc()
  }, [])

  async function handleUpload(file) {
    if (!file || uploading) return

    if (doc) {
      const ok = confirm(
        `上传「${file.name}」将替换当前知识库中的「${doc.title || doc.filename}」，是否继续？`
      )
      if (!ok) return
    }

    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('department', department || '文档库')
      const resp = await axios.post('/api/upload', form, { headers: getAuthHeader() })
      setDoc({
        doc_id: resp.data.doc_id,
        filename: resp.data.filename,
        title: resp.data.title,
        department: resp.data.department,
        chunk_count: resp.data.chunk_count,
        page_count: resp.data.page_count,
      })
    } catch (err) {
      const detail = err?.response?.data?.detail
      alert(typeof detail === 'string' ? detail : '上传失败')
    } finally {
      setUploading(false)
      setDragOver(false)
    }
  }

  async function removeDoc() {
    if (!doc) return
    if (!confirm('确定清空当前知识库文档？')) return
    try {
      await axios.delete(`/api/upload/docs/${doc.doc_id}`, { headers: getAuthHeader() })
      setDoc(null)
    } catch {
      alert('删除失败')
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  return (
    <div className="user-kb-panel">
      <div className="user-kb-hero">
        <div className="user-kb-hero-icon">
          <Sparkles size={22} strokeWidth={1.8} />
        </div>
        <div>
          <h4 className="user-kb-hero-title">定制你的私有知识库</h4>
          <p className="user-kb-hero-text">
            上传一份培养方案、章程或手册，系统会自动解析并向量化。
            在<strong>智能问答</strong>中会优先检索这份资料；重新上传会更新知识库内容。
          </p>
        </div>
      </div>

      <div className="user-kb-stats">
        <div className="user-kb-stat">
          <div className="user-kb-stat-num">{doc ? '1' : '0'}</div>
          <div className="user-kb-stat-label">当前文档</div>
        </div>
        <div className="user-kb-stat">
          <div className="user-kb-stat-num">{doc?.chunk_count ?? '—'}</div>
          <div className="user-kb-stat-label">知识片段</div>
        </div>
        <div className="user-kb-stat">
          <div className="user-kb-stat-num">{doc?.page_count ? doc.page_count : '—'}</div>
          <div className="user-kb-stat-label">页数</div>
        </div>
      </div>

      <div
        className={`user-kb-dropzone ${dragOver ? 'is-dragover' : ''} ${uploading ? 'is-uploading' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="user-kb-dropzone-inner">
          <div className="user-kb-dropzone-icon">
            {doc ? <RefreshCw size={28} strokeWidth={1.6} /> : <CloudUpload size={28} strokeWidth={1.6} />}
          </div>
          <div className="user-kb-dropzone-copy">
            <strong>
              {uploading
                ? '正在解析入库…'
                : doc
                  ? '拖拽新文件到此处，或点击选择'
                  : '拖拽文件到此处，或点击选择'}
            </strong>
            <span>支持 PDF · Word · TXT · Markdown，单个不超过 20MB</span>
          </div>
          <div className="user-kb-dropzone-actions">
            <input
              className="user-kb-dept-input"
              type="text"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              placeholder="来源标签（如：教务部 / 招生办）"
              disabled={uploading}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt,.md"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleUpload(f)
                e.target.value = ''
              }}
            />
            <button
              type="button"
              className="btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? '处理中…' : doc ? '重新上传' : '选择文件'}
            </button>
          </div>
        </div>
      </div>

      <div className="user-kb-tips">
        <div className="user-kb-tip">
          <MessageCircleMore size={16} strokeWidth={1.8} />
          <span>上传后在智能问答中直接提问，例如「我的培养方案学分要求是什么？」</span>
        </div>
        <div className="user-kb-tip">
          <Layers size={16} strokeWidth={1.8} />
          <span>知识库仅保存一份文档，且仅对你本人可见</span>
        </div>
      </div>

      <div className="user-kb-list-head">
        <h4>当前文档</h4>
        {doc?.filename && <span>{doc.filename}</span>}
      </div>

      {loading ? (
        <div className="user-kb-skeleton">
          <div className="user-kb-skeleton-row" />
        </div>
      ) : doc ? (
        <article className="user-kb-doc user-kb-doc--current">
          <div className={`user-kb-doc-badge user-kb-doc-badge--${extTone(fileExt(doc.filename || doc.title))}`}>
            {fileExt(doc.filename || doc.title)}
          </div>
          <div className="user-kb-doc-body">
            <div className="user-kb-doc-title">{doc.title || doc.filename}</div>
            <div className="user-kb-doc-meta">
              <span>{doc.department || '文档库'}</span>
              {doc.chunk_count > 0 && <span>{doc.chunk_count} 片段</span>}
              {doc.page_count > 0 && <span>{doc.page_count} 页</span>}
            </div>
          </div>
          <button
            type="button"
            className="user-kb-doc-remove"
            onClick={removeDoc}
            title="清空知识库"
            aria-label="清空知识库"
          >
            <Trash2 size={16} strokeWidth={1.8} />
          </button>
        </article>
      ) : (
        <div className="user-kb-empty">
          <FileText size={32} strokeWidth={1.5} />
          <strong>还没有文档</strong>
          <p>上传一份文档后，智能问答就能基于你的资料回答问题了。</p>
        </div>
      )}
    </div>
  )
}
