import axios from 'axios'

// Base URL is empty by default so requests go to /api/style on the same origin
// (Vite proxies /api to the FastAPI backend in development).
// Set VITE_API_BASE_URL (e.g. http://localhost:8000) to call the backend directly.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// The styling workflow runs several agents and an LLM, so allow a long wait.
const REQUEST_TIMEOUT_MS = 180000

/**
 * Build the query text sent to the backend. The backend reads the budget from
 * the query text itself, so the budget is appended as "Budget: under ₹N".
 */
export function buildQuery(message, budget) {
  const text = message.trim()
  const amount = Number(budget)
  if (budget !== '' && budget != null && Number.isFinite(amount) && amount > 0) {
    return `${text}. Budget: under ₹${Math.round(amount)}`
  }
  return text
}

/** POST /api/style  ->  { user_query (required), user_profile (optional) } */
export async function requestStyle({ userQuery, userProfile }) {
  const body = { user_query: userQuery }
  if (userProfile) body.user_profile = userProfile

  const response = await axios.post(`${API_BASE_URL}/api/style`, body, {
    timeout: REQUEST_TIMEOUT_MS,
    headers: { 'Content-Type': 'application/json' },
  })
  return response.data
}

/** Turn any axios/network failure into a friendly, human message. */
export function friendlyError(error) {
  if (error?.code === 'ECONNABORTED') {
    return 'The stylist is taking longer than expected. Please try again in a moment.'
  }
  if (!error?.response) {
    return "We couldn't reach the stylist service. Please check that the backend is running and try again."
  }
  const { status, data } = error.response
  if (status === 503) {
    return 'The stylist service isn’t fully configured yet (the AI key may be missing). Please check the backend setup.'
  }
  if (status === 422) {
    return 'That request couldn’t be processed. Please check your message and budget, then try again.'
  }
  if (status >= 500) {
    return 'Something went wrong while styling your look. Please try again shortly.'
  }
  const detail = typeof data?.detail === 'string' ? data.detail : ''
  return detail || 'Something unexpected happened. Please try again.'
}
