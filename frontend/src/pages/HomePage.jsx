import { Link } from 'react-router-dom'

const roleEntries = [
  {
    role: '学生',
    accent: '学生',
    items: ['教务资料', '培养方案', '专业查询', '就业信息', '校医院', '后勤服务'],
  },
  {
    role: '教师',
    accent: '教师',
    items: ['OA 系统', '邮箱', 'VPN', '人力资源系统', '科研项目系统', '教务部'],
  },
  {
    role: '研究生',
    accent: '研究生',
    items: ['研究生招生', '培养管理', '学位管理', '相关下载', '导师队伍'],
  },
  {
    role: '考生 / 家长',
    accent: '考生',
    items: ['学校简介', '学院专业', '本科招生', '研究生招生', '录取情况'],
  },
]

export default function HomePage() {
  return (
    <div className="container">
      {/* Hero */}
      <section className="section" style={{ textAlign: 'center', paddingTop: 64 }}>
        <div className="eyebrow">ZHKU CAMPUS AGENT</div>
        <h1 style={{ marginTop: 24, fontSize: 64, maxWidth: 900, margin: '24px auto 0' }}>
          仲恺校园信息服务智能体
        </h1>
        <p
          style={{
            fontSize: 18,
            color: 'var(--color-slate)',
            maxWidth: 720,
            margin: '24px auto 0',
            lineHeight: 1.5,
          }}
        >
          基于仲恺农业工程学院公开网站信息构建的校园信息服务智能体，
          面向学生、教师和访客提供学校信息问答、办事资料检索、服务入口导航和可信来源展示。
        </p>
        <div style={{ marginTop: 40, display: 'flex', gap: 16, justifyContent: 'center' }}>
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
                <Link to="/chat" className="satellite-cta" style={{ position: 'absolute', bottom: -10, right: -10 }}>
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

      {/* MVP 演示问题 */}
      <section className="section">
        <div className="eyebrow">EXAMPLES</div>
        <h2 style={{ marginTop: 16, marginBottom: 48 }}>你可以这样问</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {[
            '仲恺农业工程学院有几个校区？',
            '学校有哪些教学机构？',
            '数据科学与大数据技术专业培养方案在哪里？',
            '补办学生证申请表在哪里？',
            '后勤维修科电话是多少？',
            '2026 年硕士研究生招生章程主要讲了什么？',
          ].map((q) => (
            <Link
              key={q}
              to={`/chat?q=${encodeURIComponent(q)}`}
              className="source-card"
              style={{ display: 'block', textDecoration: 'none' }}
            >
              <div style={{ fontWeight: 500, color: 'var(--color-ink)' }}>{q}</div>
              <div style={{ fontSize: 13, color: 'var(--color-slate)', marginTop: 6 }}>
                点击提问 →
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
