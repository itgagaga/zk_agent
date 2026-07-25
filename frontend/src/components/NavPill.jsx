import { Link, NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: '首页' },
  { to: '/chat', label: '智能问答' },
  { to: '/downloads', label: '资料智库' },
  { to: '/services', label: '办事助手' },
  { to: '/documents', label: '智能文档' },
  { to: '/resume', label: '简历生成' },
]

export default function NavPill() {
  return (
    <nav className="nav-pill">
      <Link to="/" style={{ fontWeight: 700 }}>
        ZHKU Agent
      </Link>
      <div style={{ display: 'flex', gap: 32 }}>
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            style={({ isActive }) => ({
              textDecoration: isActive ? 'underline' : 'none',
              textUnderlineOffset: 6,
            })}
          >
            {l.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
