import React, { useState, useMemo } from 'react'

const IMPACT_CONFIG = {
  HIGH:   { icon: '⚡', color: 'text-orange-400', bg: 'bg-orange-900/15', border: 'border-orange-700/30', badge: 'bg-orange-900/40 text-orange-400 border-orange-700/40' },
  MEDIUM: { icon: '📊', color: 'text-blue-400',   bg: 'bg-blue-900/15',   border: 'border-blue-700/30',  badge: 'bg-blue-900/40   text-blue-400   border-blue-700/40'   },
  LOW:    { icon: '📰', color: 'text-terminal-text-muted', bg: 'bg-terminal-surface/40', border: 'border-terminal-border', badge: 'bg-terminal-muted/30 text-terminal-text-dim border-terminal-border' },
}

const SENTIMENT_CONFIG = {
  BULLISH: { icon: '📈', color: 'text-green-400',              label: 'Haussier' },
  BEARISH: { icon: '📉', color: 'text-red-400',                label: 'Baissier' },
  NEUTRAL: { icon: '➡️', color: 'text-terminal-text-muted',   label: 'Neutre'   },
}

// Reliability stars display
function Stars({ score = 3 }) {
  const s = Math.max(1, Math.min(5, score))
  return (
    <span className="text-[9px] tracking-[-1px] text-yellow-500/70">
      {'★'.repeat(s)}{'☆'.repeat(5 - s)}
    </span>
  )
}

// Global sentiment summary bar
function SentimentBar({ articles }) {
  const regular = articles.filter(a => !a.is_calendar)
  const bullish = regular.filter(a => a.direction === 'BULLISH').length
  const bearish = regular.filter(a => a.direction === 'BEARISH').length
  const neutral = regular.filter(a => a.direction === 'NEUTRAL').length
  const total   = bullish + bearish + neutral

  if (total === 0) return null

  const dominant  = bearish > bullish ? 'BEARISH' : bullish > bearish ? 'BULLISH' : 'NEUTRAL'
  const cfg       = SENTIMENT_CONFIG[dominant]

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[10px] font-mono
      ${dominant === 'BULLISH' ? 'bg-green-900/10 border-green-800/30' :
        dominant === 'BEARISH' ? 'bg-red-900/10 border-red-800/30' :
        'bg-terminal-surface/30 border-terminal-border'}`}
    >
      <span>{cfg.icon}</span>
      <span className={`font-bold ${cfg.color}`}>Sentiment : {dominant}</span>
      <span className="text-terminal-text-dim ml-auto">
        {bullish}📈 · {bearish}📉 · {neutral}➡️
      </span>
    </div>
  )
}

export default function NewsPanel({ articles, stats, onRefresh, loading }) {
  const [expanded,  setExpanded]  = useState(null)
  const [showAll,   setShowAll]   = useState(false)

  const filtered = useMemo(() => {
    if (!articles?.length) return []
    return showAll
      ? articles
      : articles.filter(a => (a.reliability ?? 3) >= 3)
  }, [articles, showAll])

  const hiddenCount = (articles?.length ?? 0) - filtered.length

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-3">

      {/* Header */}
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

      {/* Sentiment summary */}
      {!loading && articles?.length > 0 && <SentimentBar articles={articles} />}

      {/* Filter toggle + pipeline stats */}
      {!loading && articles?.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-terminal-text-dim font-mono">
              {filtered.length} article{filtered.length > 1 ? 's' : ''}
              {!showAll && hiddenCount > 0 && ` · ${hiddenCount} caché${hiddenCount > 1 ? 's' : ''} (≤2★)`}
            </span>
            {hiddenCount > 0 && (
              <button
                onClick={() => setShowAll(v => !v)}
                className="text-gold-400/60 hover:text-gold-400 transition-colors font-mono"
              >
                {showAll ? '⊖ Qualité ≥3★ seulement' : '⊕ Toutes sources'}
              </button>
            )}
          </div>
          {stats && stats.rss_seen > 0 && (
            <div className="text-[9px] text-terminal-text-dim font-mono flex gap-2 flex-wrap">
              <span>RSS: <span className="text-terminal-text-muted">{stats.rss_kept}/{stats.rss_seen}</span> filtrés</span>
              {stats.claude_articles > 0 && <span>· Claude: <span className="text-terminal-text-muted">+{stats.claude_articles}</span></span>}
              <span>· Total retenu: <span className="text-green-400/70">{stats.total_kept}</span></span>
            </div>
          )}
        </div>
      )}

      {/* Articles list */}
      {loading && !articles?.length ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => <div key={i} className="h-14 bg-terminal-muted/20 rounded-lg" />)}
        </div>
      ) : !filtered.length ? (
        <div className="text-center py-6 text-terminal-text-dim text-xs">
          Aucune actualité disponible
        </div>
      ) : (
        <div className="overflow-y-auto pr-1 space-y-2" style={{ maxHeight: '420px' }}>
          {filtered.map((article, i) => {
            const impact     = IMPACT_CONFIG[article.impact]        || IMPACT_CONFIG.LOW
            const sentiment  = SENTIMENT_CONFIG[article.direction]  || SENTIMENT_CONFIG.NEUTRAL
            const isExpanded = expanded === i
            const stars      = article.reliability ?? 3

            return (
              <div
                key={i}
                className={`rounded-lg border p-3 cursor-pointer transition-all hover:opacity-90 ${impact.bg} ${impact.border}`}
                onClick={() => setExpanded(isExpanded ? null : i)}
              >
                <div className="flex items-start gap-2">
                  <span className="text-sm flex-shrink-0 mt-0.5">{impact.icon}</span>
                  <div className="flex-1 min-w-0">

                    {/* Title + badges */}
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs text-terminal-base font-semibold leading-snug flex-1">
                        {article.title}
                      </p>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className={`text-xs`} title={sentiment.label}>{sentiment.icon}</span>
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${impact.badge}`}>
                          {article.impact}
                        </span>
                      </div>
                    </div>

                    {/* Expanded summary */}
                    {isExpanded && article.summary && (
                      <p className="text-xs text-terminal-text-muted mt-2 leading-relaxed border-t border-terminal-border pt-2">
                        {article.summary}
                      </p>
                    )}

                    {/* Source + stars */}
                    {article.source && (
                      <div className="flex items-center gap-1.5 mt-1">
                        <p className="text-[10px] text-terminal-text-dim font-mono">{article.source}</p>
                        <Stars score={stars} />
                      </div>
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
