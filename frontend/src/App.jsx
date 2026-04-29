import React, { useState, useEffect, useCallback, useRef } from 'react'
import MarketOverview from './components/MarketOverview'
import PriceChart from './components/PriceChart'
import RecommendationCard from './components/RecommendationCard'
import NewsPanel from './components/NewsPanel'
import RiskCalculator from './components/RiskCalculator'
import ChatAssistant from './components/ChatAssistant'
import PatternPanel from './components/PatternPanel'
import SentimentPanel from './components/SentimentPanel'
import MacroPanel from './components/MacroPanel'
import TradeJournal from './components/TradeJournal'
import { getPrice, getLivePrice, getLatestAnalysis, getNews, runAnalysis } from './services/api'

const REFRESH_INTERVAL_MS = 60_000

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'journal',   label: 'Journal de Trades' },
]

function PriceDot({ isUp, isDown }) {
  const color = isUp ? 'bg-green-400' : isDown ? 'bg-red-400' : 'bg-gray-500'
  return <span className={`w-2 h-2 rounded-full ${color} animate-pulse inline-block`} />
}

function Header({ price, changePct, priceKey, flashClass, loading, activeTab, onTabChange }) {
  const isUp   = changePct > 0
  const isDown = changePct < 0

  return (
    <header className="bg-terminal-card border-b border-terminal-border sticky top-0 z-50 shadow-lg shadow-black/40">
      <div className="max-w-[1800px] mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="text-gold-400 text-xl font-bold leading-none">◈</div>
            <div>
              <div className="text-sm font-bold text-terminal-base tracking-wide">XAUUSD BOT</div>
              <div className="text-[10px] text-terminal-text-dim hidden sm:block">AI-Powered Gold Analysis</div>
            </div>
          </div>

          {/* Price block */}
          <div className="flex items-center gap-4">
            {loading ? (
              <div className="text-gold-400 text-xs animate-pulse">Chargement...</div>
            ) : price ? (
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div
                    key={priceKey}
                    className={`text-2xl font-bold font-mono leading-tight ${flashClass || 'text-gold-400'}`}
                  >
                    ${price.toFixed(2)}
                  </div>
                  <div className={`text-xs font-mono text-right ${isUp ? 'text-green-400' : isDown ? 'text-red-400' : 'text-terminal-text-muted'}`}>
                    {isUp ? '▲' : isDown ? '▼' : '—'} {Math.abs(changePct || 0).toFixed(3)}%
                  </div>
                </div>
                <PriceDot isUp={isUp} isDown={isDown} />
              </div>
            ) : null}

            <div className="hidden md:flex flex-col items-end">
              <div className="text-[10px] text-terminal-text-dim">
                {new Date().toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })}
              </div>
              <div className="text-[10px] text-terminal-text-dim">
                {new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-0 border-t border-terminal-border -mx-0">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`px-5 py-2 text-xs font-semibold tracking-wide transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-gold-400 text-gold-400 bg-gold-400/5'
                  : 'border-transparent text-terminal-text-dim hover:text-terminal-text-muted hover:border-terminal-muted'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  )
}

export default function App() {
  const [activeTab,       setActiveTab]       = useState('dashboard')
  const [marketData,      setMarketData]       = useState(null)
  const [analysis,        setAnalysis]         = useState(null)
  const [news,            setNews]             = useState([])
  const [loadingMarket,   setLoadingMarket]    = useState(true)
  const [loadingAnalysis, setLoadingAnalysis]  = useState(false)
  const [loadingNews,     setLoadingNews]      = useState(false)
  const [flashClass,      setFlashClass]       = useState('')
  const [priceKey,        setPriceKey]         = useState(0)
  const [marketError,     setMarketError]      = useState(null)
  const prevPriceRef = useRef(null)

  const fetchMarket = useCallback(async () => {
    try {
      const data = await getPrice()
      setMarketData(data)
      setMarketError(null)
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Erreur réseau'
      console.error('Market fetch error:', msg, e)
      setMarketError(msg)
    } finally {
      setLoadingMarket(false)
    }
  }, [])

  const fetchAnalysis = useCallback(async () => {
    try {
      const data = await getLatestAnalysis()
      if (data && !data.message) setAnalysis(data)
    } catch (e) {
      console.error('Analysis fetch error:', e)
    }
  }, [])

  const fetchNews = useCallback(async (refresh = false) => {
    setLoadingNews(true)
    try {
      const data = await getNews(refresh)
      setNews(data.articles || [])
    } catch (e) {
      console.error('News fetch error:', e)
    } finally {
      setLoadingNews(false)
    }
  }, [])

  const handleRunAnalysis = async () => {
    setLoadingAnalysis(true)
    try {
      const result = await runAnalysis()
      setAnalysis(result)
    } catch (e) {
      console.error('Run analysis error:', e)
    } finally {
      setLoadingAnalysis(false)
    }
  }

  // Price flash on change
  useEffect(() => {
    const price = marketData?.price
    if (price == null) return
    if (prevPriceRef.current !== null && Math.abs(price - prevPriceRef.current) > 0.01) {
      const cls = price > prevPriceRef.current ? 'price-flash-up' : 'price-flash-down'
      setFlashClass(cls)
      setPriceKey(k => k + 1)
      const timer = setTimeout(() => setFlashClass(''), 900)
      prevPriceRef.current = price
      return () => clearTimeout(timer)
    }
    prevPriceRef.current = price
  }, [marketData?.price])

  useEffect(() => {
    fetchMarket()
    fetchAnalysis()
    fetchNews()
  }, [])

  // Full market data (indicators) every 60s
  useEffect(() => {
    const id = setInterval(fetchMarket, REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [fetchMarket])

  // Live price only every 1s — silent, no loading state
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const data = await getLivePrice()
        setMarketData(prev => {
          if (!prev) return prev
          return { ...prev, price: data.price, change_pct: data.change_pct }
        })
      } catch {
        // keep last known value on error
      }
    }, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#080c14', color: '#b0c4d8' }}>
      <Header
        price={marketData?.price}
        changePct={marketData?.change_pct}
        priceKey={priceKey}
        flashClass={flashClass}
        loading={loadingMarket}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {activeTab === 'dashboard' && (
        <main className="max-w-[1800px] mx-auto px-4 py-4">

          {/* ── API error banner ── */}
          {marketError && (
            <div className="mb-3 flex items-start gap-3 px-4 py-3 bg-red-900/20 border border-red-700/40 rounded-lg text-xs text-red-300">
              <span className="flex-shrink-0 text-base">⚠️</span>
              <div>
                <span className="font-bold">Données de marché indisponibles — </span>
                {marketError}
              </div>
            </div>
          )}

          {/* ── 3-Column Main Layout ── */}
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_320px] xl:grid-cols-[300px_1fr_340px] gap-3 items-start">

            {/* ── LEFT COLUMN : Market → Macro → Sentiment → Risk ── */}
            <div className="space-y-3">
              <MarketOverview
                data={marketData}
                loading={loadingMarket}
                flashClass={flashClass}
                priceKey={priceKey}
              />
              <MacroPanel />
              <SentimentPanel />
              <RiskCalculator latestAnalysis={analysis} />
            </div>

            {/* ── CENTER COLUMN : Chart → Chat → Patterns ── */}
            <div className="space-y-3">
              <PriceChart indicators={marketData} />
              <ChatAssistant />
              <PatternPanel />
            </div>

            {/* ── RIGHT COLUMN : Recommendation → News ── */}
            <div className="space-y-3">
              <RecommendationCard
                analysis={analysis}
                onRefresh={handleRunAnalysis}
                loading={loadingAnalysis}
              />
              <NewsPanel
                articles={news}
                onRefresh={fetchNews}
                loading={loadingNews}
              />
            </div>

          </div>

        </main>
      )}

      {activeTab === 'journal' && <TradeJournal />}

      <footer className="text-center py-4 text-[10px] text-terminal-text-dim border-t border-terminal-border mt-4">
        XAUUSD Trading Bot · Claude AI · Twelve Data + FRED + COT + RSS
        <span className="ml-4 text-red-900">⚠ Usage éducatif uniquement</span>
      </footer>
    </div>
  )
}
