import React, { useState, useEffect } from 'react'
import { getSignalHistory } from '../services/api'

// ── Config maps ────────────────────────────────────────────────
const DIRECTION_CONFIG = {
  BUY:      { color: 'text-green-400',  bg: 'bg-green-400/8',   border: 'border-green-500/30',  label: '▲ BUY',      glow: 'shadow-green-900/30'  },
  SELL:     { color: 'text-red-400',    bg: 'bg-red-400/8',     border: 'border-red-500/30',    label: '▼ SELL',     glow: 'shadow-red-900/30'    },
  ATTENDRE: { color: 'text-blue-400',   bg: 'bg-blue-400/8',    border: 'border-blue-500/30',   label: '⏳ ATTENDRE', glow: 'shadow-blue-900/20'   },
  WAIT:     { color: 'text-blue-400',   bg: 'bg-blue-400/8',    border: 'border-blue-500/30',   label: '⏳ ATTENDRE', glow: 'shadow-blue-900/20'   },
}

const SIGNAL_CONFIG = {
  STRONG:   { icon: '✅', label: 'SIGNAL FORT',   color: 'text-green-400',  bg: 'bg-green-900/30',  border: 'border-green-700/50'  },
  MODERATE: { icon: '⚡', label: 'SIGNAL MODÉRÉ', color: 'text-yellow-400', bg: 'bg-yellow-900/20', border: 'border-yellow-700/40' },
  WAIT:     { icon: '⏳', label: 'ATTENDRE',       color: 'text-blue-400',   bg: 'bg-blue-900/20',   border: 'border-blue-700/40'   },
}

const HISTORY_CONFIG = {
  STRONG:   'text-green-400',
  MODERATE: 'text-yellow-400',
  WAIT:     'text-blue-400',
}

// ── Sub-components ─────────────────────────────────────────────
function SignalBadge({ level, confluence, detail }) {
  const cfg = SIGNAL_CONFIG[level] || SIGNAL_CONFIG.WAIT
  return (
    <div className={`px-3 py-2 rounded-lg border ${cfg.bg} ${cfg.border}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base leading-none">{cfg.icon}</span>
          <span className={`text-xs font-bold font-mono ${cfg.color}`}>{cfg.label}</span>
        </div>
        {confluence != null && (
          <span className={`text-xs font-mono font-bold ${cfg.color}`}>
            {confluence}%
          </span>
        )}
      </div>
      {detail && (
        <div className={`text-[10px] font-mono mt-1 ${cfg.color} opacity-70`}>{detail}</div>
      )}
    </div>
  )
}

function ConfidenceBar({ value }) {
  const color = value >= 70 ? 'bg-green-500' : value >= 50 ? 'bg-yellow-500' : 'bg-red-500'
  const label = value >= 70 ? 'text-green-400' : value >= 50 ? 'text-yellow-400' : 'text-red-400'
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-terminal-text-muted">Confiance IA</span>
        <span className={`font-mono font-bold ${label}`}>{value}%</span>
      </div>
      <div className="h-1.5 bg-terminal-muted/30 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function PriceRow({ label, value, color = 'text-terminal-base' }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-terminal-border last:border-0">
      <span className="text-terminal-text-muted text-xs">{label}</span>
      <span className={`text-xs font-mono font-bold ${color}`}>
        {value !== null && value !== undefined ? `$${Number(value).toFixed(2)}` : '—'}
      </span>
    </div>
  )
}

function WatchConditions({ conditions, title = 'Conditions à surveiller' }) {
  if (!conditions?.length) return null
  return (
    <div className="bg-blue-900/10 border border-blue-800/30 rounded-lg p-3">
      <div className="text-[10px] font-semibold text-blue-400 uppercase tracking-widest mb-2">{title}</div>
      <ul className="space-y-1.5">
        {conditions.map((c, i) => (
          <li key={i} className="text-xs text-terminal-text-muted flex items-start gap-2">
            <span className="text-blue-500 mt-0.5 flex-shrink-0">→</span>
            <span>{c}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function BlockingConditions({ conditions }) {
  if (!conditions?.length) return null
  return (
    <div className="bg-red-900/10 border border-red-800/30 rounded-lg p-3">
      <div className="text-[10px] font-semibold text-red-400 uppercase tracking-widest mb-2">Conditions bloquantes</div>
      <ul className="space-y-1.5">
        {conditions.map((c, i) => (
          <li key={i} className="text-xs text-red-300 flex items-start gap-2">
            <span className="flex-shrink-0 mt-0.5">⛔</span>
            <span>{c}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000
  if (diff < 120)       return 'à l\'instant'
  if (diff < 3600)      return `il y a ${Math.round(diff / 60)}min`
  if (diff < 86400)     return `il y a ${Math.round(diff / 3600)}h`
  return `il y a ${Math.round(diff / 86400)}j`
}

function SignalHistory({ history }) {
  if (!history?.length) return null
  return (
    <div>
      <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-2">
        Historique des signaux
      </div>
      <div className="space-y-1">
        {history.map((h, i) => {
          const isActionable = h.signal_level === 'STRONG' || h.signal_level === 'MODERATE'
          let icon, label, color

          if (isActionable) {
            if (h.direction === 'BUY') {
              icon = '✅'; label = `BUY`; color = 'text-green-400'
            } else if (h.direction === 'SELL') {
              icon = '🔴'; label = `SELL`; color = 'text-red-400'
            } else {
              icon = '⚡'; label = h.direction || 'TRADE'; color = 'text-yellow-400'
            }
          } else {
            icon = '⏳'; label = 'ATTENDRE'; color = 'text-blue-400'
          }

          return (
            <div key={i} className="flex items-center justify-between text-[10px] font-mono">
              <div className="flex items-center gap-1.5">
                <span>{icon}</span>
                <span className={`font-bold ${color}`}>{label}</span>
                {isActionable && h.confluence_score > 0 && (
                  <span className="text-terminal-text-dim">{h.confluence_score}%</span>
                )}
              </div>
              <span className="text-terminal-text-dim">{timeAgo(h.created_at)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────
export default function RecommendationCard({ analysis, onRefresh, loading }) {
  const [history, setHistory] = useState([])
  const dir             = analysis?.direction
  const normalizedDir   = (dir === 'WAIT' || dir === 'NO_TRADE') ? 'ATTENDRE' : (dir || 'ATTENDRE')
  const cfg             = DIRECTION_CONFIG[normalizedDir] || DIRECTION_CONFIG.ATTENDRE
  const signalLevel     = analysis?.signal_level || (analysis?.confidence >= 80 ? 'STRONG' : analysis?.confidence >= 70 ? 'MODERATE' : analysis ? 'WAIT' : null)
  const showHighImpact  = analysis && (analysis.confidence > 65 || analysis.dangerous_period)
  const isNoTrade       = normalizedDir === 'ATTENDRE'

  // Extract blocking conditions from context_snapshot if present
  const blockingConds = analysis?.context_snapshot?.signal_eval?.blocking_conditions || []
  const watchConds    = analysis?.watch_conditions || []

  useEffect(() => {
    getSignalHistory(4).then(setHistory).catch(() => {})
  }, [analysis])

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Recommandation IA</h2>
          {showHighImpact && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-orange-900/30 text-orange-400 border-orange-700/40 font-mono font-bold animate-pulse">
              ⚡ HIGH
            </span>
          )}
        </div>
        <button
          onClick={() => !loading && onRefresh()}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-gold-400/30 text-gold-400 hover:bg-gold-400/10 transition-colors disabled:opacity-50 disabled:cursor-wait font-mono"
        >
          <span className={loading ? 'animate-spin inline-block' : ''}>⟳</span>
          {loading ? 'Analyse...' : 'Lancer'}
        </button>
      </div>

      {loading && !analysis ? (
        <div className="space-y-2 animate-pulse">
          <div className="h-10 bg-terminal-muted/30 rounded-lg" />
          <div className="h-14 bg-terminal-muted/30 rounded-lg" />
          <div className="h-3 bg-terminal-muted/20 rounded w-3/4" />
          <div className="h-3 bg-terminal-muted/20 rounded w-1/2" />
        </div>
      ) : !analysis ? (
        <div className="text-center py-6 text-terminal-text-dim text-xs space-y-2">
          <div className="text-3xl opacity-40">📊</div>
          <div>Cliquez sur Lancer pour démarrer l'analyse IA</div>
          <SignalHistory history={history} />
        </div>
      ) : (
        <>
          {/* Signal level badge */}
          {signalLevel && (
            <SignalBadge
              level={signalLevel}
              confluence={analysis.confluence_score}
              detail={analysis.confluence_detail}
            />
          )}

          {/* Conservative mode warning */}
          {analysis.conservative_mode && (
            <div className="flex items-start gap-2 px-3 py-2 bg-orange-900/15 border border-orange-700/40 rounded-lg text-xs text-orange-300">
              <span className="flex-shrink-0">🛡</span>
              <span>{analysis.conservative_reason}</span>
            </div>
          )}

          {/* Position reduction warning */}
          {analysis.position_reduction && !isNoTrade && (
            <div className="flex items-start gap-2 px-3 py-2 bg-yellow-900/15 border border-yellow-700/40 rounded-lg text-xs text-yellow-300">
              <span className="flex-shrink-0">⚡</span>
              <span>Volatilité ATR élevée — réduire la taille de position de 50%</span>
            </div>
          )}

          {/* Direction badge (only if there's an actual trade direction) */}
          {!isNoTrade && (
            <div className={`flex items-center justify-between p-4 rounded-lg border shadow-lg ${cfg.bg} ${cfg.border} ${cfg.glow}`}>
              <span className={`text-2xl font-bold font-mono ${cfg.color}`}>{cfg.label}</span>
              <div className="text-right">
                <div className="text-xs text-terminal-text-muted">{analysis.timeframe}</div>
                {analysis.created_at && (
                  <div className="text-xs text-terminal-text-dim font-mono">
                    {new Date(analysis.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ATTENDRE explanation */}
          {isNoTrade && analysis.no_trade_reason && (
            <div className="px-3 py-2.5 bg-gray-800/30 border border-gray-700/40 rounded-lg">
              <p className="text-xs text-terminal-text-muted leading-relaxed">{analysis.no_trade_reason}</p>
            </div>
          )}

          {/* Blocking conditions */}
          <BlockingConditions conditions={blockingConds} />

          {/* Dangerous period alert */}
          {analysis.dangerous_period && (
            <div className="flex items-start gap-2 p-3 bg-orange-900/20 border border-orange-700/40 rounded-lg text-xs text-orange-300">
              <span className="flex-shrink-0 mt-0.5">⚠️</span>
              <span>{analysis.dangerous_reason || 'Période dangereuse détectée'}</span>
            </div>
          )}

          {/* Price levels — only when a trade is proposed */}
          {!isNoTrade && analysis.entry && (
            <div className="border border-terminal-border rounded-lg p-3">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-2">Niveaux</div>
              <PriceRow label="📍 Entrée"    value={analysis.entry}         color="text-gold-400" />
              <PriceRow label="🛑 Stop Loss" value={analysis.stop_loss}     color="text-red-400" />
              <PriceRow label="🎯 TP1"       value={analysis.take_profit_1} color="text-green-400" />
              <PriceRow label="🎯 TP2"       value={analysis.take_profit_2} color="text-emerald-400" />
              <div className="flex justify-between items-center pt-1.5 mt-0.5">
                <span className="text-terminal-text-muted text-xs">Ratio R/R</span>
                <span className={`text-xs font-mono font-bold ${
                  analysis.risk_reward >= 2 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {analysis.risk_reward ? `1:${analysis.risk_reward.toFixed(1)}` : '—'}
                </span>
              </div>
            </div>
          )}

          {/* Confidence + risk % */}
          <ConfidenceBar value={analysis.confidence || 0} />
          {analysis.recommended_risk_pct != null && (
            <div className="flex justify-between items-center text-xs">
              <span className="text-terminal-text-muted">Risque recommandé</span>
              <span className={`font-mono font-bold ${analysis.conservative_mode ? 'text-orange-400' : 'text-terminal-base'}`}>
                {analysis.recommended_risk_pct}% du capital
              </span>
            </div>
          )}

          {/* Market summary */}
          {analysis.market_summary && (
            <p className="text-xs text-terminal-text-muted leading-relaxed border-l-2 border-gold-400/30 pl-3 italic">
              {analysis.market_summary}
            </p>
          )}

          {/* Watch conditions (for WAIT/NO_TRADE) */}
          {isNoTrade && watchConds.length > 0 && (
            <WatchConditions conditions={watchConds} title="Ce qu'il faut surveiller" />
          )}

          {/* Arguments (scrollable) */}
          {analysis.main_arguments?.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest">Arguments</div>
                {showHighImpact && <span className="text-[10px] text-orange-400 font-mono">⚡ signal fort</span>}
              </div>
              <div className="overflow-y-auto pr-1" style={{ maxHeight: '220px' }}>
                <ul className="space-y-1.5">
                  {analysis.main_arguments.map((arg, i) => (
                    <li key={i} className="text-xs text-terminal-base flex items-start gap-2">
                      <span className="text-green-500 mt-0.5 flex-shrink-0">✓</span>
                      <span>{arg}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Risks (scrollable) */}
          {analysis.main_risks?.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-2">Risques</div>
              <div className="overflow-y-auto pr-1" style={{ maxHeight: '160px' }}>
                <ul className="space-y-1.5">
                  {analysis.main_risks.map((risk, i) => (
                    <li key={i} className="text-xs text-terminal-base flex items-start gap-2">
                      <span className="text-red-500 mt-0.5 flex-shrink-0">⚠</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Watch conditions for WAIT when we have arguments (not a hard NO_TRADE) */}
          {!isNoTrade && watchConds.length > 0 && (
            <WatchConditions conditions={watchConds} />
          )}

          {/* Alternative scenario */}
          {analysis.alternative_scenario && (
            <div className="bg-terminal-surface/50 border border-terminal-border rounded-lg p-3">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-1">Scénario alternatif</div>
              <p className="text-xs text-terminal-text-muted">{analysis.alternative_scenario}</p>
            </div>
          )}

          {/* Signal history */}
          {history.length > 0 && (
            <div className="border-t border-terminal-border pt-3">
              <SignalHistory history={history} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
