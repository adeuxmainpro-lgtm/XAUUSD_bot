import React, { useState, useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import {
  getTrades, createTrade, updateTrade, deleteTrade,
  getJournalStats, getJournalDetailed, analyzeTrade,
  getLatestAnalysis, exportTradesCSV,
} from '../services/api'

const STATUS_COLORS = {
  OPEN: 'text-green-400 bg-green-900/30 border-green-700',
  WIN:  'text-green-400 bg-green-900/30 border-green-800',
  LOSS: 'text-red-400 bg-red-900/30 border-red-800',
  BE:   'text-gray-400 bg-gray-800 border-gray-700',
}

function OpenBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs border text-green-400 bg-green-900/30 border-green-700">
      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
      OPEN
    </span>
  )
}

const EMPTY_FORM = {
  trade_date:    new Date().toISOString().split('T')[0],
  direction:     'BUY',
  entry_price:   '',
  stop_loss:     '',
  take_profit_1: '',
  take_profit_2: '',
  exit_price:    '',
  status:        'OPEN',
  profit_eur:    '',
  lot_size:      '0.01',
  notes:         '',
}

// ─────────────────────────────────────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({ label, value, color = 'text-gray-200' }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg px-3 py-2">
      <div className="text-[10px] text-terminal-text-dim mb-0.5">{label}</div>
      <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
    </div>
  )
}

function StatRow({ label, value, color = 'text-gray-300' }) {
  return (
    <div className="flex justify-between text-xs py-1 border-b border-terminal-border">
      <span className="text-terminal-text-muted">{label}</span>
      <span className={`font-mono font-semibold ${color}`}>{value}</span>
    </div>
  )
}

function WrBar({ label, wr, count, pnl }) {
  if (wr == null) return null
  const color    = wr >= 60 ? 'bg-green-500' : wr >= 45 ? 'bg-yellow-500' : 'bg-red-500'
  const txtColor = wr >= 60 ? 'text-green-400' : wr >= 45 ? 'text-yellow-400' : 'text-red-400'
  const pnlColor = pnl >= 0 ? 'text-green-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-28 text-[11px] text-terminal-text-muted truncate shrink-0">{label}</div>
      <div className="flex-1 h-2 bg-terminal-bg rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(wr, 100)}%` }} />
      </div>
      <div className={`text-[11px] font-mono font-semibold w-10 text-right ${txtColor}`}>{wr}%</div>
      <div className="text-[10px] text-terminal-text-dim w-8 text-right">({count})</div>
      {pnl !== undefined && (
        <div className={`text-[10px] font-mono w-16 text-right ${pnlColor}`}>
          {pnl >= 0 ? '+' : ''}{pnl}€
        </div>
      )}
    </div>
  )
}

const _DAYS_ORDER = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi']

function WeekdayHeatmap({ byWeekday }) {
  if (!byWeekday || !Object.keys(byWeekday).length) return null
  const maxAbs = Math.max(...Object.values(byWeekday).map(v => Math.abs(v.pnl || 0)), 1)
  return (
    <div className="flex gap-1">
      {_DAYS_ORDER.map(day => {
        const d = byWeekday[day]
        if (!d) return (
          <div key={day} className="flex-1 text-center">
            <div className="text-[9px] text-terminal-text-dim mb-1">{day.slice(0,3)}</div>
            <div className="h-12 bg-terminal-bg rounded opacity-30" />
          </div>
        )
        const intensity = Math.round((Math.abs(d.pnl || 0) / maxAbs) * 100)
        const isPos = (d.pnl || 0) >= 0
        const bg = isPos
          ? `rgba(34,197,94,${0.1 + intensity * 0.008})`
          : `rgba(239,68,68,${0.1 + intensity * 0.008})`
        const wr = d.win_rate
        const wrColor = wr >= 60 ? 'text-green-400' : wr >= 45 ? 'text-yellow-400' : 'text-red-400'
        return (
          <div key={day} className="flex-1 text-center">
            <div className="text-[9px] text-terminal-text-dim mb-1">{day.slice(0,3)}</div>
            <div
              className="h-12 rounded flex flex-col items-center justify-center gap-0.5"
              style={{ background: bg }}
            >
              <div className={`text-[10px] font-semibold ${wrColor}`}>{wr}%</div>
              <div className="text-[9px] text-terminal-text-dim">({d.count})</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function TradeJournal() {
  const [trades,       setTrades]       = useState([])
  const [stats,        setStats]        = useState(null)
  const [detailed,     setDetailed]     = useState(null)
  const [showForm,     setShowForm]     = useState(false)
  const [editingTrade, setEditingTrade] = useState(null)
  const [form,         setForm]         = useState(EMPTY_FORM)
  const [aiAnalysis,   setAiAnalysis]   = useState({})
  const [loadingAI,    setLoadingAI]    = useState({})
  const [loading,      setLoading]      = useState(true)
  const [activeTab,    setActiveTab]    = useState('trades')
  const chartRef      = useRef(null)
  const chartInstance = useRef(null)

  const load = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [t, s, d] = await Promise.all([getTrades(), getJournalStats(), getJournalDetailed()])
      setTrades(t)
      setStats(s)
      setDetailed(d)
    } catch (e) { console.error(e) }
    if (!silent) setLoading(false)
  }

  useEffect(() => {
    load()
    // Poll every 30 s to reflect automatic TP1/SL closures without page reload
    const interval = setInterval(() => load(true), 30_000)
    return () => clearInterval(interval)
  }, [])

  // Bankroll chart
  useEffect(() => {
    if (!chartRef.current || !stats?.bankroll_history?.length) return
    if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }
    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 160,
      layout: { background: { color: '#0d1420' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1a2535' }, horzLines: { color: '#1a2535' } },
      rightPriceScale: { borderColor: '#253347' },
      timeScale: { borderColor: '#253347', timeVisible: true },
    })
    const series = chart.addLineSeries({ color: '#d4a82a', lineWidth: 2, priceLineVisible: false })
    series.setData(stats.bankroll_history.map(p => ({ time: p.date, value: p.pnl })))
    chart.timeScale().fitContent()
    chartInstance.current = chart
    const onResize = () => { if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth }) }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [stats])

  const openNewForm = async () => {
    let prefill = { ...EMPTY_FORM }
    try {
      const analysis = await getLatestAnalysis()
      if (analysis && !analysis.message) {
        prefill.entry_price   = analysis.entry?.toString() || ''
        prefill.stop_loss     = analysis.stop_loss?.toString() || ''
        prefill.take_profit_1 = analysis.take_profit_1?.toString() || ''
        prefill.take_profit_2 = analysis.take_profit_2?.toString() || ''
        prefill.direction     = ['BUY','SELL'].includes(analysis.direction) ? analysis.direction : 'BUY'
      }
    } catch {}
    setForm(prefill)
    setEditingTrade(null)
    setShowForm(true)
  }

  const openEditForm = (trade) => {
    setForm({
      trade_date:    trade.trade_date    || '',
      direction:     trade.direction     || 'BUY',
      entry_price:   trade.entry_price?.toString()   || '',
      stop_loss:     trade.stop_loss?.toString()      || '',
      take_profit_1: trade.take_profit_1?.toString()  || '',
      take_profit_2: trade.take_profit_2?.toString()  || '',
      exit_price:    trade.exit_price?.toString()     || '',
      status:        trade.status        || 'OPEN',
      profit_eur:    trade.profit_eur?.toString()     || '',
      lot_size:      trade.lot_size?.toString()       || '0.01',
      notes:         trade.notes         || '',
    })
    setEditingTrade(trade)
    setShowForm(true)
  }

  const calcPnl = (direction, entry, exit, lot) => {
    const e = parseFloat(entry)
    const x = parseFloat(exit)
    const l = parseFloat(lot) || 0.01
    if (!e || !x) return ''
    const pnl = direction === 'BUY'
      ? (x - e) * l * 100
      : (e - x) * l * 100
    return pnl.toFixed(2)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const entry    = parseFloat(form.entry_price)
    const exitP    = form.exit_price ? parseFloat(form.exit_price) : null
    const lot      = parseFloat(form.lot_size) || 0.01
    const manualPnl = form.profit_eur !== '' ? parseFloat(form.profit_eur) : null

    // Auto-calculate P&L if exit_price is set and user left P&L blank
    let profit_eur = manualPnl
    if (exitP !== null && manualPnl === null) {
      profit_eur = parseFloat(calcPnl(form.direction, entry, exitP, lot)) || 0
    }

    const payload = {
      trade_date: form.trade_date,
      direction:  form.direction,
      entry_price:   entry,
      stop_loss:     form.stop_loss     ? parseFloat(form.stop_loss)     : null,
      take_profit_1: form.take_profit_1 ? parseFloat(form.take_profit_1) : null,
      take_profit_2: form.take_profit_2 ? parseFloat(form.take_profit_2) : null,
      exit_price:    exitP,
      status:        form.status,
      profit_eur:    profit_eur ?? 0,
      lot_size:      lot,
      notes:         form.notes || null,
    }
    try {
      editingTrade ? await updateTrade(editingTrade.id, payload) : await createTrade(payload)
      setShowForm(false)
      await load()
    } catch (e) { console.error(e) }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce trade ?')) return
    try { await deleteTrade(id); await load() } catch {}
  }

  const handleAIAnalyze = async (trade) => {
    setLoadingAI(p => ({ ...p, [trade.id]: true }))
    try {
      const res = await analyzeTrade(trade.id)
      setAiAnalysis(p => ({ ...p, [trade.id]: res.analysis }))
    } catch {}
    setLoadingAI(p => ({ ...p, [trade.id]: false }))
  }

  const handleExportCSV = async () => {
    try {
      const blob = await exportTradesCSV()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `xauusd_trades_${new Date().toISOString().split('T')[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {}
  }

  // Current streak display
  const streak = detailed?.streak || 0
  const streakLabel = streak > 0
    ? `🟢 ${streak} gains consécutifs`
    : streak < 0
    ? `🔴 ${Math.abs(streak)} pertes consécutives`
    : '—'

  const openCount = trades.filter(t => t.status === 'OPEN').length

  const INNER_TABS = [
    { id: 'trades',  label: 'Trades' },
    { id: 'stats',   label: 'Analyses' },
    { id: 'heatmap', label: 'Heatmap' },
  ]

  return (
    <div className="max-w-[1600px] mx-auto px-4 py-4 space-y-4">

      {/* KPI Banner */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-9 gap-2">
          <StatCard label="Trades" value={stats.total_trades} />
          <StatCard label="Gains"  value={stats.wins}  color="text-green-400" />
          <StatCard label="Pertes" value={stats.losses} color="text-red-400" />
          <StatCard label="Win Rate"
            value={`${stats.win_rate}%`}
            color={stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}
          />
          <StatCard label="Profit Factor"
            value={stats.profit_factor === Infinity ? '∞' : stats.profit_factor}
            color={stats.profit_factor >= 1 ? 'text-green-400' : 'text-red-400'}
          />
          <StatCard label="P&L Total"
            value={`€${stats.total_pnl}`}
            color={stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}
          />
          <StatCard label="Max Drawdown" value={`€${stats.max_drawdown}`} color="text-red-400" />
          <StatCard label="Meilleure série" value={stats.best_streak} color="text-green-400" />
          <StatCard label="Streak actuel" value={streakLabel} color={streak > 0 ? 'text-green-400' : streak < 0 ? 'text-red-400' : 'text-gray-400'} />
        </div>
      )}

      {/* Inner tabs */}
      <div className="flex gap-0 border-b border-terminal-border">
        {INNER_TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-xs font-semibold tracking-wide border-b-2 -mb-px transition-colors ${
              activeTab === t.id
                ? 'border-gold-400 text-gold-400'
                : 'border-transparent text-terminal-text-dim hover:text-terminal-text-muted'
            }`}
          >
            {t.label}
            {t.id === 'trades' && openCount > 0 && (
              <span className="ml-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-green-900/40 text-green-400 border border-green-700/50">
                <span className="w-1 h-1 rounded-full bg-green-400 animate-pulse inline-block" />
                {openCount}
              </span>
            )}
          </button>
        ))}
        {openCount > 0 && (
          <div className="flex items-center gap-1.5 ml-2 text-[10px] text-green-400 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Suivi auto actif
          </div>
        )}
        <div className="ml-auto flex items-center gap-2 pb-1">
          <button
            onClick={handleExportCSV}
            className="px-3 py-1 text-[11px] border border-terminal-border text-terminal-text-dim hover:text-terminal-base hover:border-terminal-muted rounded transition-colors"
          >
            ↓ Export CSV
          </button>
          <button
            onClick={openNewForm}
            className="px-3 py-1.5 bg-gold-400 text-black text-xs font-bold rounded hover:bg-gold-300 transition-colors"
          >
            + Nouveau trade
          </button>
        </div>
      </div>

      {/* ── TRADES TAB ── */}
      {activeTab === 'trades' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
          {/* Trades table */}
          <div className="space-y-2">
            {loading && <div className="text-xs text-terminal-text-dim animate-pulse">Chargement...</div>}
            {!loading && trades.length === 0 && (
              <div className="bg-terminal-card border border-terminal-border rounded-lg p-8 text-center">
                <p className="text-terminal-text-muted text-sm">Aucun trade enregistré.</p>
              </div>
            )}
            {trades.length > 0 && (
              <div className="bg-terminal-card border border-terminal-border rounded-lg overflow-x-auto">
                <table className="w-full text-xs min-w-[700px]">
                  <thead>
                    <tr className="border-b border-terminal-border text-terminal-text-dim">
                      <th className="text-left px-3 py-2">Date</th>
                      <th className="text-left px-3 py-2">Dir.</th>
                      <th className="text-right px-3 py-2">Entrée</th>
                      <th className="text-right px-3 py-2">Sortie</th>
                      <th className="text-right px-3 py-2">P&L €</th>
                      <th className="text-left px-3 py-2">Statut</th>
                      <th className="text-left px-3 py-2">Session</th>
                      <th className="text-right px-3 py-2">Score</th>
                      <th className="text-right px-3 py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map(trade => (
                      <React.Fragment key={trade.id}>
                        <tr className="border-b border-terminal-border/50 hover:bg-terminal-bg/30 transition-colors">
                          <td className="px-3 py-2 text-terminal-text-dim">{trade.trade_date}</td>
                          <td className="px-3 py-2">
                            <span className={`font-bold ${trade.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                              {trade.direction}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-terminal-base">${trade.entry_price?.toFixed(2)}</td>
                          <td className="px-3 py-2 text-right font-mono text-terminal-text-muted">
                            {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '—'}
                          </td>
                          <td className={`px-3 py-2 text-right font-mono font-semibold ${
                            trade.profit_eur > 0 ? 'text-green-400' : trade.profit_eur < 0 ? 'text-red-400' : 'text-terminal-text-muted'
                          }`}>
                            {trade.profit_eur > 0 ? '+' : ''}{trade.profit_eur?.toFixed(2)}€
                          </td>
                          <td className="px-3 py-2">
                            {trade.status === 'OPEN' ? (
                              <OpenBadge />
                            ) : (
                              <span className={`px-2 py-0.5 rounded text-xs border ${STATUS_COLORS[trade.status] || STATUS_COLORS.OPEN}`}>
                                {trade.status}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-terminal-text-dim">
                            {trade.session_at_entry ? (
                              <span className="text-[10px] text-gold-400">{trade.session_at_entry}</span>
                            ) : '—'}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {trade.trade_score != null ? (
                              <span className={`font-mono text-[11px] font-semibold ${
                                trade.trade_score >= 80 ? 'text-green-400' :
                                trade.trade_score >= 70 ? 'text-yellow-400' : 'text-terminal-text-dim'
                              }`}>
                                {trade.trade_score}/100
                              </span>
                            ) : '—'}
                          </td>
                          <td className="px-3 py-2 text-right space-x-2">
                            {trade.status === 'LOSS' && (
                              <button
                                onClick={() => handleAIAnalyze(trade)}
                                disabled={loadingAI[trade.id]}
                                className="text-purple-400 hover:text-purple-300 disabled:opacity-50"
                                title="Analyser avec IA"
                              >
                                {loadingAI[trade.id] ? '…' : '🤖'}
                              </button>
                            )}
                            <button onClick={() => openEditForm(trade)} className="text-terminal-text-dim hover:text-gold-400">✎</button>
                            <button onClick={() => handleDelete(trade.id)} className="text-terminal-text-dim hover:text-red-400">✕</button>
                          </td>
                        </tr>
                        {aiAnalysis[trade.id] && (
                          <tr>
                            <td colSpan={9} className="px-4 py-3 bg-purple-900/20 border-b border-terminal-border">
                              <div className="text-xs text-purple-200 whitespace-pre-line leading-relaxed">
                                <span className="text-purple-400 font-semibold">🤖 Analyse IA: </span>
                                {aiAnalysis[trade.id]}
                              </div>
                            </td>
                          </tr>
                        )}
                        {trade.notes && !aiAnalysis[trade.id] && (
                          <tr>
                            <td colSpan={9} className="px-4 py-1 bg-terminal-bg border-b border-terminal-border">
                              <span className="text-[11px] text-terminal-text-dim">📝 {trade.notes}</span>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Bankroll chart + basic stats */}
          <div className="space-y-4">
            <div className="bg-terminal-card border border-terminal-border rounded-lg p-4">
              <h3 className="text-xs font-semibold text-terminal-text-dim uppercase tracking-wider mb-3">P&L cumulé</h3>
              {stats?.bankroll_history?.length > 1 ? (
                <div ref={chartRef} className="w-full" />
              ) : (
                <div className="h-40 flex items-center justify-center text-xs text-terminal-text-dim">
                  Pas encore assez de trades clôturés.
                </div>
              )}
            </div>
            {stats && stats.total_trades > 0 && (
              <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-1">
                <h3 className="text-xs font-semibold text-terminal-text-dim uppercase tracking-wider mb-2">Statistiques</h3>
                <StatRow label="Gain moyen"     value={`€${stats.avg_win}`}          color="text-green-400" />
                <StatRow label="Perte moyenne"  value={`-€${stats.avg_loss}`}        color="text-red-400" />
                <StatRow label="Pire série"     value={`${stats.worst_streak} pertes`} color="text-red-400" />
                <StatRow label="Meilleure série" value={`${stats.best_streak} gains`}  color="text-green-400" />
                <StatRow label="Streak actuel"  value={streakLabel} color={streak > 0 ? 'text-green-400' : streak < 0 ? 'text-red-400' : 'text-terminal-text-dim'} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── STATS TAB ── */}
      {activeTab === 'stats' && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {detailed?.by_session && Object.keys(detailed.by_session).length > 0 && (
            <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
                Win Rate par Session
              </div>
              <div className="space-y-2">
                {Object.entries(detailed.by_session)
                  .sort((a, b) => (b[1].win_rate || 0) - (a[1].win_rate || 0))
                  .map(([s, v]) => (
                    <WrBar key={s} label={s} wr={v.win_rate} count={v.count} pnl={v.pnl} />
                  ))}
              </div>
            </div>
          )}

          {detailed?.by_score && Object.keys(detailed.by_score).length > 0 && (
            <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
                Win Rate par Score SMC/ICT
              </div>
              <div className="space-y-2">
                {Object.entries(detailed.by_score)
                  .sort((a, b) => (b[1].win_rate || 0) - (a[1].win_rate || 0))
                  .map(([b, v]) => (
                    <WrBar key={b} label={b} wr={v.win_rate} count={v.count} />
                  ))}
              </div>
            </div>
          )}

          {detailed?.by_weekday && Object.keys(detailed.by_weekday).length > 0 && (
            <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-3">
                Win Rate par Jour de la Semaine
              </div>
              <div className="space-y-2">
                {_DAYS_ORDER
                  .filter(d => detailed.by_weekday[d])
                  .map(d => (
                    <WrBar key={d} label={d} wr={detailed.by_weekday[d].win_rate} count={detailed.by_weekday[d].count} pnl={detailed.by_weekday[d].pnl} />
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── HEATMAP TAB ── */}
      {activeTab === 'heatmap' && (
        <div className="space-y-6">
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
            <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-4">
              Heatmap Performances — par Jour de la Semaine
            </div>
            {detailed?.by_weekday ? (
              <WeekdayHeatmap byWeekday={detailed.by_weekday} />
            ) : (
              <div className="text-xs text-terminal-text-dim text-center py-4">Données insuffisantes</div>
            )}
            <div className="mt-3 text-[10px] text-terminal-text-dim">
              Intensité = P&L absolu · Couleur = positif (vert) / négatif (rouge) · Valeur = win rate %
            </div>
          </div>

          {detailed?.by_session && Object.keys(detailed.by_session).length > 0 && (
            <div className="bg-terminal-card border border-terminal-border rounded-xl p-4">
              <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest border-b border-terminal-border pb-1 mb-4">
                Heatmap Performances — par Session
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(detailed.by_session)
                  .sort((a, b) => (b[1].win_rate || 0) - (a[1].win_rate || 0))
                  .map(([s, v]) => {
                    const wr = v.win_rate || 0
                    const bg = wr >= 60
                      ? 'bg-green-900/30 border-green-800/40'
                      : wr >= 45
                      ? 'bg-yellow-900/20 border-yellow-800/40'
                      : 'bg-red-900/20 border-red-800/40'
                    const tc = wr >= 60 ? 'text-green-400' : wr >= 45 ? 'text-yellow-400' : 'text-red-400'
                    return (
                      <div key={s} className={`border rounded-lg p-3 text-center ${bg}`}>
                        <div className="text-[11px] text-terminal-text-muted truncate">{s}</div>
                        <div className={`text-xl font-bold font-mono mt-1 ${tc}`}>{wr}%</div>
                        <div className="text-[10px] text-terminal-text-dim">{v.count} trades</div>
                        <div className={`text-[10px] font-mono ${v.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {v.pnl >= 0 ? '+' : ''}{v.pnl}€
                        </div>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TRADE FORM MODAL ── */}
      {showForm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-terminal-card border border-terminal-border rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-terminal-base">
                {editingTrade ? 'Modifier le trade' : 'Nouveau trade'}
              </h3>
              <button onClick={() => setShowForm(false)} className="text-terminal-text-dim hover:text-white text-lg">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date" type="date" value={form.trade_date}
                  onChange={v => setForm(p => ({ ...p, trade_date: v }))} required />
                <div>
                  <label className="text-xs text-terminal-text-dim mb-1 block">Direction</label>
                  <select value={form.direction} onChange={e => setForm(p => ({ ...p, direction: e.target.value }))}
                    className="w-full bg-terminal-bg border border-terminal-border rounded px-2 py-1.5 text-xs text-terminal-base">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Prix d'entrée" type="number" step="0.01" value={form.entry_price}
                  onChange={v => setForm(p => ({ ...p, entry_price: v }))} required />
                <Field label="Stop Loss" type="number" step="0.01" value={form.stop_loss}
                  onChange={v => setForm(p => ({ ...p, stop_loss: v }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="TP1" type="number" step="0.01" value={form.take_profit_1}
                  onChange={v => setForm(p => ({ ...p, take_profit_1: v }))} />
                <Field label="TP2" type="number" step="0.01" value={form.take_profit_2}
                  onChange={v => setForm(p => ({ ...p, take_profit_2: v }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Prix de sortie" type="number" step="0.01" value={form.exit_price}
                  onChange={v => setForm(p => ({ ...p, exit_price: v }))} />
                <Field label="Lot size" type="number" step="0.001" value={form.lot_size}
                  onChange={v => setForm(p => ({ ...p, lot_size: v }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-terminal-text-dim mb-1 block">Statut</label>
                  <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                    className="w-full bg-terminal-bg border border-terminal-border rounded px-2 py-1.5 text-xs text-terminal-base">
                    <option value="OPEN">OPEN</option>
                    <option value="WIN">WIN</option>
                    <option value="LOSS">LOSS</option>
                    <option value="BE">BE (Break-Even)</option>
                  </select>
                </div>
                <Field label="P&L (€)" type="number" step="0.01" value={form.profit_eur}
                  onChange={v => setForm(p => ({ ...p, profit_eur: v }))} />
              </div>
              <div>
                <label className="text-xs text-terminal-text-dim mb-1 block">Notes</label>
                <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                  rows={2}
                  className="w-full bg-terminal-bg border border-terminal-border rounded px-2 py-1.5 text-xs text-terminal-base resize-none"
                  placeholder="Raison de l'entrée, contexte..." />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit"
                  className="flex-1 py-2 bg-gold-400 text-black text-xs font-bold rounded hover:bg-gold-300 transition-colors">
                  {editingTrade ? 'Mettre à jour' : 'Enregistrer'}
                </button>
                <button type="button" onClick={() => setShowForm(false)}
                  className="flex-1 py-2 bg-terminal-bg text-terminal-text-muted text-xs rounded hover:bg-terminal-border transition-colors">
                  Annuler
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, onChange, ...props }) {
  return (
    <div>
      <label className="text-xs text-terminal-text-dim mb-1 block">{label}</label>
      <input
        {...props}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-terminal-bg border border-terminal-border rounded px-2 py-1.5 text-xs text-terminal-base font-mono"
      />
    </div>
  )
}
