import { useState, useCallback } from 'react'
import axios from 'axios'
import ResumeForm from '../components/ResumeForm'
import ResumePreview from '../components/ResumePreview'
import InterviewChat from '../components/InterviewChat'

const INITIAL_DATA = {
  basic: { name: '', phone: '', email: '', address: '', website: '', photo: '' },
  education: [{ school: '', major: '', degree: '', start: '', end: '' }],
  skills: [{ category: '', items: '' }],
  projects: [{ name: '', role: '', start: '', end: '', description: '', tech_stack: '' }],
  intro_keywords: '',
  target_position: '',
  intro: '',
}

// 空字段默认值，导出时自动补齐
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
  const education = data.education.map(e => {
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

export default function ResumePage() {
  const [data, setData] = useState(INITIAL_DATA)
  const [templateId, setTemplateId] = useState('classic')
  const [enhancing, setEnhancing] = useState(false)
  // 子标签：resume | interview
  const [activeTab, setActiveTab] = useState('resume')

  const handleChange = useCallback((newData) => {
    setData(newData)
  }, [])

  async function handleEnhance() {
    setEnhancing(true)
    try {
      // 补齐空字段的默认值再发给 LLM
      const filled = fillDefaults(data)
      const resp = await axios.post('/api/resume/enhance', {
        intro_keywords: filled.intro_keywords,
        skills: filled.skills,
        projects: filled.projects,
        target_position: filled.target_position,
        basic: filled.basic,
        education: filled.education,
      })
      const result = resp.data
      setData(prev => {
        // 用默认值补齐 basic 和 education，保留用户已填的
        const basic = { ...fillDefaults(prev).basic, ...prev.basic }
        const education = prev.education.map((e, i) => {
          const defEdu = DEFAULTS.education[0]
          const filled = { ...defEdu, ...e }
          return filled
        })
        // 去掉 basic 中仍为空的默认值覆盖（只补用户没填的）
        for (const [k, v] of Object.entries(basic)) {
          if (!prev.basic[k] && DEFAULTS.basic[k]) {
            basic[k] = DEFAULTS.basic[k]
          }
        }
        return {
          ...prev,
          basic,
          education,
          intro: result.intro || prev.intro_keywords || DEFAULTS.intro_keywords,
          skills: result.skills.length > 0 ? result.skills : prev.skills,
          projects: result.projects.length > 0 ? result.projects : prev.projects,
        }
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
        <div className="eyebrow">RESUME & INTERVIEW</div>
        <h1>简历 & 面试</h1>
        <p>填写简历信息，AI 优化内容并导出 PDF；或基于简历进行模拟面试</p>
        {/* 子标签切换 */}
        <div className="resume-tabs">
          <button
            className={`resume-tab ${activeTab === 'resume' ? 'active' : ''}`}
            onClick={() => setActiveTab('resume')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            简历生成
          </button>
          <button
            className={`resume-tab ${activeTab === 'interview' ? 'active' : ''}`}
            onClick={() => setActiveTab('interview')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
            模拟面试
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

      {activeTab === 'interview' && (
        <InterviewChat
          onBack={() => setActiveTab('resume')}
        />
      )}
    </div>
  )
}
