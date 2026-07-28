import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import {
  BriefcaseBusiness,
  CloudUpload,
  FileUser,
  GraduationCap,
  MessageCircleMore,
  RefreshCw,
} from 'lucide-react'
import { getAuthHeader } from '../authStore.js'

export default function PersonalResume() {
  const [resume, setResume] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  async function loadResume() {
    setLoading(true)
    try {
      const resp = await axios.get('/api/resume/profile', { headers: getAuthHeader() })
      setResume(resp.data?.ok ? resp.data.resume : null)
    } catch {
      setResume(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadResume()
  }, [])

  async function handleUpload(file) {
    if (!file || uploading) return

    if (resume?.filename) {
      const ok = confirm(
        `上传「${file.name}」将替换当前简历，毕业季与模拟面试将同步更新，是否继续？`
      )
      if (!ok) return
    }

    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await axios.post('/api/resume/upload', form, { headers: getAuthHeader() })
      setResume(resp.data.resume || null)
    } catch (err) {
      const detail = err?.response?.data?.detail
      alert(typeof detail === 'string' ? detail : '上传失败')
    } finally {
      setUploading(false)
      setDragOver(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  const name = resume?.basic?.name || ''
  const position = resume?.target_position || ''
  const school = resume?.education?.[0]?.school || ''
  const major = resume?.education?.[0]?.major || ''
  const skills = (resume?.skills || [])
    .map((s) => s.items)
    .filter(Boolean)
    .join('、')

  return (
    <div className="user-kb-panel user-resume-panel">
      <div className="user-kb-hero">
        <div className="user-kb-hero-icon">
          <FileUser size={22} strokeWidth={1.8} />
        </div>
        <div>
          <h4 className="user-kb-hero-title">个人简历</h4>
          <p className="user-kb-hero-text">
            上传 PDF / Word 等简历文件，系统自动解析为结构化信息。
            与<strong>毕业季</strong>、<strong>模拟面试</strong>共用同一份简历，任一入口上传都会同步更新。
          </p>
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
            {resume ? <RefreshCw size={28} strokeWidth={1.6} /> : <CloudUpload size={28} strokeWidth={1.6} />}
          </div>
          <div className="user-kb-dropzone-copy">
            <strong>
              {uploading
                ? '正在解析简历…'
                : resume
                  ? '拖拽新文件到此处，或点击选择'
                  : '拖拽简历到此处，或点击选择'}
            </strong>
            <span>支持 PDF · Word · TXT · Markdown，最大 10MB</span>
          </div>
          <div className="user-kb-dropzone-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md"
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
              {uploading ? '处理中…' : resume ? '重新上传' : '选择简历'}
            </button>
          </div>
        </div>
      </div>

      <div className="user-kb-tips">
        <div className="user-kb-tip">
          <MessageCircleMore size={16} strokeWidth={1.8} />
          <span>模拟面试会基于这份简历提问；也可在毕业季进一步编辑、优化与导出</span>
        </div>
        <div className="user-kb-tip">
          <BriefcaseBusiness size={16} strokeWidth={1.8} />
          <span>
            前往 <Link to="/resume">毕业季</Link> 可在线填写、AI 润色并预览简历
          </span>
        </div>
      </div>

      <div className="user-kb-list-head">
        <h4>当前简历</h4>
        {resume?.filename && <span>{resume.filename}</span>}
      </div>

      {loading ? (
        <div className="user-kb-skeleton">
          <div className="user-kb-skeleton-row" />
        </div>
      ) : resume ? (
        <article className="user-resume-card">
          <div className="user-resume-card-head">
            <div>
              <div className="user-resume-card-name">{name || '未识别姓名'}</div>
              {position && <div className="user-resume-card-position">{position}</div>}
            </div>
            {resume.filename && (
              <div className="user-resume-card-file">{resume.filename}</div>
            )}
          </div>
          {(school || major) && (
            <div className="user-resume-card-row">
              <GraduationCap size={16} strokeWidth={1.8} />
              <span>
                {[school, major].filter(Boolean).join(' · ')}
              </span>
            </div>
          )}
          {skills && (
            <div className="user-resume-card-skills">{skills}</div>
          )}
          {resume.upload_time && (
            <div className="user-resume-card-meta">上次更新：{resume.upload_time}</div>
          )}
        </article>
      ) : (
        <div className="user-kb-empty">
          <FileUser size={32} strokeWidth={1.5} />
          <strong>还没有简历</strong>
          <p>上传简历后，可在毕业季编辑优化，或在模拟面试中直接使用。</p>
        </div>
      )}
    </div>
  )
}
