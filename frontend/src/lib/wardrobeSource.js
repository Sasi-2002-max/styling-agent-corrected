// Decides "mock store" vs "real retailers (SerpApi)" for the Wardrobe page, and stores hearted products.
// Mode is detected from the DATA, not an env flag: your Fitting Room already marks mock products
// with a store name containing "demo" or "mock" (see isDemo in FittingRoom.jsx).
import { readSavedLooks } from './savedLooks.js'

export const FAVORITES_KEY = 'styleai.favoriteProducts.v1'
export const FAVORITES_UPDATED_EVENT = 'styleai:favorites-updated'
const MODE_KEY = 'styleai.shoppingMode.v1'

export const isDemoProduct = (p) => /demo|mock/i.test((p && p.store) || '')
export const isRealLook = (look) =>
  Array.isArray(look?.products) && look.products.length > 0 && look.products.some((p) => !isDemoProduct(p))

export function retailerUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const url = new URL(value.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}
export const retailerName = (value) =>
  (typeof value === 'string' ? value.replace(/^SerpApi\s*\/\s*/i, '').trim() : 'retailer')

// ---- mode ----
// Fitting Room calls this whenever it shows an outfit; Wardrobe reads it on open.
export function recordShoppingMode(products) {
  try {
    if (!Array.isArray(products) || !products.length) return
    localStorage.setItem(MODE_KEY, products.some((p) => !isDemoProduct(p)) ? 'real' : 'mock')
  } catch { /* storage unavailable */ }
}

export function resolveShoppingMode() {
  try {
    const stored = localStorage.getItem(MODE_KEY)
    if (stored === 'real' || stored === 'mock') return stored
    if (readFavoriteProducts().length || readSavedLooks().some(isRealLook)) return 'real'
  } catch { /* ignore */ }
  return 'mock'
}

// ---- favourites (real products only) ----
export function readFavoriteProducts() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

const FIELDS = ['product_id', 'store', 'brand', 'title', 'category', 'color', 'price', 'currency', 'image_url', 'product_url']

function writeFavorites(list) {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(list))
    window.dispatchEvent(new Event(FAVORITES_UPDATED_EVENT))
  } catch { /* storage unavailable */ }
}

export function addFavoriteProduct(product) {
  if (!product || !product.product_id || isDemoProduct(product)) return
  const list = readFavoriteProducts().filter((p) => String(p.product_id) !== String(product.product_id))
  const clean = Object.fromEntries(FIELDS.filter((k) => product[k] !== undefined).map((k) => [k, product[k]]))
  writeFavorites([{ ...clean, savedAt: Date.now() }, ...list])
}

export function removeFavoriteProduct(id) {
  writeFavorites(readFavoriteProducts().filter((p) => String(p.product_id) !== String(id)))
}

// ---- favourite -> wardrobe item ----
const GROUP_RULES = [
  [/dress|gown|skirt/i, 'Dresses'],
  [/jacket|blazer|coat|outer|hoodie|cardigan/i, 'Outerwear'],
  [/shoe|sneaker|boot|heel|sandal|loafer|footwear/i, 'Shoes'],
  [/bag|purse|tote|clutch|backpack/i, 'Bags'],
  [/pant|jean|trouser|short|bottom|legging/i, 'Bottoms'],
  [/top|shirt|tee|blouse|sweater|kurta|polo/i, 'Tops'],
]
const SHAPE = { Tops: 'tops', Bottoms: 'pants', Dresses: 'dresses', Outerwear: 'shirts', Shoes: 'shoes', Bags: 'bags', Accessories: 'accessories' }
const groupFor = (text = '') => (GROUP_RULES.find(([re]) => re.test(text)) || [null, 'Accessories'])[1]

export function favoriteToItem(p) {
  const group = groupFor(`${p.category || ''} ${p.title || ''}`)
  return {
    id: String(p.product_id),
    name: p.title || 'Saved product',
    group,
    shape: SHAPE[group],
    color: p.color || '',
    brand: retailerName(p.store),
    imageData: retailerUrl(p.image_url),
    productUrl: retailerUrl(p.product_url),
    favorite: true,
    addedAt: Number(p.savedAt) || 0,
  }
}
