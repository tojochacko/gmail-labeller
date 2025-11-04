import { useEffect, useState } from 'react'
import './PatternViewer.css'

interface LabelPattern {
  pattern_id: string
  label_type: 'Important' | 'Not Important'
  pattern_type: 'domain' | 'keyword'
  pattern_value: string
  confidence_score: number
  occurrence_count: number
  is_user_defined: boolean
  created_at: string
  last_seen_at: string
}

interface PatternViewerProps {
  userId: string
}

export function PatternViewer({ userId }: PatternViewerProps) {
  const [patterns, setPatterns] = useState<LabelPattern[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')
  const [labelTypeFilter, setLabelTypeFilter] = useState<string>('')
  const [patternTypeFilter, setPatternTypeFilter] = useState<string>('')
  const [currentPage, setCurrentPage] = useState(1)

  const PATTERNS_PER_PAGE = 50
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  useEffect(() => {
    fetchPatterns()
  }, [userId, labelTypeFilter, patternTypeFilter])

  const fetchPatterns = async () => {
    try {
      setLoading(true)
      setError('')

      const queryParams = new URLSearchParams({
        user_id: userId,
      })

      if (labelTypeFilter) {
        queryParams.append('label_type', labelTypeFilter)
      }
      if (patternTypeFilter) {
        queryParams.append('pattern_type', patternTypeFilter)
      }

      const response = await fetch(`${API_BASE_URL}/api/patterns?${queryParams}`)

      if (!response.ok) {
        throw new Error(`Failed to fetch patterns: ${response.statusText}`)
      }

      const data = await response.json()
      setPatterns(data.patterns || [])
      setCurrentPage(1) // Reset to first page when filters change
    } catch (err) {
      console.error('Failed to fetch patterns:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch patterns')
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = () => {
    fetchPatterns()
  }

  const handleClearFilters = () => {
    setLabelTypeFilter('')
    setPatternTypeFilter('')
  }

  // Pagination
  const totalPages = Math.ceil(patterns.length / PATTERNS_PER_PAGE)
  const startIndex = (currentPage - 1) * PATTERNS_PER_PAGE
  const endIndex = startIndex + PATTERNS_PER_PAGE
  const currentPatterns = patterns.slice(startIndex, endIndex)

  const handlePreviousPage = () => {
    setCurrentPage((prev) => Math.max(1, prev - 1))
  }

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(totalPages, prev + 1))
  }

  return (
    <div className="pattern-viewer">
      <div className="pattern-viewer__header">
        <div>
          <h2>AI Learning Patterns</h2>
          <p className="hint">
            These patterns are automatically learned from your email labeling behavior
          </p>
        </div>
        <button type="button" onClick={handleRefresh} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="pattern-viewer__filters">
        <div className="filter-group">
          <label htmlFor="label-type-filter" className="filter-label">
            Label Type:
          </label>
          <select
            id="label-type-filter"
            value={labelTypeFilter}
            onChange={(e) => setLabelTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Labels</option>
            <option value="Important">Important</option>
            <option value="Not Important">Not Important</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="pattern-type-filter" className="filter-label">
            Pattern Type:
          </label>
          <select
            id="pattern-type-filter"
            value={patternTypeFilter}
            onChange={(e) => setPatternTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Types</option>
            <option value="domain">Domains</option>
            <option value="keyword">Keywords</option>
          </select>
        </div>

        {(labelTypeFilter || patternTypeFilter) && (
          <button type="button" onClick={handleClearFilters} className="filter-clear">
            Clear Filters
          </button>
        )}
      </div>

      {error && (
        <div className="pattern-viewer__error">
          <p className="status status--error">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="pattern-viewer__loading">
          <p>Loading patterns...</p>
        </div>
      ) : patterns.length === 0 ? (
        <div className="pattern-viewer__empty">
          <p className="hint">
            No patterns learned yet. Start labeling emails to help the AI learn your preferences!
          </p>
        </div>
      ) : (
        <>
          <div className="pattern-viewer__stats">
            <p className="hint">
              Showing {startIndex + 1}-{Math.min(endIndex, patterns.length)} of {patterns.length}{' '}
              patterns
            </p>
          </div>

          <div className="pattern-viewer__table-container">
            <table className="pattern-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Confidence</th>
                  <th>Occurrences</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {currentPatterns.map((pattern) => (
                  <tr key={pattern.pattern_id}>
                    <td>
                      <span
                        className={`label-badge ${
                          pattern.label_type === 'Important'
                            ? 'label-badge--important'
                            : 'label-badge--not-important'
                        }`}
                      >
                        {pattern.label_type}
                      </span>
                    </td>
                    <td>
                      <span className="pattern-type">
                        {pattern.pattern_type === 'domain' ? '🌐 Domain' : '🔑 Keyword'}
                      </span>
                    </td>
                    <td className="pattern-value">{pattern.pattern_value}</td>
                    <td className="pattern-confidence">
                      <div className="confidence-bar-container">
                        <div
                          className="confidence-bar"
                          style={{ width: `${pattern.confidence_score * 100}%` }}
                        />
                      </div>
                      <span className="confidence-text">
                        {(pattern.confidence_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="pattern-occurrences">{pattern.occurrence_count}</td>
                    <td>
                      <span
                        className={`source-badge ${
                          pattern.is_user_defined ? 'source-badge--manual' : 'source-badge--auto'
                        }`}
                      >
                        {pattern.is_user_defined ? '👤 Manual' : '🤖 Learned'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pattern-viewer__pagination">
              <button
                type="button"
                onClick={handlePreviousPage}
                disabled={currentPage === 1}
                className="pagination-button"
              >
                Previous
              </button>
              <span className="pagination-info">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                onClick={handleNextPage}
                disabled={currentPage === totalPages}
                className="pagination-button"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
