import React, { useState, useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import { getBacktest } from '../services/api'

function KpiCard({ label, value, sub, color = 'text-terminal-base' }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-3 flex flex-col gap-0.5">
      <div className="text-[10px] text-terminal-text-dim uppercase tracking-wide">{label}</div>
      <div className={`text-xl font-bold font-mono ${color}`}>{value ?? '—'}</div>
      {sub && <div className="text-[10px] text-terminal-text-muted">{sub}</div>}
    </div>
  )
}

function AnnualRow({ year, data, maxRR }) {
  const isPos  = data.total_rr >= 0
  const width  = maxRR > 0 ? Math.min(Math.abs(data.total_rr) / maxRR * 100, 100) : 0
  const barCls = isPos ? 'bg-green-500' : 'bg-red-500'
  const rrCls  = isPos ? 'text-green-400' : 'text-red-400'

  return (
    <div className="flex items-center gap-3">
      <div className="text-[11px] font-mono text-terminal-text-muted w-10 shrink-0">{year}</div>
      <div className="flex-1 h-2 bg-terminal-bg rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barCls}`} style={{ width: `${width}%` }} />
      </div>
      <div className={`text-[11px] font-mono font-semibold w-14 text-right ${rrCls}`}>
        {isPos ? '+' : ''}{data.total_rr}R
      </div>
      <div className="text-[11px] font-mono text-terminal-text-dim w-10 text-right">{data.win_rate}%</div>
      <div className="text-[10px] text-terminal-text-dim w-8 text-right">({data.trades})</div>
    </div>
  )
}

function EquityCurveChart({ curve }) {
  const ref      = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!ref.current || !curve?.length) return
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null }

    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 180,
      layout: { background: { color: '#0d1420' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1a2535' }, horzLines: { color: '#1a2535' } },
      rightPriceScale: { borderColor: '#253347' },
      timeScale: { borderColor: '#253347', timeVisible: false },
      crosshair: { mode: 0 },
    })

    const series = chart.addAreaSeries({
      lineColor: '#d4a82a',
      topColor:   'rgba(212,168,42,0.25)',
      bottomColor:'rgba(212,168,42,0.02)',
      lineWidth: 2,
      priceLineVisible: false,
    })

    const formatted = curve.map(p => ({ time: p.date, value: p.equity_r }))
    try { series.setData(formatted) } catch {}
    chart.timeScale().fitContent()
    chartRef.current = chart

    const onResize = () => { if (ref.current) chart.applyOptions({ width: ref.current.clientWidth }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [curve])

  return <div ref={ref} className="w-full" />
}

export default function BacktestPanel() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [years,   setYears]   = useState(5)

  const load = (y) => {
    setLoading(true)
    setError(null)
    getBacktest(y)
      .then(d => { setData(d); setError(d.error || null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(years) }, [])

  const handleYearsChange = (y) => {
    setYears(y)
    load(y)
  }

  if (loading) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-xl p-8 text-center">
        <div className="text-terminal-text-dim text-xs animate-pulse">
          Exécution du backtest {years} ans…
        </div>
        <div className="text-[10px] text-terminal-text-dim mt-1">Téléchargement des données XAUUSD via Yahoo Finance…</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-xl p-6 text-center text-xs text-terminal-text-muted">
        {error || 'Données indisponibles'}
      </div>
    )
  }

  const wrColor  = data.win_rate >= 55 ? 'text-green-400' : data.win_rate >= 45 ? 'text-yellow-400' : 'text-red-400'
  const pfColor  = !data.profit_factor ? 'text-terminal-text-dim'
                 : data.profit_factor >= 1.5 ? 'text-green-400'
                 : data.profit_factor >= 1   ? 'text-yellow-400'
                 : 'text-red-400'
  const shrColor = data.sharpe_ratio >= 1 ? 'text-green-400' : data.sharpe_ratio >= 0 ? 'text-yellow-400' : 'text-red-400'
  const pnlColor = data.total_pnl_rr >= 0 ? 'text-green-400' : 'text-red-400'

  const annual = data.annual_breakdown ?? {}
  const maxRR  = Math.max(...Object.values(annual).map(v => Math.abs(v.total_rr)), 1)

  return (
    <div className="space-y-4">
      {/* Year selector */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-terminal-text-dim">Période :</span>
        {[3, 5, 7, 10].map(y => (
          <button
            key={y}
            onClick={() => handleYearsChange(y)}
            className={`px-3 py-1 text-[11px] rounded border transition-colors ${
              years === y
                ? 'bg-gold-400/20 border-gold-400/60 text-gold-400'
                : 'border-terminal-border text-terminal-text-dim hover:border-terminal-muted'
            }`}
          >
            {y} ans
          </button>
        ))}
        <span className="ml-auto text-[10px] text-terminal-text-dim">
          {data.candles_analyzed} bougies · {data.total_trades} trades simulés
        </span>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-3">
        <KpiCard label="Win Rate"      value={`${data.win_rate}%`}              sub={`${data.wins}W / ${data.losses}L`}  color={wrColor}  />
        <KpiCard label="Profit Factor" value={data.profit_factor?.toFixed(2) ?? 'N/A'}  sub="gross win / gross loss"       color={pfColor}  />
        <KpiCard label="Sharpe Ratio"  value={data.sharpe_ratio}               sub="annualisé (R units)"                 color={shrColor} />
        <KpiCard label="PnL Total"     value={`${data.total_pnl_rr >= 0 ? '+' : ''}${data.total_pnl_rr}R`}  sub={`${data.years} ans`}  color={pnlColor} />
        <KpiCard label="Max Drawdown"  value={`-${data.max_drawdown_rr}R`}     sub="en unités R"                         color="text-red-400" />
        <KpiCard label="Gain moy."     value={`+${data.avg_win_rr}R`}          color="text-green-400" />
        <KpiCard label="Perte moy."    value={`${data.avg_loss_rr}R`}          color="text-red-400"  />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Annual breakdown */}
        <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
          <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
            Breakdown annuel
          </div>
          <div className="flex items-center gap-3 mb-2 text-[9px] text-terminal-text-dim">
            <div className="w-10">Année</div>
            <div className="flex-1">PnL</div>
            <div className="w-14 text-right">Σ R</div>
            <div className="w-10 text-right">WR</div>
            <div className="w-8 text-right">N</div>
          </div>
          <div className="space-y-2">
            {Object.entries(annual)
              .sort((a, b) => a[0].localeCompare(b[0]))
              .map(([yr, d]) => (
                <AnnualRow key={yr} year={yr} data={d} maxRR={maxRR} />
              ))}
          </div>
        </div>

        {/* By direction + metrics */}
        <div className="space-y-4">
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
              Par Direction
            </div>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(data.by_direction ?? {}).map(([dir, v]) => {
                const wr = v.win_rate
                const c  = wr == null ? 'text-terminal-text-dim'
                         : wr >= 55   ? 'text-green-400'
                         : wr >= 45   ? 'text-yellow-400'
                         : 'text-red-400'
                return (
                  <div key={dir} className="bg-terminal-bg rounded-lg p-3 text-center">
                    <div className={`text-xs font-semibold ${dir === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{dir}</div>
                    <div className={`text-lg font-bold font-mono ${c}`}>{wr != null ? `${wr}%` : '—'}</div>
                    <div className="text-[10px] text-terminal-text-dim">{v.trades} trades</div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
              Fréquence
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-terminal-text-muted">Trades / an</span>
              <span className="font-mono text-terminal-base font-semibold">{data.trades_per_year}</span>
            </div>
            <div className="flex items-center justify-between text-xs mt-2">
              <span className="text-terminal-text-muted">Période analysée</span>
              <span className="font-mono text-terminal-base">{data.years} ans</span>
            </div>
          </div>
        </div>
      </div>

      {/* Equity curve */}
      {data.equity_curve?.length > 1 && (
        <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
          <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3 flex items-center justify-between">
            <span>Courbe de Capital (R cumulatifs)</span>
            <span className={`font-mono ${data.total_pnl_rr >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.total_pnl_rr >= 0 ? '+' : ''}{data.total_pnl_rr}R final
            </span>
          </div>
          <EquityCurveChart curve={data.equity_curve} />
          <div className="mt-2 flex items-center gap-4 text-[10px]">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-0.5 bg-gold-400 rounded" />
              <span className="text-terminal-text-dim">Stratégie SMC/ICT</span>
            </div>
            <div className="text-terminal-text-dim">
              Max DD : <span className="text-red-400 font-mono">-{data.max_drawdown_rr}R</span>
            </div>
            <div className="text-terminal-text-dim">
              Sharpe : <span className={`font-mono ${data.sharpe_ratio >= 1 ? 'text-green-400' : 'text-yellow-400'}`}>{data.sharpe_ratio}</span>
            </div>
          </div>
        </div>
      )}

      {/* Buy & Hold comparison */}
      {data.annual_breakdown && Object.keys(data.annual_breakdown).length > 0 && (() => {
        const annualEntries = Object.entries(data.annual_breakdown)
        const strategyPnl = data.total_pnl_rr
        const bhNote = "Le Buy & Hold XAUUSD sur la même période est disponible via les données de prix réels. Cette stratégie actif-passif montre que le trading actif a du sens uniquement si le profit factor > 1."
        const pfOk = data.profit_factor && data.profit_factor > 1.0
        return (
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
              Synthèse stratégie
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-terminal-bg rounded-lg p-3">
                <div className="text-[10px] text-terminal-text-dim">Stratégie SMC/ICT</div>
                <div className={`text-lg font-bold font-mono mt-0.5 ${strategyPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {strategyPnl >= 0 ? '+' : ''}{strategyPnl}R
                </div>
                <div className="text-[10px] text-terminal-text-dim mt-0.5">
                  {data.trades_per_year} trades/an · PF {data.profit_factor || '?'}
                </div>
              </div>
              <div className="bg-terminal-bg rounded-lg p-3">
                <div className="text-[10px] text-terminal-text-dim">Profil de risque</div>
                <div className={`text-sm font-bold mt-0.5 ${pfOk ? 'text-green-400' : 'text-red-400'}`}>
                  {pfOk ? '✅ Profitable' : '❌ Non-profitable'}
                </div>
                <div className="text-[10px] text-terminal-text-dim mt-0.5">
                  Profit factor {pfOk ? `${data.profit_factor} > 1` : `${data.profit_factor || '?'} < 1`}
                </div>
              </div>
            </div>
            <div className="mt-2 text-[10px] text-terminal-text-dim italic">{bhNote}</div>
          </div>
        )
      })()}

      {/* Disclaimer */}
      {data.note && (
        <div className="text-[10px] text-terminal-text-dim italic border-t border-terminal-border pt-2">
          ⚠ {data.note}
        </div>
      )}
    </div>
  )
}
