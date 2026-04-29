import React, { useState, useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import { getTrades, createTrade, updateTrade, deleteTrade, getJournalStats, analyzeTrade, getLatestAnalysis } from '../services/api'

const STATUS_COLORS = {
  OPEN: 'text-blue-400 bg-blue-900/30 border-blue-800',
  WIN: 'text-green-400 bg-green-900/30 border-green-800',
  LOSS: 'text-red-400 bg-red-900/30 border-red-800',
  BE: 'text-gray-400 bg-gray-800 border-gray-700',
}

const EMPTY_FORM = {
  trade_date: new Date().toISOString().split('T')[0],
  direction: 'BUY',
  entry_price: '',
  stop_loss: '',
  take_profit_1: '',
  take_profit_2: '',
  exit_price: '',
  status: 'OPEN',
  profit_eur: '',
  lot_size: '0.01',
  notes: '',
}

export default function TradeJournal() {
  const [trades, setTrades] = useState([])
  const [stats, setStats] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editingTrade, setEditingTrade] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [aiAnalysis, setAiAnalysis] = useState({})
  const [loadingAI, setLoadingAI] = useState({})
  const [loading, setLoading] = useState(true)
  const chartRef = useRef(null)
  const chartInstance = useRef(null)

  const load = async () => {
    setLoading(true)
    try {
      const [t, s] = await Promise.all([getTrades(), getJournalStats()])
      setTrades(t)
      setStats(s)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  // Bankroll chart
  useEffect(() => {
    if (!chartRef.current || !stats?.bankroll_history?.length) return
    if (chartInstance.current) {
      chartInstance.current.remove()
      chartInstance.current = null
    }
    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 160,
      layout: { background: { color: '#111827' }, textColor: '#9CA3AF' },
      grid: { vertLines: { color: '#1F2937' }, horzLines: { color: '#1F2937' } },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: { borderColor: '#374151', timeVisible: true },
    })
    const series = chart.addLineSeries({
      color: '#EAB308',
      lineWidth: 2,
      priceLineVisible: false,
    })
    const chartData = stats.bankroll_history.map(p => ({
      time: p.date,
      value: p.pnl,
    }))
    series.setData(chartData)
    chart.timeScale().fitContent()
    chartInstance.current = chart

    const handleResize = () => {
      if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [stats])

  const openNewForm = async () => {
    let prefill = { ...EMPTY_FORM }
    try {
      const analysis = await getLatestAnalysis()
      if (analysis && !analysis.message) {
        prefill.entry_price = analysis.entry?.toString() || ''
        prefill.stop_loss = analysis.stop_loss?.toString() || ''
        prefill.take_profit_1 = analysis.take_profit_1?.toString() || ''
        prefill.take_profit_2 = analysis.take_profit_2?.toString() || ''
        prefill.direction = analysis.direction === 'BUY' ? 'BUY' : analysis.direction === 'SELL' ? 'SELL' : 'BUY'
      }
    } catch (e) {}
    setForm(prefill)
    setEditingTrade(null)
    setShowForm(true)
  }

  const openEditForm = (trade) => {
    setForm({
      trade_date: trade.trade_date || '',
      direction: trade.direction || 'BUY',
      entry_price: trade.entry_price?.toString() || '',
      stop_loss: trade.stop_loss?.toString() || '',
      take_profit_1: trade.take_profit_1?.toString() || '',
      take_profit_2: trade.take_profit_2?.toString() || '',
      exit_price: trade.exit_price?.toString() || '',
      status: trade.status || 'OPEN',
      profit_eur: trade.profit_eur?.toString() || '',
      lot_size: trade.lot_size?.toString() || '0.01',
      notes: trade.notes || '',
    })
    setEditingTrade(trade)
    setShowForm(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const payload = {
      trade_date: form.trade_date,
      direction: form.direction,
      entry_price: parseFloat(form.entry_price),
      stop_loss: form.stop_loss ? parseFloat(form.stop_loss) : null,
      take_profit_1: form.take_profit_1 ? parseFloat(form.take_profit_1) : null,
      take_profit_2: form.take_profit_2 ? parseFloat(form.take_profit_2) : null,
      exit_price: form.exit_price ? parseFloat(form.exit_price) : null,
      status: form.status,
      profit_eur: form.profit_eur ? parseFloat(form.profit_eur) : 0,
      lot_size: parseFloat(form.lot_size) || 0.01,
      notes: form.notes || null,
    }
    try {
      if (editingTrade) {
        await updateTrade(editingTrade.id, payload)
      } else {
        await createTrade(payload)
      }
      setShowForm(false)
      await load()
    } catch (e) { console.error(e) }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce trade ?')) return
    try { await deleteTrade(id); await load() } catch (e) { console.error(e) }
  }

  const handleAIAnalyze = async (trade) => {
    setLoadingAI(p => ({ ...p, [trade.id]: true }))
    try {
      const res = await analyzeTrade(trade.id)
      setAiAnalysis(p => ({ ...p, [trade.id]: res.analysis }))
    } catch (e) { console.error(e) }
    setLoadingAI(p => ({ ...p, [trade.id]: false }))
  }

  return (
    <div className="max-w-[1600px] mx-auto px-4 py-4 space-y-4">

      {/* Stats Banner */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <StatCard label="Trades" value={stats.total_trades} />
          <StatCard label="Gains" value={stats.wins} color="text-green-400" />
          <StatCard label="Pertes" value={stats.losses} color="text-red-400" />
          <StatCard label="Win Rate" value={`${stats.win_rate}%`} color={stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'} />
          <StatCard label="Profit Factor" value={stats.profit_factor === Infinity ? '∞' : stats.profit_factor} color={stats.profit_factor >= 1 ? 'text-green-400' : 'text-red-400'} />
          <StatCard label="P&L Total" value={`€${stats.total_pnl}`} color={stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'} />
          <StatCard label="Max Drawdown" value={`€${stats.max_drawdown}`} color="text-red-400" />
          <StatCard label="Meilleure série" value={stats.best_streak} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        {/* Left: trades table */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">Journal de Trades</h2>
            <button
              onClick={openNewForm}
              className="px-3 py-1.5 bg-yellow-500 text-black text-xs font-bold rounded hover:bg-yellow-400 transition-colors"
            >
              + Ajouter un trade
            </button>
          </div>

          {loading && <div className="text-xs text-gray-500 animate-pulse">Chargement...</div>}

          {!loading && trades.length === 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center">
              <p className="text-gray-500 text-sm">Aucun trade enregistré.</p>
              <p className="text-gray-600 text-xs mt-1">Cliquez sur "+ Ajouter un trade" pour commencer.</p>
            </div>
          )}

          {trades.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="text-left px-3 py-2">Date</th>
                    <th className="text-left px-3 py-2">Dir.</th>
                    <th className="text-right px-3 py-2">Entrée</th>
                    <th className="text-right px-3 py-2">Sortie</th>
                    <th className="text-right px-3 py-2">P&L €</th>
                    <th className="text-left px-3 py-2">Statut</th>
                    <th className="text-right px-3 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map(trade => (
                    <React.Fragment key={trade.id}>
                      <tr className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                        <td className="px-3 py-2 text-gray-400">{trade.trade_date}</td>
                        <td className="px-3 py-2">
                          <span className={`font-bold ${trade.direction === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                            {trade.direction}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-gray-300">${trade.entry_price?.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-400">
                          {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '—'}
                        </td>
                        <td className={`px-3 py-2 text-right font-mono font-semibold ${trade.profit_eur > 0 ? 'text-green-400' : trade.profit_eur < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                          {trade.profit_eur > 0 ? '+' : ''}{trade.profit_eur?.toFixed(2)}€
                        </td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded text-xs border ${STATUS_COLORS[trade.status] || STATUS_COLORS.OPEN}`}>
                            {trade.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right space-x-2">
                          {trade.status === 'LOSS' && (
                            <button
                              onClick={() => handleAIAnalyze(trade)}
                              disabled={loadingAI[trade.id]}
                              className="text-purple-400 hover:text-purple-300 disabled:opacity-50"
                              title="Analyser avec IA"
                            >
                              {loadingAI[trade.id] ? '...' : '🤖'}
                            </button>
                          )}
                          <button onClick={() => openEditForm(trade)} className="text-gray-500 hover:text-yellow-400">✎</button>
                          <button onClick={() => handleDelete(trade.id)} className="text-gray-600 hover:text-red-400">✕</button>
                        </td>
                      </tr>
                      {/* AI analysis row */}
                      {aiAnalysis[trade.id] && (
                        <tr>
                          <td colSpan={7} className="px-4 py-3 bg-purple-900/20 border-b border-gray-800">
                            <div className="text-xs text-purple-200 whitespace-pre-line leading-relaxed">
                              <span className="text-purple-400 font-semibold">🤖 Analyse IA: </span>
                              {aiAnalysis[trade.id]}
                            </div>
                          </td>
                        </tr>
                      )}
                      {/* Notes row */}
                      {trade.notes && !aiAnalysis[trade.id] && (
                        <tr>
                          <td colSpan={7} className="px-4 py-1 bg-gray-800/30 border-b border-gray-800">
                            <span className="text-xs text-gray-500">📝 {trade.notes}</span>
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

        {/* Right: bankroll chart + stats */}
        <div className="space-y-4">
          {/* Bankroll chart */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Évolution P&L cumulé</h3>
            {stats?.bankroll_history?.length > 1 ? (
              <div ref={chartRef} className="w-full" />
            ) : (
              <div className="h-40 flex items-center justify-center text-xs text-gray-600">
                Pas encore assez de trades clôturés.
              </div>
            )}
          </div>

          {/* Detailed stats */}
          {stats && stats.total_trades > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Statistiques</h3>
              <StatRow label="Gain moyen" value={`€${stats.avg_win}`} color="text-green-400" />
              <StatRow label="Perte moyenne" value={`-€${stats.avg_loss}`} color="text-red-400" />
              <StatRow label="Pire série" value={`${stats.worst_streak} pertes`} color="text-red-400" />
              <StatRow label="Meilleure série" value={`${stats.best_streak} gains`} color="text-green-400" />
            </div>
          )}
        </div>
      </div>

      {/* Trade Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-200">
                {editingTrade ? 'Modifier le trade' : 'Nouveau trade'}
              </h3>
              <button onClick={() => setShowForm(false)} className="text-gray-500 hover:text-white text-lg">✕</button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date" type="date" value={form.trade_date}
                  onChange={v => setForm(p => ({ ...p, trade_date: v }))} required />
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Direction</label>
                  <select
                    value={form.direction}
                    onChange={e => setForm(p => ({ ...p, direction: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                  >
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
                  <label className="text-xs text-gray-500 mb-1 block">Statut</label>
                  <select
                    value={form.status}
                    onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                  >
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
                <label className="text-xs text-gray-500 mb-1 block">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                  rows={2}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 resize-none"
                  placeholder="Raison de l'entrée, contexte..."
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  className="flex-1 py-2 bg-yellow-500 text-black text-xs font-bold rounded hover:bg-yellow-400 transition-colors"
                >
                  {editingTrade ? 'Mettre à jour' : 'Enregistrer'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="flex-1 py-2 bg-gray-800 text-gray-400 text-xs rounded hover:bg-gray-700 transition-colors"
                >
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
      <label className="text-xs text-gray-500 mb-1 block">{label}</label>
      <input
        {...props}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono"
      />
    </div>
  )
}

function StatCard({ label, value, color = 'text-gray-200' }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
    </div>
  )
}

function StatRow({ label, value, color = 'text-gray-300' }) {
  return (
    <div className="flex justify-between text-xs py-1 border-b border-gray-800">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono font-semibold ${color}`}>{value}</span>
    </div>
  )
}
