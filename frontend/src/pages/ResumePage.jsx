import { useState, useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import ResumeForm from '../components/ResumeForm'
import ResumePreview from '../components/ResumePreview'
import InterviewChat from '../components/InterviewChat'
import AcademicSearchPanel from '../components/AcademicSearchPanel'
import { getAuthHeader, getAuthSnapshot, subscribeAuth } from '../authStore.js'

const INITIAL_DATA = {
  basic: { name: '', phone: '', email: '', address: '', website: '', photo: '' },
  education: [{ school: '', major: '', degree: '', start: '', end: '' }],
  skills: [{ category: '', items: '' }],
  projects: [{ name: '', role: '', start: '', end: '', description: '', tech_stack: '' }],
  intro_keywords: '',
  target_position: '',
  intro: '',
}

const DEFAULTS = {
  basic: { name: '张三', phone: '138****0000', email: 'example@email.com', address: '广东省广州市', website: '' },
  education: [{ school: '仲恺农业工程学院', major: '计算机科学与技术', degree: '本科', start: '2022.09', end: '2026.06' }],
  target_position: '软件开发工程师',
  intro_keywords: '有编程基础；学习能力强；有团队协作经验',
}

function fillDefaults(data) {
  const basic = { ...data.basic }
  for (const [k, v] of Object.entries(DEFAULTS.basic)) {
    if (!basic[k]) basic[k] = v
  }
  const education = data.education.map((e) => {
    const filled = { ...e }
    for (const [k, v] of Object.entries(DEFAULTS.education[0])) {
      if (!filled[k]) filled[k] = v
    }
    return filled
  })
  const target_position = data.target_position || DEFAULTS.target_position
  const intro_keywords = data.intro_keywords || DEFAULTS.intro_keywords
  return { ...data, basic, education, target_position, intro_keywords }
}

function mergeResume(server) {
  if (!server || typeof server !== 'object') return INITIAL_DATA
  return {
    ...INITIAL_DATA,
    ...server,
    basic: { ...INITIAL_DATA.basic, ...(server.basic || {}) },
    education: Array.isArray(server.education) && server.education.length
      ? server.education
      : INITIAL_DATA.education,
    skills: Array.isArray(server.skills) && server.skills.length
      ? server.skills
      : INITIAL_DATA.skills,
    projects: Array.isArray(server.projects) && server.projects.length
      ? server.projects
      : INITIAL_DATA.projects,
  }
}

export default function ResumePage() {
  const auth = useSyncExternalStore(subscribeAuth, getAuthSnapshot)
  const loggedIn = Boolean(auth.user && auth.token)

  const [data, setData] = useState(INITIAL_DATA)
  const [templateId, setTemplateId] = useState('classic')
  const [enhancing, setEnhancing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState('resume')
  const saveTimer = useRef(null)
  const skipNextSave = useRef(false)

  useEffect(() => {
    if (!loggedIn) return
    let cancelled = false
    ;(async () => {
      try {
        const resp = await axios.get('/api/resume/profile', { headers: getAuthHeader() })
        if (cancelled) return
        if (resp.data?.ok && resp.data.resume) {
          skipNextSave.current = true
          setData(mergeResume(resp.data.resume))
        }
      } catch {
        // 401 等忽略
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loggedIn])

  const persistProfile = useCallback(
    (payload) => {
      if (!loggedIn) return
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(async () => {
        setSaving(true)
        try {
          await axios.put('/api/resume/profile', payload, { headers: getAuthHeader() })
        } catch (err) {
          console.warn('简历保存失败', err?.message || err)
        } finally {
          setSaving(false)
        }
      }, 800)
    },
    [loggedIn],
  )

  const handleChange = useCallback(
    (newData) => {
      setData(newData)
      if (skipNextSave.current) {
        skipNextSave.current = false
        return
      }
      persistProfile(newData)
    },
    [persistProfile],
  )

  async function handleEnhance() {
    setEnhancing(true)
    try {
      const filled = fillDefaults(data)
      const resp = await axios.post(
        '/api/resume/enhance',
        {
          intro_keywords: filled.intro_keywords,
          skills: filled.skills,
          projects: filled.projects,
          target_position: filled.target_position,
          basic: filled.basic,
          education: filled.education,
        },
        { headers: getAuthHeader() },
      )
      const result = resp.data
      setData((prev) => {
        const basic = { ...fillDefaults(prev).basic, ...prev.basic }
        const education = prev.education.map((e) => {
          const defEdu = DEFAULTS.education[0]
          return { ...defEdu, ...e }
        })
        for (const [k] of Object.entries(basic)) {
          if (!prev.basic[k] && DEFAULTS.basic[k]) {
            basic[k] = DEFAULTS.basic[k]
          }
        }
        const next = {
          ...prev,
          basic,
          education,
          intro: result.intro || prev.intro_keywords || DEFAULTS.intro_keywords,
          skills: result.skills.length > 0 ? result.skills : prev.skills,
          projects: result.projects.length > 0 ? result.projects : prev.projects,
        }
        persistProfile(next)
        return next
      })
    } catch (e) {
      console.error('简历增强失败:', e)
      alert('AI 优化失败，请检查后端服务是否正常运行。')
    } finally {
      setEnhancing(false)
    }
  }

  return (
    <div className="resume-page">
      <div className="resume-page-header">
        <div className="eyebrow">GRADUATION</div>
        <h1>毕业季</h1>
        <p>AI 简历优化与模拟面试，或搜索学术论文助力毕业设计</p>
        {loggedIn ? (
          <p className="resume-sync-hint">
            {saving ? '正在同步到账号…' : '已绑定当前账号，与个人中心简历互通同步'}
          </p>
        ) : (
          <div className="auth-gate-banner" style={{ marginTop: 16 }}>
            <span>登录后可将简历与面试资料绑定到账号。</span>
            <Link to="/login" className="btn-primary" style={{ textDecoration: 'none' }}>
              去登录
            </Link>
          </div>
        )}
        <div className="resume-tabs">
          <button
            className={`resume-tab ${activeTab === 'resume' ? 'active' : ''}`}
            onClick={() => setActiveTab('resume')}
          >
            简历生成
          </button>
          <button
            className={`resume-tab ${activeTab === 'interview' ? 'active' : ''}`}
            onClick={() => setActiveTab('interview')}
          >
            模拟面试
          </button>
          <button
            className={`resume-tab ${activeTab === 'academic' ? 'active' : ''}`}
            onClick={() => setActiveTab('academic')}
          >
            学术搜索
          </button>
        </div>
      </div>

      {activeTab === 'resume' && (
        <div className="resume-page-body">
          <div className="resume-page-left">
            <ResumeForm
              data={data}
              onChange={handleChange}
              onEnhance={handleEnhance}
              enhancing={enhancing}
            />
          </div>
          <div className="resume-page-right">
            <ResumePreview
              data={data}
              templateId={templateId}
              onTemplateChange={setTemplateId}
              onEnhance={handleEnhance}
              enhancing={enhancing}
            />
          </div>
        </div>
      )}

      {activeTab === 'interview' && <InterviewChat onBack={() => setActiveTab('resume')} />}

      {activeTab === 'academic' && <AcademicSearchPanel />}
    </div>
  )
}
