import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../authStore.js'

export default function RegisterPage() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    username: '',
    email: '',
    display_name: '',
    password: '',
    password2: '',
    role: 'student',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function update(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (!form.username.trim()) {
      setError('请填写用户名')
      return
    }
    if (form.password.length < 6) {
      setError('密码至少 6 位')
      return
    }
    if (form.password !== form.password2) {
      setError('两次输入的密码不一致')
      return
    }
    setLoading(true)
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim() || undefined,
        display_name: form.display_name.trim() || undefined,
        password: form.password,
        role: form.role,
      })
      navigate('/', { replace: true })
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (Array.isArray(detail)) {
        setError(detail.map((d) => d.msg || JSON.stringify(d)).join('；'))
      } else {
        setError('注册失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <p className="eyebrow">账号</p>
        <h1 className="auth-title">注册</h1>
        <p className="auth-sub">创建账号，开始使用仲恺校园信息服务智能体。</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label">
            用户名
            <input
              className="auth-input"
              type="text"
              autoComplete="username"
              value={form.username}
              onChange={update('username')}
              placeholder="2–32 位，中英文/数字/下划线"
              disabled={loading}
              required
            />
          </label>
          <label className="auth-label">
            显示名称（可选）
            <input
              className="auth-input"
              type="text"
              value={form.display_name}
              onChange={update('display_name')}
              placeholder="默认与用户名相同"
              disabled={loading}
            />
          </label>
          <label className="auth-label">
            邮箱（可选）
            <input
              className="auth-input"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={update('email')}
              placeholder="可用于登录"
              disabled={loading}
            />
          </label>
          <label className="auth-label">
            身份
            <select
              className="auth-input"
              value={form.role}
              onChange={update('role')}
              disabled={loading}
            >
              <option value="student">学生</option>
              <option value="teacher">教师</option>
            </select>
          </label>
          <label className="auth-label">
            密码
            <input
              className="auth-input"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={update('password')}
              placeholder="至少 6 位"
              disabled={loading}
              required
            />
          </label>
          <label className="auth-label">
            确认密码
            <input
              className="auth-input"
              type="password"
              autoComplete="new-password"
              value={form.password2}
              onChange={update('password2')}
              placeholder="再次输入密码"
              disabled={loading}
              required
            />
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="btn-primary auth-submit" type="submit" disabled={loading}>
            {loading ? '注册中…' : '注册并登录'}
          </button>
        </form>

        <p className="auth-switch">
          已有账号？<Link to="/login">去登录</Link>
        </p>
      </div>
    </div>
  )
}
