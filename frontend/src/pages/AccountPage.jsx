import { useEffect, useState, useSyncExternalStore } from 'react'
import { NavLink, Navigate, useParams } from 'react-router-dom'
import {
  BookOpen,
  Calendar,
  CalendarDays,
  CheckCircle2,
  FileUser,
  GraduationCap,
  Mail,
  User,
  UserCircle2,
} from 'lucide-react'
import {
  getAuthSnapshot,
  subscribeAuth,
  updateProfile,
} from '../authStore.js'
import PersonalKnowledgeBase from '../components/PersonalKnowledgeBase.jsx'
import PersonalResume from '../components/PersonalResume.jsx'
import PersonalSchedule from '../components/PersonalSchedule.jsx'

const ROLE_OPTIONS = [
  { value: 'student', label: '学生', Icon: GraduationCap, desc: '本科 / 研究生' },
  { value: 'teacher', label: '教师', Icon: User, desc: '教学与科研' },
]

const ACCOUNT_SECTIONS = ['knowledge', 'resume', 'schedule']

const NAV_ITEMS = [
  { id: 'profile', to: '/account', label: '个人资料', Icon: UserCircle2 },
  { id: 'knowledge', to: '/account/knowledge', label: '个人知识库', Icon: BookOpen },
  { id: 'resume', to: '/account/resume', label: '个人简历', Icon: FileUser },
  { id: 'schedule', to: '/account/schedule', label: '我的课表', Icon: CalendarDays },
]

function getInitials(user) {
  const name = (user.display_name || user.username || '?').trim()
  if (/[\u4e00-\u9fff]/.test(name)) return name.slice(0, 1)
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function formatJoinDate(iso) {
  if (!iso) return null
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return null
  }
}

export default function AccountPage() {
  const auth = useSyncExternalStore(subscribeAuth, getAuthSnapshot)
  const { user, ready } = auth
  const { section } = useParams()
  const tab = ACCOUNT_SECTIONS.includes(section) ? section : 'profile'

  const [form, setForm] = useState({
    display_name: '',
    email: '',
    role: 'student',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (user) {
      setForm({
        display_name: user.display_name || '',
        email: user.email || '',
        role: user.role || 'student',
      })
      setError('')
      setSaved(false)
    }
  }, [user])

  if (!ready) return null

  if (!user) {
    return <Navigate to="/login" replace state={{ from: `/account${section ? `/${section}` : ''}` }} />
  }

  if (section && !ACCOUNT_SECTIONS.includes(section)) {
    return <Navigate to="/account" replace />
  }

  const joinDate = formatJoinDate(user.created_at)
  const dirty =
    form.display_name !== (user.display_name || '') ||
    form.email !== (user.email || '') ||
    form.role !== (user.role || 'student')

  function update(field) {
    return (e) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
      setSaved(false)
    }
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateProfile({
        display_name: form.display_name.trim() || undefined,
        email: form.email.trim() || undefined,
        role: form.role,
      })
      setSaved(true)
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg || JSON.stringify(d)).join('；'))
      } else {
        setError('保存失败，请稍后重试')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="account-page">
      <div className="container">
        <header className="account-page-header">
          <div className="eyebrow">MY ACCOUNT</div>
          <h1>个人中心</h1>
          <p className="account-page-lead">
            管理个人资料、私有知识库与个人简历，定制你的校园智能体体验。
          </p>

          <div className="account-user-badge">
            <span className="account-avatar-sm" aria-hidden="true">
              {getInitials(user)}
            </span>
            <span className="account-user-badge-name">{user.display_name || user.username}</span>
            <span className="account-user-badge-meta">
              @{user.username}
              {joinDate && (
                <span className="account-user-badge-join">
                  · <Calendar size={13} strokeWidth={2} /> {joinDate}
                </span>
              )}
            </span>
          </div>

          <nav className="account-tabs" aria-label="个人中心导航">
            {NAV_ITEMS.map(({ id, to, label, Icon }) => (
              <NavLink
                key={id}
                to={to}
                end={id === 'profile'}
                className={({ isActive }) => `account-tab ${isActive ? 'active' : ''}`}
              >
                <Icon size={17} strokeWidth={1.8} />
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        <div className="account-content">
          {tab === 'profile' ? (
            <form className="user-profile-form" onSubmit={handleSaveProfile}>
              <section className="user-profile-section">
                <div className="user-profile-section-head">
                  <UserCircle2 size={18} strokeWidth={1.8} />
                  <div>
                    <h4>基本信息</h4>
                    <p>这些信息会显示在导航栏与你的对话体验中</p>
                  </div>
                </div>
                <div className="user-profile-grid">
                  <label className="user-field">
                    <span className="user-field-label">显示名称</span>
                    <input
                      className="user-field-input"
                      type="text"
                      value={form.display_name}
                      onChange={update('display_name')}
                      placeholder="在界面中展示的名字"
                      disabled={saving}
                      maxLength={64}
                    />
                  </label>
                  <label className="user-field user-field--full">
                    <span className="user-field-label">身份角色</span>
                    <div className="user-role-picker">
                      {ROLE_OPTIONS.map(({ value, label, Icon, desc }) => (
                        <button
                          key={value}
                          type="button"
                          className={`user-role-option ${form.role === value ? 'is-active' : ''}`}
                          onClick={() => {
                            setForm((prev) => ({ ...prev, role: value }))
                            setSaved(false)
                          }}
                          disabled={saving}
                        >
                          <Icon size={18} strokeWidth={1.8} />
                          <span className="user-role-option-label">{label}</span>
                          <span className="user-role-option-desc">{desc}</span>
                        </button>
                      ))}
                    </div>
                  </label>
                </div>
              </section>

              <section className="user-profile-section">
                <div className="user-profile-section-head">
                  <Mail size={18} strokeWidth={1.8} />
                  <div>
                    <h4>账号与安全</h4>
                    <p>用户名不可修改；邮箱可用于登录与找回</p>
                  </div>
                </div>
                <div className="user-profile-grid">
                  <label className="user-field">
                    <span className="user-field-label">用户名</span>
                    <input
                      className="user-field-input is-readonly"
                      type="text"
                      value={user.username}
                      disabled
                      readOnly
                    />
                  </label>
                  <label className="user-field">
                    <span className="user-field-label">邮箱</span>
                    <input
                      className="user-field-input"
                      type="email"
                      value={form.email}
                      onChange={update('email')}
                      placeholder="可选，可用于登录"
                      disabled={saving}
                    />
                  </label>
                </div>
              </section>

              <div className="user-profile-actions">
                <div className="user-profile-feedback">
                  {error && <div className="auth-error">{error}</div>}
                  {saved && !error && (
                    <div className="user-profile-saved">
                      <CheckCircle2 size={16} strokeWidth={2} />
                      资料已保存
                    </div>
                  )}
                  {!error && !saved && dirty && (
                    <span className="user-profile-dirty">有未保存的更改</span>
                  )}
                </div>
                <button
                  type="submit"
                  className="btn-primary user-profile-save"
                  disabled={saving || !dirty}
                >
                  {saving ? '保存中…' : '保存资料'}
                </button>
              </div>
            </form>
          ) : tab === 'knowledge' ? (
            <PersonalKnowledgeBase />
          ) : tab === 'schedule' ? (
            <PersonalSchedule />
          ) : (
            <PersonalResume />
          )}
        </div>
      </div>
    </div>
  )
}
