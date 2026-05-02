import React, { useState, useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import { getPerformance, getJournalStats } from '../services/api'

function StatCard({ label, value, sub, color = 'text-terminal-base' }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-3 flex flex-col gap-0.5">
      <div className="text-[10px] text-terminal-text-dim uppercase tracking-wide">{label}</div>
      <div className={`text-xl font-bold font-mono ${color}`}>{value ?? '—'}</div>
      {sub && <div className="text-[10px] text-terminal-text-muted">{sub}</div>}
    </div>
  )
}

function WrBar({ label, wr, count }) {
  const color = wr >= 60 ? 'bg-green-500' : wr >= 45 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = wr >= 60 ? 'text-green-400' : wr >= 45 ? 'text-yellow-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-28 text-[11px] text-terminal-text-muted truncate shrink-0">{label}</div>
      <div className="flex-1 h-2 bg-terminal-bg rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(wr, 100)}%` }} />
      </div>
      <div className={`text-[11px] font-mono font-semibold w-10 text-right ${textColor}`}>{wr}%</div>
      <div className="text-[10px] text-terminal-text-dim w-10 text-right">({count})</div>
    </div>
  )
}

function SectionTitle({ children }) {
  return (
    <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-2">
      {children}
    </div>
  )
}

function EquityChart({ history }) {
  const ref      = useRef(null)
  const chartRef = useRef(null)
  useEffect(() => {
    if (!ref.current || !history?.length) return
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null }
    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 150,
      layout: { background: { color: '#0d1420' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1a2535' }, horzLines: { color: '#1a2535' } },
      rightPriceScale: { borderColor: '#253347' },
      timeScale: { borderColor: '#253347', timeVisible: false },
    })
    const lastPnl = history[history.length - 1]?.pnl || 0
    const series  = chart.addAreaSeries({
      lineColor: lastPnl >= 0 ? '#22c55e' : '#ef4444',
      topColor:   lastPnl >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
      bottomColor:'rgba(0,0,0,0.0)',
      lineWidth: 2,
      priceLineVisible: false,
    })
    try { series.setData(history.map(p => ({ time: p.date, value: p.pnl }))) } catch {}
    chart.timeScale().fitContent()
    chartRef.current = chart
    const onResize = () => { if (ref.current) chart.applyOptions({ width: ref.current.clientWidth }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [history])
  return <div ref={ref} className="w-full" />
}

export default function PerformancePanel() {
  const [data,      setData]    = useState(null)
  const [bankroll,  setBankroll] = useState([])
  const [loading,   setLoading] = useState(true)
  const [error,     setError]   = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getPerformance(),
      getJournalStats().catch(() => null),
    ]).then(([d, s]) => {
      setData(d)
      setError(d.error || null)
      if (s?.bankroll_history?.length > 1) setBankroll(s.bankroll_history)
    }).catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-xl p-6 text-center text-terminal-text-dim text-xs animate-pulse">
        Chargement performances ML…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-xl p-6 text-center text-xs text-terminal-text-muted">
        {error || 'Données indisponibles'}
        <div className="mt-1 text-[10px] text-terminal-text-dim">Fermez des trades dans le journal pour générer les stats.</div>
      </div>
    )
  }

  const pf = data.profit_factor
  const pfColor = pf == null ? 'text-terminal-text-dim' : pf >= 1.5 ? 'text-green-400' : pf >= 1 ? 'text-yellow-400' : 'text-red-400'
  const wrColor = data.win_rate >= 55 ? 'text-green-400' : data.win_rate >= 45 ? 'text-yellow-400' : 'text-red-400'

  const changes = data.weight_adjustments?.changes ?? []

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Win Rate"
          value={`${data.win_rate}%`}
          sub={`${data.wins}W / ${data.losses}L`}
          color={wrColor}
        />
        <StatCard
          label="Profit Factor"
          value={pf != null ? pf.toFixed(2) : 'N/A'}
          sub={pf >= 1.5 ? 'Excellent' : pf >= 1 ? 'Positif' : 'Négatif'}
          color={pfColor}
        />
        <StatCard
          label="Gain moyen"
          value={data.avg_win_eur ? `+${data.avg_win_eur}€` : '—'}
          color="text-green-400"
        />
        <StatCard
          label="Perte moyenne"
          value={data.avg_loss_eur ? `-${data.avg_loss_eur}€` : '—'}
          color="text-red-400"
        />
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

        {/* By direction */}
        {Object.keys(data.by_direction ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par Direction</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_direction).map(([d, v]) => (
                <WrBar key={d} label={d} wr={v.win_rate} count={v.count} />
              ))}
            </div>
          </div>
        )}

        {/* By session */}
        {Object.keys(data.by_session ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par Session</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_session)
                .sort((a, b) => b[1].win_rate - a[1].win_rate)
                .map(([s, v]) => <WrBar key={s} label={s} wr={v.win_rate} count={v.count} />)}
            </div>
          </div>
        )}

        {/* By Wyckoff */}
        {Object.keys(data.by_wyckoff ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par Phase Wyckoff</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_wyckoff)
                .sort((a, b) => b[1].win_rate - a[1].win_rate)
                .map(([p, v]) => <WrBar key={p} label={p} wr={v.win_rate} count={v.count} />)}
            </div>
          </div>
        )}

        {/* By RSI */}
        {Object.keys(data.by_rsi ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par RSI à l'entrée</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_rsi)
                .sort((a, b) => b[1].win_rate - a[1].win_rate)
                .map(([r, v]) => <WrBar key={r} label={r} wr={v.win_rate} count={v.count} />)}
            </div>
          </div>
        )}

        {/* By confluence */}
        {Object.keys(data.by_confluence ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par Confluence</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_confluence)
                .sort((a, b) => b[1].win_rate - a[1].win_rate)
                .map(([c, v]) => <WrBar key={c} label={c} wr={v.win_rate} count={v.count} />)}
            </div>
          </div>
        )}

        {/* By trend */}
        {Object.keys(data.by_trend ?? {}).length > 0 && (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <SectionTitle>Par Tendance</SectionTitle>
            <div className="space-y-2">
              {Object.entries(data.by_trend)
                .sort((a, b) => b[1].win_rate - a[1].win_rate)
                .map(([t, v]) => <WrBar key={t} label={t} wr={v.win_rate} count={v.count} />)}
            </div>
          </div>
        )}
      </div>

      {/* Equity curve */}
      {bankroll.length > 1 && (
        <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
          <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
            Courbe de Capital — P&L Réel (€)
          </div>
          <EquityChart history={bankroll} />
        </div>
      )}

      {/* ML weight adjustments */}
      <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
        <SectionTitle>Ajustements de poids ML automatiques</SectionTitle>
        {changes.length === 0 ? (
          <div className="text-[11px] text-terminal-text-dim">Aucun ajustement appliqué (données insuffisantes ou poids déjà optimaux).</div>
        ) : (
          <ul className="space-y-1">
            {changes.map((c, i) => (
              <li key={i} className="text-[11px] text-terminal-text-muted flex gap-2">
                <span className="text-gold-400">•</span>{c}
              </li>
            ))}
          </ul>
        )}

        {data.weight_adjustments?.applied && (
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
            {Object.entries(data.weight_adjustments.applied).map(([k, v]) => {
              const vn = Number(v)
              const color = vn > 1.1 ? 'text-green-400' : vn < 0.9 ? 'text-red-400' : 'text-terminal-text-muted'
              return (
                <div key={k} className="flex flex-col items-center bg-terminal-bg rounded p-1.5">
                  <div className="text-[9px] text-terminal-text-dim truncate w-full text-center">{k}</div>
                  <div className={`text-xs font-mono font-semibold ${color}`}>{vn.toFixed(2)}×</div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {data.generated_at && (
        <div className="text-[10px] text-terminal-text-dim text-right">
          Généré le {new Date(data.generated_at).toLocaleString('fr-FR')} · basé sur {data.total_trades} trades
        </div>
      )}
    </div>
  )
}
