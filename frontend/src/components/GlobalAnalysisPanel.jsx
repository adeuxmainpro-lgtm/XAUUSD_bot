import React, { useState, useEffect, useCallback } from 'react'
import { getCompositeScore } from '../services/api'

const DIR_COLOR = {
  BUY:     'text-green-400',
  SELL:    'text-red-400',
  NEUTRAL: 'text-terminal-text-muted',
  BULLISH: 'text-green-400',
  BEARISH: 'text-red-400',
}

const DIR_BG = {
  BUY:  'bg-green-400',
  SELL: 'bg-red-400',
}

// Category labels in French
const CAT_LABELS = {
  technical:     'Technique',
  patterns:      'Patterns',
  macro:         'Macro',
  institutional: 'Institutionnel',
  retail:        'Sentiment',
  news:          'Actualités',
}

const SYM_LABELS = {
  '^GSPC':    'S&P500',
  'BTC-USD':  'Bitcoin',
  'CL=F':     'WTI Pétrole',
  '^VIX':     'VIX',
  'TLT':      'TLT ETF',
  'DX-Y.NYB': 'DXY Dollar',
}

function ScoreGauge({ score = 50 }) {
  const pct     = Math.max(0, Math.min(100, score))
  const isBuy   = pct > 60
  const isSell  = pct < 40
  const barColor = isBuy ? 'bg-green-500' : isSell ? 'bg-red-500' : 'bg-orange-400'
  const label    = isBuy ? 'BUY' : isSell ? 'SELL' : 'FAIBLE'
  const textColor = isBuy ? 'text-green-400' : isSell ? 'text-red-400' : 'text-orange-400'

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between">
        <span className={`text-3xl font-bold font-mono ${textColor}`}>{score}<span className="text-lg text-terminal-text-dim">/100</span></span>
        <span className={`text-sm font-bold ${textColor}`}>{label}</span>
      </div>
      <div className="relative h-3 bg-terminal-muted/30 rounded-full overflow-hidden">
        {/* Zones background */}
        <div className="absolute inset-y-0 left-0 right-[40%] bg-red-900/20" />
        <div className="absolute inset-y-0 left-[60%] right-0 bg-green-900/20" />
        {/* Score bar */}
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
        {/* Threshold markers */}
        <div className="absolute inset-y-0 left-[40%] w-px bg-orange-400/40" />
        <div className="absolute inset-y-0 left-[60%] w-px bg-orange-400/40" />
      </div>
      <div className="flex justify-between text-[9px] text-terminal-text-dim font-mono">
        <span>SELL &lt;40</span>
        <span>FAIBLE 40-60</span>
        <span>BUY &gt;60</span>
      </div>
    </div>
  )
}

function CategoryBar({ name, score, max, direction }) {
  const pct      = max > 0 ? Math.round((score / max) * 100) : 50
  const barColor = direction === 'BUY' ? 'bg-green-500/70' : direction === 'SELL' ? 'bg-red-500/70' : 'bg-terminal-muted/50'
  const textColor = DIR_COLOR[direction] || 'text-terminal-text-muted'

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-terminal-text-dim font-mono w-20 flex-shrink-0">{CAT_LABELS[name] || name}</span>
      <div className="flex-1 h-1.5 bg-terminal-muted/20 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] font-mono text-terminal-text-dim w-8 text-right">{score}/{max}</span>
      <span className={`text-[10px] font-bold w-12 text-right ${textColor}`}>{direction}</span>
    </div>
  )
}

function CorrelationRow({ sym, data }) {
  const corr  = data.correlation_30d ?? 0
  const sig   = data.signal || 'NEUTRAL'
  const color = DIR_COLOR[sig] || 'text-terminal-text-muted'
  const corrColor = corr > 0.3 ? 'text-green-400' : corr < -0.3 ? 'text-red-400' : 'text-terminal-text-muted'

  return (
    <div className="flex items-center justify-between py-0.5 border-b border-terminal-border/30 last:border-0">
      <span className="text-[10px] font-mono text-terminal-base">{SYM_LABELS[sym] || sym}</span>
      <div className="flex items-center gap-3">
        <span className={`text-[10px] font-mono ${corrColor}`}>{corr > 0 ? '+' : ''}{corr.toFixed(3)}</span>
        <span className={`text-[10px] font-bold ${color}`}>{sig}</span>
      </div>
    </div>
  )
}

export default function GlobalAnalysisPanel() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const fetchData = useCallback(async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getCompositeScore(refresh)
      setData(result)
    } catch (e) {
      setError('Données indisponibles')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const composite  = data?.composite   || {}
  const ns         = data?.new_sources || {}
  const score      = composite.score   ?? 50
  const categories = composite.categories || {}
  const corr       = ns.correlations   || {}
  const etf        = ns.etf_flows      || {}
  const opts       = ns.options        || {}
  const yields     = ns.yields         || {}
  const fed        = ns.fed_nlp        || {}

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Analyse Globale</h2>
          <p className="text-[10px] text-terminal-text-dim mt-0.5">Score composite 100pts · Corrélations · ETF · Options · Fed</p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={loading}
          className="text-xs text-gold-400/60 hover:text-gold-400 disabled:opacity-50 transition-colors font-mono"
        >
          {loading ? '...' : '↻ Actualiser'}
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-400 py-2">{error}</div>
      )}

      {loading && !data ? (
        <div className="space-y-3 animate-pulse">
          <div className="h-12 bg-terminal-muted/20 rounded" />
          <div className="h-24 bg-terminal-muted/20 rounded" />
          <div className="h-16 bg-terminal-muted/20 rounded" />
        </div>
      ) : (
        <>
          {/* Composite score gauge */}
          {composite.score !== undefined && (
            <div className="bg-terminal-surface/40 border border-terminal-border rounded-lg p-3 space-y-3">
              <ScoreGauge score={score} />
              {composite.label && (
                <p className="text-[10px] text-terminal-text-muted font-mono text-center">{composite.label}</p>
              )}
            </div>
          )}

          {/* Category bars */}
          {Object.keys(categories).length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Détail par catégorie</p>
              {Object.entries(categories).map(([cat, data]) => (
                <CategoryBar
                  key={cat}
                  name={cat}
                  score={data.score}
                  max={data.max}
                  direction={data.direction}
                />
              ))}
            </div>
          )}

          {/* Correlations */}
          {Object.keys(corr).length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Corrélations 30j avec GC=F</p>
              <div className="bg-terminal-surface/30 rounded-lg px-3 py-1.5">
                {Object.entries(corr).map(([sym, d]) => (
                  <CorrelationRow key={sym} sym={sym} data={d} />
                ))}
              </div>
            </div>
          )}

          {/* ETF Flows */}
          {Object.keys(etf).length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Flux ETF Or</p>
              <div className="flex gap-2">
                {Object.entries(etf).map(([ticker, d]) => {
                  const pct   = d.price_change_pct ?? 0
                  const vol   = d.volume_vs_avg ?? 1
                  const sig   = d.signal || 'NEUTRAL'
                  const color = DIR_COLOR[sig] || 'text-terminal-text-muted'
                  return (
                    <div key={ticker} className="flex-1 bg-terminal-surface/30 rounded-lg p-2 text-center">
                      <div className="text-xs font-bold text-terminal-base">{ticker}</div>
                      <div className={`text-sm font-mono font-bold ${pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                      </div>
                      <div className="text-[10px] text-terminal-text-dim">vol ×{vol.toFixed(1)}</div>
                      <div className={`text-[10px] font-bold ${color}`}>{sig}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Options P/C */}
          {opts.put_call_ratio !== undefined && (
            <div className="bg-terminal-surface/30 rounded-lg p-2.5 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Options GLD P/C Ratio</span>
                <span className={`text-xs font-bold ${DIR_COLOR[opts.signal] || 'text-terminal-text-muted'}`}>{opts.signal}</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <div className="text-lg font-mono font-bold text-terminal-base">{opts.put_call_ratio?.toFixed(2)}</div>
                  <div className="text-[9px] text-terminal-text-dim">P/C Ratio</div>
                </div>
                <div className="flex-1 text-[10px] text-terminal-text-muted leading-relaxed">{opts.note}</div>
              </div>
            </div>
          )}

          {/* Treasury Yields */}
          {yields.y10 !== undefined && (
            <div className="bg-terminal-surface/30 rounded-lg p-2.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Courbe des Taux Treasury</span>
                <span className={`text-xs font-bold ${DIR_COLOR[yields.signal] || 'text-terminal-text-muted'}`}>{yields.signal}</span>
              </div>
              <div className="flex gap-3 text-center">
                {yields.y2  !== undefined && <div><div className="text-sm font-mono font-bold text-terminal-base">{yields.y2?.toFixed(2)}%</div><div className="text-[9px] text-terminal-text-dim">2 ans</div></div>}
                {yields.y10 !== undefined && <div><div className="text-sm font-mono font-bold text-terminal-base">{yields.y10?.toFixed(2)}%</div><div className="text-[9px] text-terminal-text-dim">10 ans</div></div>}
                {yields.y30 !== undefined && <div><div className="text-sm font-mono font-bold text-terminal-base">{yields.y30?.toFixed(2)}%</div><div className="text-[9px] text-terminal-text-dim">30 ans</div></div>}
                {yields.spread_2_10 !== undefined && (
                  <div>
                    <div className={`text-sm font-mono font-bold ${yields.inverted ? 'text-orange-400' : 'text-terminal-base'}`}>
                      {yields.spread_2_10 > 0 ? '+' : ''}{yields.spread_2_10?.toFixed(3)}%
                    </div>
                    <div className="text-[9px] text-terminal-text-dim">2s-10s {yields.inverted ? '⚡Inversée' : ''}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Fed NLP */}
          {fed.bias !== undefined && (
            <div className="bg-terminal-surface/30 rounded-lg p-2.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-terminal-text-dim uppercase tracking-wider font-semibold">Discours Fed NLP</span>
                <span className={`text-xs font-bold ${DIR_COLOR[fed.gold_signal] || 'text-terminal-text-muted'}`}>{fed.gold_signal}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-center">
                  <div className={`text-lg font-mono font-bold ${fed.score > 0 ? 'text-green-400' : fed.score < 0 ? 'text-red-400' : 'text-terminal-text-muted'}`}>
                    {fed.score > 0 ? '+' : ''}{fed.score}
                  </div>
                  <div className="text-[9px] text-terminal-text-dim">Score /±5</div>
                </div>
                <div className="flex-1">
                  <div className={`text-xs font-bold ${fed.bias === 'DOVISH' ? 'text-green-400' : fed.bias === 'HAWKISH' ? 'text-red-400' : 'text-terminal-text-muted'}`}>
                    {fed.bias}
                  </div>
                  {fed.summary && <div className="text-[10px] text-terminal-text-muted mt-0.5 leading-relaxed">{fed.summary}</div>}
                </div>
              </div>
              {fed.speeches?.length > 0 && (
                <div className="text-[9px] text-terminal-text-dim mt-1 space-y-0.5">
                  {fed.speeches.slice(0, 2).map((s, i) => <div key={i}>• {s}</div>)}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
