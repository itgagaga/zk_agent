import { useEffect, useState } from 'react'
import axios from 'axios'

export default function ServicesPage() {
  const [category, setCategory] = useState('')
  const [userRole, setUserRole] = useState('')
  const [items, setItems] = useState([])

  async function load() {
    const resp = await axios.get('/api/resources/service-links', {
      params: { category, user_role: userRole, top_k: 50 },
    })
    setItems(resp.data.items || [])
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="container section">
      <div className="eyebrow">SERVICES</div>
      <h2 style={{ marginTop: 16, marginBottom: 32 }}>服务入口导航</h2>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <select
          className="chat-input"
          style={{ width: 200 }}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">全部分类</option>
          <option value="教务">教务</option>
          <option value="科研">科研</option>
          <option value="行政">行政</option>
          <option value="后勤">后勤</option>
          <option value="网络">网络</option>
          <option value="医疗">医疗</option>
          <option value="招采">招采</option>
          <option value="就业">就业</option>
        </select>
        <select
          className="chat-input"
          style={{ width: 200 }}
          value={userRole}
          onChange={(e) => setUserRole(e.target.value)}
        >
          <option value="">所有角色</option>
          <option value="学生">学生</option>
          <option value="教师">教师</option>
          <option value="研究生">研究生</option>
          <option value="访客">访客</option>
        </select>
        <button className="btn-primary" onClick={load}>
          查询
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 16,
        }}
      >
        {items.length === 0 ? (
          <div className="chat-bubble" style={{ color: 'var(--color-slate)' }}>
            暂无服务入口数据。数据由 crawler 模块采集官网公共服务栏目后填充。
          </div>
        ) : (
          items.map((item, i) => (
            <a
              key={i}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="source-card"
              style={{ textDecoration: 'none', display: 'block' }}
            >
              <div className="source-title">{item.name}</div>
              <div className="source-meta">
                {item.category && <span>{item.category} · </span>}
                {item.user_role && <span>{item.user_role}</span>}
                {item.requires_login && <span> · 需登录</span>}
              </div>
              {item.description && (
                <div style={{ marginTop: 8, fontSize: 13, color: 'var(--color-granite)' }}>
                  {item.description}
                </div>
              )}
            </a>
          ))
        )}
      </div>
    </div>
  )
}
