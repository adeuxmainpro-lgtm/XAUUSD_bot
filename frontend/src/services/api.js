import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 60000 })

// Market
export const getPrice     = () => api.get('/market/price').then(r => r.data)
export const getLivePrice = () => api.get('/market/price/live').then(r => r.data)
export const getOHLC      = (interval = '1h', outputsize = 200) =>
  api.get(`/market/ohlc/${interval}`, { params: { outputsize } }).then(r => r.data)
export const getIndicators = () => api.get('/market/indicators').then(r => r.data)

// Analysis
export const runAnalysis      = () => api.post('/analysis/run/sync').then(r => r.data)
export const getLatestAnalysis = () => api.get('/analysis/latest').then(r => r.data)
export const getSignalHistory  = (limit = 5) => api.get('/analysis/signal-history', { params: { limit } }).then(r => r.data)

// News
export const getNews = (refresh = false) =>
  api.get('/news', { params: { refresh } }).then(r => r.data)

// Chat
export const sendChatMessage = (message) => api.post('/chat', { message }).then(r => r.data)
export const getChatHistory = (limit = 20) =>
  api.get('/chat/history', { params: { limit } }).then(r => r.data)

// Risk
export const calculateRisk = (payload) => api.post('/risk/calculate', payload).then(r => r.data)
export const getRiskFromAnalysis = (bankroll_eur, risk_level = 'normal') =>
  api.get('/risk/from-analysis', { params: { bankroll_eur, risk_level } }).then(r => r.data)

// Patterns
export const getPatterns = (interval = '1h') =>
  api.get('/patterns', { params: { interval } }).then(r => r.data)

// Sentiment & COT
export const getSentiment = (refresh = false) =>
  api.get('/sentiment', { params: { refresh } }).then(r => r.data)

// Trade Journal
export const getTrades = (limit = 100) =>
  api.get('/journal/trades', { params: { limit } }).then(r => r.data)
export const createTrade = (trade) => api.post('/journal/trades', trade).then(r => r.data)
export const updateTrade = (id, trade) => api.put(`/journal/trades/${id}`, trade).then(r => r.data)
export const deleteTrade = (id) => api.delete(`/journal/trades/${id}`)
export const getJournalStats = () => api.get('/journal/stats').then(r => r.data)
export const getJournalDetailed = () => api.get('/journal/stats/detailed').then(r => r.data)
export const analyzeTrade = (id) => api.post(`/journal/trades/${id}/analyze`).then(r => r.data)
export const exportTradesCSV = () =>
  api.get('/journal/export/csv', { responseType: 'blob' }).then(r => r.data)

// Macro context
export const getMacroContext = () => api.get('/macro/context').then(r => r.data)

// Composite score (correlations, ETF flows, options, yields, Fed NLP)
export const getCompositeScore = (refresh = false) =>
  api.get('/analysis/composite', { params: { refresh } }).then(r => r.data)

// Performance & Backtest
export const getPerformance = () => api.get('/performance').then(r => r.data)
export const getBacktest = (years = 5) =>
  api.get('/performance/backtest', { params: { years } }).then(r => r.data)

// Bankroll
export const getBankroll = () => api.get('/journal/bankroll').then(r => r.data)
export const setInitialBankroll = (amount) =>
  api.put('/journal/bankroll', { initial_bankroll: amount }).then(r => r.data)

// API quota
export const getQuota = () => api.get('/market/quota').then(r => r.data)
