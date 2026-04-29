import React, { useState, useEffect } from 'react'
import { getMacroContext } from '../services/api'

const TREND_ICON  = { hausse: '↑', baisse: '↓', stable: '→' }

function trendColor(trend, indicator) {
  if (!trend || trend === 'stable') return 'text-terminal-text-muted'
  if (indicator === 'cpi') return trend === 'hausse' ? 'text-green-400' : 'text-red-400'
  return trend === 'hausse' ? 'text-red-400' : 'text-green-400'
}

function MetricRow({ label, value, trend, indicator }) {
  const tc = trendColor(trend, indicator)
  const icon = TREND_ICON[trend] || '→'
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-terminal-border last:border-0">
      <span className="text-xs text-terminal-text-muted">{label}</span>
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-xs font-bold text-terminal-base">{value ?? '—'}</span>
        {trend && (
          <span className={`text-xs font-bold font-mono ${tc}`} title={`Tendance: ${trend}`}>{icon}</span>
        )}
      </div>
    </div>
  )
}

export default function MacroPanel() {
  const [macro,   setMacro]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMacroContext()
      .then(setMacro)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const dxyNote = !macro ? null
    : macro.dxy_trend === 'hausse' ? 'DXY ↑ → pression baissière sur l\'or'
    : macro.dxy_trend === 'baisse' ? 'DXY ↓ → soutien mécanique pour l\'or'
    : 'DXY stable — corrélation inverse avec l\'or'

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4">
      <h3 className="text-sm font-bold text-terminal-base uppercase tracking-wider mb-3">
        Contexte Macro
      </h3>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-7 bg-terminal-muted/20 rounded" />)}
        </div>
      ) : macro ? (
        <>
          <div>
            <MetricRow label="Taux FED" value={macro.fed_rate != null ? `${macro.fed_rate}%`   : null} trend={macro.fed_trend} indicator="fed" />
            <MetricRow label="CPI (YoY)" value={macro.cpi_yoy  != null ? `${macro.cpi_yoy}%`   : null} trend={macro.cpi_trend} indicator="cpi" />
            <MetricRow label="DXY"       value={macro.dxy       != null ? macro.dxy.toFixed(2)  : null} trend={macro.dxy_trend} indicator="dxy" />
            <MetricRow label="NFP"       value={macro.nfp_change_k != null ? `+${macro.nfp_change_k}K` : null} />
          </div>

          {dxyNote && <p className="text-[10px] text-terminal-text-dim mt-2 mb-3 italic">{dxyNote}</p>}

          {macro.next_event && (
            <div className="mb-3 px-3 py-2.5 bg-yellow-900/15 border border-yellow-800/30 rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-xs text-yellow-400 font-semibold">⏰ {macro.next_event.title}</span>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                  macro.next_event.impact === 'HIGH'
                    ? 'bg-red-900/40 text-red-400 border-red-800/40'
                    : 'bg-blue-900/40 text-blue-400 border-blue-800/40'
                }`}>
                  {macro.next_event.impact}
                </span>
              </div>
              <p className="text-[10px] text-yellow-600 mt-0.5 font-mono">{macro.next_event.countdown}</p>
            </div>
          )}

          {macro.gold_summary && (
            <p className="text-xs text-terminal-text-muted leading-relaxed border-l-2 border-gold-400/20 pl-3">
              {macro.gold_summary}
            </p>
          )}

          <p className="text-[10px] text-terminal-text-dim mt-3">FRED · Twelve Data · Forex Factory — cache 4h</p>
        </>
      ) : (
        <p className="text-xs text-terminal-text-dim">Données macro indisponibles.</p>
      )}
    </div>
  )
}
