import React, { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'
import { getOHLC } from '../services/api'

const LIVE_INTERVAL_MS = 60000

const INTERVALS = [
  { label: '15m', value: '15min' },
  { label: '1h',  value: '1h'    },
  { label: '4h',  value: '4h'    },
  { label: '1j',  value: '1day'  },
]

const CHART_BG   = '#080c14'
const GRID_COLOR = '#1a2535'
const SCALE_COLOR = '#253347'

export default function PriceChart({ indicators }) {
  const chartRef      = useRef(null)
  const chartInstance = useRef(null)
  const candleSeries  = useRef(null)
  const ema20Series   = useRef(null)
  const ema50Series   = useRef(null)
  const ema200Series  = useRef(null)
  const liveTimerRef  = useRef(null)
  const [interval, setSelectedInterval] = useState('1h')
  const [loading,  setLoading]  = useState(true)
  const [candles,  setCandles]  = useState(0)
  const [isLive,   setIsLive]   = useState(true)
  const [chartError, setChartError] = useState(null)
  const [dataSource, setDataSource] = useState('twelve_data')

  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_BG },
        textColor: '#6b7d95',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#2d3f57', style: 1, labelBackgroundColor: '#1a2535' },
        horzLine: { color: '#2d3f57', style: 1, labelBackgroundColor: '#1a2535' },
      },
      rightPriceScale: {
        borderColor: SCALE_COLOR,
        textColor: '#6b7d95',
      },
      timeScale: {
        borderColor: SCALE_COLOR,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => {
          const d = new Date(time * 1000)
          return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
        },
      },
      width:  chartRef.current.clientWidth,
      height: 500,
    })

    candleSeries.current = chart.addCandlestickSeries({
      upColor:         '#22c55e',
      downColor:       '#ef4444',
      borderUpColor:   '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor:     '#22c55e',
      wickDownColor:   '#ef4444',
    })
    ema20Series.current = chart.addLineSeries({
      color: '#f59e0b', lineWidth: 1, title: 'EMA20', priceLineVisible: false, lastValueVisible: false,
    })
    ema50Series.current = chart.addLineSeries({
      color: '#3b82f6', lineWidth: 1, title: 'EMA50', priceLineVisible: false, lastValueVisible: false,
    })
    ema200Series.current = chart.addLineSeries({
      color: '#a855f7', lineWidth: 1.5, title: 'EMA200', priceLineVisible: false, lastValueVisible: false,
    })

    chartInstance.current = chart

    const handleResize = () => {
      if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [])

  useEffect(() => { loadData() }, [interval])

  // Live candle update — refresh only the last candle every 5s
  useEffect(() => {
    if (liveTimerRef.current) clearInterval(liveTimerRef.current)
    liveTimerRef.current = setInterval(async () => {
      if (!candleSeries.current) return
      try {
        const res = await getOHLC(interval, 1)
        const ohlc = res.data || []
        if (!ohlc.length) return
        const d = ohlc[0]
        candleSeries.current.update({
          time:  Math.floor(new Date(d.datetime).getTime() / 1000),
          open:  d.open,
          high:  d.high,
          low:   d.low,
          close: d.close,
        })
        setIsLive(true)
      } catch {
        setIsLive(false)
      }
    }, LIVE_INTERVAL_MS)
    return () => { if (liveTimerRef.current) clearInterval(liveTimerRef.current) }
  }, [interval])

  const loadData = async () => {
    setLoading(true)
    setChartError(null)
    try {
      const res  = await getOHLC(interval, 200)
      const ohlc = res.data || []
      if (res.source) setDataSource(res.source)

      if (ohlc.length === 0) {
        setChartError('Aucune donnée OHLC reçue — vérifiez la clé API Twelve Data et le quota.')
        return
      }

      const data = ohlc
        .map(d => ({
          time:  Math.floor(new Date(d.datetime).getTime() / 1000),
          open:  d.open,
          high:  d.high,
          low:   d.low,
          close: d.close,
        }))
        .sort((a, b) => a.time - b.time)

      if (candleSeries.current && data.length > 0) {
        candleSeries.current.setData(data)
        setCandles(data.length)
      }

      const closes = data.map(c => ({ time: c.time, value: c.close }))
      if (closes.length > 20  && ema20Series.current)  ema20Series.current.setData(calcEMA(closes, 20))
      if (closes.length > 50  && ema50Series.current)  ema50Series.current.setData(calcEMA(closes, 50))
      if (closes.length > 200 && ema200Series.current) ema200Series.current.setData(calcEMA(closes, 200))
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Erreur réseau'
      console.error('Chart load error:', msg, e)
      setChartError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-terminal-border">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-bold text-terminal-base uppercase tracking-wider">Graphique XAUUSD</h2>
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-red-500 animate-pulse' : 'bg-gray-600'}`} />
            <span className={`text-[9px] font-mono font-bold tracking-widest ${isLive ? 'text-red-400' : 'text-terminal-text-dim'}`}>
              {isLive ? 'LIVE' : 'OFF'}
            </span>
          </div>
          <div className="hidden sm:flex items-center gap-3 text-[10px] text-terminal-text-dim">
            <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-yellow-500 inline-block rounded" /> EMA20</span>
            <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-blue-500  inline-block rounded" /> EMA50</span>
            <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-purple-500 inline-block rounded" /> EMA200</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {candles > 0 && !loading && (
            <span className="text-[10px] text-terminal-text-dim font-mono">{candles} bougies</span>
          )}
          <div className="flex gap-1">
            {INTERVALS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setSelectedInterval(value)}
                className={`px-2.5 py-1 text-xs rounded font-mono transition-all ${
                  interval === value
                    ? 'bg-gold-400/15 text-gold-400 border border-gold-400/30 font-bold'
                    : 'text-terminal-text-muted hover:text-terminal-base border border-transparent hover:border-terminal-border'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart area */}
      <div className="relative" style={{ minHeight: '500px' }}>
        {loading && (
          <div className="absolute inset-0 bg-terminal-card/80 flex items-center justify-center z-10">
            <div className="flex items-center gap-2 text-gold-400 text-xs">
              <div className="w-1.5 h-1.5 bg-gold-400 rounded-full animate-ping" />
              Chargement des bougies...
            </div>
          </div>
        )}
        {!loading && chartError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 px-8">
            <span className="text-2xl">⚠️</span>
            <p className="text-xs text-red-400 text-center font-mono">{chartError}</p>
            <button
              onClick={loadData}
              className="text-xs px-3 py-1.5 border border-gold-400/30 text-gold-400 rounded hover:bg-gold-400/10 transition-colors font-mono"
            >
              ↻ Réessayer
            </button>
          </div>
        )}
        <div ref={chartRef} className="w-full" />
      </div>

      {/* Data source indicator */}
      <div className="px-3 py-1.5 border-t border-terminal-border flex items-center gap-1.5">
        {dataSource === 'yahoo_finance' ? (
          <>
            <span className="text-yellow-400 text-[10px]">⚠️</span>
            <span className="text-[10px] font-mono text-yellow-400">Mode secours actif — Yahoo Finance (GC=F)</span>
          </>
        ) : (
          <>
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
            <span className="text-[10px] font-mono text-terminal-text-dim">Source : Twelve Data</span>
          </>
        )}
      </div>
    </div>
  )
}

function calcEMA(data, period) {
  if (data.length < period) return []
  const k = 2 / (period + 1)
  const result = []
  let ema = data.slice(0, period).reduce((s, d) => s + d.value, 0) / period
  result.push({ time: data[period - 1].time, value: ema })
  for (let i = period; i < data.length; i++) {
    ema = data[i].value * k + ema * (1 - k)
    result.push({ time: data[i].time, value: ema })
  }
  return result
}
