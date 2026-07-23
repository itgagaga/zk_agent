import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

const FEATURES = [
  {
    icon: '💬',
    title: '智能问答',
    desc: '基于官网真实资料的 AI 问答，支持流式输出、来源追溯、多轮对话',
    link: '/chat',
    linkText: '开始提问',
  },
  {
    icon: '📄',
    title: '文档中心',
    desc: '上传培养方案、章程等文档到永久知识库，RAG 自动检索回答',
    link: '/documents',
    linkText: '管理文档',
  },
  {
    icon: '📥',
    title: '资料下载',
    desc: '按关键词和分类检索校内可下载资料，快速找到所需表格和文件',
    link: '/downloads',
    linkText: '搜索资料',
  },
  {
    icon: '🧭',
    title: '服务导航',
    desc: '按角色和分类查找校内服务入口，一键直达目标系统',
    link: '/services',
    linkText: '浏览服务',
  },
]

const roleEntries = [
  {
    role: '学生',
    items: ['教务资料', '培养方案', '专业查询', '就业信息', '校医院', '后勤服务'],
  },
  {
    role: '研究生',
    items: ['研究生招生', '培养管理', '学位管理', '相关下载', '导师队伍'],
  },
  {
    role: '教师',
    items: ['OA 系统', '邮箱', 'VPN', '人力资源系统', '科研项目系统', '教务部'],
  },
  {
    role: '考生 / 家长',
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
      <section className="section">
        <div className="eyebrow">SERVICES</div>
        <h2 style={{ marginTop: 16, marginBottom: 48 }}>按角色选择入口</h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 32,
          }}
        >
          {roleEntries.map((entry) => (
            <div key={entry.role} style={{ textAlign: 'center' }}>
              <div className="portrait-card" style={{ margin: '0 auto 24px' }}>
                <span style={{ fontSize: 24, fontWeight: 500 }}>{entry.role}</span>
                <Link
                  to="/chat"
                  className="satellite-cta"
                  style={{ position: 'absolute', bottom: -10, right: -10 }}
                >
                  →
                </Link>
              </div>
              <div style={{ fontSize: 14, color: 'var(--color-slate)', lineHeight: 1.8 }}>
                {entry.items.map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 功能卡片 */}
      <section className="section">
        <div className="eyebrow">FEATURES</div>
        <h2 style={{ marginTop: 16, marginBottom: 32 }}>核心功能</h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <Link key={f.title} to={f.link} className="feature-card">
              <div className="feature-icon">{f.icon}</div>
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
