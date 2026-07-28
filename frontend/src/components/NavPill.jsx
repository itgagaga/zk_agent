import { Link, NavLink } from 'react-router-dom'
import { useSyncExternalStore } from 'react'
import { getAuthSnapshot, subscribeAuth, logout } from '../authStore.js'

const links = [
  { to: '/', label: '首页' },
  { to: '/chat', label: '智能问答' },
  { to: '/downloads', label: '资料智库' },
  { to: '/documents', label: '智能文档' },
  { to: '/resume', label: '毕业季' },
]

export default function NavPill() {
  const { user } = useSyncExternalStore(subscribeAuth, getAuthSnapshot)

  return (
    <nav className="nav-pill">
      <Link to="/" style={{ fontWeight: 700 }}>
        ZHKU Agent
      </Link>
      <div style={{ display: 'flex', gap: 32, flex: 1 }}>
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
      <div className="nav-auth">
        {user ? (
          <>
            <span className="nav-user-name" title={user.username}>
              {user.display_name || user.username}
            </span>
            <button type="button" className="nav-auth-btn" onClick={() => logout()}>
              退出
            </button>
          </>
        ) : (
          <>
            <Link to="/login" className="nav-auth-link">
              登录
            </Link>
            <Link to="/register" className="btn-primary nav-auth-cta">
              注册
            </Link>
          </>
        )}
      </div>
    </nav>
  )
}
