import { useEffect, useRef, useState } from 'react'
import AppShell from '../components/AppShell.jsx'
import { ArrowUp, Check, Copy, RefreshCw, RotateCcw, Sparkles, TriangleAlert } from 'lucide-react'
import { extractOutfit, saveSelectedOutfit, summarizeOutfit } from '../lib/outfitHandoff.js'
import './AIStylist.css'

// Where the FastAPI backend runs. Change it with a VITE_API_BASE_URL setting if needed.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 180000 // aligned with styleApi.js; server workflow is optimized too

const QUICK_PROMPTS = [
  { label: 'Indoor wedding outfit', hint: 'Elegant and comfortable for a ceremony', text: 'I need an indoor wedding outfit' },
  { label: 'Office outfit', hint: 'Polished smart-casual for work days', text: 'Suggest an office outfit' },
  { label: 'College outfit', hint: 'Easy, trendy looks for campus', text: 'Suggest a college outfit' },
  { label: 'Casual weekend outfit', hint: 'Relaxed pieces for time off', text: 'Suggest a casual weekend outfit' },
]

// ---------------------------------------------------------------------------
// Talking to the backend: POST /api/style
// Request body (from backend/main.py, StylingRequest):
//   user_query   (required text)
//   user_profile (optional object) -> not sent yet, because the Profile page does not save anywhere
// Returns { ok: true, data } or { ok: false, message, details }. It never throws.
// ---------------------------------------------------------------------------
async function requestStyle(query) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  let response
  try {
    response = await fetch(API_BASE + '/api/style', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_query: query }),
      signal: controller.signal,
    })
  } catch (error) {
    if (error && error.name === 'AbortError') {
      return {
        ok: false,
        message: 'The stylist is taking longer than expected. Please try again in a moment.',
      }
    }
    return {
      ok: false,
      message:
        'I could not reach the StyleAI server at ' +
        API_BASE +
        '. Please check that the backend is running and try again.',
    }
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // the error reply was not JSON; that is fine
    }
    let message = 'Something went wrong (error ' + response.status + '). Please try again.'
    if (response.status === 422) {
      message = 'The server could not read that request. Please check your message and try again.'
    } else if (response.status === 503) {
      message = 'The AI service is not available on the server right now. Please try again later.'
    } else if (response.status >= 500) {
      message = 'The stylist ran into a problem while working on your request. Please try again.'
    }
    return { ok: false, message, details: detail }
  }

  try {
    return { ok: true, data: await response.json() }
  } catch {
    return { ok: false, message: 'The server sent a reply that I could not read. Please try again.' }
  }
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function asArray(value) {
  return Array.isArray(value) ? value : []
}

function formatPrice(price, currency) {
  if (price === undefined || price === null || price === '') return ''
  const number = Number(price)
  if (Number.isNaN(number)) return String(price)
  if (!currency || currency === 'INR') return '₹' + number.toLocaleString('en-IN')
  return currency + ' ' + number.toLocaleString('en-IN')
}

// Text to place in the input when the user arrives from the Home page.
function startingText(params) {
  const prompt = (params.get('prompt') || '').trim()
  const occasion = (params.get('occasion') || '').trim()
  if (prompt && occasion && !prompt.toLowerCase().includes(occasion.toLowerCase())) {
    return prompt + ' (Occasion: ' + occasion + ')'
  }
  if (prompt) return prompt
  if (occasion) return 'I need a ' + occasion.toLowerCase() + ' outfit'
  return ''
}

// Plain-text version of a reply, used by the Copy button.
function replyAsText(result) {
  const plan = result.outfit_plan || {}
  const lines = []
  if (plan.occasion) lines.push('Occasion: ' + plan.occasion)
  if (plan.style) lines.push('Style: ' + plan.style)
  const pieces = [...asArray(plan.items), ...asArray(plan.accessories)]
  if (pieces.length > 0) {
    lines.push('', 'Pieces:')
    pieces.forEach((p) => lines.push('- ' + [p.category, p.item].filter(Boolean).join(': ') + (p.color ? ' (' + p.color + ')' : '')))
  }
  if (plan.reasoning) lines.push('', plan.reasoning)
  const products = asArray(result.selected_products)
  if (products.length > 0) {
    lines.push('', 'Products:')
    products.forEach((p) => lines.push('- ' + (p.title || p.name || 'Product') + ' ' + formatPrice(p.price, p.currency)))
  }
  return lines.join('\n')
}

// ---------------------------------------------------------------------------
// Showing the backend's answer: a short summary + "Try This Outfit"
// ---------------------------------------------------------------------------
function StylistResult({ message, handoff, onTry }) {
  const { result, outfit } = message
  const summary = summarizeOutfit(outfit)
  const approved = result.approved === true || result.status === 'approved'
  const clicked = handoff && handoff.id === message.id ? handoff : null

  if (!outfit || !summary) {
    return (
      <div className="st-result">
        <p className="st-text">
          The stylist did not return an outfit for this request{result.status ? ' (status: ' + result.status + ')' : ''}.
          Try rephrasing it or changing the budget.
        </p>
      </div>
    )
  }

  const details = [
    summary.occasion && ['Occasion', summary.occasion],
    summary.style && ['Style', summary.style],
    summary.keyItems.length > 0 && [
      'Key items',
      summary.keyItems.join(', ') + (summary.extraItemCount > 0 ? ' +' + summary.extraItemCount + ' more' : ''),
    ],
    summary.budget && ['Budget', formatPrice(summary.budget.amount, summary.budget.currency)],
  ].filter(Boolean)

  return (
    <div className="st-result">
      <p className={approved ? 'st-status st-status-ok' : 'st-status st-status-warn'}>
        {approved
          ? 'Here is the look I put together for you.'
          : 'I could not put together a fully approved outfit this time, but here is what the stylist found.'}
      </p>

      {details.length > 0 ? (
        <dl className="st-summary">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="st-text">The stylist returned an outfit without a summary.</p>
      )}

      <div className="st-try">
        <button type="button" className="btn btn-gold" onClick={() => onTry(message)}>
          Try This Outfit
        </button>
        {clicked && !clicked.ok && (
          <p className="st-try-note st-try-note-warn" role="status">
            This browser blocked saving the outfit, so it could not be opened in the Fitting Room.
          </p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------
function AIStylist({ params }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState(() => startingText(params))
  const [budget, setBudget] = useState('')
  const [inputError, setInputError] = useState('')
  const [budgetError, setBudgetError] = useState('')
  const [loading, setLoading] = useState(false)
  const [copiedId, setCopiedId] = useState(null)
  const [handoff, setHandoff] = useState(null) // { id, ok } for the last "Try This Outfit" click

  const nextId = useRef(1)
  const lastQuery = useRef('')
  const lastBudget = useRef(null)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  // Dark theme hook: lets AIStylist.css switch the shell (sidebar/header) to dark while this page is open.
  useEffect(() => {
    document.body.classList.add('st-dark')
    return () => document.body.classList.remove('st-dark')
  }, [])

  // Follow the conversation once it has started (the welcome screen stays at the top).
  useEffect(() => {
    const el = scrollRef.current
    if (el && (messages.length > 0 || loading)) el.scrollTo({ top: el.scrollHeight })
  }, [messages, loading])

  function addMessage(message) {
    const id = nextId.current
    nextId.current += 1
    setMessages((old) => [...old, { id, ...message }])
  }

  function applyQuickPrompt(text) {
    setInput(text)
    setInputError('')
    if (inputRef.current) inputRef.current.focus()
  }

  async function runQuery(query, requestedBudget = null) {
    lastQuery.current = query
    lastBudget.current = requestedBudget
    setLoading(true)
    const outcome = await requestStyle(query)
    setLoading(false)

    if (outcome.ok) {
      // Keep the real backend data (not a copy of demo data) for the summary and the handoff.
      const outfit = extractOutfit(outcome.data, { userQuery: query, requestedBudget })
      addMessage({ role: 'stylist', result: outcome.data, outfit, query, budget: requestedBudget })
    } else {
      addMessage({ role: 'error', text: outcome.message, details: outcome.details })
    }
    if (inputRef.current) inputRef.current.focus()
  }

  function sendMessage() {
    if (loading) return

    const text = input.trim()
    let problem = false

    if (!text) {
      setInputError('Please type what you would like to wear.')
      problem = true
    }
    if (budget !== '' && !(Number(budget) > 0)) {
      setBudgetError('Budget must be more than 0.')
      problem = true
    }
    if (problem) return

    setInputError('')
    setBudgetError('')

    // The backend reads the budget from the sentence, e.g. "... under ₹5000".
    const query = budget !== '' ? text.replace(/[.!?\s]+$/, '') + ' under ₹' + Number(budget) : text

    addMessage({ role: 'user', text, budget: budget !== '' ? Number(budget) : null })
    setInput('')
    runQuery(query, budget !== '' ? Number(budget) : null)
  }

  function retry() {
    if (loading || !lastQuery.current) return
    setMessages((old) => old.filter((m) => m.role !== 'error'))
    runQuery(lastQuery.current, lastBudget.current)
  }

  async function copyReply(message) {
    try {
      await navigator.clipboard.writeText(replyAsText(message.result))
      setCopiedId(message.id)
      setTimeout(() => setCopiedId((current) => (current === message.id ? null : current)), 1800)
    } catch {
      // clipboard not available (for example on plain http); nothing to do
    }
  }

  function regenerate(message) {
    if (loading || !message.query) return
    runQuery(message.query, message.budget)
  }

  // Keep the chosen outfit for the Fitting Room page, then open it.
  function tryOutfit(message) {
    if (!message.outfit) return
    if (saveSelectedOutfit(message.outfit)) {
      window.location.hash = '#/fitting-room'
    } else {
      setHandoff({ id: message.id, ok: false })
    }
  }

  function newConversation() {
    if (loading) return
    setMessages([])
    setHandoff(null)
    setInput('')
    setBudget('')
    setInputError('')
    setBudgetError('')
  }

  function handleSubmit(event) {
    event.preventDefault()
    sendMessage()
  }

  // Enter sends. Shift+Enter adds a new line.
  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      sendMessage()
    }
  }

  return (
    <AppShell
      currentPath="/ai-stylist"
      title="AI Stylist"
      actions={
        messages.length > 0 && (
          <button type="button" className="st-ghost" onClick={newConversation} disabled={loading}>
            <RotateCcw size={15} /> New conversation
          </button>
        )
      }
    >
      <section className="st-chat" aria-label="AI Stylist chat">
        <div className="st-scroll" ref={scrollRef} aria-live="polite">
          <div className="st-column">
            {messages.length === 0 && !loading && (
              <div className="st-welcome">
                <h2>What are we dressing you for?</h2>
                <p className="st-welcome-sub">
                  Describe the moment, set a budget if you like, and I&apos;ll style a complete look.
                </p>
                <div className="st-prompts">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt.label}
                      type="button"
                      className="st-prompt"
                      onClick={() => applyQuickPrompt(prompt.text)}
                    >
                      <span className="st-prompt-title">{prompt.label}</span>
                      <span className="st-prompt-hint">{prompt.hint}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => {
              if (message.role === 'user') {
                return (
                  <div key={message.id} className="st-row st-row-user">
                    <div className="st-bubble st-bubble-user">
                      <p>{message.text}</p>
                      {message.budget !== null && (
                        <p className="st-bubble-note">Budget: ₹{message.budget.toLocaleString('en-IN')}</p>
                      )}
                    </div>
                  </div>
                )
              }
              if (message.role === 'error') {
                return (
                  <div key={message.id} className="st-error" role="alert">
                    <TriangleAlert size={18} />
                    <div>
                      <p>{message.text}</p>
                      {message.details && <p className="st-error-details">Details: {message.details}</p>}
                      <button type="button" onClick={retry} disabled={loading}>
                        Try again
                      </button>
                    </div>
                  </div>
                )
              }
              return (
                <article key={message.id} className="st-reply">
                  <div className="st-reply-head">
                    <span className="st-avatar" aria-hidden="true">
                      <Sparkles size={14} />
                    </span>
                    Your stylist
                  </div>
                  <StylistResult message={message} handoff={handoff} onTry={tryOutfit} />
                  <div className="st-actions">
                    <button type="button" onClick={() => copyReply(message)}>
                      {copiedId === message.id ? <Check size={14} /> : <Copy size={14} />}
                      {copiedId === message.id ? 'Copied' : 'Copy'}
                    </button>
                    <button type="button" onClick={() => regenerate(message)} disabled={loading}>
                      <RefreshCw size={14} /> Regenerate
                    </button>
                  </div>
                </article>
              )
            })}

            {loading && (
              <div className="st-loading" role="status">
                <span className="st-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                Your stylist is working on it. This can take a little while…
              </div>
            )}
          </div>
        </div>

        <form className="st-composer" onSubmit={handleSubmit} noValidate>
          <div className="st-composer-column">
            <div className="st-box">
              <label className="st-visually-hidden" htmlFor="chat-input">
                Your outfit request
              </label>
              <textarea
                id="chat-input"
                ref={inputRef}
                rows={2}
                value={input}
                disabled={loading}
                placeholder="Example: I need an indoor wedding outfit..."
                onChange={(event) => {
                  setInput(event.target.value)
                  setInputError('')
                }}
                onKeyDown={handleKeyDown}
                aria-invalid={inputError ? 'true' : 'false'}
                aria-describedby={inputError ? 'chat-input-error' : undefined}
              />
              {inputError && (
                <p className="st-field-error" id="chat-input-error" role="alert">
                  {inputError}
                </p>
              )}

              <div className="st-box-row">
                <div className="st-budget">
                  <label htmlFor="chat-budget">Budget</label>
                  <span className="st-budget-field">
                    ₹
                    <input
                      id="chat-budget"
                      type="number"
                      inputMode="numeric"
                      min="1"
                      placeholder="Optional"
                      value={budget}
                      disabled={loading}
                      onChange={(event) => {
                        setBudget(event.target.value)
                        setBudgetError('')
                      }}
                      aria-invalid={budgetError ? 'true' : 'false'}
                    />
                  </span>
                  {budgetError && (
                    <span className="st-field-error" role="alert">
                      {budgetError}
                    </span>
                  )}
                </div>

                <button type="submit" className="btn btn-gold st-send" disabled={loading}>
                  {loading ? 'Finding your outfit…' : 'Send'}
                  {!loading && <ArrowUp size={16} />}
                </button>
              </div>
            </div>
            <p className="st-hint">Enter to send · Shift + Enter for a new line · Styling ideas are AI-generated, so double-check before you buy.</p>
          </div>
        </form>
      </section>
    </AppShell>
  )
}

export default AIStylist
