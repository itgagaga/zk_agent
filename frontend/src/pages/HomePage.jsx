import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  BookOpenText,
  BriefcaseBusiness,
  Compass,
  Download,
  FileSearch,
  GraduationCap,
  MessageCircleMore,
  School,
} from 'lucide-react'
import studentIllustration from '../assets/roles/student.svg'
import graduateIllustration from '../assets/roles/graduate.svg'
import teacherIllustration from '../assets/roles/teacher.svg'
import familyIllustration from '../assets/roles/family.svg'

const FEATURES = [
  {
    Icon: MessageCircleMore,
    title: '智能问答',
    desc: '基于官网真实资料的 AI 问答，支持流式输出、来源追溯、多轮对话',
    link: '/chat',
    linkText: '开始提问',
  },
  {
    Icon: FileSearch,
    title: '文档中心',
    desc: '上传培养方案、章程等文档到永久知识库，RAG 自动检索回答',
    link: '/documents',
    linkText: '管理文档',
  },
  {
    Icon: Download,
    title: '资料下载',
    desc: '按关键词和分类检索校内可下载资料，快速找到所需表格和文件',
    link: '/downloads',
    linkText: '搜索资料',
  },
  {
    Icon: Compass,
    title: '服务导航',
    desc: '按角色和分类查找校内服务入口，一键直达目标系统',
    link: '/services',
    linkText: '浏览服务',
  },
]

const roleEntries = [
  {
    role: '学生',
    kicker: '学习与校园生活',
    illustration: studentIllustration,
    Icon: BookOpenText,
    tone: 'amber',
    prompt: '我是本科生，请介绍适合学生使用的校园服务和资料入口',
    items: ['教务资料', '培养方案', '专业查询', '就业信息', '校医院', '后勤服务'],
  },
  {
    role: '研究生',
    kicker: '培养与学术支持',
    illustration: graduateIllustration,
    Icon: GraduationCap,
    tone: 'blue',
    prompt: '我是研究生，请介绍研究生培养、学位和资料下载入口',
    items: ['研究生招生', '培养管理', '学位管理', '相关下载', '导师队伍'],
  },
  {
    role: '教师',
    kicker: '教学与科研办公',
    illustration: teacherIllustration,
    Icon: BriefcaseBusiness,
    tone: 'green',
    prompt: '我是教师，请介绍教学、科研和办公相关的校园服务入口',
    items: ['OA 系统', '邮箱', 'VPN', '人力资源系统', '科研项目系统', '教务部'],
  },
  {
    role: '考生 / 家长',
    kicker: '了解仲恺与招生',
    illustration: familyIllustration,
    Icon: School,
    tone: 'rose',
    prompt: '我是考生或家长，请介绍学校概况、学院专业和招生信息',
    items: ['学校简介', '学院专业', '本科招生', '研究生招生', '录取情况'],
  },
]

const POPULAR_QS = [
  { q: '仲恺农业工程学院有几个校区？', cat: '学校概况' },
  { q: '学校有哪些教学机构？', cat: '学校概况' },
  { q: '2026年本科招生章程主要讲了什么？', cat: '招生信息' },
  { q: '数学与数据科学学院电话是多少？', cat: '联系方式' },
  { q: '补办学生证申请表在哪里？', cat: '教务资料' },
  { q: '就业协议书怎么申请？', cat: '就业服务' },
]

function useCountUp(target, duration = 1200) {
  const [val, setVal] = useState(0)
  const ref = useRef(null)
  const started = useRef(false)

  useEffect(() => {
    if (!ref.current || started.current) return
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !started.current) {
          started.current = true
          const start = performance.now()
          const tick = (now) => {
            const elapsed = now - start
            const progress = Math.min(elapsed / duration, 1)
            const eased = 1 - Math.pow(1 - progress, 3)
            setVal(Math.round(target * eased))
            if (progress < 1) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        }
      },
      { threshold: 0.3 }
    )
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [target, duration])

  return { val, ref }
}

function StatItem({ value, label, suffix = '' }) {
  const { val, ref } = useCountUp(value)
  return (
    <div className="stat-item" ref={ref}>
      <div className="stat-num">
        {val}
        {suffix}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export default function HomePage() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch('/api/stats')
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {})
  }, [])

  return (
    <div className="container">
      {/* Hero */}
      <section className="section" style={{ textAlign: 'center', paddingTop: 56 }}>
        <div className="eyebrow">ZHKU CAMPUS AGENT</div>
        <h1 style={{ marginTop: 24, fontSize: 56, maxWidth: 900, margin: '24px auto 0' }}>
          仲恺校园信息服务智能体
        </h1>
        <p
          style={{
            fontSize: 17,
            color: 'var(--color-slate)',
            maxWidth: 720,
            margin: '20px auto 0',
            lineHeight: 1.5,
          }}
        >
          基于仲恺农业工程学院公开网站信息构建的校园信息服务智能体，
          面向学生、教师和访客提供学校信息问答、办事资料检索、服务入口导航和可信来源展示。
        </p>
        <div style={{ marginTop: 36, display: 'flex', gap: 16, justifyContent: 'center' }}>
          <Link to="/chat" className="btn-primary">
            开始提问
          </Link>
          <Link to="/documents" className="btn-secondary">
            智能文档
          </Link>
        </div>
      </section>

      {/* 角色入口 */}
      <section className="section role-section">
        <div className="role-section-heading">
          <div>
            <div className="eyebrow">SERVICES</div>
            <h2>按角色选择入口</h2>
          </div>
          <p>选择与你最接近的身份，快速找到常用服务与可信校园信息。</p>
        </div>
        <svg
          className="role-orbit"
          viewBox="0 0 1200 420"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d="M-40 300 C 160 30, 340 390, 570 176 S 920 50, 1240 260" />
          <path d="M80 390 C 290 210, 410 310, 620 270 S 980 170, 1160 34" />
        </svg>
        <div className="role-grid">
          {roleEntries.map((entry) => (
            <Link
              key={entry.role}
              to={`/chat?q=${encodeURIComponent(entry.prompt)}`}
              className={`role-card role-card--${entry.tone}`}
            >
              <div className="role-visual">
                <div className="role-number">0{roleEntries.indexOf(entry) + 1}</div>
                <img src={entry.illustration} alt="" className="role-illustration" />
                <span className="role-arrow" aria-hidden="true">
                  <ArrowUpRight size={22} strokeWidth={1.8} />
                </span>
              </div>
              <div className="role-card-copy">
                <div className="role-kicker">
                  <entry.Icon size={15} strokeWidth={1.8} />
                  {entry.kicker}
                </div>
                <h3>{entry.role}</h3>
                <div className="role-tags">
                {entry.items.map((item) => (
                    <span key={item}>{item}</span>
                ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
        <div className="asset-credit">
          项目内置原创 SVG · 视觉风格参考 Open Peeps
        </div>
      </section>

      {/* 功能卡片 */}
      <section className="section">
        <div className="eyebrow">FEATURES</div>
        <h2 style={{ marginTop: 16, marginBottom: 32 }}>核心功能</h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <Link key={f.title} to={f.link} className="feature-card">
              <div className="feature-icon">
                <f.Icon size={28} strokeWidth={1.7} />
              </div>
              <div className="feature-title">{f.title}</div>
              <div className="feature-desc">{f.desc}</div>
              <div className="feature-link">{f.linkText} →</div>
            </Link>
          ))}
        </div>
      </section>

      {/* 热门问题 */}
      <section className="section">
        <div className="eyebrow">POPULAR</div>
        <h2 style={{ marginTop: 16, marginBottom: 32 }}>热门问题</h2>
        <div className="popular-grid">
          {POPULAR_QS.map((item) => (
            <Link
              key={item.q}
              to={`/chat?q=${encodeURIComponent(item.q)}`}
              className="popular-card"
            >
              <div className="popular-cat">{item.cat}</div>
              <div className="popular-q">{item.q}</div>
              <div className="popular-arrow">点击提问 →</div>
            </Link>
          ))}
        </div>
      </section>

      {/* 数据统计横幅 */}
      {stats && (
        <section className="section">
          <div className="stats-banner">
            <StatItem value={stats.total_chunks || 0} label="知识片段" />
            <div className="stat-divider" />
            <StatItem value={stats.campus_chunks || 0} label="官网资料" />
            <div className="stat-divider" />
            <StatItem value={stats.document_chunks || 0} label="文档库" />
            <div className="stat-divider" />
            <StatItem value={stats.uploaded_docs || 0} label="已上传文档" />
            <div className="stat-divider" />
            <StatItem value={(stats.tools || []).length} label="智能工具" />
          </div>
        </section>
      )}
    </div>
  )
}
