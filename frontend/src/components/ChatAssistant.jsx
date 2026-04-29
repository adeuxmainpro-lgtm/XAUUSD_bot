import React, { useState, useRef, useEffect } from 'react'
import { sendChatMessage, getChatHistory } from '../services/api'

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

function BotAvatar() {
  return (
    <div className="w-7 h-7 rounded-lg bg-gold-400/15 border border-gold-400/30 flex items-center justify-center text-[11px] font-bold text-gold-400 flex-shrink-0">
      XA
    </div>
  )
}

function Message({ role, content, timestamp }) {
  const isUser = role === 'user'
  return (
    <div className={`flex gap-2 items-end animate-fade-in ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser && <BotAvatar />}
      <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`} style={{ maxWidth: '82%' }}>
        <div className={`px-3.5 py-2.5 text-xs leading-relaxed break-words ${
          isUser
            ? 'bg-gold-400 text-gray-900 font-medium rounded-2xl rounded-br-sm'
            : 'bg-terminal-surface border border-terminal-border text-terminal-base rounded-2xl rounded-bl-sm'
        }`}>
          {content}
        </div>
        {timestamp && (
          <span className="text-[9px] text-terminal-text-dim font-mono px-1">
            {formatTime(timestamp)}
          </span>
        )}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-2 items-end animate-fade-in">
      <BotAvatar />
      <div className="bg-terminal-surface border border-terminal-border rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
        {[0, 160, 320].map(delay => (
          <div
            key={delay}
            className="w-1.5 h-1.5 bg-terminal-muted rounded-full animate-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

const QUICK_QUESTIONS = [
  'Analyse le marché',
  'Risques actuels ?',
  'Impact du DXY ?',
  'Trader maintenant ?',
]

export default function ChatAssistant() {
  const [messages,      setMessages]      = useState([])
  const [input,         setInput]         = useState('')
  const [loading,       setLoading]       = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => { loadHistory() }, [])
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const loadHistory = async () => {
    try {
      const res = await getChatHistory(20)
      if (res.history?.length > 0) {
        setMessages(res.history.map(m => ({ ...m, timestamp: m.timestamp || null })))
      } else {
        setMessages([{
          role: 'assistant',
          content: "Bonjour ! Je suis votre analyste XAUUSD. Posez vos questions sur l'or, les niveaux clés ou demandez une analyse du marché.",
          timestamp: Date.now(),
        }])
      }
    } catch {
      setMessages([{
        role: 'assistant',
        content: 'Bonjour ! Prêt à analyser le marché XAUUSD avec vous.',
        timestamp: Date.now(),
      }])
    }
    setHistoryLoaded(true)
  }

  const handleSend = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg, timestamp: Date.now() }])
    setLoading(true)
    try {
      const res = await sendChatMessage(msg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response, timestamp: Date.now() }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Erreur de communication. Vérifiez que le backend est démarré.',
        timestamp: Date.now(),
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg flex flex-col overflow-hidden">

      {/* ── Header ── */}
      <div className="px-4 py-3 bg-terminal-surface/50 border-b border-terminal-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gold-400/15 border border-gold-400/30 flex items-center justify-center text-xs font-bold text-gold-400">
            XA
          </div>
          <div>
            <div className="text-xs font-bold text-terminal-base tracking-wide">XAUUSD Analyst</div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-[10px] text-green-400">En ligne</span>
            </div>
          </div>
        </div>
        <span className="text-[10px] text-terminal-text-dim font-mono">Claude · IA</span>
      </div>

      {/* ── Messages ── */}
      <div
        className="chat-messages overflow-y-auto p-4 space-y-4 flex-shrink-0"
        style={{ height: '280px', background: 'rgba(5,9,16,0.7)' }}
      >
        {!historyLoaded ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-terminal-text-dim text-xs animate-pulse">Chargement...</div>
          </div>
        ) : (
          messages.map((msg, i) => <Message key={i} {...msg} />)
        )}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* ── Quick questions ── */}
      <div className="px-4 py-2 flex gap-1.5 flex-wrap border-t border-terminal-border flex-shrink-0">
        {QUICK_QUESTIONS.map(q => (
          <button
            key={q}
            onClick={() => { setInput(q); inputRef.current?.focus() }}
            className="text-[10px] px-2.5 py-1 rounded-full border border-terminal-border text-terminal-text-dim hover:text-gold-400 hover:border-gold-400/30 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* ── Input ── */}
      <div className="px-4 pb-4 pt-2 flex-shrink-0">
        <div className="flex gap-2 items-end bg-terminal-surface border border-terminal-border rounded-2xl px-3.5 py-2.5 focus-within:border-gold-400/40 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez une question sur l'or..."
            rows={1}
            className="flex-1 bg-transparent text-xs text-terminal-base placeholder-terminal-text-dim resize-none focus:outline-none leading-relaxed"
            style={{ minHeight: '20px', maxHeight: '80px' }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="w-7 h-7 rounded-full bg-gold-400 flex items-center justify-center text-gray-900 hover:bg-gold-300 disabled:opacity-35 disabled:cursor-not-allowed transition-all flex-shrink-0"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M1.5 10.5L10.5 6L1.5 1.5V5.25L7.5 6L1.5 6.75V10.5Z" fill="currentColor"/>
            </svg>
          </button>
        </div>
        <p className="text-[9px] text-terminal-text-dim mt-1.5 text-center tracking-wide">
          ↵ Envoyer · Shift+↵ saut de ligne
        </p>
      </div>

    </div>
  )
}
