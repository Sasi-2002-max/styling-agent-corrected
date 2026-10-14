import { useMemo, useRef, useState, useEffect } from 'react'
import {
  UserRound, Plus, Shirt, Heart, Search, ChevronDown, ChevronRight,
  LayoutGrid, List, Ellipsis, ArrowRight, Camera, Sparkles, X,
} from 'lucide-react'
import AppShell from '../components/AppShell.jsx'
import { productImageFor } from '../lib/productImages.js'
import { swatchHex } from '../lib/fittingRoomAdapter.js'
import { readSavedLooks, SAVED_LOOKS_UPDATED_EVENT } from '../lib/savedLooks.js'
import heroImg from '../assets/styleai-hero.jpg'
import {
  GROUPS, WARDROBE_ITEMS, STYLE_SUGGESTIONS, STYLE_MATCHES, singular,
} from '../lib/wardrobeDemo.js'
import './Wardrobe.css'

const SORTS = {
  newest: { label: 'Newest first', fn: (a, b) => dateValue(b) - dateValue(a) },
  oldest: { label: 'Oldest first', fn: (a, b) => dateValue(a) - dateValue(b) },
  name: { label: 'Name A–Z', fn: (a, b) => a.name.localeCompare(b.name) },
  nameDesc: { label: 'Name Z–A', fn: (a, b) => b.name.localeCompare(a.name) },
}
const dateValue = (item) => Number.isFinite(new Date(item.addedAt).getTime()) ? new Date(item.addedAt).getTime() : 0
const STORAGE_KEY = 'styleai-wardrobe-items-v1'
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const byId = Object.fromEntries(WARDROBE_ITEMS.map((i) => [i.id, i]))
const imageOf = (item) => item.imageData || productImageFor({ category: item.shape, color: item.color })
const dotColor = (item) => swatchHex(item.color) || '#cfc2a8'

function Thumb({ item }) {
  if (!item) return null
  return <img src={imageOf(item)} alt={item.name} loading="lazy" />
}

function retailerUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const url = new URL(value.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

function retailerName(value) {
  return typeof value === 'string' ? value.replace(/^SerpApi\s*\/\s*/i, '').trim() : 'retailer'
}

function lookDate(look) {
  const value = look.createdAt || look.date
  const parsed = value ? new Date(value) : null
  return parsed && Number.isFinite(parsed.getTime())
    ? parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : 'Saved look'
}

function ItemCard({ item, onToggleFavorite }) {
  return (
    <article className="wd-card">
      <div className="wd-card-img">
        <Thumb item={item} />
        <button
          type="button"
          className={item.favorite ? 'wd-heart wd-heart-on' : 'wd-heart'}
          aria-label={item.favorite ? `Remove ${item.name} from favourites` : `Add ${item.name} to favourites`}
          aria-pressed={!!item.favorite}
          onClick={(event) => { event.stopPropagation(); onToggleFavorite(item.id) }}
        ><Heart size={18} strokeWidth={1.6} /></button>
      </div>
      <div className="wd-card-info">
        <div className="wd-card-text">
          <h3>{item.name}</h3>
          <p>{singular(item.group)}</p>
        </div>
        <div className="wd-card-foot">
          <span className="wd-swatch"><span className="wd-dot" style={{ background: dotColor(item) }} aria-hidden="true" />{item.color}</span>
          <button type="button" className="wd-more" aria-label={`Remove ${item.name}`} title="Remove item (local prototype)" onClick={() => window.dispatchEvent(new CustomEvent('styleai-remove-item', { detail: item.id }))}>
            <Ellipsis size={18} />
          </button>
        </div>
      </div>
    </article>
  )
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="wd-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="wd-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="wd-modal-head"><h2>{title}</h2><button type="button" className="wd-modal-close" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
        {children}
      </section>
    </div>
  )
}

export default function Wardrobe() {
  const [items, setItems] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (!saved) return WARDROBE_ITEMS
      const parsed = JSON.parse(saved)
      return Array.isArray(parsed) ? parsed : WARDROBE_ITEMS
    } catch { return WARDROBE_ITEMS }
  })
  const [savedLooks, setSavedLooks] = useState(() => readSavedLooks())
  const [group, setGroup] = useState('All')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('newest')
  const [view, setView] = useState('grid')
  const [modal, setModal] = useState(null)
  const [selectedLook, setSelectedLook] = useState(null)
  const [form, setForm] = useState({ name: '', group: '', color: '', brand: '', notes: '' })
  const [formError, setFormError] = useState('')
  const [imageData, setImageData] = useState('')
  const [imageError, setImageError] = useState('')
  const fileRef = useRef(null)

  // Dark theme hook: lets Wardrobe.css switch the shell (sidebar/header) to dark while this page is open.
  useEffect(() => {
    document.body.classList.add('wd-dark')
    return () => document.body.classList.remove('wd-dark')
  }, [])

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(items)) } catch {
      // Large images may exceed browser storage. The current session remains usable.
    }
  }, [items])

  useEffect(() => {
    const refreshSavedLooks = () => setSavedLooks(readSavedLooks())
    window.addEventListener(SAVED_LOOKS_UPDATED_EVENT, refreshSavedLooks)
    window.addEventListener('storage', refreshSavedLooks)
    return () => {
      window.removeEventListener(SAVED_LOOKS_UPDATED_EVENT, refreshSavedLooks)
      window.removeEventListener('storage', refreshSavedLooks)
    }
  }, [])

  useEffect(() => {
    const remove = (event) => {
      if (window.confirm('Remove this item from your local prototype wardrobe?')) {
        setItems((list) => list.filter((item) => item.id !== event.detail))
      }
    }
    window.addEventListener('styleai-remove-item', remove)
    return () => window.removeEventListener('styleai-remove-item', remove)
  }, [])

  const counts = useMemo(() => {
    const c = { All: items.length }
    for (const g of GROUPS) c[g] = items.filter((i) => i.group === g).length
    return c
  }, [items])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items
      .filter((i) => group === 'All' || i.group === group)
      .filter((i) => !q || `${i.name} ${i.group} ${i.color} ${i.brand || ''}`.toLowerCase().includes(q))
      .sort(SORTS[sort].fn)
  }, [items, group, query, sort])

  const toggleFavorite = (id) => setItems((list) => list.map((i) => i.id === id ? { ...i, favorite: !i.favorite } : i))
  const openAdd = (withPicker = false) => {
    setForm({ name: '', group: '', color: '', brand: '', notes: '' })
    setFormError('')
    setImageData('')
    setImageError('')
    setModal('add')
    if (withPicker) setTimeout(() => fileRef.current?.click(), 0)
  }
  const handleImage = (file) => {
    setImageError('')
    if (!file) return
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setImageError('Choose a PNG, JPG/JPEG, or WEBP image.')
      if (fileRef.current) fileRef.current.value = ''
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError('Image must be 5 MB or smaller.')
      if (fileRef.current) fileRef.current.value = ''
      return
    }
    const reader = new FileReader()
    reader.onload = () => setImageData(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => setImageError('This image could not be previewed. Please try another file.')
    reader.readAsDataURL(file)
  }
  const saveNewItem = (event) => {
    event.preventDefault()
    if (!form.name.trim() || !form.group || !form.color.trim()) {
      setFormError('Please enter an item name, choose a category, and enter a color.')
      return
    }
    const id = `local-${Date.now()}`
    setItems((list) => [{
      id, name: form.name.trim(), group: form.group, shape: ({ Tops: 'tops', Bottoms: 'pants', Dresses: 'dresses', Outerwear: 'shirts', Shoes: 'shoes', Bags: 'bags', Accessories: 'accessories' })[form.group],
      color: form.color.trim(), brand: form.brand.trim(), notes: form.notes.trim(),
      addedAt: Date.now(), favorite: false, ...(imageData ? { imageData } : {}),
    }, ...list])
    setGroup('All')
    setQuery('')
    setSort('newest')
    setModal(null)
  }

  // Saved Looks counts outfits saved in this browser; Favorites counts wardrobe items.
  // Derive both from their source data so filters, sorting, and view mode cannot skew totals.
  const favoriteCount = useMemo(
    () => new Set(items.filter((item) => item.favorite).map((item) => item.id)).size,
    [items],
  )

  const stats = [
    { value: items.length, label: 'Total Items' },
    { value: savedLooks.length, label: 'Saved Looks' },
    { value: favoriteCount, label: 'Favorites' },
    { value: GROUPS.filter((g) => counts[g] > 0).length, label: 'Categories' },
    { value: STYLE_MATCHES, label: 'Style Matches' },
  ]
  const quickActions = [
    { icon: Plus, label: 'Add New Item', onClick: () => openAdd(false) },
    { icon: Camera, label: 'Upload from Device', onClick: () => openAdd(true) },
    { icon: Sparkles, label: 'Get Style Suggestions', href: '#/ai-stylist' },
    { icon: Shirt, label: 'Create New Look', onClick: () => setModal('create-look') },
  ]
  const selectedLookItems = selectedLook
    ? Array.isArray(selectedLook.products)
      ? selectedLook.products.map((product, index) => ({
        id: product.product_id || `saved-product-${index}`,
        name: product.title || 'Saved product',
        group: product.category || 'Product',
        color: product.color || '',
        imageData: retailerUrl(product.image_url),
        shape: product.category || 'tops',
        productUrl: retailerUrl(product.product_url),
        store: retailerName(product.store),
        price: product.price,
        currency: product.currency || 'INR',
      }))
      : (selectedLook.itemIds || [])
        .map((id) => items.find((item) => item.id === id) || byId[id])
        .filter(Boolean)
    : []

  return (
    <AppShell currentPath="/wardrobe" title="My Wardrobe" actions={<a className="wd-profile" href="#/profile" aria-label="My Profile"><UserRound size={24} strokeWidth={2} /></a>}>
      <div className="wd-page">
        <section className="wd-banner">
          <img className="wd-banner-img" src={heroImg} alt="Garments hanging in a styling room" />
          <div className="wd-banner-body">
            <div className="wd-banner-top">
              <div><h2>Your Personal Wardrobe</h2><p>All your clothing, accessories, and saved looks in one place.</p></div>
              <button type="button" className="wd-add-btn" onClick={() => openAdd(false)}><Plus size={18} strokeWidth={1.8} /> Add New Item</button>
            </div>
            <dl className="wd-stats">{stats.map(({ value, label }) => <div className="wd-stat" key={label}><dd>{value}</dd><dt>{label}</dt></div>)}</dl>
          </div>
        </section>
        <div className="wd-cols">
          <div className="wd-main">
            <section className="wd-collection">
              <div className="wd-pills" role="tablist" aria-label="Filter by category">
                {['All', ...GROUPS].map((g) => <button key={g} type="button" role="tab" aria-selected={group === g} className={group === g ? 'wd-pill wd-pill-on' : 'wd-pill'} onClick={() => setGroup(g)}>{g === 'All' ? 'All Items' : g}<sup>{counts[g]}</sup></button>)}
              </div>
              <div className="wd-toolbar">
                <label className="wd-search"><Search size={18} /><input type="search" placeholder="Search your wardrobe..." value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search your wardrobe" />{query && <button type="button" className="wd-clear-search" onClick={() => setQuery('')} aria-label="Clear search"><X size={16} /></button>}</label>
                <label className="wd-sort"><select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort items">{Object.entries(SORTS).map(([key, { label }]) => <option key={key} value={key}>Sort by: {label}</option>)}</select><ChevronDown size={16} /></label>
                <div className="wd-view" role="group" aria-label="View mode">
                  <button type="button" className={view === 'grid' ? 'wd-view-on' : ''} aria-label="Grid view" aria-pressed={view === 'grid'} onClick={() => setView('grid')}><LayoutGrid size={19} /></button>
                  <button type="button" className={view === 'list' ? 'wd-view-on' : ''} aria-label="List view" aria-pressed={view === 'list'} onClick={() => setView('list')}><List size={19} /></button>
                </div>
              </div>
              {visible.length ? <div className={view === 'grid' ? 'wd-grid' : 'wd-grid wd-list'}>{visible.map((item) => <ItemCard key={item.id} item={item} onToggleFavorite={toggleFavorite} />)}</div> :
                <div className="wd-empty"><Search size={25} /><p>No items match your search or category.</p><span>Try another search or clear your filters.</span>{(query || group !== 'All') && <button type="button" className="wd-secondary-btn" onClick={() => { setQuery(''); setGroup('All') }}>Clear filters</button>}</div>}
            </section>
            <section className="wd-suggest">
              <div className="wd-suggest-head"><div><h2>Style Suggestions for Your Wardrobe</h2><p>Outfit ideas using items you already own.</p></div><a className="wd-link" href="#/ai-stylist">View More <ArrowRight size={16} /></a></div>
              <div className="wd-suggest-grid">{STYLE_SUGGESTIONS.map((s) => <button type="button" className="wd-outfit" key={s.id} onClick={() => { setSelectedLook({ ...s, date: 'Demo suggestion', demo: true }); setModal('suggestion') }}><div className="wd-outfit-imgs">{s.itemIds.map((id) => <Thumb key={id} item={items.find((i) => i.id === id) || byId[id]} />)}</div><span>{s.name}</span></button>)}</div>
            </section>
          </div>
          <aside className="wd-side">
            <section className="wd-panel"><div className="wd-side-head"><h2>Saved Looks</h2><button type="button" className="wd-link wd-text-button" onClick={() => setModal('all-looks')}>View All <ArrowRight size={16} /></button></div>
              <ul className="wd-looks">
                {savedLooks.length ? savedLooks.slice(0, 3).map((look) => (
                  <li key={look.id}>
                    <button type="button" className="wd-look-button" onClick={() => { setSelectedLook(look); setModal('look-details') }}>
                      <div className="wd-look-imgs">{look.products.slice(0, 2).map((product, index) => <Thumb key={product.product_id || index} item={{ name: product.title || 'Saved product', color: product.color || '', shape: product.category || 'tops', imageData: retailerUrl(product.image_url) }} />)}</div>
                      <div className="wd-look-text"><strong>{look.name}</strong><span>{look.products.length} item{look.products.length === 1 ? '' : 's'}, {lookDate(look)}</span></div>
                      <ChevronRight size={18} />
                    </button>
                  </li>
                )) : <li className="wd-saved-empty">Saved outfits will appear here. Use “Save Look” in the fitting room to keep one on this device.</li>}
              </ul>
            </section>
            <section className="wd-panel"><h2 className="wd-side-title">Quick Actions</h2><div className="wd-actions">{quickActions.map(({ icon: Icon, label, href, onClick }) => { const inner = <><Icon size={20} strokeWidth={1.6} /><span>{label}</span><ChevronRight size={17} /></>; return href ? <a key={label} className="wd-action" href={href}>{inner}</a> : <button key={label} type="button" className="wd-action" onClick={onClick}>{inner}</button> })}</div></section>
          </aside>
        </div>
      </div>

      {modal === 'add' && <Modal title="Add a Wardrobe Item" onClose={() => setModal(null)}>
        <form className="wd-form" onSubmit={saveNewItem}>
          <label>Item name <span>*</span><input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Linen shirt" /></label>
          <label>Category <span>*</span><select value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })}><option value="">Choose category</option>{GROUPS.map((g) => <option key={g} value={g}>{g}</option>)}</select></label>
          <label>Color <span>*</span><input value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} placeholder="e.g. Sage green" /></label>
          <label>Brand (optional)<input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} placeholder="Brand name" /></label>
          <label>Notes (optional)<textarea rows="3" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Fit, occasion, or care notes" /></label>
          <div className="wd-image-upload"><span>Item image (optional)</span><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => handleImage(e.target.files?.[0])} /><small>PNG, JPG, or WEBP · maximum 5 MB. Kept locally in this browser prototype.</small>{imageError && <p className="wd-form-error">{imageError}</p>}{imageData && <img className="wd-image-preview" src={imageData} alt="Preview of selected wardrobe item" />}</div>
          {formError && <p className="wd-form-error" role="alert">{formError}</p>}
          <p className="wd-prototype-note">This item is saved in this browser only; it is not uploaded to the backend.</p>
          <div className="wd-form-actions"><button type="button" className="wd-secondary-btn" onClick={() => setModal(null)}>Cancel</button><button type="submit" className="wd-primary-btn">Add Item</button></div>
        </form>
      </Modal>}
      {(modal === 'look-details' || modal === 'suggestion') && selectedLook && <Modal title={selectedLook.name} onClose={() => setModal(null)}>
        <div className="wd-detail-content">
          <p className="wd-prototype-note">{selectedLook.demo ? 'Style suggestion — not saved.' : `Saved on this device · ${lookDate(selectedLook)}`}</p>
          <div className="wd-detail-items">{selectedLookItems.map((item) => (
            <div className="wd-detail-item" key={item.id}>
              <Thumb item={item} />
              <div>
                <strong>{item.name}</strong>
                <span>{item.group}{item.color ? ` · ${item.color}` : ''}{item.price !== undefined && item.price !== null && Number.isFinite(Number(item.price)) ? ` · ${item.currency === 'INR' ? '₹' : `${item.currency} `}${Number(item.price).toLocaleString('en-IN')}` : ''}</span>
                {item.productUrl && <a href={item.productUrl} target="_blank" rel="noopener noreferrer">Shop at {item.store}</a>}
              </div>
            </div>
          ))}</div>
          {selectedLook.totalPrice !== undefined && selectedLook.totalPrice !== null && Number.isFinite(Number(selectedLook.totalPrice)) && <p className="wd-prototype-note">Outfit total: {selectedLook.currency === 'INR' ? '₹' : `${selectedLook.currency || ''} `}{Number(selectedLook.totalPrice).toLocaleString('en-IN')}</p>}
          <div className="wd-form-actions"><button type="button" className="wd-secondary-btn" onClick={() => setModal(null)}>Close</button>{selectedLook.demo && <a className="wd-primary-btn" href="#/ai-stylist">Open AI Stylist</a>}</div>
        </div>
      </Modal>}
      {modal === 'all-looks' && <Modal title="Saved Looks" onClose={() => setModal(null)}><div className="wd-detail-content">{savedLooks.length ? savedLooks.map((look) => <button type="button" className="wd-all-look" key={look.id} onClick={() => { setSelectedLook(look); setModal('look-details') }}><span>{look.name}</span><small>{look.products.length} item{look.products.length === 1 ? '' : 's'}, {lookDate(look)}</small><ChevronRight size={17} /></button>) : <p className="wd-prototype-note">No saved outfits yet. Save a look from the fitting room and it will appear here.</p>}</div></Modal>}
      {modal === 'create-look' && <Modal title="Create a New Look" onClose={() => setModal(null)}><div className="wd-detail-content"><p>To create and save an outfit, use the existing AI Stylist workflow to generate a look and continue to the Fitting Room. This Wardrobe page does not currently have a supported standalone look-creation form.</p><div className="wd-form-actions"><button type="button" className="wd-secondary-btn" onClick={() => setModal(null)}>Cancel</button><a className="wd-primary-btn" href="#/ai-stylist">Open AI Stylist</a></div></div></Modal>}
    </AppShell>
  )
}
