import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import {
  ArrowUpRight,
  BookOpenText,
  BriefcaseBusiness,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  GraduationCap,
  HeartPulse,
  Laptop,
  ListChecks,
  MapPinned,
  Phone,
  Search,
  Users,
  Wrench,
} from 'lucide-react'
import EmbeddedChat from '../components/EmbeddedChat'
import EmploymentBrowser from '../components/EmploymentBrowser'
import { askAndOpen } from '../embeddedChatStore'
import { downloadCategories } from '../resourceViewModel'

const STORE_KEY = '资料智库'

const CHAT_SUGGESTIONS = [
  '帮我查找缓考申请表',
  '补办学生证需要什么材料？',
  '校园网怎么连？',
  '后勤报修入口在哪？',
]

const QUICK_TASKS = [
  {
    Icon: FileSearch,
    title: '找资料与表格',
    desc: '定位官方表格、附件和下载入口。',
    prompt: '帮我找资料，我想找相关的官方表格、附件和下载入口',
  },
  {
    Icon: MapPinned,
    title: '找服务入口',
    desc: '按办事需求推荐系统入口与官网链接。',
    prompt: '我想办理校园事务，请帮我找到对应的官方服务入口',
  },
  {
    Icon: ListChecks,
    title: '材料与步骤',
    desc: '整理办理前材料清单和可执行步骤。',
    prompt: '请帮我梳理办事需要的材料清单和具体步骤',
  },
  {
    Icon: Phone,
    title: '查联系方式',
    desc: '查找公开电话、办公地点等联系信息。',
    prompt: '请帮我查找相关的公开联系方式',
  },
]

const SERVICE_CATEGORIES = ['教务', '科研', '行政', '后勤', '网络', '医疗', '招采', '就业']

const ROLES = [
  { label: '全部', value: '', Icon: Users },
  { label: '学生', value: '学生', Icon: BookOpenText },
  { label: '研究生', value: '研究生', Icon: GraduationCap },
  { label: '教师', value: '教师', Icon: BriefcaseBusiness },
  { label: '访客', value: '访客', Icon: MapPinned },
]

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

function extractDomain(url) {
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}

function LinkPreview({ url }) {
  const domain = extractDomain(url)
  if (!domain) return null
  const faviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

  return (
    <div className="resource-link-preview">
      <img
        className="resource-link-preview-favicon"
        src={faviconUrl}
        alt=""
        width={20}
        height={20}
        onError={(e) => { e.target.style.display = 'none' }}
      />
      <span className="resource-link-preview-domain">{domain}</span>
      <a
        className="resource-link-preview-visit"
        href={url}
        target="_blank"
        rel="noreferrer"
      >
        访问网站 <ExternalLink size={13} />
      </a>
    </div>
  )
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

export default function DownloadsPage() {
  const browseRef = useRef(null)
  const [activeTab, setActiveTab] = useState('downloads')

  const [keyword, setKeyword] = useState('')
  const [downloadCategory, setDownloadCategory] = useState('')
  const [downloadCategoriesState, setDownloadCategoriesState] = useState([])
  const [downloadItems, setDownloadItems] = useState([])
  const [downloadTotal, setDownloadTotal] = useState(0)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [downloadError, setDownloadError] = useState('')

  const [serviceCategory, setServiceCategory] = useState('')
  const [userRole, setUserRole] = useState('')
  const [serviceItems, setServiceItems] = useState([])
  const [contacts, setContacts] = useState([])
  const [serviceLoading, setServiceLoading] = useState(false)
  const [serviceError, setServiceError] = useState('')

  function scrollToBrowse(tab) {
    if (tab) setActiveTab(tab)
    requestAnimationFrame(() => {
      browseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  async function loadDownloads(nextKeyword = keyword, nextCategory = downloadCategory) {
    setDownloadLoading(true)
    setDownloadError('')
    try {
      const resp = await axios.get('/api/resources/downloads', {
        params: { keyword: nextKeyword, category: nextCategory, top_k: 50 },
      })
      const data = resp.data || {}
      setDownloadItems(data.items || [])
      setDownloadTotal(data.total || 0)
      setDownloadCategoriesState(downloadCategories(data))
    } catch {
      setDownloadItems([])
      setDownloadTotal(0)
      setDownloadCategoriesState([])
      setDownloadError('暂时无法连接资料库，请稍后再试。')
    } finally {
      setDownloadLoading(false)
    }
  }

  async function loadServices(nextCategory = serviceCategory, nextRole = userRole) {
    setServiceLoading(true)
    setServiceError('')
    try {
      const [serviceResp, contactResp] = await Promise.all([
        axios.get('/api/resources/service-links', {
          params: { category: nextCategory, user_role: nextRole, top_k: 50 },
        }),
        axios.get('/api/resources/contacts', {
          params: { department: nextCategory, top_k: 8 },
        }),
      ])
      setServiceItems(serviceResp.data.items || [])
      setContacts(contactResp.data.items || [])
    } catch {
      setServiceItems([])
      setContacts([])
      setServiceError('暂时无法连接服务目录，请稍后再试。')
    } finally {
      setServiceLoading(false)
    }
  }

  function selectRole(value) {
    setUserRole(value)
    loadServices(serviceCategory, value)
  }

  function openScenario(category, prompt) {
    setActiveTab('services')
    setServiceCategory(category)
    loadServices(category, userRole)
    askAndOpen(STORE_KEY, prompt)
  }

  useEffect(() => {
    loadDownloads()
    loadServices()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="container agent-page">
      <section className="agent-page-hero agent-page-hero--library">
        <div className="agent-page-hero-copy">
          <div className="eyebrow">AGENT LIBRARY</div>
          <h1>办事资料智库</h1>
          <p>
            找资料、找入口、查联系方式，一站完成校园办事检索，
            并始终核对官网来源。
          </p>
          <div className="agent-hero-cta-row">
            <button
              className="btn-primary agent-hero-cta"
              onClick={() => scrollToBrowse('downloads')}
            >
              <Search size={17} /> 搜索资料
            </button>
            <button
              className="btn-secondary agent-hero-cta"
              onClick={() => scrollToBrowse('services')}
            >
              <MapPinned size={17} /> 浏览服务
            </button>
          </div>
        </div>
        <div className="agent-page-hero-mark" aria-hidden="true">
          <FileSearch size={112} strokeWidth={1.05} />
          <span>资料 · 入口 · 联系</span>
        </div>
      </section>

      <section className="agent-subsection">
        <div className="agent-section-title">
          <div>
            <div className="eyebrow">WORKFLOWS</div>
            <h2>你能做什么？</h2>
          </div>
          <p>从办事目标出发，资料与服务入口一起找。</p>
        </div>
        <div className="agent-capability-grid">
          {QUICK_TASKS.map(({ Icon, title, desc, prompt }) => (
            <button
              key={title}
              className="agent-capability-card"
              onClick={() => askAndOpen(STORE_KEY, prompt)}
            >
              <span className="agent-capability-icon"><Icon size={24} /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
              <span className="agent-card-action">开始对话 <ArrowUpRight size={15} /></span>
            </button>
          ))}
        </div>
      </section>

      <section className="agent-subsection" ref={browseRef}>
        <div className="agent-browse-tabs" role="tablist" aria-label="资料、服务与就业">
          <button
            role="tab"
            aria-selected={activeTab === 'downloads'}
            className={activeTab === 'downloads' ? 'active' : ''}
            onClick={() => setActiveTab('downloads')}
          >
            <Download size={16} /> 资料下载
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'services'}
            className={activeTab === 'services' ? 'active' : ''}
            onClick={() => setActiveTab('services')}
          >
            <MapPinned size={16} /> 服务入口
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'employment'}
            className={activeTab === 'employment' ? 'active' : ''}
            onClick={() => setActiveTab('employment')}
          >
            <BriefcaseBusiness size={16} /> 就业信息
          </button>
        </div>

        {activeTab === 'downloads' ? (
          <>
            <div className="agent-search-panel">
              <div className="agent-search-heading">
                <div>
                  <div className="eyebrow">OFFICIAL RESOURCES</div>
                  <h2>官方资料检索</h2>
                </div>
                <span>{downloadLoading ? '正在检索…' : `已找到 ${downloadTotal} 条资料`}</span>
              </div>
              <div className="agent-search-row">
                <div className="agent-search-input-wrap">
                  <Search size={19} />
                  <input
                    placeholder="输入事项或资料名，如：缓考、学生证、培养方案"
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && loadDownloads()}
                  />
                </div>
                <button className="btn-primary" onClick={() => loadDownloads()} disabled={downloadLoading}>
                  {downloadLoading ? '检索中' : '搜索资料'}
                </button>
              </div>
              <div className="agent-filter-chips">
                <button
                  className={!downloadCategory ? 'active' : ''}
                  onClick={() => { setDownloadCategory(''); loadDownloads(keyword, '') }}
                >
                  全部
                </button>
                {downloadCategoriesState.map((item) => (
                  <button
                    key={item}
                    className={downloadCategory === item ? 'active' : ''}
                    onClick={() => { setDownloadCategory(item); loadDownloads(keyword, item) }}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            <div className="resource-result-grid">
              {downloadItems.length === 0 ? (
                <div className="agent-empty-state">
                  <FileSearch size={34} strokeWidth={1.4} />
                  <h3>{downloadError || '当前条件下暂未找到资料'}</h3>
                  <p>换个关键词试试，或尝试不同的分类筛选。</p>
                </div>
              ) : (
                downloadItems.map((item, i) => (
                  <article key={`${item.title}-${i}`} className="resource-result-card">
                    <div className="resource-file-mark">
                      <FileText size={22} />
                      <span>{item.file_type?.toUpperCase() || 'FILE'}</span>
                    </div>
                    <div className="resource-result-body">
                      <h3>{item.title}</h3>
                      <div className="resource-result-meta">
                        {item.department && <span>{item.department}</span>}
                        {item.category && <span>{item.category}</span>}
                        {item.publish_date && <span>{item.publish_date}</span>}
                      </div>
                      {item.source_page_url && (
                        <LinkPreview url={item.source_page_url} />
                      )}
                      <div className="resource-result-actions">
                        {item.file_url && (
                          <a href={item.file_url} target="_blank" rel="noreferrer">
                            <Download size={14} /> 下载附件
                          </a>
                        )}
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          </>
        ) : activeTab === 'services' ? (
          <>
            <div className="agent-section-title" style={{ marginBottom: 20 }}>
              <div>
                <div className="eyebrow">FOR YOU</div>
                <h2>先告诉我你的身份</h2>
              </div>
              <p>据此调整推荐的服务入口与展示。</p>
            </div>
            <div className="role-filter-row">
              {ROLES.map(({ label, value, Icon }) => (
                <button
                  key={label}
                  className={userRole === value ? 'active' : ''}
                  onClick={() => selectRole(value)}
                >
                  <Icon size={18} strokeWidth={1.8} />
                  {label}
                </button>
              ))}
            </div>

            <div className="service-scenario-grid" style={{ marginBottom: 28 }}>
              {SCENARIOS.map(({ Icon, title, desc, category, prompt }) => (
                <article key={title} className="service-scenario-card">
                  <span className="agent-capability-icon"><Icon size={24} /></span>
                  <h3>{title}</h3>
                  <p>{desc}</p>
                  <div className="service-scenario-actions">
                    <button onClick={() => openScenario(category, prompt)}>
                      开始对话 <ArrowUpRight size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>

            <div className="agent-search-panel">
              <div className="agent-search-heading">
                <div>
                  <div className="eyebrow">SERVICE DIRECTORY</div>
                  <h2>官方服务目录</h2>
                </div>
                <span>
                  {serviceLoading
                    ? '正在查询…'
                    : `${serviceItems.length} 个入口 · ${contacts.length} 条联系信息`}
                </span>
              </div>
              <div className="service-directory-controls">
                <div className="agent-search-input-wrap">
                  <Search size={19} />
                  <select
                    value={serviceCategory}
                    onChange={(e) => setServiceCategory(e.target.value)}
                  >
                    <option value="">全部服务分类</option>
                    {SERVICE_CATEGORIES.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                </div>
                <button
                  className="btn-primary"
                  onClick={() => loadServices()}
                  disabled={serviceLoading}
                >
                  {serviceLoading ? '查询中' : '查询目录'}
                </button>
              </div>
            </div>

            {serviceError && (
              <div className="agent-empty-state compact">
                <MapPinned size={30} />
                <h3>{serviceError}</h3>
                <button
                  className="btn-secondary"
                  onClick={() => { setServiceCategory(''); loadServices('', userRole) }}
                >
                  换个分类试试
                </button>
              </div>
            )}

            {!serviceError && (
              <div className="service-result-layout">
                <div>
                  <h3 className="service-result-label">服务入口</h3>
                  <div className="service-link-grid">
                    {serviceItems.length === 0 ? (
                      <div className="service-list-empty">当前分类暂无入口数据，换个分类试试</div>
                    ) : serviceItems.map((item, i) => (
                      <a
                        key={`${item.name}-${i}`}
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="service-link-card"
                      >
                        <div>
                          <span>{item.category || serviceCategory || '校园服务'}</span>
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
          </>
        ) : (
          <EmploymentBrowser />
        )}
      </section>

      <EmbeddedChat
        title="资料智库助手"
        contextHint="资料智库"
        suggestions={CHAT_SUGGESTIONS}
        allowKnowledgeScope
      />
    </div>
  )
}
