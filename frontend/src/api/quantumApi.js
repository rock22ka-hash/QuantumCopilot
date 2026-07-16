import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: BASE, timeout: 60000 })

export const generateCircuit = (prompt, shots = 1024) =>
  api.post('/generate-circuit', { prompt, shots, api_key: localStorage.getItem('gemini_api_key') || null }).then(r => r.data)

export const simulateCircuit = (code, shots = 1024, noisy = true) =>
  api.post('/simulate', { code, shots, noisy }).then(r => r.data)

export const analyzeCircuit = (code) =>
  api.post('/analyze', { code }).then(r => r.data)

export const optimizeCircuit = (code) =>
  api.post('/optimize', { code }).then(r => r.data)

export const explainCircuit = (code) =>
  api.post('/explain', { code, api_key: localStorage.getItem('gemini_api_key') || null }).then(r => r.data)

export const tutorChat = (messages, api_key = null) =>
  api.post('/explain/tutor', { messages, api_key: api_key || localStorage.getItem('gemini_api_key') || null }).then(r => r.data)
