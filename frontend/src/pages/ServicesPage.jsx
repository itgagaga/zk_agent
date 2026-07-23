import { useEffect, useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  BookOpenText,
  BriefcaseBusiness,
  GraduationCap,
  HeartPulse,
  Laptop,
  MapPinned,
  Phone,
  Search,
  Sparkles,
  Users,
  Wrench,
} from 'lucide-react'

const ROLES = [
  { label: '全部', value: '', Icon: Users },
  { label: '学生', value: '学生', Icon: BookOpenText },
  { label: '研究生', value: '研究生', Icon: GraduationCap },
  { label: '教师', value: '教师', Icon: BriefcaseBusiness },
  { label: '访客', value: '访客', Icon: MapPinned },
]

const CATEGORIES = ['教务', '科研', '行政', '后勤', '网络', '医疗', '招采', '就业']

const SCENARIOS = [
  {
    Icon: BookOpenText,
    title: '教务与学籍',
    desc: '培养方案、学籍学位、考试与常用表格。',
    category: '教务',
    query: '我想办理教务或学籍相关事项，请告诉我入口、材料和步骤',
  },
  {
    Icon: Laptop,
    title: '网络与数字服务',
    desc: '校园网、VPN、邮箱和常用信息系统。',
    category: '网络',
    query: '请介绍校园网络、VPN和邮箱服务的入口与使用说明',
  },
  {
    Icon: Wrench,
    title: '后勤与报修',
    desc: '校区后勤服务、报修与生活保障信息。',
    category: '后勤',
    query: '我需要校园后勤或报修服务，请帮我查找入口和联系方式',
  },
  {
    Icon: HeartPulse,
    title: '医疗与健康',
    desc: '校医院、就医指引和公开医疗服务信息。',
    category: '医疗',
    query: '请介绍校医院就医流程、所需材料和公开联系方式',
  },
]

export default function ServicesPage() {
  const [category, setCategory] = useState('')
  const [userRole, setUserRole] = useState('')
  const [items, setItems] = useState([])
  const [contacts, setContacts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load(nextCategory = category, nextRole = userRole) {
    setLoading(true)
    setError('')
    try {
      const [serviceResp, contactResp] = await Promise.all([
        axios.get('/api/resources/service-links', {
          params: { category: nextCategory, user_role: nextRole, top_k: 50 },
        }),
        axios.get('/api/resources/contacts', {
          params: { department: nextCategory, top_k: 8 },
        }),
      ])
      setItems(serviceResp.data.items || [])
      setContacts(contactResp.data.items || [])
    } catch {
      setItems([])
      setContacts([])
      setError('暂时无法连接服务目录，你仍可直接询问智能体。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="container agent-page">
      <section className="agent-page-hero agent-page-hero--service">
        <div className="agent-page-hero-copy">
          <div className="eyebrow">CAMPUS AGENT</div>
          <h1>校园办事助手</h1>
          <p>
            从“我要办什么”出发，智能体帮你找到服务入口、所需材料、
            办理步骤与公开联系方式，并始终附上官网来源。
          </p>
          <Link
            to="/chat?q=我想办理一项校园事务，请先询问我的需求，再给出入口、材料、步骤和联系方式"
            className="btn-primary agent-hero-cta"
          >
            <Sparkles size={17} /> 开始智能办理
          </Link>
        </div>
        <div className="agent-page-hero-mark" aria-hidden="true">
          <MapPinned size={112} strokeWidth={1.05} />
          <span>理解需求 · 路由服务 · 核验来源</span>
        </div>
      </section>

      <section className="agent-subsection">
        <div className="agent-section-title">
          <div>
            <div className="eyebrow">FOR YOU</div>
            <h2>先告诉我你的身份</h2>
          </div>
          <p>智能体会据此调整推荐的服务和回答方式。</p>
        </div>
        <div className="role-filter-row">
          {ROLES.map(({ label, value, Icon }) => (
            <button
              key={label}
              className={userRole === value ? 'active' : ''}
              onClick={() => setUserRole(value)}
            >
              <Icon size={18} strokeWidth={1.8} />
              {label}
            </button>
          ))}
        </div>

        <div className="service-scenario-grid">
          {SCENARIOS.map(({ Icon, title, desc, category: itemCategory, query }) => (
            <article key={title} className="service-scenario-card">
              <span className="agent-capability-icon"><Icon size={24} /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
              <div className="service-scenario-actions">
                <Link to={`/chat?q=${encodeURIComponent(`${userRole ? `我是${userRole}，` : ''}${query}`)}`}>
                  问智能体 <Sparkles size={14} />
                </Link>
                <button onClick={() => { setCategory(itemCategory); load(itemCategory, userRole) }}>
                  查服务 <ArrowUpRight size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="agent-subsection">
        <div className="agent-search-panel">
          <div className="agent-search-heading">
            <div>
              <div className="eyebrow">SERVICE DIRECTORY</div>
              <h2>官方服务目录</h2>
            </div>
            <span>{loading ? '正在查询…' : `${items.length} 个入口 · ${contacts.length} 条联系信息`}</span>
          </div>
          <div className="service-directory-controls">
            <div className="agent-search-input-wrap">
              <Search size={19} />
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">全部服务分类</option>
                {CATEGORIES.map((item) => <option key={item}>{item}</option>)}
              </select>
            </div>
            <button className="btn-primary" onClick={() => load()} disabled={loading}>
              {loading ? '查询中' : '查询目录'}
            </button>
          </div>
        </div>

        {error && (
          <div className="agent-empty-state compact">
            <MapPinned size={30} />
            <h3>{error}</h3>
            <Link to="/chat?q=请帮我寻找校园服务入口和联系方式" className="btn-secondary">
              询问智能体
            </Link>
          </div>
        )}

        {!error && (
          <div className="service-result-layout">
            <div>
              <h3 className="service-result-label">服务入口</h3>
              <div className="service-link-grid">
                {items.length === 0 ? (
                  <div className="service-list-empty">当前分类暂无入口数据</div>
                ) : items.map((item, i) => (
                  <a
                    key={`${item.name}-${i}`}
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="service-link-card"
                  >
                    <div>
                      <span>{item.category || category || '校园服务'}</span>
                      <h3>{item.name}</h3>
                      {item.department && <p>{item.department}</p>}
                    </div>
                    <ArrowUpRight size={19} />
                  </a>
                ))}
              </div>
            </div>
            <aside className="contact-panel">
              <div className="contact-panel-title">
                <Phone size={18} />
                <h3>公开联系方式</h3>
              </div>
              {contacts.length === 0 ? (
                <p className="service-list-empty">暂无匹配的公开联系信息</p>
              ) : contacts.map((item, i) => (
                <div key={`${item.office_name}-${i}`} className="contact-item">
                  <div>
                    <strong>{item.office_name || item.department}</strong>
                    {item.address && <span>{item.address}</span>}
                  </div>
                  {item.phone && <a href={`tel:${item.phone}`}>{item.phone}</a>}
                </div>
              ))}
            </aside>
          </div>
        )}
      </section>
    </div>
  )
}
