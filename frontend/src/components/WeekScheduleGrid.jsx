import { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react'
import { getAuthHeader } from '../authStore.js'
import { getColorIndex, getCourseStyle } from '../utils/scheduleColors.js'

const WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

const TIME_ROWS = [
  { key: '第一二节', label: '1–2 节', time: '08:00' },
  { key: '第三四节', label: '3–4 节', time: '10:00' },
  { key: '第五节', label: '5 节', time: '14:00' },
  { key: '第六七节', label: '6–7 节', time: '15:00' },
  { key: '第八九节', label: '8–9 节', time: '17:00' },
  { key: '第十十一十二节', label: '10–12 节', time: '19:00' },
]

function CourseBlock({ course, legendMap, showDetail = true }) {
  const colorIndex = getColorIndex(course.name, legendMap)
  return (
    <div
      className={`ct-course-block ct-course-block--c${colorIndex % 8}`}
      style={getCourseStyle(colorIndex)}
      title={`${course.name} · ${course.weeks ? `第${course.weeks}周` : ''}`}
    >
      <span className="ct-course-block-name">{course.name}</span>
      {showDetail && (
        <>
          {course.location && (
            <span className="ct-course-block-loc">{course.location}</span>
          )}
          <span className="ct-course-block-teacher">{course.teacher}</span>
          {course.is_online && <span className="ct-course-block-tag">网课</span>}
        </>
      )}
    </div>
  )
}

export default function WeekScheduleGrid({ user, todayIndex }) {
  const [gridData, setGridData] = useState(null)
  const [selectedWeek, setSelectedWeek] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadWeek = useCallback(
    async (week) => {
      if (!user) return
      setLoading(true)
      try {
        const params = week != null ? { week } : {}
        const resp = await axios.get('/api/schedule/week', {
          params,
          headers: getAuthHeader(),
        })
        if (resp.data?.ok) {
          setGridData(resp.data)
          setSelectedWeek(resp.data.selected_week)
        }
      } catch {
        setGridData(null)
      } finally {
        setLoading(false)
      }
    },
    [user]
  )

  useEffect(() => {
    loadWeek()
  }, [loadWeek])

  const gridMap = useMemo(() => {
    const map = {}
    if (!gridData?.grid) return map
    for (const row of gridData.grid) {
      map[row.time_slot] = row.days || {}
    }
    return map
  }, [gridData])

  if (!user) return null
  if (!gridData && loading) {
    return <p className="ct-schedule-loading">加载课表中…</p>
  }
  if (!gridData) return null

  const {
    current_week: currentWeek,
    min_week: minWeek,
    max_week: maxWeek,
    legend = [],
    legend_map: legendMap = {},
    day_dates: dayDates = {},
    course_count: courseCount = 0,
    unique_course_count: uniqueCount = 0,
    is_current_week: isCurrentWeek,
    meta = {},
  } = gridData

  function goWeek(w) {
    const next = Math.max(minWeek, Math.min(maxWeek, w))
    loadWeek(next)
  }

  return (
    <section className="ct-section ct-schedule-section">
      <div className="ct-section-head ct-schedule-head">
        <div>
          <h2>课表视图</h2>
          {meta.semester && (
            <p>
              {meta.semester} · {meta.class_name} · {meta.major}
            </p>
          )}
        </div>
      </div>

      {/* 周次导航 — 参考 CourseKit dateRange / Timetablely 周切换 */}
      <div className="ct-week-nav">
        <button
          type="button"
          className="ct-week-nav-btn"
          disabled={selectedWeek <= minWeek || loading}
          onClick={() => goWeek(selectedWeek - 1)}
          aria-label="上一周"
        >
          <ChevronLeft size={18} />
          上一周
        </button>

        <div className="ct-week-nav-center">
          <label className="ct-week-select-label" htmlFor="ct-week-select">
            教学周
          </label>
          <select
            id="ct-week-select"
            className="ct-week-select"
            value={selectedWeek ?? currentWeek}
            disabled={loading}
            onChange={(e) => goWeek(Number(e.target.value))}
          >
            {Array.from({ length: maxWeek - minWeek + 1 }, (_, i) => minWeek + i).map((w) => (
              <option key={w} value={w}>
                第 {w} 周{w === currentWeek ? '（本周）' : ''}
              </option>
            ))}
          </select>
          <span className="ct-week-summary">
            {courseCount} 节课 · {uniqueCount} 门课
          </span>
        </div>

        <button
          type="button"
          className="ct-week-nav-btn"
          disabled={selectedWeek >= maxWeek || loading}
          onClick={() => goWeek(selectedWeek + 1)}
          aria-label="下一周"
        >
          下一周
          <ChevronRight size={18} />
        </button>

        {!isCurrentWeek && (
          <button
            type="button"
            className="ct-week-back-btn"
            disabled={loading}
            onClick={() => loadWeek(currentWeek)}
          >
            <RotateCcw size={15} />
            回到本周
          </button>
        )}
      </div>

      <div className={`ct-grid-wrap ${loading ? 'is-loading' : ''}`}>
        <table className="ct-grid">
          <thead>
            <tr>
              <th className="ct-grid-corner">节次</th>
              {WEEKDAYS.map((d, i) => (
                <th
                  key={d}
                  className={isCurrentWeek && i === todayIndex ? 'is-today' : ''}
                >
                  <span className="ct-grid-day-name">{d.replace('星期', '周')}</span>
                  {dayDates[d] && <span className="ct-grid-day-date">{dayDates[d]}</span>}
                  {isCurrentWeek && i === todayIndex && <span className="ct-today-dot" />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TIME_ROWS.map((row) => {
              const dayCourses = gridMap[row.key] || {}
              return (
                <tr key={row.key}>
                  <td className="ct-grid-time">
                    <span>{row.label}</span>
                    <small>{row.time}</small>
                  </td>
                  {WEEKDAYS.map((d, i) => {
                    const list = dayCourses[d] || []
                    const isToday = isCurrentWeek && i === todayIndex
                    return (
                      <td key={d} className={isToday ? 'is-today' : ''}>
                        {list.length > 0 ? (
                          list.map((c, j) => (
                            <CourseBlock
                              key={`${c.name}-${j}`}
                              course={c}
                              legendMap={legendMap}
                            />
                          ))
                        ) : (
                          <span className="ct-grid-empty" aria-hidden="true" />
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {courseCount === 0 && (
        <p className="ct-week-empty-hint">第 {selectedWeek} 教学周没有排课，可切换其他周查看。</p>
      )}

      {legend.length > 0 && (
        <div className="ct-legend">
          <span className="ct-legend-title">本周课程</span>
          <div className="ct-legend-items">
            {legend.map(({ name, color_index: idx }) => (
              <span
                key={name}
                className={`ct-legend-chip ct-course-block--c${idx % 8}`}
                style={getCourseStyle(idx)}
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export { WEEKDAYS, TIME_ROWS }
