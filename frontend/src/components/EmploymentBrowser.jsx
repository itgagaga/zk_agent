import { useEffect, useState } from 'react'
import axios from 'axios'
import { BriefcaseBusiness, ExternalLink, Search } from 'lucide-react'
import { jobQuery } from '../resourceViewModel'

export default function EmploymentBrowser() {
  const [kind, setKind] = useState('posting')
  const [keyword, setKeyword] = useState('')
  const [company, setCompany] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function load(nextKind = kind) {
    setLoading(true)
    setError('')
    try {
      const response = await axios.get('/api/resources/jobs', {
        params: jobQuery(nextKind, keyword, company, 50),
      })
      setItems(response.data?.items || [])
      setTotal(response.data?.total || 0)
    } catch {
      setItems([])
      setTotal(0)
      setError('就业数据暂时无法读取，请稍后再试。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load('posting')
  }, [])

  function selectKind(nextKind) {
    setKind(nextKind)
    load(nextKind)
  }

  function submitSearch() {
    load()
  }

  return (
    <div className="employment-browser">
      <div className="agent-search-heading">
        <div>
          <div className="eyebrow">CAREER</div>
          <h2>就业信息</h2>
        </div>
        <span>{loading ? '正在检索…' : `已找到 ${total} 条信息`}</span>
      </div>

      <div className="agent-filter-chips">
        <button
          className={kind === 'posting' ? 'active' : ''}
          onClick={() => selectKind('posting')}
        >
          公开职位
        </button>
        <button
          className={kind === 'fair' ? 'active' : ''}
          onClick={() => selectKind('fair')}
        >
          招聘活动
        </button>
      </div>

      <div className="employment-search-row">
        <label className="employment-search-input">
          <Search size={17} />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && submitSearch()}
            placeholder="职位、活动或行业"
          />
        </label>
        <input
          className="employment-company-input"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && submitSearch()}
          placeholder="公司名称"
        />
        <button className="btn-primary" onClick={submitSearch} disabled={loading}>
          {loading ? '检索中' : '搜索'}
        </button>
      </div>

      {error ? (
        <div className="agent-empty-state">
          <h3>{error}</h3>
        </div>
      ) : items.length === 0 ? (
        <div className="agent-empty-state">
          <BriefcaseBusiness size={34} />
          <h3>当前条件下暂无就业信息</h3>
        </div>
      ) : (
        <div className="resource-result-grid">
          {items.map((item) => (
            <article className="resource-result-card" key={`${item.kind}-${item.id}`}>
              <div className="resource-result-body">
                <h3>{item.title}</h3>
                <div className="resource-result-meta">
                  {item.company && <span>{item.company}</span>}
                  {(item.published || item.time) && (
                    <span>{item.published || item.time}</span>
                  )}
                  {item.location && <span>{item.location}</span>}
                  {item.salary && <span>{item.salary}</span>}
                  {item.education && <span>{item.education}</span>}
                </div>
                <div className="resource-result-actions">
                  <a href={item.url} target="_blank" rel="noreferrer">
                    查看官方详情 <ExternalLink size={14} />
                  </a>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
