import React, { useState } from 'react'

const IMPACT_CONFIG = {
  HIGH:   { icon: '⚡', color: 'text-orange-400', bg: 'bg-orange-900/15', border: 'border-orange-700/30', badge: 'bg-orange-900/40 text-orange-400 border-orange-700/40' },
  MEDIUM: { icon: '📊', color: 'text-blue-400',   bg: 'bg-blue-900/15',   border: 'border-blue-700/30',  badge: 'bg-blue-900/40   text-blue-400   border-blue-700/40'   },
  LOW:    { icon: '📰', color: 'text-terminal-text-muted', bg: 'bg-terminal-surface/40', border: 'border-terminal-border', badge: 'bg-terminal-muted/30 text-terminal-text-dim border-terminal-border' },
}

const DIRECTION_CONFIG = {
  BULLISH: { color: 'text-green-400', label: '▲' },
  BEARISH: { color: 'text-red-400',   label: '▼' },
  NEUTRAL: { color: 'text-terminal-text-muted', label: '→' },
}

export default function NewsPanel({ articles, onRefresh, loading }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Actualités Or</h2>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-[10px] text-orange-400 font-semibold">⚡ HIGH</span>
            <span className="text-[10px] text-terminal-text-dim">·</span>
            <span className="text-[10px] text-blue-400 font-semibold">📊 MEDIUM</span>
            <span className="text-[10px] text-terminal-text-dim">·</span>
            <span className="text-[10px] text-terminal-text-dim font-semibold">📰 LOW</span>
          </div>
        </div>
        <button
          onClick={() => !loading && onRefresh(true)}
          disabled={loading}
          className="text-xs text-gold-400/60 hover:text-gold-400 disabled:opacity-50 transition-colors font-mono"
        >
          {loading ? '...' : '↻ Actualiser'}
        </button>
      </div>

      {loading && !articles?.length ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => <div key={i} className="h-14 bg-terminal-muted/20 rounded-lg" />)}
        </div>
      ) : !articles?.length ? (
        <div className="text-center py-6 text-terminal-text-dim text-xs">
          Aucune actualité disponible
        </div>
      ) : (
        <div className="overflow-y-auto pr-1 space-y-2" style={{ maxHeight: '200px' }}>
          {articles.map((article, i) => {
            const impact    = IMPACT_CONFIG[article.impact]    || IMPACT_CONFIG.LOW
            const direction = DIRECTION_CONFIG[article.direction] || DIRECTION_CONFIG.NEUTRAL
            const isExpanded = expanded === i

            return (
              <div
                key={i}
                className={`rounded-lg border p-3 cursor-pointer transition-all hover:opacity-90 ${impact.bg} ${impact.border}`}
                onClick={() => setExpanded(isExpanded ? null : i)}
              >
                <div className="flex items-start gap-2">
                  <span className="text-sm flex-shrink-0 mt-0.5">{impact.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs text-terminal-base font-semibold leading-snug flex-1">
                        {article.title}
                      </p>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className={`text-xs font-bold ${direction.color}`}>{direction.label}</span>
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${impact.badge}`}>
                          {article.impact}
                        </span>
                      </div>
                    </div>

                    {isExpanded && article.summary && (
                      <p className="text-xs text-terminal-text-muted mt-2 leading-relaxed border-t border-terminal-border pt-2">
                        {article.summary}
                      </p>
                    )}

                    {article.source && (
                      <p className="text-[10px] text-terminal-text-dim mt-1 font-mono">{article.source}</p>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
