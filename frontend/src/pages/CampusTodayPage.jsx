import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import {
  CalendarDays,
  Cloud,
  CloudRain,
  CloudSun,
  Droplets,
  MapPin,
  RefreshCw,
  Sparkles,
  Sun,
  Thermometer,
  Upload,
  Wind,
} from 'lucide-react'
import campusGarden from '../assets/campus/garden.webp'
import campusLibrary from '../assets/campus/library.webp'
import campusNight from '../assets/campus/night.webp'
import WeekScheduleGrid from '../components/WeekScheduleGrid.jsx'
import CampusNavigate from '../components/CampusNavigate.jsx'
import { getColorIndex, getCourseStyle } from '../utils/scheduleColors.js'
import { getAuthHeader, getAuthSnapshot, subscribeAuth } from '../authStore.js'

const WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

function getCourseColorIndex(name, legendMap) {
  return getColorIndex(name, legendMap)
}

function WeatherIcon({ text, size = 48 }) {
  if (/雨|雷|雪/.test(text || '')) return <CloudRain size={size} strokeWidth={1.5} />
  if (/云|阴|雾/.test(text || '')) return <Cloud size={size} strokeWidth={1.5} />
  if (/晴/.test(text || '')) return <Sun size={size} strokeWidth={1.5} />
  return <CloudSun size={size} strokeWidth={1.5} />
}

function weatherMood(text) {
  if (/雨|雷/.test(text || '')) return 'rainy'
  if (/云|阴/.test(text || '')) return 'cloudy'
  if (/晴/.test(text || '')) return 'sunny'
  return 'default'
}

function formatDate() {
  const now = new Date()
  return now.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export default function CampusTodayPage() {
  const { user } = useSyncExternalStore(subscribeAuth, getAuthSnapshot)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshingAdvice, setRefreshingAdvice] = useState(false)

  const todayIndex = useMemo(() => {
    const d = new Date().getDay()
    return d === 0 ? 6 : d - 1
  }, [])

  const loadData = useCallback(async (refreshAdvice = false) => {
    if (refreshAdvice) setRefreshingAdvice(true)
    else setLoading(true)
    try {
      const params = refreshAdvice ? { refresh_advice: true } : {}
      const [todayResp] = await Promise.all([
        axios.get('/api/schedule/today', {
          params,
          headers: getAuthHeader(),
        }),
      ])
      setData(todayResp.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
      setRefreshingAdvice(false)
    }
  }, [user])

  useEffect(() => {
    loadData()
  }, [loadData])

  const weather = data?.weather
  const mood = weatherMood(weather?.text)
  const courses = data?.today_courses || []
  const legendMap = useMemo(() => {
    const map = {}
    for (const c of courses) {
      if (!map[c.name]) map[c.name] = getCourseColorIndex(c.name, {})
    }
    return map
  }, [courses])

  const adviceLines = (data?.advice || '')
    .split(/\n+/)
    .map((s) => s.replace(/^[\d\-•·\.]+\s*/, '').trim())
    .filter(Boolean)

  function timelineDotStyle(name) {
    const idx = getCourseColorIndex(name, legendMap)
    const style = getCourseStyle(idx)
    return { background: style['--course-border'] }
  }

  function timelineCardStyle(name) {
    const idx = getCourseColorIndex(name, legendMap)
    return getCourseStyle(idx)
  }

  return (
    <div className="campus-today-page">
      <div className="campus-today-bg" aria-hidden="true">
        <img src={campusGarden} alt="" className="campus-today-bg-img campus-today-bg-img--1" />
        <img src={campusLibrary} alt="" className="campus-today-bg-img campus-today-bg-img--2" />
        <div className="campus-today-bg-gradient" />
      </div>

      <div className="container campus-today-container">
        <header className="campus-today-header">
          <div className="eyebrow">CAMPUS TODAY</div>
          <h1>今日校园</h1>
          <p className="campus-today-lead">
            课表一览、实时天气与 AI 贴心建议，让每一天的校园生活更有条理。
          </p>
        </header>

        <div className="campus-today-hero-grid">
          {/* 天气卡片 */}
          <section className={`ct-weather-card ct-weather-card--${mood}`}>
            <div className="ct-weather-card-deco" aria-hidden="true">
              <img src={campusNight} alt="" />
            </div>
            <div className="ct-weather-card-body">
              <div className="ct-weather-top">
                <div>
                  <span className="ct-weather-date">{formatDate()}</span>
                  <h2>{data?.weekday || WEEKDAYS[todayIndex]}</h2>
                  {data?.has_schedule && (
                    <span className="ct-week-badge">第 {data.current_week} 教学周</span>
                  )}
                </div>
                <div className="ct-weather-icon-wrap">
                  <WeatherIcon text={weather?.text} size={52} />
                </div>
              </div>

              {weather?.error ? (
                <p className="ct-weather-error">{weather.error}</p>
              ) : weather ? (
                <>
                  <div className="ct-weather-main">
                    <span className="ct-temp">{weather.temp || '—'}</span>
                    <span className="ct-temp-unit">°C</span>
                    <span className="ct-weather-text">{weather.text || '广州'}</span>
                  </div>
                  <div className="ct-weather-stats">
                    <span>
                      <Thermometer size={15} /> 体感 {weather.feels_like || '—'}°C
                    </span>
                    <span>
                      <Wind size={15} /> {weather.wind_dir}
                      {weather.wind_scale}级
                    </span>
                    <span>
                      <Droplets size={15} /> 湿度 {weather.humidity || '—'}%
                    </span>
                  </div>
                  {weather.forecast?.length > 0 && (
                    <div className="ct-forecast-row">
                      {weather.forecast.slice(0, 3).map((d) => (
                        <div key={d.date} className="ct-forecast-item">
                          <span>{d.date?.slice(5)}</span>
                          <span>{d.text_day}</span>
                          <span>
                            {d.temp_min}~{d.temp_max}°
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="ct-weather-loading">{loading ? '加载天气…' : '暂无天气数据'}</p>
              )}
            </div>
          </section>

          {/* AI 建议 */}
          <section className="ct-advice-card">
            <div className="ct-advice-head">
              <Sparkles size={20} strokeWidth={1.8} />
              <h3>AI 今日建议</h3>
              <button
                type="button"
                className="ct-advice-refresh"
                disabled={refreshingAdvice || loading}
                onClick={() => loadData(true)}
                title="重新生成建议"
              >
                <RefreshCw size={16} className={refreshingAdvice ? 'is-spinning' : ''} />
              </button>
            </div>
            <div className="ct-advice-body">
              {loading && !data ? (
                <p className="ct-advice-loading">正在结合课表与天气生成建议…</p>
              ) : (
                <ul className="ct-advice-list">
                  {adviceLines.length > 0 ? (
                    adviceLines.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))
                  ) : (
                    <li>{data?.advice || '暂无建议'}</li>
                  )}
                </ul>
              )}
            </div>
            {!user && (
              <p className="ct-advice-hint">
                <Link to="/login">登录</Link> 并上传课表，可获得更个性化的建议。
              </p>
            )}
          </section>
        </div>

        {/* 去哪儿 */}
        <CampusNavigate weather={weather} />

        {/* 今日课程时间线 */}
        <section className="ct-section">
          <div className="ct-section-head">
            <CalendarDays size={22} strokeWidth={1.8} />
            <div>
              <h2>今日课程</h2>
              <p>
                {data?.has_schedule
                  ? courses.length > 0
                    ? `共 ${courses.length} 节课`
                    : '当前教学周今日无排课，Enjoy your free day!'
                  : '上传课表后此处将显示今日课程'}
              </p>
            </div>
            {!data?.has_schedule && (
              <Link to={user ? '/account/schedule' : '/login'} className="btn-primary ct-upload-cta">
                <Upload size={16} />
                {user ? '去上传课表' : '登录上传'}
              </Link>
            )}
          </div>

          {data?.has_schedule && courses.length > 0 ? (
            <div className="ct-timeline">
              {courses.map((c, i) => (
                <article key={`${c.name}-${c.start}-${i}`} className="ct-timeline-item">
                  <div className="ct-timeline-time">
                    <span>{c.start}</span>
                    <span className="ct-timeline-sep">—</span>
                    <span>{c.end}</span>
                  </div>
                  <div className="ct-timeline-dot" style={timelineDotStyle(c.name)} />
                  <div
                    className="ct-timeline-card"
                    style={{
                      borderLeftColor: timelineCardStyle(c.name)['--course-border'],
                      background: timelineCardStyle(c.name)['--course-bg'],
                    }}
                  >
                    <h4>{c.name}</h4>
                    <p className="ct-timeline-teacher">{c.teacher}</p>
                    <p className="ct-timeline-loc">
                      <MapPin size={14} />
                      {c.location || '地点待定'}
                      {c.is_online && <span className="ct-online-tag">网课</span>}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="ct-empty-day">
              <img src={campusLibrary} alt="校园图书馆" />
              <div>
                <h3>{data?.has_schedule ? '今日无课' : '尚未导入课表'}</h3>
                <p>
                  {data?.has_schedule
                    ? '可以好好利用这一天自习、运动，或探索校园角落。'
                    : '在个人中心上传教务系统导出的 Excel 课表，即可在此查看每日安排。'}
                </p>
              </div>
            </div>
          )}
        </section>

        {/* 课表视图：默认本周，可切换教学周 */}
        {data?.has_schedule && user && (
          <WeekScheduleGrid user={user} todayIndex={todayIndex} />
        )}
      </div>
    </div>
  )
}
