import React, { useState } from 'react'
import { calculateRisk } from '../services/api'

const INPUT_CLS =
  'w-full bg-terminal-surface border border-terminal-border rounded-lg px-3 py-2 text-xs font-mono text-terminal-base focus:border-gold-400/50 focus:outline-none transition-colors placeholder-terminal-text-dim'

function ResultRow({ label, value, highlight, positive }) {
  const valueColor = highlight
    ? positive === true ? 'text-green-400' : positive === false ? 'text-red-400' : 'text-gold-400'
    : 'text-terminal-base'
  return (
    <div className={`flex justify-between items-center py-1.5 border-b border-terminal-border last:border-0 ${highlight ? 'bg-terminal-surface/30 px-2 -mx-2 rounded' : ''}`}>
      <span className="text-terminal-text-muted text-xs">{label}</span>
      <span className={`text-xs font-mono font-bold ${valueColor}`}>{value}</span>
    </div>
  )
}

export default function RiskCalculator({ latestAnalysis }) {
  const [form, setForm] = useState({
    bankroll:  '1000',
    risk_pct:  '1',
    entry:     latestAnalysis?.entry?.toFixed(2)         || '',
    stop_loss: latestAnalysis?.stop_loss?.toFixed(2)     || '',
    tp1:       latestAnalysis?.take_profit_1?.toFixed(2) || '',
    tp2:       latestAnalysis?.take_profit_2?.toFixed(2) || '',
  })
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const handleChange = e => setForm(f => ({ ...f, [e.target.name]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const entry = parseFloat(form.entry)
      const sl    = parseFloat(form.stop_loss)
      if (!entry || !sl) throw new Error('Entrée et stop loss requis')
      const slDistance = Math.abs(entry - sl)
      if (slDistance <= 0) throw new Error('Distance SL invalide')
      const riskPct = parseFloat(form.risk_pct)
      if (!riskPct || riskPct <= 0 || riskPct > 100) throw new Error('Risque invalide (ex: 0.5, 1, 2.5)')
      const res = await calculateRisk({
        bankroll_eur:   parseFloat(form.bankroll),
        risk_pct:       riskPct,
        stop_loss_pips: slDistance,
        entry_price:    entry,
        take_profit_1:  form.tp1 ? parseFloat(form.tp1) : null,
        take_profit_2:  form.tp2 ? parseFloat(form.tp2) : null,
      })
      setResult(res)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const prefill = () => {
    if (!latestAnalysis) return
    setForm(f => ({
      ...f,
      entry:     latestAnalysis.entry?.toFixed(2)         || '',
      stop_loss: latestAnalysis.stop_loss?.toFixed(2)     || '',
      tp1:       latestAnalysis.take_profit_1?.toFixed(2) || '',
      tp2:       latestAnalysis.take_profit_2?.toFixed(2) || '',
    }))
  }

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Calculateur Position</h2>
        {latestAnalysis?.entry && (
          <button onClick={prefill} className="text-xs text-gold-400/70 hover:text-gold-400 transition-colors font-mono">
            ← Depuis analyse
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">Bankroll (€)</label>
            <input type="number" name="bankroll" value={form.bankroll} onChange={handleChange}
              className={INPUT_CLS} placeholder="1000" min="1" required />
          </div>
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">Risque (%)</label>
            <input type="number" name="risk_pct" value={form.risk_pct} onChange={handleChange}
              className={INPUT_CLS} placeholder="1" min="0.1" max="100" step="0.1" required />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">Entrée ($)</label>
            <input type="number" name="entry" value={form.entry} onChange={handleChange}
              className={INPUT_CLS} placeholder="2345.00" step="0.01" required />
          </div>
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">Stop Loss ($)</label>
            <input type="number" name="stop_loss" value={form.stop_loss} onChange={handleChange}
              className={INPUT_CLS} placeholder="2330.00" step="0.01" required />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">TP1 ($)</label>
            <input type="number" name="tp1" value={form.tp1} onChange={handleChange}
              className={INPUT_CLS} placeholder="2365.00" step="0.01" />
          </div>
          <div>
            <label className="text-[10px] text-terminal-text-muted uppercase tracking-wide block mb-1">TP2 ($)</label>
            <input type="number" name="tp2" value={form.tp2} onChange={handleChange}
              className={INPUT_CLS} placeholder="2385.00" step="0.01" />
          </div>
        </div>

        {error && <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded px-3 py-2">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-gold-400/15 border border-gold-400/30 text-gold-400 text-xs font-bold rounded-lg hover:bg-gold-400/25 transition-colors disabled:opacity-50 tracking-wide uppercase"
        >
          {loading ? 'Calcul en cours...' : 'Calculer la position'}
        </button>
      </form>

      {result && (
        <div className="border border-terminal-border rounded-lg p-3 space-y-0 animate-fade-in">
          <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-2">Résultats</div>
          <ResultRow label="Capital risqué"  value={`€${result.amount_risked_eur} (${result.risk_pct}%)`} highlight />
          <ResultRow label="Lots standard"   value={result.lot_size_standard} />
          <ResultRow label="Lots mini"       value={result.lot_size_mini} />
          <ResultRow label="Lots micro"      value={result.lot_size_micro} />
          <ResultRow label="Valeur position" value={`$${result.position_value_usd?.toLocaleString()}`} />
          <ResultRow label="Levier utilisé"  value={`${result.leverage_used}x`} />
          <ResultRow label="Perte max (SL)"  value={`€${result.max_loss_eur}`} positive={false} highlight />
          {result.tp1_profit_eur && (
            <ResultRow label="Gain TP1" value={`€${result.tp1_profit_eur}`} positive={true} highlight />
          )}
          {result.tp2_profit_eur && (
            <ResultRow label="Gain TP2" value={`€${result.tp2_profit_eur}`} positive={true} />
          )}
          {result.risk_reward && (
            <ResultRow
              label="Ratio R/R"
              value={`1:${result.risk_reward}`}
              highlight
              positive={result.risk_reward >= 2}
            />
          )}
        </div>
      )}
    </div>
  )
}
