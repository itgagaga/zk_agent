import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
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
  Users,
  Wrench,
} from 'lucide-react'
import EmbeddedChat from '../components/EmbeddedChat'
import { askAndOpen } from '../embeddedChatStore'

const CHAT_SUGGESTIONS = [
  '我要办理学生证相关事务',
  '校园网怎么连？',
  '校医院看病流程是什么？',
  '后勤报修入口在哪？',
]

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
    prompt: '我想了解教务与学籍相关的服务，包括培养方案、学籍学位、考试与常用表格',
  },
  {
    Icon: Laptop,
    title: '网络与数字服务',
    desc: '校园网、VPN、邮箱和常用信息系统。',
    category: '网络',
    prompt: '我想了解网络与数字服务，包括校园网、VPN、邮箱和常用信息系统',
  },
  {
    Icon: Wrench,
    title: '后勤与报修',
    desc: '校区后勤服务、报修与生活保障信息。',
    category: '后勤',
    prompt: '我想了解后勤与报修相关的服务，包括校区后勤服务、报修与生活保障',
  },
  {
    Icon: HeartPulse,
    title: '医疗与健康',
    desc: '校医院、就医指引和公开医疗服务信息。',
    category: '医疗',
    prompt: '我想了解医疗与健康相关的服务，包括校医院、就医指引和医疗服务',
  },
]

const STORE_KEY = '校园办事助手'

function extractDomain(url) {
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}

function ServicePreview({ url }) {
  if (!url) return null
  const domain = extractDomain(url)
  if (!domain) return null
  return (
    <div className="service-link-preview">
      <img
        className="service-link-preview-favicon"
        src={`https://www.google.com/s2/favicons?domain=${domain}`}
        alt=""
        width={20}
        height={20}
      />
      <span className="service-link-preview-domain">{domain}</span>
      <a
        className="service-link-preview-visit"
        href={url}
        target="_blank"
        rel="noreferrer"
      >
        访问网站 <ArrowUpRight size={12} />
      </a>
    </div>
  )
}

export default function ServicesPage() {
  const directoryRef = useRef(null)
  const [category, setCategory] = useState('')
  const [userRole, setUserRole] = useState('')
  const [items, setItems] = useState([])
  const [contacts, setContacts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function scrollToDirectory() {
    directoryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

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
      setError('暂时无法连接服务目录，请稍后再试。')
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
          <div className="eyebrow">CAMPUS SERVICES</div>
          <h1>校园办事助手</h1>
          <p>
            从"我要办什么"出发，找到服务入口、所需材料、
            办理步骤与公开联系方式，并始终附上官网来源。
          </p>
          <button
            className="btn-primary agent-hero-cta"
            onClick={scrollToDirectory}
          >
            浏览服务
          </button>
        </div>
        <div className="agent-page-hero-mark" aria-hidden="true">
          <MapPinned size={112} strokeWidth={1.05} />
          <span>查找入口 · 浏览服务 · 核验来源</span>
        </div>
      </section>

      <section className="agent-subsection">
        <div className="agent-section-title">
          <div>
            <div className="eyebrow">FOR YOU</div>
            <h2>先告诉我你的身份</h2>
          </div>
          <p>系统会据此调整推荐的服务和展示方式。</p>
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
          {SCENARIOS.map(({ Icon, title, desc, category: itemCategory, prompt }) => (
            <article key={title} className="service-scenario-card">
              <span className="agent-capability-icon"><Icon size={24} /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
              <div className="service-scenario-actions">
                <button onClick={() => askAndOpen(STORE_KEY, prompt)}>
                  开始对话 <ArrowUpRight size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="agent-subsection" ref={directoryRef}>
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
            <button className="btn-secondary" onClick={() => { setCategory(''); load('', userRole) }}>
              换个分类试试
            </button>
          </div>
        )}

        {!error && (
          <div className="service-result-layout">
            <div>
              <h3 className="service-result-label">服务入口</h3>
              <div className="service-link-grid">
                {items.length === 0 ? (
                  <div className="service-list-empty">当前分类暂无入口数据，换个分类试试</div>
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
                      <ServicePreview url={item.url} />
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

      <EmbeddedChat
        title="办事助手"
        contextHint="校园办事助手"
        suggestions={CHAT_SUGGESTIONS}
      />
    </div>
  )
}
