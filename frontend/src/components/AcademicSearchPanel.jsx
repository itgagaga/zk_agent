import { useState, useRef, useEffect } from 'react'
import axios from 'axios'

const EXAMPLE_QUERIES = [
  { q: 'deep learning', label: 'Deep Learning' },
  { q: '物联网 农业监测', label: 'IoT 农业' },
  { q: '计算机视觉 目标检测', label: '目标检测' },
  { q: 'natural language processing', label: 'NLP' },
  { q: 'reinforcement learning robotics', label: '强化学习' },
]

const SUGGESTIONS = [
  '找毕设方向的参考文献',
  '搜索高引用的经典论文',
  '查找某领域的最新研究',
  '了解前沿技术的发展脉络',
]

export default function AcademicSearchPanel() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [analysis, setAnalysis] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [showAnalysis, setShowAnalysis] = useState(false)
  const [queryOptimization, setQueryOptimization] = useState(null)
  const [optimizing, setOptimizing] = useState(false)
  const inputRef = useRef(null)
  const resultsRef = useRef(null)
  const analysisRef = useRef(null)

  async function doSearch(keyword) {
    const q = (keyword || query).trim()
    if (!q) return
    if (keyword) setQuery(keyword)

    setLoading(true)
    setSearched(true)
    setAnalysis('')
    setShowAnalysis(false)
    setQueryOptimization(null)
    setOptimizing(true)
    try {
      // 先调用 LLM 优化关键词
      let optResp
      try {
        optResp = await axios.get('/api/resources/academic/optimize', {
          params: { keyword: q },
        })
        setQueryOptimization(optResp.data)
      } catch {
        // 关键词优化失败不影响主搜索
      }
      setOptimizing(false)

      // 再调用搜索 API（后端内部也会走 LLM 优化）
      const resp = await axios.get('/api/resources/academic', {
        params: { keyword: q, top_k: 8 },
      })
      setResults(resp.data.items || [])
      setTotal(resp.data.total || 0)
      // 如果搜索结果中有 LLM 优化信息，也更新
      if (resp.data.llm_query_optimization && !queryOptimization) {
        setQueryOptimization(resp.data.llm_query_optimization)
      }
    } catch (err) {
      console.error('学术搜索失败:', err)
      setResults([])
      setTotal(0)
    } finally {
      setLoading(false)
      setOptimizing(false)
    }
  }

  async function doAnalyze() {
    if (results.length === 0) return
    setAnalyzing(true)
    setShowAnalysis(true)
    setAnalysis('')
    try {
      const resp = await axios.post('/api/resources/academic/analyze', {
        keyword: query,
        papers: results,
      })
      setAnalysis(resp.data.analysis || '')
    } catch (err) {
      console.error('AI 解读失败:', err)
      setAnalysis('(AI 解读请求失败，请稍后重试)')
    } finally {
      setAnalyzing(false)
    }
  }

  function handleSearch(e) {
    e?.preventDefault()
    doSearch()
  }

  // 搜索后滚动到结果区
  useEffect(() => {
    if (searched && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [results, searched])

  // AI 解读完成后滚动
  useEffect(() => {
    if (showAnalysis && analysisRef.current) {
      analysisRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [analysis, showAnalysis])

  return (
    <div className="academic-search-panel">
      {/* 英雄区 */}
      <div className="as-hero">
        <div className="as-hero-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="11" y1="8" x2="11" y2="14" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </div>
        <h2 className="as-hero-title">学术论文搜索</h2>
        <p className="as-hero-desc">
          搜索全球学术论文，助力毕业设计与课题研究。<br />
          数据来源 Crossref（1.5 亿+ 论文）与 arXiv 预印本，完全免费。
        </p>
      </div>

      {/* 搜索栏 */}
      <form className="as-search-form" onSubmit={handleSearch}>
        <div className="as-search-row">
          <div className="as-search-input-wrap">
            <svg className="as-search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={inputRef}
              className="as-search-input"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="输入研究方向或关键词，如：深度学习、物联网 农业、transformer"
              disabled={loading}
            />
          </div>
          <button
            className="as-search-btn"
            type="submit"
            disabled={loading || !query.trim()}
          >
            {loading ? <><span className="rf-spinner" /> 搜索中</> : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                搜索论文
              </>
            )}
          </button>
        </div>
      </form>

      {/* 空状态：建议 + 示例 */}
      {!searched && (
        <div className="as-empty-state">
          <div className="as-suggestions">
            <div className="as-suggestions-label">你可以这样搜索</div>
            <div className="as-suggestions-list">
              {SUGGESTIONS.map((s, i) => (
                <div key={i} className="as-suggestion-item">
                  <span className="as-suggestion-bullet">&#8250;</span>
                  {s}
                </div>
              ))}
            </div>
          </div>
          <div className="as-examples">
            <div className="as-examples-label">热门关键词</div>
            <div className="as-examples-chips">
              {EXAMPLE_QUERIES.map(item => (
                <button
                  key={item.q}
                  className="as-example-chip"
                  onClick={() => doSearch(item.q)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 搜索结果 */}
      {searched && (
        <div className="as-results" ref={resultsRef}>
          {/* LLM 关键词优化展示 */}
          {queryOptimization && (
            <div className="as-query-optimization">
              <div className="as-query-opt-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1H9a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
                  <line x1="9" y1="21" x2="15" y2="21" />
                </svg>
                <span>LLM 关键词优化</span>
              </div>
              <div className="as-query-opt-body">
                <span className="as-query-opt-original">
                  原始查询：{queryOptimization.original || query}
                </span>
                {queryOptimization.zh_keywords && (
                  <span className="as-query-opt-kw">
                    Crossref → {queryOptimization.zh_keywords}
                  </span>
                )}
                {queryOptimization.en_keywords && (
                  <span className="as-query-opt-kw">
                    arXiv → {queryOptimization.en_keywords}
                  </span>
                )}
              </div>
            </div>
          )}
          {/* 关键词优化中 */}
          {optimizing && !queryOptimization && (
            <div className="as-query-optimizing">
              <span className="rf-spinner" />
              <span>LLM 正在优化搜索关键词...</span>
            </div>
          )}
          <div className="as-results-header">
            <div className="as-results-header-row">
              {loading ? (
                <div className="as-results-loading">
                  <span className="rf-spinner" />
                  <span>正在搜索 Crossref 和 arXiv...</span>
                </div>
              ) : (
                <div className="as-results-summary">
                  <span className="as-results-count">{total}</span> 篇相关论文
                </div>
              )}
              {!loading && results.length > 0 && (
                <button
                  className="as-ai-btn"
                  onClick={doAnalyze}
                  disabled={analyzing}
                >
                  {analyzing ? (
                    <><span className="rf-spinner" /> AI 解读中</>
                  ) : (
                    <>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1H9a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
                        <line x1="9" y1="21" x2="15" y2="21" />
                      </svg>
                      AI 解读
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* AI 解读区 */}
          {showAnalysis && (
            <div className="as-analysis" ref={analysisRef}>
              <div className="as-analysis-header">
                <div className="as-analysis-icon">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1H9a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
                    <line x1="9" y1="21" x2="15" y2="21" />
                  </svg>
                </div>
                <span className="as-analysis-title">AI 学术解读</span>
                {!analyzing && analysis && (
                  <button className="as-analysis-close" onClick={() => setShowAnalysis(false)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                )}
              </div>
              <div className="as-analysis-body">
                {analyzing ? (
                  <div className="as-analysis-loading">
                    <span className="rf-spinner" />
                    <span>正在分析论文，生成研究脉络与推荐...</span>
                  </div>
                ) : (
                  <div className="as-analysis-content">
                    {analysis.split('\n').map((line, i) => (
                      <p key={i}>{line}</p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {results.length > 0 && (
            <div className="as-results-list">
              {results.map((paper, i) => (
                <div key={i} className="as-paper-card">
                  <div className="as-paper-main">
                    <div className="as-paper-left">
                      <span className="as-paper-index">{i + 1}</span>
                    </div>
                    <div className="as-paper-body">
                      <div className="as-paper-title-row">
                        {paper.url ? (
                          <a href={paper.url} target="_blank" rel="noreferrer" className="as-paper-title">
                            {paper.title}
                          </a>
                        ) : (
                          <span className="as-paper-title">{paper.title}</span>
                        )}
                        <span className={`as-paper-source as-paper-source--${paper.source?.toLowerCase()}`}>
                          {paper.source}
                        </span>
                      </div>
                      <div className="as-paper-meta">
                        {paper.year && <span className="as-paper-year">{paper.year}</span>}
                        {paper.authors && <span className="as-paper-authors">{paper.authors}</span>}
                      </div>
                      {paper.snippet && (
                        <div className="as-paper-snippet">{paper.snippet}</div>
                      )}
                      <div className="as-paper-footer">
                        {paper.cited > 0 && (
                          <span className="as-paper-cited">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M6 9l6 6 6-6" />
                            </svg>
                            被引用 {paper.cited} 次
                          </span>
                        )}
                        {paper.doi && (
                          <a
                            href={`https://doi.org/${paper.doi}`}
                            target="_blank"
                            rel="noreferrer"
                            className="as-paper-doi-link"
                          >
                            <span className="as-doi-label">DOI</span>
                            {paper.doi}
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
                            </svg>
                          </a>
                        )}
                        {paper.url && (
                          <a href={paper.url} target="_blank" rel="noreferrer" className="as-paper-external">
                            查看原文
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
                            </svg>
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && results.length === 0 && (
            <div className="as-no-results">
              <div className="as-no-results-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  <line x1="8" y1="11" x2="14" y2="11" />
                </svg>
              </div>
              <p className="as-no-results-title">未找到相关论文</p>
              <p className="as-no-results-hint">试试更换关键词，或使用英文搜索以获得更多 arXiv 结果</p>
              <div className="as-no-results-retry">
                {EXAMPLE_QUERIES.slice(0, 3).map(item => (
                  <button
                    key={item.q}
                    className="as-example-chip"
                    onClick={() => doSearch(item.q)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
