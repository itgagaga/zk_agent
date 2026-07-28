import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import {
  CalendarDays,
  CloudUpload,
  FileSpreadsheet,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react'
import { getAuthHeader } from '../authStore.js'

function formatUpdatedAt(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export default function PersonalSchedule() {
  const [schedule, setSchedule] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  async function loadSchedule() {
    setLoading(true)
    try {
      const resp = await axios.get('/api/schedule/profile', { headers: getAuthHeader() })
      setSchedule(resp.data.schedule || null)
    } catch {
      setSchedule(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSchedule()
  }, [])

  async function handleUpload(file) {
    if (!file || uploading) return
    const ext = (file.name || '').toLowerCase()
    if (!ext.endsWith('.xls') && !ext.endsWith('.xlsx')) {
      alert('请上传教务系统导出的 .xls 或 .xlsx 课表')
      return
    }

    if (schedule) {
      const ok = confirm(
        `上传「${file.name}」将替换当前课表「${schedule.filename || schedule._filename || '已保存课表'}」，是否继续？`
      )
      if (!ok) return
    }

    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await axios.post('/api/schedule/upload', form, {
        headers: getAuthHeader(),
      })
      setSchedule(resp.data.schedule)
    } catch (err) {
      const detail = err?.response?.data?.detail
      alert(typeof detail === 'string' ? detail : '课表上传失败')
    } finally {
      setUploading(false)
      setDragOver(false)
    }
  }

  async function removeSchedule() {
    if (!schedule) return
    if (!confirm('确定删除当前课表？「今日校园」将无法展示你的个人课程。')) return
    try {
      await axios.delete('/api/schedule/profile', { headers: getAuthHeader() })
      setSchedule(null)
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

  const meta = schedule?.meta || {}
  const courseCount = schedule?.courses?.length ?? 0

  return (
    <div className="user-schedule-panel">
      <div className="user-schedule-hero">
        <div className="user-schedule-hero-icon">
          <CalendarDays size={22} strokeWidth={1.8} />
        </div>
        <div>
          <h4 className="user-schedule-hero-title">导入个人课表</h4>
          <p className="user-schedule-hero-text">
            从教务系统导出「学生个人课表」Excel 并上传，即可在
            <strong>今日校园</strong>查看每日课程、天气与 AI 出行建议。
          </p>
        </div>
      </div>

      <div
        className={`user-schedule-dropzone ${dragOver ? 'is-dragover' : ''} ${uploading ? 'is-uploading' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleUpload(file)
            e.target.value = ''
          }}
        />
        <div className="user-schedule-dropzone-inner">
          <div className="user-schedule-dropzone-icon">
            <CloudUpload size={28} strokeWidth={1.6} />
          </div>
          <div className="user-schedule-dropzone-copy">
            <strong>拖拽课表 Excel 到此处</strong>
            <span>支持 .xls / .xlsx · 格式需与教务系统导出一致</span>
          </div>
          <div className="user-schedule-dropzone-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={16} strokeWidth={2} />
              {uploading ? '解析中…' : '选择文件'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={loading || uploading}
              onClick={loadSchedule}
            >
              <RefreshCw size={16} strokeWidth={2} />
              刷新
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <p className="user-schedule-empty">加载中…</p>
      ) : schedule ? (
        <div className="user-schedule-card">
          <div className="user-schedule-card-head">
            <FileSpreadsheet size={20} strokeWidth={1.8} />
            <div>
              <h4>{meta.title || schedule.filename || '我的课表'}</h4>
              <p>
                {meta.semester && `${meta.semester} · `}
                {meta.class_name && `${meta.class_name} · `}
                {meta.major}
              </p>
            </div>
          </div>
          <div className="user-schedule-stats">
            <span>{courseCount} 条课程记录</span>
            <span>第 {schedule.current_week ?? '—'} 教学周</span>
            {schedule._updated_at && (
              <span>更新于 {formatUpdatedAt(schedule._updated_at)}</span>
            )}
          </div>
          <div className="user-schedule-card-actions">
            <button type="button" className="user-schedule-remove" onClick={removeSchedule}>
              <Trash2 size={15} strokeWidth={2} />
              删除课表
            </button>
          </div>
        </div>
      ) : (
        <p className="user-schedule-empty">
          尚未上传课表。未登录用户仍可在「今日校园」查看天气与通用建议。
        </p>
      )}
    </div>
  )
}
