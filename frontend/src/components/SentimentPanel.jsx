import React, { useState, useEffect } from 'react'
import { getSentiment } from '../services/api'

const IMPL_COLOR = {
  BULLISH: 'text-green-400',
  BEARISH: 'text-red-400',
  NEUTRAL: 'text-terminal-text-muted',
}

function fgColor(v) {
  if (v <= 25) return { text: 'text-red-400',    bar: 'bg-red-500',    from: 'from-red-900/20'    }
  if (v <= 45) return { text: 'text-orange-400', bar: 'bg-orange-400', from: 'from-orange-900/20' }
  if (v <= 55) return { text: 'text-yellow-400', bar: 'bg-yellow-400', from: 'from-yellow-900/20' }
  if (v <= 75) return { text: 'text-lime-400',   bar: 'bg-lime-400',   from: 'from-lime-900/20'   }
  return              { text: 'text-green-400',  bar: 'bg-green-500',  from: 'from-green-900/20'  }
}

function CotRow({ label, value, change, sentiment }) {
  if (value == null) return null
  const positive = value > 0
  return (
    <div className="flex items-center justify-between text-xs py-1.5 border-b border-terminal-border last:border-0">
      <span className="text-terminal-text-muted text-[11px]">{label}</span>
      <div className="flex items-center gap-2">
        {change != null && (
          <span className={`text-[10px] font-mono ${change > 0 ? 'text-green-500' : 'text-red-500'}`}>
            {change > 0 ? '+' : ''}{(change / 1000).toFixed(1)}K
          </span>
        )}
        <span className={`font-mono font-bold text-xs ${positive ? 'text-green-400' : 'text-red-400'}`}>
          {positive ? '+' : ''}{(value / 1000).toFixed(0)}K
        </span>
      </div>
    </div>
  )
}

export default function SentimentPanel() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async (refresh = false) => {
    setLoading(true)
    try { setData(await getSentiment(refresh)) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const fg  = data?.fear_greed
  const cot = data?.cot
  const fc  = fg ? fgColor(fg.value) : null

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Sentiment & COT</h3>
        <button
          onClick={() => load(true)}
          disabled={loading}
          className="text-xs text-terminal-text-dim hover:text-gold-400 transition-colors font-mono"
        >
          {loading ? '...' : '↻'}
        </button>
      </div>

      {/* Fear & Greed */}
      {fg ? (
        <div className={`rounded-lg p-3 bg-gradient-to-br ${fc.from} to-transparent border border-terminal-border`}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-terminal-text-muted">Fear & Greed Index</span>
            <span className={`text-xs font-semibold ${IMPL_COLOR[fg.gold_implication] || 'text-gray-400'}`}>
              Or: {fg.gold_implication}
            </span>
          </div>
          <div className="flex items-baseline gap-3 mb-2.5">
            <span className={`text-4xl font-bold font-mono ${fc.text}`}>{fg.value}</span>
            <div>
              <div className={`text-sm font-semibold ${fc.text}`}>{fg.label}</div>
              {fg.change_1d !== undefined && (
                <div className={`text-[10px] font-mono ${fg.change_1d > 0 ? 'text-green-500' : fg.change_1d < 0 ? 'text-red-500' : 'text-gray-500'}`}>
                  {fg.change_1d > 0 ? '+' : ''}{fg.change_1d} / 24h
                </div>
              )}
            </div>
          </div>
          {/* Gauge */}
          <div className="relative w-full h-2 bg-terminal-muted/30 rounded-full overflow-hidden mb-2">
            <div
              className={`absolute left-0 top-0 h-full rounded-full transition-all duration-700 ${fc.bar}`}
              style={{ width: `${fg.value}%` }}
            />
          </div>
          {/* Scale labels */}
          <div className="flex justify-between text-[9px] text-terminal-text-dim mb-1.5">
            <span>Extr. Fear</span><span>Fear</span><span>Neutre</span><span>Greed</span><span>Extr. Greed</span>
          </div>
          {fg.gold_note && (
            <p className="text-[11px] text-terminal-text-muted leading-relaxed">{fg.gold_note}</p>
          )}
        </div>
      ) : loading ? (
        <div className="h-28 bg-terminal-muted/10 rounded-lg animate-pulse" />
      ) : null}

      {/* COT Report */}
      {cot && !cot.error && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest">COT Report</span>
            <span className="text-[10px] text-terminal-text-dim font-mono">{cot.report_date || '—'}</span>
          </div>
          <div>
            <CotRow label="Managed Money net"      value={cot.mm_net}      change={cot.mm_net_change} sentiment={cot.mm_sentiment} />
            <CotRow label="Spéculateurs non-comm." value={cot.noncomm_net} sentiment={cot.spec_sentiment} />
            <CotRow label="Commerciaux (hedgers)"  value={cot.comm_net} />
          </div>
          {cot.long_ratio_pct != null && (
            <div>
              <div className="flex justify-between text-[10px] mb-1">
                <span className="text-terminal-text-muted">Ratio long spéculatif</span>
                <span className="font-mono font-bold text-blue-400">{cot.long_ratio_pct}%</span>
              </div>
              <div className="w-full h-1.5 bg-terminal-muted/30 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500/70 rounded-full transition-all" style={{ width: `${cot.long_ratio_pct}%` }} />
              </div>
            </div>
          )}
          {cot.contrarian_note && (
            <div className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg px-3 py-2">
              ⚠ {cot.contrarian_note}
            </div>
          )}
        </div>
      )}

      {!loading && !fg && !cot && (
        <div className="text-xs text-terminal-text-dim text-center py-4">Données de sentiment indisponibles.</div>
      )}
    </div>
  )
}
