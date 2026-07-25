import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import {
  ArrowUpRight,
  ClipboardCheck,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  ListChecks,
  Search,
} from 'lucide-react'
import EmbeddedChat from '../components/EmbeddedChat'

const CHAT_SUGGESTIONS = [
  '帮我查找缓考申请表',
  '补办学生证需要什么材料？',
  '培养方案在哪下载？',
  '研究生学位申请流程',
]

const QUICK_TASKS = [
  {
    Icon: FileSearch,
    title: '帮我找资料',
    desc: '输入事项或关键词，快速定位官方表格、附件和下载入口。',
  },
  {
    Icon: ListChecks,
    title: '生成材料清单',
    desc: '根据公开办事指南，整理办理前需要准备的材料。',
  },
  {
    Icon: ClipboardCheck,
    title: '梳理办理步骤',
    desc: '把分散的通知和附件整理成清晰、可执行的步骤。',
  },
  {
    Icon: FileText,
    title: '解读文件内容',
    desc: '找到文件后，可进入智能文档继续摘要、问答与对比。',
  },
]

const CATEGORIES = ['学生下载', '学籍学位', '考务', '培养方案', '研究生培养', '研究生招生']

function extractDomain(url) {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function LinkPreview({ url }) {
  const domain = extractDomain(url)
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

export default function DownloadsPage() {
  const searchRef = useRef(null)
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function scrollToSearch() {
    searchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function load(nextKeyword = keyword, nextCategory = category) {
    setLoading(true)
    setError('')
    try {
      const resp = await axios.get('/api/resources/downloads', {
        params: { keyword: nextKeyword, category: nextCategory, top_k: 50 },
      })
      setItems(resp.data.items || [])
      setTotal(resp.data.total || 0)
    } catch {
      setItems([])
      setTotal(0)
      setError('暂时无法连接资料库，请稍后再试。')
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
      <section className="agent-page-hero agent-page-hero--library">
        <div className="agent-page-hero-copy">
          <div className="eyebrow">AGENT LIBRARY</div>
          <h1>办事资料智库</h1>
          <p>
            快速定位资料、核对来源、整理材料，
            再把复杂文件交给智能文档继续解读。
          </p>
          <button
            className="btn-primary agent-hero-cta"
            onClick={scrollToSearch}
          >
            <Search size={17} /> 搜索资料
          </button>
        </div>
        <div className="agent-page-hero-mark" aria-hidden="true">
          <FileSearch size={112} strokeWidth={1.05} />
          <span>检索 · 核验 · 整理</span>
        </div>
      </section>

      <section className="agent-subsection">
        <div className="agent-section-title">
          <div>
            <div className="eyebrow">WORKFLOWS</div>
            <h2>你能做什么？</h2>
          </div>
          <p>从目标出发，而不是从文件名开始。</p>
        </div>
        <div className="agent-capability-grid">
          {QUICK_TASKS.map(({ Icon, title, desc }) => (
            <button
              key={title}
              className="agent-capability-card"
              onClick={scrollToSearch}
            >
              <span className="agent-capability-icon"><Icon size={24} /></span>
              <h3>{title}</h3>
              <p>{desc}</p>
              <span className="agent-card-action">开始搜索 <ArrowUpRight size={15} /></span>
            </button>
          ))}
        </div>
      </section>

      <section className="agent-subsection" ref={searchRef}>
        <div className="agent-search-panel">
          <div className="agent-search-heading">
            <div>
              <div className="eyebrow">OFFICIAL RESOURCES</div>
              <h2>官方资料检索</h2>
            </div>
            <span>{loading ? '正在检索…' : `已找到 ${total} 条资料`}</span>
          </div>
          <div className="agent-search-row">
            <div className="agent-search-input-wrap">
              <Search size={19} />
              <input
                placeholder="输入事项或资料名，如：缓考、学生证、培养方案"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && load()}
              />
            </div>
            <button className="btn-primary" onClick={() => load()} disabled={loading}>
              {loading ? '检索中' : '搜索资料'}
            </button>
          </div>
          <div className="agent-filter-chips">
            <button
              className={!category ? 'active' : ''}
              onClick={() => { setCategory(''); load(keyword, '') }}
            >
              全部
            </button>
            {CATEGORIES.map((item) => (
              <button
                key={item}
                className={category === item ? 'active' : ''}
                onClick={() => { setCategory(item); load(keyword, item) }}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="resource-result-grid">
          {items.length === 0 ? (
            <div className="agent-empty-state">
              <FileSearch size={34} strokeWidth={1.4} />
              <h3>{error || '当前条件下暂未找到资料'}</h3>
              <p>换个关键词试试，或尝试不同的分类筛选。</p>
            </div>
          ) : (
            items.map((item, i) => (
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
      </section>

      <EmbeddedChat
        title="资料智库助手"
        contextHint="资料智库"
        suggestions={CHAT_SUGGESTIONS}
      />
    </div>
  )
}
