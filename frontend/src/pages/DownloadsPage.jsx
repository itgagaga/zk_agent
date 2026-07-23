import { useEffect, useState } from 'react'
import axios from 'axios'

export default function DownloadsPage() {
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)

  async function load() {
    const resp = await axios.get('/api/resources/downloads', {
      params: { keyword, category, top_k: 50 },
    })
    setItems(resp.data.items || [])
    setTotal(resp.data.total || 0)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="container section">
      <div className="eyebrow">DOWNLOADS</div>
      <h2 style={{ marginTop: 16, marginBottom: 32 }}>资料下载中心</h2>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <input
          className="chat-input"
          placeholder="搜索关键词，如：缓考 / 学生证 / 培养方案"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && load()}
        />
        <select
          className="chat-input"
          style={{ width: 200 }}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">全部分类</option>
          <option value="学生下载">学生下载</option>
          <option value="学籍学位">学籍学位</option>
          <option value="考务">考务</option>
          <option value="培养方案">培养方案</option>
          <option value="研究生培养">研究生培养</option>
          <option value="研究生招生">研究生招生</option>
        </select>
        <button className="btn-primary" onClick={load}>
          搜索
        </button>
      </div>

      <div style={{ color: 'var(--color-slate)', marginBottom: 16 }}>
        共 {total} 条结果
      </div>

      <div>
        {items.length === 0 ? (
          <div className="chat-bubble" style={{ color: 'var(--color-slate)' }}>
            暂无资料。数据由 crawler 模块采集后填充。
          </div>
        ) : (
          items.map((item, i) => (
            <div key={i} className="source-card">
              <div className="source-title">{item.title}</div>
              <div className="source-meta">
                {item.department && <span>{item.department} · </span>}
                {item.category && <span>{item.category} · </span>}
                {item.file_type && <span>{item.file_type.toUpperCase()}</span>}
              </div>
              {item.file_url && (
                <a
                  href={item.file_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-secondary"
                  style={{ marginTop: 12, display: 'inline-block' }}
                >
                  下载文件 ↗
                </a>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
