/**
 * 用户鉴权状态：token / user 持久化到 localStorage。
 * 使用 useSyncExternalStore 订阅，与 chatStore 模式一致。
 */
import axios from 'axios'

const TOKEN_KEY = 'zhku_auth_token'
const USER_KEY = 'zhku_auth_user'

let state = {
  token: null,
  user: null,
  ready: false,
}

const listeners = new Set()

function emit() {
  listeners.forEach((fn) => fn())
}

function persist() {
  try {
    if (state.token) localStorage.setItem(TOKEN_KEY, state.token)
    else localStorage.removeItem(TOKEN_KEY)
    if (state.user) localStorage.setItem(USER_KEY, JSON.stringify(state.user))
    else localStorage.removeItem(USER_KEY)
  } catch {
    // ignore quota / private mode
  }
}

function loadFromStorage() {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const raw = localStorage.getItem(USER_KEY)
    const user = raw ? JSON.parse(raw) : null
    state = { token: token || null, user, ready: true }
  } catch {
    state = { token: null, user: null, ready: true }
  }
  emit()
}

loadFromStorage()

export function getAuthSnapshot() {
  return state
}

export function subscribeAuth(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getAuthHeader() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {}
}

function setSession(token, user) {
  state = { token, user, ready: true }
  persist()
  emit()
}

export function logout() {
  setSession(null, null)
}

export async function login(username, password) {
  const resp = await axios.post('/api/auth/login', { username, password })
  const { access_token, user } = resp.data
  setSession(access_token, user)
  return user
}

export async function register(payload) {
  const resp = await axios.post('/api/auth/register', payload)
  const { access_token, user } = resp.data
  setSession(access_token, user)
  return user
}

/** 用当前 token 刷新用户信息；失败则登出。 */
export async function refreshMe() {
  if (!state.token) {
    state = { ...state, ready: true }
    emit()
    return null
  }
  try {
    const resp = await axios.get('/api/auth/me', {
      headers: getAuthHeader(),
    })
    state = { ...state, user: resp.data, ready: true }
    persist()
    emit()
    return resp.data
  } catch {
    logout()
    return null
  }
}
