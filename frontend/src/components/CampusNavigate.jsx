import { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import {
  Bus,
  Car,
  ChevronDown,
  ChevronUp,
  CloudRain,
  Footprints,
  Loader2,
  MapPin,
  Navigation,
  Sparkles,
  Bike,
} from 'lucide-react'

const MODE_ICONS = {
  transit: Bus,
  driving: Car,
  walking: Footprints,
  cycling: Bike,
}

function WeatherIconSmall({ text }) {
  if (/雨|雷|雪/.test(text || '')) return <CloudRain size={16} />
  return null
}

export default function CampusNavigate({ weather: pageWeather }) {
  const [locations, setLocations] = useState([])
  const [travelModes, setTravelModes] = useState({})
  const [origin, setOrigin] = useState('海珠校区')
  const [destination, setDestination] = useState('广州南站')
  const [travelMode, setTravelMode] = useState('transit')
  const [loading, setLoading] = useState(false)
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [expandedPlan, setExpandedPlan] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const resp = await axios.get('/api/schedule/navigate/locations')
        if (cancelled) return
        setLocations(resp.data.locations || [])
        setTravelModes(resp.data.travel_modes || {})
      } catch {
        if (!cancelled) {
          setLocations([
            { key: '海珠校区', label: '海珠校区', category: 'campus' },
            { key: '白云校区', label: '白云校区', category: 'campus' },
            { key: '广州南站', label: '广州南站', category: 'hub' },
            { key: '广州东站', label: '广州东站', category: 'hub' },
            { key: '白云机场', label: '白云机场', category: 'hub' },
          ])
          setTravelModes({
            transit: '公交/地铁',
            driving: '驾车',
            walking: '步行',
            cycling: '骑行',
          })
        }
      } finally {
        if (!cancelled) setLoadingMeta(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const campusOptions = useMemo(
    () => locations.filter((l) => l.category === 'campus'),
    [locations],
  )
  const hubOptions = useMemo(
    () => locations.filter((l) => l.category === 'hub'),
    [locations],
  )

  const handleSearch = useCallback(async () => {
    if (origin === destination) {
      setError('起点与终点不能相同')
      setResult(null)
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const resp = await axios.post('/api/schedule/navigate', {
        origin,
        destination,
        travel_mode: travelMode,
      })
      if (!resp.data.ok) {
        setError(resp.data.error || '路线规划失败')
        return
      }
      setResult(resp.data)
      setExpandedPlan(0)
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail || '请求失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [origin, destination, travelMode])

  const displayWeather = result?.weather || pageWeather
  const analysis = result?.analysis
  const hasRoutes = (result?.routes?.length || 0) > 0
  const hasSteps = (result?.steps?.length || 0) > 0

  return (
    <section className="ct-section ct-navigate-section">
      <div className="ct-section-head">
        <Navigation size={22} strokeWidth={1.8} />
        <div>
          <h2>去哪儿</h2>
          <p>选择起点与终点，结合实时天气为你推荐最佳出行方案</p>
        </div>
      </div>

      <div className="ct-navigate-card">
        <div className="ct-navigate-form">
          <div className="ct-navigate-field">
            <label htmlFor="nav-origin">
              <MapPin size={15} />
              我在哪
            </label>
            <select
              id="nav-origin"
              value={origin}
              disabled={loadingMeta || loading}
              onChange={(e) => setOrigin(e.target.value)}
            >
              <optgroup label="校区">
                {campusOptions.map((loc) => (
                  <option key={`o-${loc.key}`} value={loc.key}>
                    {loc.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="交通枢纽">
                {hubOptions.map((loc) => (
                  <option key={`o-${loc.key}`} value={loc.key}>
                    {loc.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>

          <div className="ct-navigate-arrow" aria-hidden="true">
            →
          </div>

          <div className="ct-navigate-field">
            <label htmlFor="nav-dest">
              <MapPin size={15} />
              要去哪
            </label>
            <select
              id="nav-dest"
              value={destination}
              disabled={loadingMeta || loading}
              onChange={(e) => setDestination(e.target.value)}
            >
              <optgroup label="校区">
                {campusOptions.map((loc) => (
                  <option key={`d-${loc.key}`} value={loc.key}>
                    {loc.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="交通枢纽">
                {hubOptions.map((loc) => (
                  <option key={`d-${loc.key}`} value={loc.key}>
                    {loc.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
        </div>

        <div className="ct-navigate-modes">
          {Object.entries(travelModes).map(([key, label]) => {
            const Icon = MODE_ICONS[key] || Bus
            return (
              <button
                key={key}
                type="button"
                className={`ct-navigate-mode${travelMode === key ? ' is-active' : ''}`}
                disabled={loading}
                onClick={() => setTravelMode(key)}
              >
                <Icon size={16} />
                {label}
              </button>
            )
          })}
        </div>

        <button
          type="button"
          className="btn-primary ct-navigate-submit"
          disabled={loading || loadingMeta}
          onClick={handleSearch}
        >
          {loading ? (
            <>
              <Loader2 size={18} className="is-spinning" />
              规划中…
            </>
          ) : (
            <>
              <Navigation size={18} />
              查询路线
            </>
          )}
        </button>

        {error && <p className="ct-navigate-error">{error}</p>}

        {result && (
          <div className="ct-navigate-result">
            <div className="ct-navigate-result-head">
              <div>
                <span className="ct-navigate-route-label">
                  {result.origin_key} → {result.destination_key}
                </span>
                <p className="ct-navigate-route-meta">
                  约 {result.duration} · {result.distance}
                  {travelModes[result.travel_mode] ? ` · ${travelModes[result.travel_mode]}` : ''}
                </p>
              </div>
              {displayWeather && !displayWeather.error && (
                <div className="ct-navigate-weather-chip">
                  <WeatherIconSmall text={displayWeather.text} />
                  <span>
                    {displayWeather.text} {displayWeather.temp}°C
                  </span>
                </div>
              )}
            </div>

            {analysis && (
              <div className="ct-navigate-analysis">
                <div className="ct-navigate-analysis-head">
                  <Sparkles size={18} />
                  <h4>AI 出行建议</h4>
                  {analysis.recommended_plan && (
                    <span className="ct-navigate-rec-badge">{analysis.recommended_plan}</span>
                  )}
                </div>
                {analysis.summary && <p className="ct-navigate-analysis-summary">{analysis.summary}</p>}
                {analysis.route_reason && (
                  <p className="ct-navigate-analysis-line">
                    <strong>推荐理由：</strong>
                    {analysis.route_reason}
                  </p>
                )}
                {analysis.weather_tips && (
                  <p className="ct-navigate-analysis-line ct-navigate-weather-tip">
                    <strong>天气提醒：</strong>
                    {analysis.weather_tips}
                  </p>
                )}
                {analysis.extra_tips && (
                  <p className="ct-navigate-analysis-line">{analysis.extra_tips}</p>
                )}
              </div>
            )}

            {hasRoutes && (
              <div className="ct-navigate-plans">
                <h4>全部方案</h4>
                {result.routes.map((route, idx) => {
                  const isOpen = expandedPlan === idx
                  return (
                    <div key={route.plan || idx} className={`ct-navigate-plan${isOpen ? ' is-open' : ''}`}>
                      <button
                        type="button"
                        className="ct-navigate-plan-head"
                        onClick={() => setExpandedPlan(isOpen ? -1 : idx)}
                      >
                        <span>
                          {route.plan || `方案${idx + 1}`} · {route.duration}
                          {route.fare ? ` · ${route.fare}` : ''}
                        </span>
                        {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                      {isOpen && (
                        <ul className="ct-navigate-plan-body">
                          {(route.segments || []).map((seg, i) => (
                            <li key={i}>{seg}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {hasSteps && !hasRoutes && (
              <div className="ct-navigate-plans">
                <h4>路线详情</h4>
                <ul className="ct-navigate-steps">
                  {result.steps.map((step, idx) => (
                    <li key={idx}>
                      <span>{step.instruction}</span>
                      {step.distance && <em>{step.distance}</em>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
