import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { extractTextContent } from '../utils/llmText.js'
import { streamAcademicSearch } from '../utils/academicSearchStream.js'
import './AcademicSearchPanel.css'

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
  const [sourceStatus, setSourceStatus] = useState({})
  const [languageSummary, setLanguageSummary] = useState(null)
  const [linkCheckSummary, setLinkCheckSummary] = useState(null)
  const [searchError, setSearchError] = useState('')
  const [searchedQuery, setSearchedQuery] = useState('')
  const [continuation, setContinuation] = useState(null)
  const [searchStatus, setSearchStatus] = useState('')
  const [stage, setStage] = useState('')
  const searchController = useRef(null)
  const searchId = useRef(null)
  const searchVersion = useRef(0)
  const analysisVersion = useRef(0)
  const inputRef = useRef(null)
  const resultsRef = useRef(null)
  const analysisRef = useRef(null)

  async function doSearch(keyword, cursor = null) {
    const q = (cursor ? searchedQuery : keyword || query).trim()
    if (!q) return
    if (keyword) setQuery(keyword)
    const version = ++searchVersion.current
    searchController.current?.abort()
    const controller = new AbortController()
    searchController.current = controller
    ++analysisVersion.current

    setLoading(true)
    setSearched(true)
    setSearchedQuery(q)
    if (!cursor) {
      setResults([])
      setTotal(0)
      setQueryOptimization(null)
      setSourceStatus({})
      setLanguageSummary(null)
      setLinkCheckSummary(null)
      searchId.current = null
    }
    setAnalysis('')
    setAnalyzing(false)
    setShowAnalysis(false)
    setContinuation(null)
    setSearchStatus('running')
    setStage(cursor ? 'resuming' : 'planning')
    setSearchError('')
    try {
      await streamAcademicSearch({ keyword: q, top_k: 8, cursor }, {
        signal: controller.signal,
        onEvent(event) {
          if (version !== searchVersion.current) return
          if (event.type === 'progress') setStage(event.stage)
          if (event.result) {
            const data = event.result
            const verified = (data.items || []).filter(paper => paper.link_verified)
            setResults(verified)
            setTotal(verified.length)
            setQueryOptimization(data.llm_query_optimization || null)
            setSourceStatus(data.source_status || {})
            setLanguageSummary(data.language_summary || null)
            setLinkCheckSummary(data.link_check_summary || null)
            setSearchStatus(data.search_status)
            setContinuation(data.continuation_cursor || null)
            searchId.current = data.search_id || searchId.current
            setStage('checking')
          }
        },
      })
    } catch (err) {
      if (version !== searchVersion.current) return
      setSearchStatus('partial')
      setContinuation(err.code === 'session_expired' ? null : searchId.current)
      if (err.name !== 'AbortError') setSearchError(err.message || '论文搜索请求失败，请稍后重试。')
      else if (!searchId.current) setSearchError('已停止等待，可以重新搜索。')
    } finally {
      if (version === searchVersion.current) setLoading(false)
    }
  }

  useEffect(() => () => {
    ++searchVersion.current
    ++analysisVersion.current
    searchController.current?.abort()
  }, [])

  async function doAnalyze() {
    if (results.length === 0) return
    const version = ++analysisVersion.current
    setAnalyzing(true)
    setShowAnalysis(true)
    setAnalysis('')
    try {
      const resp = await axios.post('/api/resources/academic/analyze', {
        keyword: searchedQuery,
        papers: results,
      })
      if (version === analysisVersion.current) {
        setAnalysis(extractTextContent(resp.data.analysis) || '模型未返回有效解读，请重试。')
      }
    } catch (err) {
      if (version !== analysisVersion.current) return
      console.error('AI 解读失败:', err)
      setAnalysis('(AI 解读请求失败，请稍后重试)')
    } finally {
      if (version === analysisVersion.current) setAnalyzing(false)
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
  }, [searchedQuery, searched])

  // AI 解读完成后滚动
  useEffect(() => {
    if (showAnalysis && analysisRef.current) {
      analysisRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [analysis, showAnalysis])

  const sources = Object.entries(sourceStatus)
  const searchUnavailable = Boolean(searchError) || (
    sources.length > 0 && sources.every(([, info]) => ['error', 'skipped'].includes(info.status))
  )

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
          {/* 展示后端本次实际使用的关键词 */}
          {queryOptimization && (
            <div className="as-query-optimization">
              <div className="as-query-opt-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1H9a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
                  <line x1="9" y1="21" x2="15" y2="21" />
                </svg>
                <span>实际检索关键词</span>
              </div>
              <div className="as-query-opt-body">
                <span className="as-query-opt-original">
                  原始查询：{queryOptimization.original || searchedQuery}
                </span>
                {queryOptimization.zh_keywords && (
                  <span className="as-query-opt-kw">
                    Crossref → {(queryOptimization.crossref_queries || [queryOptimization.zh_keywords]).join(' / ')}
                  </span>
                )}
                {queryOptimization.arxiv_query && (
                  <span className="as-query-opt-kw">
                    arXiv → {queryOptimization.arxiv_query}
                  </span>
                )}
              </div>
            </div>
          )}
          {/* 关键词优化中 */}
          {loading && !queryOptimization && (
            <div className="as-query-optimizing">
              <span className="rf-spinner" />
              <span>正在准备检索关键词...</span>
            </div>
          )}
          <div className="as-results-header">
            <div className="as-results-header-row">
              <div className="as-results-summary">
                <span className="as-results-count">{total}</span> 篇已验证论文
                {loading && <span className="as-live-progress" role="status"><span className="rf-spinner" />
                  {stage === 'planning' ? '正在准备关键词' : stage === 'resuming' ? '正在继续检查' : '正在检索并检查更多论文'}
                </span>}
              </div>
              {loading && <button className="as-paper-external" type="button" onClick={() => searchController.current?.abort()}>停止等待</button>}
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

          {linkCheckSummary?.checked > 0 && (
            <p className="as-language-note" role="status">
              已确认 {linkCheckSummary.returned || 0} 篇原文可访问
              {linkCheckSummary.rejected > 0 && `，已过滤 ${linkCheckSummary.rejected} 个不可访问链接`}
              {linkCheckSummary.unconfirmed > 0 && `，${linkCheckSummary.unconfirmed} 个链接超时待确认`}
              {linkCheckSummary.timed_out && '；部分链接未能在时限内确认，未展示'}
            </p>
          )}
          {results.length > 0 && languageSummary?.preferred === 'zh' && (
            <p className="as-language-note" role="status">
              {languageSummary.zh > 0
                ? `中文优先：中文 ${languageSummary.zh} 篇，英文补充 ${languageSummary.en || 0} 篇`
                : loading ? '正在继续查找中文论文，以下为已验证的英文结果。' : '本次未确认可访问的相关中文论文，以下为英文补充结果。'}
            </p>
          )}
          {sources.length > 0 && (
            <div className="as-source-status" aria-live="polite">
              {sources.map(([source, info]) => (
                <div key={source} className={`as-source-status-item as-source-status-item--${info.status}`}>
                  <strong>{source}</strong>
                  <span>
                    {info.status === 'success' && `检索完成，展示 ${info.selected_count || 0} 篇`}
                    {info.status === 'partial' && '部分查询失败，已展示可用结果'}
                    {info.status === 'error' && '检索失败，请稍后重试'}
                    {info.status === 'skipped' && '未检索：未生成可用的英文关键词'}
                    {info.status === 'pending' && (loading ? '仍在检索中' : '本轮尚未完成，可继续搜索')}
                  </span>
                </div>
              ))}
            </div>
          )}
          {!loading && searchError && <p className="as-search-error" role="alert">{searchError}</p>}
          {!loading && searchStatus === 'partial' && continuation && (
            <div className="as-continue-search" role="status">
              <span>已保留验证通过的结果，部分检索或链接检查尚未完成。</span>
              <button className="as-paper-external" type="button" onClick={() => doSearch(null, continuation)}>继续完善结果</button>
            </div>
          )}

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
                <div key={paper.doi || paper.url || paper.title} className="as-paper-card">
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
              <p className="as-no-results-title">
                {continuation ? '检查尚未完成' : searchUnavailable ? '搜索暂不可用' : linkCheckSummary?.candidates > 0 ? '未找到可访问的论文原文' : '未找到相关论文'}
              </p>
              <p className="as-no-results-hint">
                {searchUnavailable ? '请稍后重试，本次未能完成论文检索' : linkCheckSummary?.candidates > 0 ? '已找到论文题录，但原文链接暂不可访问或未能确认，请稍后重试或更换关键词' : '试试更具体的研究主题，或补充英文专业术语'}
              </p>
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
