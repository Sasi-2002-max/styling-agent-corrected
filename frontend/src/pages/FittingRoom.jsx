import { useEffect, useMemo, useRef, useState } from 'react'
import { Heart, Lightbulb, ArrowUpRight, Repeat, Bookmark, Check } from 'lucide-react'
import AppShell from '../components/AppShell.jsx'
import { FittingRoomProvider, useFittingRoom } from '../fitting-room/FittingRoomProvider'
import { categoryForSlot, OUTFIT_SLOTS } from '../fitting-room/categoryMap'
import { isAlternativeForSlot, requestAlternatives } from '../fitting-room/productSwitching'
import { loadSelectedOutfit } from '../lib/outfitHandoff.js'
import { productImageFor } from '../lib/productImages.js'
import { saveSavedLook } from '../lib/savedLooks.js'
import { ROW_GROUPS, buildFittingRoomResponse, totalPrice } from '../lib/fittingRoomAdapter.js'
import './FittingRoom.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const API_OPTIONS = { baseUrl: API_BASE }

const TABS = [
  { key: 'all', label: 'All pieces' },
  { key: 'top', label: 'Top' },
  { key: 'bottom', label: 'Bottom' },
  { key: 'footwear', label: 'Shoes' },
  { key: 'accessories', label: 'Accessories' },
]

const FALLBACK_WHY =
  'Your stylist picked pieces that work together: balanced proportions, a cohesive colour story, and items you can wear on repeat.'

const formatPrice = (price, currency) => {
  if (typeof price !== 'number' || !Number.isFinite(price)) return ''
  const rounded = price.toLocaleString('en-IN', { maximumFractionDigits: 0 })
  return !currency || currency === 'INR' ? '₹' + rounded : currency + ' ' + rounded
}

const isDemo = (product) => /demo|mock/i.test((product && product.store) || '')

function safeRetailerUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const url = new URL(value.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

const retailerName = (value) => (typeof value === 'string' ? value.replace(/^SerpApi\s*\/\s*/i, '').trim() : '')

// Small brand badge for the retailer chip.
function RetailerChip({ store }) {
  const name = retailerName(store)
  if (!name) return <span className="fr-chip fr-chip-empty" />
  const key = name.toLowerCase()
  const badge = key.includes('myntra')
    ? { letter: 'M', bg: '#ff3f6c', fg: '#fff' }
    : key.includes('flipkart')
      ? { letter: 'F', bg: '#2874f0', fg: '#ffd814' }
      : key.includes('amazon')
        ? { letter: 'a', bg: '#fff', fg: '#111' }
        : { letter: name.charAt(0).toUpperCase(), bg: '#e8dcc6', fg: '#3b2a1e' }
  return (
    <span className="fr-chip">
      <span className="fr-chip-badge" style={{ background: badge.bg, color: badge.fg }}>
        {badge.letter}
      </span>
      {name}
    </span>
  )
}

function Photo({ product }) {
  const [failedUrl, setFailedUrl] = useState(null)
  const url = (product && product.image_url) || null
  const src = productImageFor(product, url !== null && failedUrl === url)
  return src ? <img src={src} alt={product.title || ''} loading="lazy" onError={() => setFailedUrl(url)} /> : null
}

function PieceCard({ label, product, liked, onLike, action }) {
  const retailerUrl = isDemo(product) ? '' : safeRetailerUrl(product.product_url)
  return (
    <article className="fr-card">
      <div className="fr-card-photo">
        <Photo product={product} />
        <button
          type="button"
          className={'fr-heart' + (liked ? ' fr-heart-on' : '')}
          aria-label={liked ? 'Remove from favourites' : 'Add to favourites'}
          aria-pressed={liked}
          onClick={onLike}
        >
          <Heart size={18} fill={liked ? 'currentColor' : 'none'} />
        </button>
      </div>
      <p className="fr-card-cat">{label}</p>
      <h3 className="fr-card-title">{product.title || 'Product'}</h3>
      <p className="fr-card-price">{formatPrice(product.price, product.currency) || 'Price unavailable'}</p>
      <RetailerChip store={product.store} />
      {action ? (
        <button type="button" className="fr-card-btn" onClick={action.onClick}>
          {action.label}
        </button>
      ) : retailerUrl ? (
        <a className="fr-card-btn" href={retailerUrl} target="_blank" rel="noopener noreferrer">
          View at retailer <ArrowUpRight size={14} />
        </a>
      ) : (
        <span className="fr-card-btn fr-card-btn-off">View at retailer <ArrowUpRight size={14} /></span>
      )}
    </article>
  )
}

function Room({ response, plan }) {
  const { state, initFromResponse, selectProduct } = useFittingRoom()
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState('all')
  const [liked, setLiked] = useState({})
  const [showAlts, setShowAlts] = useState(false)
  const [alts, setAlts] = useState({}) // slot -> { status, products }
  const [saveNote, setSaveNote] = useState('') // '' | 'saved' | 'error'

  const initRef = useRef(initFromResponse)
  initRef.current = initFromResponse
  useEffect(() => {
    initRef.current(response)
    setReady(true)
  }, [response])

  const outfit = state.selectedOutfit

  // Outfit pieces in template order: Top, Bottom, Shoes, Accessories.
  const pieces = useMemo(() => {
    const list = []
    for (const group of ROW_GROUPS) {
      for (const slot of group.slots) {
        if (outfit[slot]) list.push({ slot, group, product: outfit[slot] })
      }
    }
    return list
  }, [outfit])

  // Any change to the outfit means the last save no longer matches it.
  const signature = pieces.map((p) => p.product.product_id).join('|')
  useEffect(() => {
    setSaveNote('')
  }, [signature])

  const saveLook = () => {
    const products = pieces.map((p) => p.product)
    const total = totalPrice(products)
    const saved = saveSavedLook({
      products,
      occasion: plan && plan.occasion,
      style: plan && plan.style,
      totalPrice: total.amount,
      currency: total.currency || 'INR',
    })
    setSaveNote(saved ? 'saved' : 'error')
  }

  const visible = pieces.filter((p) => tab === 'all' || p.group.key === tab)
  const toggleLike = (id) => setLiked((l) => ({ ...l, [id]: !l[id] }))

  // Load alternatives for the visible slots when "Find alternatives" is opened.
  const loadingRef = useRef(new Set())
  useEffect(() => {
    if (!showAlts) return
    visible.forEach(({ slot, product }) => {
      if (alts[slot] || loadingRef.current.has(slot)) return
      loadingRef.current.add(slot)
      setAlts((a) => ({ ...a, [slot]: { status: 'loading', products: [] } }))
      requestAlternatives({ product_id: product.product_id, category: categoryForSlot(slot) }, API_OPTIONS)
        .then((r) => setAlts((a) => ({ ...a, [slot]: { status: 'ready', products: r.products || [] } })))
        .catch(() => setAlts((a) => ({ ...a, [slot]: { status: 'error', products: [] } })))
    })
  }, [showAlts, tab, pieces]) // eslint-disable-line react-hooks/exhaustive-deps

  const altCards = []
  if (showAlts) {
    for (const { slot, group, product } of visible) {
      for (const alt of (alts[slot] && alts[slot].products) || []) {
        if (alt && alt.product_id !== product.product_id) altCards.push({ slot, group, product: alt })
      }
    }
  }
  const altsLoading = showAlts && visible.some(({ slot }) => !alts[slot] || alts[slot].status === 'loading')

  const pick = ({ slot, product }) => {
    if (isAlternativeForSlot(slot, product)) selectProduct(product)
  }

  if (!ready) return <div className="fr-loading" role="status">Loading your outfit…</div>

  const why = (plan && (plan.reasoning || plan.why)) || FALLBACK_WHY

  return (
    <div className="fr-page">
      <section className="fr-hero">
        <div className="fr-hero-text">
          <p className="fr-eyebrow">Fitting Room</p>
          <h1>Outfit of the Day</h1>
          <p className="fr-hero-sub">Your AI stylist has curated this look for you</p>
        </div>
        <aside className="fr-why">
          <h2>
            <Lightbulb size={22} strokeWidth={1.5} /> Why this look works
          </h2>
          <p>{why}</p>
        </aside>
      </section>

      <div className="fr-toolbar">
        <div className="fr-tabs" role="tablist" aria-label="Filter pieces">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={'fr-tab' + (tab === t.key ? ' fr-tab-on' : '')}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="fr-actions">
        <button type="button" className="fr-save-btn" onClick={saveLook} disabled={pieces.length === 0}>
          {saveNote === 'saved' ? <Check size={18} /> : <Bookmark size={18} />}
          {saveNote === 'saved' ? 'Look saved' : 'Save look'}
        </button>
        <button
          type="button"
          className={'fr-alt-btn' + (showAlts ? ' fr-alt-btn-on' : '')}
          aria-pressed={showAlts}
          onClick={() => setShowAlts((v) => !v)}
        >
          <Repeat size={18} /> Find alternatives
        </button>
        </div>
      </div>

      {saveNote && (
        <p className={'fr-save-note' + (saveNote === 'error' ? ' fr-save-note-error' : '')} role="status">
          {saveNote === 'saved' ? (
            <>Outfit saved to your wardrobe. <a href="#/wardrobe">View in My Wardrobe</a></>
          ) : (
            'Could not save this look in browser storage.'
          )}
        </p>
      )}

      <div className="fr-grid">
        {visible.length === 0 && <p className="fr-note">No pieces in this category for this outfit.</p>}
        {visible.map(({ slot, group, product }) => (
          <PieceCard
            key={product.product_id}
            label={group.label === 'Footwear' ? 'Shoes' : group.label}
            product={product}
            liked={!!liked[product.product_id]}
            onLike={() => toggleLike(product.product_id)}
          />
        ))}
      </div>

      {showAlts && (
        <section className="fr-alts" aria-label="Alternatives">
          <h2>Alternatives</h2>
          {altsLoading && altCards.length === 0 && <p className="fr-note">Finding alternatives…</p>}
          {!altsLoading && altCards.length === 0 && <p className="fr-note">No alternatives found.</p>}
          <div className="fr-grid">
            {altCards.map((entry) => (
              <PieceCard
                key={entry.product.product_id}
                label={entry.group.label === 'Footwear' ? 'Shoes' : entry.group.label}
                product={entry.product}
                liked={!!liked[entry.product.product_id]}
                onLike={() => toggleLike(entry.product.product_id)}
                action={{ label: 'Use in outfit', onClick: () => pick(entry) }}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

export default function FittingRoom() {
  const [handoff] = useState(() => loadSelectedOutfit())
  const response = useMemo(() => buildFittingRoomResponse(handoff), [handoff])

  return (
    <AppShell currentPath="/fitting-room" variant="dark">
      {response ? (
        <FittingRoomProvider initialMannequin="female">
          <Room response={response} plan={handoff.outfit_plan} />
        </FittingRoomProvider>
      ) : (
        <div className="fr-page">
          <section className="fr-hero">
            <div className="fr-hero-text">
              <p className="fr-eyebrow">Fitting Room</p>
              <h1>No outfit yet</h1>
              <p className="fr-hero-sub">
                Ask the AI Stylist for an outfit, then choose “Try This Outfit”.
              </p>
              <a className="fr-alt-btn fr-cta" href="#/ai-stylist">Go to AI Stylist</a>
            </div>
          </section>
        </div>
      )}
    </AppShell>
  )
}
