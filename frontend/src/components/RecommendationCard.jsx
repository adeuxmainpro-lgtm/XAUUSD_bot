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
  STRONG:    { icon: '✅', label: 'SIGNAL FORT',       color: 'text-green-400',  bg: 'bg-green-900/30',  border: 'border-green-700/50'  },
  MODERATE:  { icon: '⚡', label: 'SIGNAL MODÉRÉ',    color: 'text-yellow-400', bg: 'bg-yellow-900/20', border: 'border-yellow-700/40' },
  WEAK:      { icon: '〰', label: 'SIGNAL FAIBLE',    color: 'text-orange-400', bg: 'bg-orange-900/15', border: 'border-orange-700/40' },
  VERY_WEAK: { icon: '〰', label: 'SIGNAL TRÈS FAIBLE', color: 'text-orange-400', bg: 'bg-orange-900/10', border: 'border-orange-700/30' },
  WAIT:      { icon: '⏳', label: 'ATTENDRE',          color: 'text-blue-400',   bg: 'bg-blue-900/20',   border: 'border-blue-700/40'   },
}

// ── Sub-components ─────────────────────────────────────────────
function SignalBadge({ level, confluence, bullish, bearish }) {
  const cfg = SIGNAL_CONFIG[level] || SIGNAL_CONFIG.WAIT
  return (
    <div className={`px-3 py-2 rounded-lg border ${cfg.bg} ${cfg.border}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base leading-none">{cfg.icon}</span>
          <span className={`text-xs font-bold font-mono ${cfg.color}`}>{cfg.label}</span>
        </div>
        {confluence != null && (
          <span className={`text-xs font-mono font-bold ${cfg.color}`}>{confluence}%</span>
        )}
      </div>
      {(bullish != null || bearish != null) && (
        <div className="flex gap-3 mt-1 text-[10px] font-mono">
          {bullish != null && <span className="text-green-400">▲ {bullish} haussiers</span>}
          {bearish != null && <span className="text-red-400">▼ {bearish} baissiers</span>}
        </div>
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

function AccordionSection({ sectionId, title, openSection, onToggle, children, badge }) {
  const isOpen = openSection === sectionId
  return (
    <div className="border border-terminal-border/50 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/5 transition-colors"
        onClick={() => onToggle(sectionId)}
      >
        <span className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest">
          {title}
        </span>
        <div className="flex items-center gap-2">
          {badge}
          <span className="text-terminal-text-dim text-[10px]">{isOpen ? '▼' : '▶'}</span>
        </div>
      </button>
      <div
        style={{
          display: 'grid',
          gridTemplateRows: isOpen ? '1fr' : '0fr',
          transition: 'grid-template-rows 260ms ease',
        }}
      >
        <div style={{ overflow: 'hidden' }}>
          <div className="px-3 pb-3 pt-1">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000
  if (diff < 120)   return 'à l\'instant'
  if (diff < 3600)  return `il y a ${Math.round(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.round(diff / 3600)}h`
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
          const isActionable = ['STRONG', 'MODERATE', 'WEAK', 'VERY_WEAK'].includes(h.signal_level)
          let icon, label, color
          if (isActionable) {
            if (h.direction === 'BUY')       { icon = '✅'; label = 'BUY';      color = 'text-green-400'  }
            else if (h.direction === 'SELL') { icon = '🔴'; label = 'SELL';     color = 'text-red-400'    }
            else                             { icon = '⚡'; label = h.direction || 'TRADE'; color = 'text-yellow-400' }
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
  const [history, setHistory]         = useState([])
  const [openSection, setOpenSection] = useState(null)

  const toggleSection = (id) => setOpenSection(prev => prev === id ? null : id)

  const dir           = analysis?.direction
  const normalizedDir = (dir === 'WAIT' || dir === 'NO_TRADE') ? 'ATTENDRE' : (dir || 'ATTENDRE')
  const cfg           = DIRECTION_CONFIG[normalizedDir] || DIRECTION_CONFIG.ATTENDRE
  const signalLevel   = analysis?.signal_level || (analysis?.confidence >= 80 ? 'STRONG' : analysis?.confidence >= 70 ? 'MODERATE' : analysis ? 'WAIT' : null)
  const isNoTrade     = normalizedDir === 'ATTENDRE'

  const watchConds  = analysis?.watch_conditions || []
  const riskPct     = analysis?.recommended_risk_pct
  const riskColor   = analysis?.conservative_mode ? 'text-orange-400' : analysis?.weak_signal ? 'text-orange-400' : 'text-terminal-base'

  // Parse bullish/bearish counts from confluence signals
  const confSignals = analysis?.context_snapshot?.confluence?.signals || []
  const bullCount = confSignals.filter(s => ['BUY', 'BULLISH', 'bullish'].includes(s.direction)).length || null
  const bearCount = confSignals.filter(s => ['SELL', 'BEARISH', 'bearish'].includes(s.direction)).length || null

  useEffect(() => {
    getSignalHistory(4).then(setHistory).catch(() => {})
  }, [analysis])

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Recommandation IA</h2>
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
          {/* Signal badge */}
          {signalLevel && (
            <SignalBadge
              level={signalLevel}
              confluence={analysis.confluence_score}
              bullish={bullCount || undefined}
              bearish={bearCount || undefined}
            />
          )}

          {/* Conservative mode warning */}
          {analysis.conservative_mode && (
            <div className="flex items-start gap-2 px-3 py-2 bg-orange-900/15 border border-orange-700/40 rounded-lg text-xs text-orange-300">
              <span className="flex-shrink-0">🛡</span>
              <span>{analysis.conservative_reason}</span>
            </div>
          )}

          {/* Weak signal notice */}
          {analysis.weak_signal && !analysis.conservative_mode && (
            <div className="flex items-start gap-2 px-3 py-2 bg-orange-900/10 border border-orange-700/30 rounded-lg text-xs text-orange-300">
              <span className="flex-shrink-0">〰</span>
              <span>Signal faible — position réduite ({riskPct}% du capital)</span>
            </div>
          )}

          {/* Position reduction warning */}
          {analysis.position_reduction && !isNoTrade && (
            <div className="flex items-start gap-2 px-3 py-2 bg-yellow-900/15 border border-yellow-700/40 rounded-lg text-xs text-yellow-300">
              <span className="flex-shrink-0">⚡</span>
              <span>Volatilité ATR élevée — réduire la taille de position de 50%</span>
            </div>
          )}

          {/* Direction badge */}
          {!isNoTrade && (
            <div className={`rounded-lg border shadow-lg ${cfg.bg} ${cfg.border} ${cfg.glow}`}>
              <div className="flex items-center justify-between p-4">
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
              {analysis.market_summary && (
                <div
                  className="px-4 pb-3 overflow-y-auto border-t border-terminal-border/40"
                  style={{ maxHeight: '100px', scrollbarWidth: 'thin' }}
                >
                  <p className="text-[11px] text-terminal-text-muted leading-relaxed pt-2">
                    {analysis.market_summary}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ATTENDRE explanation */}
          {isNoTrade && analysis.no_trade_reason && (
            <div className="px-3 py-2.5 bg-gray-800/30 border border-gray-700/40 rounded-lg">
              <p className="text-xs text-terminal-text-muted leading-relaxed">{analysis.no_trade_reason}</p>
            </div>
          )}

          {/* Dangerous period / macro alert */}
          {analysis.dangerous_period && (
            <div className="flex items-start gap-2 p-3 bg-orange-900/20 border border-orange-700/40 rounded-lg text-xs text-orange-300">
              <span className="flex-shrink-0 mt-0.5">⚠️</span>
              <span>{analysis.dangerous_reason || 'Annonce macro imminente'}</span>
            </div>
          )}

          {/* Price levels */}
          {!isNoTrade && analysis.entry && (
            <div className="border border-terminal-border rounded-lg p-3">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-2">Niveaux</div>
              <PriceRow label="📍 Entrée"    value={analysis.entry}         color="text-gold-400" />
              <PriceRow label="🛑 Stop Loss" value={analysis.stop_loss}     color="text-red-400" />
              <PriceRow label="🎯 TP1 (50%)" value={analysis.take_profit_1} color="text-green-400" />
              <PriceRow label="🎯 TP2 (50%)" value={analysis.take_profit_2} color="text-emerald-400" />
              <div className="flex justify-between items-center pt-1.5 mt-0.5">
                <span className="text-terminal-text-muted text-xs">Ratio R/R</span>
                <span className={`text-xs font-mono font-bold ${
                  analysis.risk_reward >= 2 ? 'text-green-400' : analysis.risk_reward >= 1.5 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {analysis.risk_reward ? `1:${analysis.risk_reward.toFixed(1)}` : '—'}
                </span>
              </div>
            </div>
          )}

          {/* Gain estimate */}
          {!isNoTrade && analysis.gain_estimate && (
            <div className="bg-terminal-surface/30 border border-terminal-border rounded-lg p-3 space-y-2">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest">
                Gain estimé — 1000€ × 1% risque
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-sm font-mono font-bold text-green-400">
                    +{analysis.gain_estimate.gain_tp1_eur}€
                  </div>
                  <div className="text-[9px] text-terminal-text-dim mt-0.5">
                    TP1 · 1:{analysis.gain_estimate.rr_tp1}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-mono font-bold text-emerald-400">
                    +{analysis.gain_estimate.gain_tp2_eur}€
                  </div>
                  <div className="text-[9px] text-terminal-text-dim mt-0.5">
                    TP2 · 1:{analysis.gain_estimate.rr_tp2}
                  </div>
                </div>
                <div className="border-l border-terminal-border pl-2">
                  <div className="text-sm font-mono font-bold text-gold-400">
                    +{analysis.gain_estimate.gain_partial_eur}€
                  </div>
                  <div className="text-[9px] text-terminal-text-dim mt-0.5">Sortie 50/50</div>
                </div>
              </div>
            </div>
          )}

          {/* Partial exit strategy */}
          {!isNoTrade && analysis.partial_exit && (
            <div className="bg-terminal-surface/20 border border-terminal-border/50 rounded-lg px-3 py-2.5">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-1.5">
                Stratégie de sortie partielle
              </div>
              <p className="text-[11px] text-terminal-text-muted leading-relaxed">{analysis.partial_exit}</p>
            </div>
          )}

          {/* Confidence */}
          <ConfidenceBar value={analysis.confidence || 0} />

          {/* Risque recommandé */}
          {riskPct != null && (
            <AccordionSection
              sectionId="risk"
              title="Risque recommandé"
              openSection={openSection}
              onToggle={toggleSection}
              badge={
                <span className={`text-[10px] font-mono font-bold ${riskColor}`}>{riskPct}%</span>
              }
            >
              <div className="flex justify-between items-center text-xs pt-0.5">
                <span className="text-terminal-text-muted">Taille de position</span>
                <span className={`font-mono font-bold ${riskColor}`}>{riskPct}% du capital</span>
              </div>
              {analysis.conservative_mode && analysis.conservative_reason && (
                <p className="text-[10px] text-orange-400 mt-1.5">{analysis.conservative_reason}</p>
              )}
              {analysis.weak_signal && !analysis.conservative_mode && (
                <p className="text-[10px] text-orange-400 mt-1.5">Signal faible — position réduite pour limiter l'exposition</p>
              )}
            </AccordionSection>
          )}

          {/* Arguments */}
          {analysis.main_arguments?.length > 0 && (
            <AccordionSection
              sectionId="arguments"
              title="Arguments"
              openSection={openSection}
              onToggle={toggleSection}
            >
              <div className="overflow-y-auto pr-1 pt-0.5" style={{ maxHeight: '180px' }}>
                <ul className="space-y-1.5">
                  {analysis.main_arguments.map((arg, i) => (
                    <li key={i} className="text-xs text-terminal-base flex items-start gap-2">
                      <span className="text-green-500 mt-0.5 flex-shrink-0">✓</span>
                      <span>{arg}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </AccordionSection>
          )}

          {/* Risks */}
          {analysis.main_risks?.length > 0 && (
            <AccordionSection
              sectionId="risks"
              title="Risques"
              openSection={openSection}
              onToggle={toggleSection}
            >
              <div className="overflow-y-auto pr-1 pt-0.5" style={{ maxHeight: '180px' }}>
                <ul className="space-y-1.5">
                  {analysis.main_risks.map((risk, i) => (
                    <li key={i} className="text-xs text-terminal-base flex items-start gap-2">
                      <span className="text-red-500 mt-0.5 flex-shrink-0">⚠</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </AccordionSection>
          )}

          {/* Ce qu'il faut surveiller */}
          {watchConds.length > 0 && (
            <AccordionSection
              sectionId="watch"
              title="Ce qu'il faut surveiller"
              openSection={openSection}
              onToggle={toggleSection}
            >
              <ul className="space-y-1.5 pt-0.5">
                {watchConds.map((c, i) => (
                  <li key={i} className="text-xs text-terminal-text-muted flex items-start gap-2">
                    <span className="text-blue-500 mt-0.5 flex-shrink-0">→</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </AccordionSection>
          )}

          {/* Scénario alternatif */}
          {analysis.alternative_scenario && (
            <AccordionSection
              sectionId="scenario"
              title="Scénario alternatif"
              openSection={openSection}
              onToggle={toggleSection}
            >
              <p className="text-xs text-terminal-text-muted pt-0.5">{analysis.alternative_scenario}</p>
            </AccordionSection>
          )}

          {/* Weekly/monthly projection */}
          {!isNoTrade && analysis.weekly_projection && (
            <div className="border border-terminal-border/40 rounded-lg px-3 py-2.5 bg-terminal-surface/10 space-y-1.5">
              <div className="flex items-center justify-between text-[10px]">
                <span className="font-semibold text-terminal-text-dim uppercase tracking-widest">
                  Projection long terme
                </span>
                <span className="text-terminal-text-dim font-mono">
                  {analysis.weekly_projection.win_rate_pct}% win rate · {analysis.weekly_projection.trades_per_week} trades/sem
                </span>
              </div>
              <div className="flex gap-4 text-[11px] font-mono">
                <div>
                  <span className="text-terminal-text-dim">Semaine : </span>
                  <span className="text-green-400 font-bold">+{analysis.weekly_projection.weekly_gain_eur}€</span>
                  <span className="text-terminal-text-dim ml-1">({analysis.weekly_projection.weekly_gain_pct}%)</span>
                </div>
                <div>
                  <span className="text-terminal-text-dim">Mois : </span>
                  <span className="text-green-400 font-bold">~{analysis.weekly_projection.monthly_gain_pct}%</span>
                </div>
              </div>
              <p className="text-[9px] text-terminal-text-dim font-mono">
                ⚠ Ne jamais risquer plus de 1% par trade · Objectif réaliste : +8–12%/mois
              </p>
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
