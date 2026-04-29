import React from 'react'

/* ── Tooltip ─────────────────────────────────────────────────── */
function Tooltip({ text, children }) {
  return (
    <span className="tooltip-container">
      {children}
      <span className="tooltip-content">{text}</span>
    </span>
  )
}

/* ── Trend badge ─────────────────────────────────────────────── */
function TrendBadge({ trend }) {
  const cfg = {
    BULLISH: { cls: 'text-green-400 bg-green-400/10 border-green-500/30', arrow: '↑' },
    BEARISH: { cls: 'text-red-400   bg-red-400/10   border-red-500/30',   arrow: '↓' },
    NEUTRAL: { cls: 'text-yellow-400 bg-yellow-400/10 border-yellow-500/30', arrow: '→' },
    UNKNOWN: { cls: 'text-gray-500  bg-gray-500/10  border-gray-600/30',  arrow: '?' },
  }
  const { cls, arrow } = cfg[trend] || cfg.UNKNOWN
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-mono font-semibold ${cls}`}>
      {arrow} {trend}
    </span>
  )
}

/* ── Individual indicator row ───────────────────────────────── */
function Indicator({ label, value, unit = '', colorFn, tooltip, bold = false }) {
  const color = colorFn ? colorFn(value) : 'text-terminal-base'
  const display = value !== null && value !== undefined ? `${value}${unit}` : '—'

  return (
    <div className="flex justify-between items-center py-1.5 border-b border-terminal-border last:border-0">
      <span className="text-xs text-terminal-text-muted flex items-center gap-1.5">
        {label}
        {tooltip && (
          <Tooltip text={tooltip}>
            <span className="text-[10px] text-terminal-text-dim hover:text-terminal-text-muted cursor-help select-none leading-none">ⓘ</span>
          </Tooltip>
        )}
      </span>
      <span className={`text-xs font-mono ${bold ? 'font-bold' : 'font-semibold'} ${color}`}>
        {display}
      </span>
    </div>
  )
}

/* ── Section heading ────────────────────────────────────────── */
function SectionLabel({ children }) {
  return (
    <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mt-3 mb-1 first:mt-0">
      {children}
    </div>
  )
}

/* ── Price level chips ──────────────────────────────────────── */
function LevelChips({ items, type }) {
  const cfg = type === 'support'
    ? 'bg-green-900/20 text-green-400 border border-green-800/40'
    : 'bg-red-900/20   text-red-400   border border-red-800/40'
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {items.map(v => (
        <span key={v} className={`text-[11px] font-mono px-1.5 py-0.5 rounded ${cfg}`}>
          ${v}
        </span>
      ))}
    </div>
  )
}

/* ── Main component ─────────────────────────────────────────── */
export default function MarketOverview({ data, loading, flashClass, priceKey }) {
  if (loading) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 space-y-2">
        <div className="text-xs font-semibold text-terminal-text-muted uppercase tracking-wider mb-3">Marché</div>
        <div className="animate-pulse space-y-2">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-4 bg-terminal-muted/30 rounded" />
          ))}
        </div>
      </div>
    )
  }

  if (!data) return null

  // Guard: if price is 0 or missing, show error instead of $0.00
  if (!data.price || data.price <= 0) {
    return (
      <div className="bg-terminal-card border border-red-800/40 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-red-400 text-sm">⚠️</span>
          <h2 className="text-sm font-bold text-red-400 uppercase tracking-wider">Données indisponibles</h2>
        </div>
        <p className="text-xs text-terminal-text-muted">
          Prix non reçu depuis Twelve Data. Vérifiez votre clé API (<code className="text-gold-400">TWELVE_DATA_API_KEY</code>) et le quota mensuel.
        </p>
        <p className="text-[10px] text-terminal-text-dim mt-2 font-mono">
          Consultez les logs backend pour le message d'erreur exact.
        </p>
      </div>
    )
  }

  const changePct  = data.change_pct
  const changeColor = changePct > 0 ? 'text-green-400' : changePct < 0 ? 'text-red-400' : 'text-terminal-text-muted'

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Marché</h2>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[9px] text-red-400 font-mono font-bold tracking-widest">LIVE</span>
          <span className="text-[10px] text-terminal-text-dim font-mono ml-1">XAU/USD</span>
        </div>
      </div>

      {/* Live price */}
      <div className="mb-3 pb-3 border-b border-terminal-border">
        <div
          key={priceKey}
          className={`text-3xl font-bold font-mono leading-tight ${flashClass || 'text-gold-400'}`}
        >
          ${data.price?.toFixed(2) ?? '—'}
        </div>
        <div className={`text-sm font-mono font-semibold mt-0.5 ${changeColor}`}>
          {changePct !== null && changePct !== undefined
            ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(3)}%`
            : ''}
        </div>
      </div>

      {/* OHLC */}
      <SectionLabel>OHLC</SectionLabel>
      <div className="grid grid-cols-3 gap-1.5 mb-3">
        {[
          ['O', data.open,  'text-terminal-base'],
          ['H', data.high,  'text-green-400'],
          ['L', data.low,   'text-red-400'],
        ].map(([k, v, c]) => (
          <div key={k} className="bg-terminal-surface/60 rounded p-1.5 text-center">
            <div className="text-terminal-text-dim text-[10px] mb-0.5">{k}</div>
            <div className={`text-[11px] font-mono font-bold ${c}`}>
              {v ? `$${v.toFixed(2)}` : '—'}
            </div>
          </div>
        ))}
      </div>

      {/* Trends */}
      <SectionLabel>Tendances</SectionLabel>
      <div className="space-y-1.5 mb-3">
        <div className="flex justify-between items-center">
          <Tooltip text="Tendance court terme basée sur le croisement EMA20/EMA50. Golden cross (EMA20>EMA50) = haussier.">
            <span className="text-xs text-terminal-text-muted cursor-help">CT (EMA20/50) ⓘ</span>
          </Tooltip>
          <TrendBadge trend={data.trend_short || 'UNKNOWN'} />
        </div>
        <div className="flex justify-between items-center">
          <Tooltip text="Tendance moyen terme basée sur le croisement EMA50/EMA200. Prix > EMA200 = structure de bull market.">
            <span className="text-xs text-terminal-text-muted cursor-help">MT (EMA50/200) ⓘ</span>
          </Tooltip>
          <TrendBadge trend={data.trend_medium || 'UNKNOWN'} />
        </div>
      </div>

      {/* Indicators */}
      <SectionLabel>Indicateurs</SectionLabel>
      <div className="space-y-0">
        <Indicator
          label="RSI(14)"
          value={data.rsi?.toFixed(1)}
          bold
          colorFn={v => v > 70 ? 'text-red-400' : v < 30 ? 'text-green-400' : 'text-terminal-base'}
          tooltip="Relative Strength Index. >70 = surachat (retournement baissier probable). <30 = survente (rebond probable). Zone 30–70 = neutre."
        />
        <Indicator
          label="MACD"
          value={data.macd?.toFixed(4)}
          colorFn={v => v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-terminal-base'}
          tooltip="Moving Average Convergence/Divergence. Positif et croissant = momentum haussier. Croisement de la ligne de signal = signal d'entrée potentiel."
        />
        <Indicator
          label="EMA 20"
          value={data.ema20?.toFixed(2)}
          unit=" $"
          tooltip="Moyenne mobile exponentielle 20 périodes. Support/résistance dynamique à court terme. Prix > EMA20 = momentum positif immédiat."
        />
        <Indicator
          label="EMA 50"
          value={data.ema50?.toFixed(2)}
          unit=" $"
          tooltip="Moyenne mobile exponentielle 50 périodes. Référence moyen terme. Croisement EMA20/EMA50 = Golden Cross (haussier) ou Death Cross (baissier)."
        />
        <Indicator
          label="EMA 200"
          value={data.ema200?.toFixed(2)}
          unit=" $"
          tooltip="Moyenne mobile exponentielle 200 périodes. Ligne de partage bull/bear market. Prix au-dessus = tendance long terme haussière."
        />
        <Indicator
          label="ATR%"
          value={data.atr_pct?.toFixed(3)}
          unit="%"
          bold
          colorFn={v => v > 0.8 ? 'text-red-400' : v > 0.5 ? 'text-yellow-400' : 'text-green-400'}
          tooltip="Average True Range en %. Mesure la volatilité journalière. >0.8% = très volatile (risque élevé, ajustez le SL). <0.3% = faible volatilité (range)."
        />
      </div>

      {/* Support / Resistance */}
      {data.supports?.length > 0 && (
        <div className="mt-3">
          <Tooltip text="Niveaux de prix où la demande a historiquement dominé l'offre. Zone de rebond potentiel, idéale pour les entrées en achat.">
            <span className="text-[10px] font-semibold text-green-500/70 uppercase tracking-widest cursor-help">
              Supports ⓘ
            </span>
          </Tooltip>
          <LevelChips items={data.supports} type="support" />
        </div>
      )}
      {data.resistances?.length > 0 && (
        <div className="mt-2.5">
          <Tooltip text="Niveaux de prix où l'offre a dominé la demande. Zone de retournement potentiel, idéale pour les prises de profit ou les ventes.">
            <span className="text-[10px] font-semibold text-red-500/70 uppercase tracking-widest cursor-help">
              Résistances ⓘ
            </span>
          </Tooltip>
          <LevelChips items={data.resistances} type="resistance" />
        </div>
      )}
    </div>
  )
}
