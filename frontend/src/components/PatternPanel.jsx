import React, { useState, useEffect } from 'react'
import { getPatterns } from '../services/api'

const INTERVAL_LABELS = { '15min': '15m', '1h': '1h', '4h': '4h', '1day': '1J' }

const TAG_COLORS = {
  bullish: 'bg-green-900/40 text-green-300 border border-green-700/50',
  bearish: 'bg-red-900/40   text-red-300   border border-red-700/50',
  neutral: 'bg-terminal-surface text-terminal-text-muted border border-terminal-border',
}

function relColor(r) {
  if (!r) return 'text-terminal-text-dim'
  if (r >= 75) return 'text-green-400'
  if (r >= 60) return 'text-yellow-400'
  return 'text-terminal-text-dim'
}

function PatternTag({ name, type, reliability, desc }) {
  return (
    <div className="tooltip-container inline-flex items-center gap-1">
      <span className={`text-[11px] px-2 py-0.5 rounded font-mono ${TAG_COLORS[type] || TAG_COLORS.neutral}`}>
        {name}
      </span>
      {reliability != null && (
        <span className={`text-[10px] font-mono font-bold ${relColor(reliability)}`}>
          {reliability}%
        </span>
      )}
      {desc && (
        <div className="tooltip-content" style={{ width: '200px' }}>
          {desc}
        </div>
      )}
    </div>
  )
}

function Tag({ label, type }) {
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded font-mono ${TAG_COLORS[type] || TAG_COLORS.neutral}`}>
      {label}
    </span>
  )
}

function Section({ title, icon, children }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-terminal-text-dim uppercase tracking-widest mb-1.5 flex items-center gap-1">
        <span>{icon}</span> {title}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

export default function PatternPanel() {
  const [patterns, setPatterns] = useState(null)
  const [interval, setInterval] = useState('1h')
  const [loading,  setLoading]  = useState(false)

  const load = async (iv) => {
    setLoading(true)
    try { setPatterns(await getPatterns(iv)) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load(interval) }, [interval])

  const cs        = patterns?.candlestick || {}
  const chart     = patterns?.chart       || []
  const smc       = patterns?.smc         || {}
  const ict       = patterns?.ict         || {}
  const harmonics = patterns?.harmonic    || []
  const elliott   = patterns?.elliott     || {}
  const vsa       = patterns?.vsa         || []

  const hasAny =
    cs.bullish?.length || cs.bearish?.length || chart.length ||
    smc.order_blocks?.length || smc.fvg?.length || smc.bos?.length ||
    ict.kill_zones?.length || ict.ote ||
    harmonics.length || elliott.impulse || elliott.correction ||
    vsa.length

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Patterns Détectés</h3>
        <div className="flex gap-1">
          {Object.entries(INTERVAL_LABELS).map(([iv, lbl]) => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              className={`px-2.5 py-1 text-xs rounded font-mono transition-all ${
                interval === iv
                  ? 'bg-gold-400/15 text-gold-400 border border-gold-400/30 font-bold'
                  : 'text-terminal-text-muted hover:text-terminal-base border border-transparent hover:border-terminal-border'
              }`}
            >
              {lbl}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-terminal-text-dim py-2 animate-pulse">
          <div className="w-1.5 h-1.5 bg-gold-400/50 rounded-full animate-ping" />
          Analyse en cours...
        </div>
      )}

      {!loading && patterns && (
        <div className="space-y-4">

          {(cs.bullish?.length > 0 || cs.bearish?.length > 0) && (
            <Section title="Chandeliers" icon="🕯">
              {cs.bullish?.map((p, i) =>
                typeof p === 'object'
                  ? <PatternTag key={i} name={p.name} type={p.type || 'bullish'} reliability={p.reliability} desc={p.desc} />
                  : <Tag key={p} label={p} type="bullish" />
              )}
              {cs.bearish?.map((p, i) =>
                typeof p === 'object'
                  ? <PatternTag key={i} name={p.name} type={p.type || 'bearish'} reliability={p.reliability} desc={p.desc} />
                  : <Tag key={p} label={p} type="bearish" />
              )}
            </Section>
          )}

          {chart.length > 0 && (
            <Section title="Chartistes" icon="📈">
              {chart.map((p, i) => (
                <div key={i} className="flex items-center gap-1">
                  <PatternTag name={p.name} type={p.type} reliability={p.reliability} desc={p.desc} />
                  {p.target     && <span className="text-terminal-text-dim text-[10px] font-mono">→ ${p.target}</span>}
                  {p.key_level && !p.target && <span className="text-terminal-text-dim text-[10px] font-mono">niv. ${p.key_level}</span>}
                </div>
              ))}
            </Section>
          )}

          {harmonics.length > 0 && (
            <Section title="Harmoniques" icon="🎯">
              {harmonics.map((h, i) => (
                <div key={i} className="flex items-center gap-1">
                  <PatternTag name={h.name} type={h.type} reliability={h.reliability} desc={h.desc} />
                  {h.d_level && <span className="text-terminal-text-dim text-[10px] font-mono">D: ${h.d_level}</span>}
                </div>
              ))}
            </Section>
          )}

          {(elliott.impulse || elliott.correction) && (
            <Section title="Elliott Wave" icon="〰">
              {elliott.impulse && (
                <div className="flex items-center gap-1">
                  <PatternTag
                    name={`Impulsion ${elliott.impulse.wave_count}W`}
                    type="neutral"
                    reliability={elliott.impulse.reliability}
                    desc={`Vague actuelle: ${elliott.impulse.current_wave}${elliott.impulse.w3_extension ? ' · W3 étendue' : ''}`}
                  />
                  <span className="text-terminal-text-dim text-[10px] font-mono">vague {elliott.impulse.current_wave}</span>
                </div>
              )}
              {elliott.correction && (
                <PatternTag
                  name={`Correction A-B-C`}
                  type={elliott.correction.bias === 'bearish' ? 'bearish' : 'neutral'}
                  reliability={elliott.correction.reliability}
                  desc={elliott.correction.desc}
                />
              )}
            </Section>
          )}

          {vsa.length > 0 && (
            <Section title="VSA Volume" icon="📊">
              {vsa.map((v, i) => (
                <PatternTag key={i} name={v.name} type={v.type} reliability={v.reliability} desc={v.desc} />
              ))}
            </Section>
          )}

          {(smc.order_blocks?.length || smc.fvg?.length || smc.bos?.length || smc.choch?.length || smc.liquidity?.length) ? (
            <Section title="Smart Money (SMC)" icon="🧠">
              {smc.order_blocks?.map((ob, i) => (
                <PatternTag key={i} name={ob.desc} type={ob.type} reliability={ob.reliability} desc={ob.desc} />
              ))}
              {smc.fvg?.map((fvg, i) => (
                <Tag key={i} label={`FVG ${fvg.type} $${fvg.bottom}–$${fvg.top}`} type={fvg.type} />
              ))}
              {smc.bos?.map((b, i)   => <Tag key={i} label={b} type={b.includes('haussier') ? 'bullish' : 'bearish'} />)}
              {smc.choch?.map((c, i) => <Tag key={i} label={c} type={c.includes('haussier') ? 'bullish' : 'bearish'} />)}
              {smc.liquidity?.map((l, i) => <Tag key={i} label={l.desc} type="neutral" />)}
            </Section>
          ) : null}

          {(ict.kill_zones?.length || ict.ote || ict.breaker_blocks?.length) ? (
            <Section title="ICT" icon="⚡">
              {ict.kill_zones?.map((kz, i) => <Tag key={i} label={kz} type="neutral" />)}
              {ict.ote && (
                <PatternTag name={ict.ote.desc} type="bullish" reliability={ict.ote.reliability} desc={ict.ote.desc} />
              )}
              {ict.breaker_blocks?.map((bb, i) => (
                <PatternTag key={i} name={bb.desc} type={bb.type} reliability={bb.reliability} desc={bb.desc} />
              ))}
            </Section>
          ) : null}

          {!hasAny && (
            <p className="text-xs text-terminal-text-dim py-2">
              Aucun pattern significatif détecté sur {INTERVAL_LABELS[interval] || interval}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
