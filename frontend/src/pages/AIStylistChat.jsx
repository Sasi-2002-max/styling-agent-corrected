import { useEffect, useRef, useState } from 'react'
import { ArrowUp, RotateCcw, TriangleAlert, Sparkles } from 'lucide-react'
import AppShell from '../components/AppShell.jsx'
import { buildQuery, friendlyError, requestStyle } from '../lib/styleApi.js'
import './AIStylistChat.css'

const EXAMPLE_PROMPTS = [
  {
    title: 'Wedding guest',
    text: 'What should I wear to a friend’s evening wedding?',
  },
  {
    title: 'Office wardrobe',
    text: 'Build me a polished smart-casual outfit for the office.',
  },
  {
    title: 'Date night',
    text: 'I need a relaxed but elegant outfit for a dinner date.',
  },
  {
    title: 'Weekend travel',
    text: 'Suggest a comfortable, stylish outfit for a weekend trip.',
  },
]

const formatPrice = (price, currency = 'INR') => {
  if (typeof price !== 'number') return ''
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(price)
  } catch {
    return `${currency} ${price}`
  }
}

/** Renders what the backend actually returned for a styling request. */
function StyleResult({ data }) {
  const plan = data.outfit_plan || {}
  const items = Array.isArray(plan.items) ? plan.items : []
  const accessories = Array.isArray(plan.accessories) ? plan.accessories : []
  const palette = Array.isArray(plan.color_palette) ? plan.color_palette : []
  const products = Array.isArray(data.selected_products) ? data.selected_products : []
  const feedback = data.critic_feedback || {}

  const hasPlan = plan.occasion || plan.style || items.length > 0

  return (
    <div className="result">
      {hasPlan && (
        <>
          <p className="result__lede">
            {[plan.style, plan.occasion].filter(Boolean).join(' · ')}
          </p>
          {plan.reasoning && <p className="result__text">{plan.reasoning}</p>}
        </>
      )}

      {palette.length > 0 && (
        <div className="result__section">
          <h3>Colour palette</h3>
          <div className="chips">
            {palette.map((c) => (
              <span className="chip" key={c}>
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {[
        ['The outfit', items],
        ['Accessories', accessories],
      ].map(
        ([label, list]) =>
          list.length > 0 && (
            <div className="result__section" key={label}>
              <h3>{label}</h3>
              <ul className="piece-list">
                {list.map((piece, i) => (
                  <li key={`${piece.item}-${i}`}>
                    <span className="piece-list__name">
                      {[piece.color, piece.item].filter(Boolean).join(' ')}
                    </span>
                    {piece.notes && <span className="piece-list__note">{piece.notes}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ),
      )}

      {products.length > 0 && (
        <div className="result__section">
          <h3>Selected pieces</h3>
          <div className="product-grid">
            {products.map((p, i) => (
              <article className="product" key={p.product_id || `${p.title}-${i}`}>
                {p.image_url && (
                  <img
                    src={p.image_url}
                    alt={p.title}
                    loading="lazy"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                )}
                <div className="product__body">
                  <p className="product__store">{[p.brand, p.store].filter(Boolean).join(' · ')}</p>
                  <p className="product__title">{p.title}</p>
                  <p className="product__price">{formatPrice(p.price, p.currency)}</p>
                  {p.product_url && (
                    <a href={p.product_url} target="_blank" rel="noreferrer">
                      View product
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      )}

      {feedback.overall_feedback && (
        <div className="result__section">
          <h3>Stylist’s review</h3>
          <p className="result__text">{feedback.overall_feedback}</p>
        </div>
      )}

      {!hasPlan && products.length === 0 && (
        <p className="result__text">
          The stylist didn’t return an outfit this time
          {data.status ? ` (status: ${data.status})` : ''}. Try rephrasing your request.
        </p>
      )}

      <details className="raw">
        <summary>View raw response</summary>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </details>
    </div>
  )
}

export default function AIStylistChat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [budget, setBudget] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastRequest, setLastRequest] = useState(null)

  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  const nextId = useRef(1)

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight })
  }, [messages, loading])

  const push = (msg) => setMessages((prev) => [...prev, { id: nextId.current++, ...msg }])

  const runRequest = async (userQuery) => {
    setLoading(true)
    setLastRequest(userQuery)
    try {
      const data = await requestStyle({ userQuery })
      push({ role: 'assistant', data })
    } catch (err) {
      push({ role: 'error', text: friendlyError(err) })
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const send = () => {
    const text = input.trim()
    if (!text || loading) return
    const query = buildQuery(text, budget)
    push({ role: 'user', text, budget: budget ? Number(budget) : null })
    setInput('')
    runRequest(query)
  }

  const retry = () => {
    if (lastRequest && !loading) {
      // Drop the error bubble before retrying.
      setMessages((prev) => prev.filter((m) => m.role !== 'error'))
      runRequest(lastRequest)
    }
  }

  const reset = () => {
    if (loading) return
    setMessages([])
    setLastRequest(null)
    setInput('')
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const canSend = input.trim().length > 0 && !loading

  return (
    <AppShell
      active="AI Stylist"
      title="AI Stylist"
      actions={
        messages.length > 0 && (
          <button type="button" className="ghost-btn" onClick={reset} disabled={loading}>
            <RotateCcw size={15} /> New conversation
          </button>
        )
      }
    >
      <section className="chat" aria-label="AI Stylist chat">
        <div className="chat__scroll" ref={scrollRef}>
          <div className="chat__column">
            {messages.length === 0 && !loading && (
              <div className="welcome">
                <p className="eyebrow">Welcome to StyleAI</p>
                <h2>What are we dressing you for?</h2>
                <p className="welcome__sub">
                  Describe the occasion, the mood, or the piece you’re building around. Add a
                  budget if you like, and your stylist will curate a complete look.
                </p>
                <div className="prompt-grid">
                  {EXAMPLE_PROMPTS.map((p) => (
                    <button
                      type="button"
                      key={p.title}
                      className="prompt-card"
                      onClick={() => {
                        setInput(p.text)
                        inputRef.current?.focus()
                      }}
                    >
                      <span className="prompt-card__title">{p.title}</span>
                      <span className="prompt-card__text">{p.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => {
              if (m.role === 'user') {
                return (
                  <div className="msg msg--user" key={m.id}>
                    <div className="bubble bubble--user">
                      {m.text}
                      {m.budget > 0 && (
                        <span className="bubble__budget">Budget: under ₹{m.budget}</span>
                      )}
                    </div>
                  </div>
                )
              }
              if (m.role === 'error') {
                return (
                  <div className="msg" key={m.id}>
                    <div className="error" role="alert">
                      <TriangleAlert size={18} />
                      <div>
                        <p>{m.text}</p>
                        <button type="button" onClick={retry} disabled={loading}>
                          Try again
                        </button>
                      </div>
                    </div>
                  </div>
                )
              }
              return (
                <div className="msg" key={m.id}>
                  <div className="avatar" aria-hidden="true">
                    <Sparkles size={16} />
                  </div>
                  <div className="bubble bubble--ai">
                    <StyleResult data={m.data} />
                  </div>
                </div>
              )
            })}

            {loading && (
              <div className="msg" aria-live="polite">
                <div className="avatar" aria-hidden="true">
                  <Sparkles size={16} />
                </div>
                <div className="bubble bubble--ai loading">
                  <span className="dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span>Curating your look… this can take up to a minute.</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="composer">
          <div className="composer__column">
            <div className="composer__box">
              <textarea
                ref={inputRef}
                rows={2}
                value={input}
                placeholder="Ask your stylist anything — e.g. “A smart outfit for a job interview”"
                aria-label="Message your stylist"
                disabled={loading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <div className="composer__row">
                <label className="budget">
                  <span>Budget</span>
                  <span className="budget__field">
                    ₹
                    <input
                      type="number"
                      min="0"
                      step="100"
                      inputMode="numeric"
                      placeholder="Optional"
                      value={budget}
                      disabled={loading}
                      onChange={(e) => setBudget(e.target.value)}
                    />
                  </span>
                </label>
                <button
                  type="button"
                  className="send-btn"
                  onClick={send}
                  disabled={!canSend}
                >
                  {loading ? 'Styling…' : 'Send'}
                  {!loading && <ArrowUp size={16} />}
                </button>
              </div>
            </div>
            <p className="composer__hint">Enter to send · Shift + Enter for a new line</p>
          </div>
        </div>
      </section>
    </AppShell>
  )
}
