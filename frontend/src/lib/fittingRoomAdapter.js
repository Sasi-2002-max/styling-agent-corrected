/**
 * Adapters between the AI Stylist handoff and the Fitting Room page.
 *
 * Nothing here is invented: products are the exact objects the backend returned
 * in POST /api/style `selected_products` (saved by outfitHandoff.js). They share
 * the FittingRoomProduct shape declared in src/fitting-room/types.ts.
 */

import { slotForCategory } from '../fitting-room/categoryMap'
import { normalizeColorName } from '../fitting-room/colorSwitching'

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

const isUsableProduct = (p) =>
  isObject(p) && typeof p.product_id === 'string' && p.product_id !== '' && typeof p.category === 'string'

const validPrice = (p) => (p && typeof p.price === 'number' && Number.isFinite(p.price) && p.price >= 0 ? p.price : null)

/**
 * Turn the saved handoff into the FittingRoomResponse shape that the existing
 * fitting-room reducer (INIT_FROM_RESPONSE) understands.
 * Returns null when there is no purchasable product to show.
 */
export function buildFittingRoomResponse(handoff, gender = 'female') {
  if (!isObject(handoff)) return null
  let products = (Array.isArray(handoff.selected_products) ? handoff.selected_products : []).filter(isUsableProduct)
  if (products.length === 0) return null

  // A complete traditional outfit already contains its lower garment. Do not
  // layer a separately recommended pair of trousers beneath an Anarkali set,
  // salwar suit, lehenga set, saree, co-ord set, jumpsuit, or one-piece dress.
  const productText = (p) => `${p.title || ''} ${p.name || ''} ${p.description || ''}`.toLowerCase()
  const completeOutfitPattern = /\b(anarkali|salwar\s*(?:kameez|suit)|suit\s*set|kurta\s*set|lehenga(?:\s*choli)?(?:\s*set)?|saree|sari|co[- ]?ord\s*set|jumpsuit|one[- ]?piece|maxi\s*dress|gown|dress)\b/
  const topProduct = products.find((p) => ['top', 'tops', 'dress', 'dresses', 'kurta', 'kurtas'].includes(String(p.category || '').toLowerCase()))
  const topText = topProduct ? productText(topProduct) : ''
  const titleClearlyDescribesSet = /\b(set|suit|with\s+(?:palazzo|pants|trouser|bottom|dupatta)|palazzo\s*&?\s*dupatta)\b/.test(topText)
  const isCompleteSet = Boolean(topProduct && completeOutfitPattern.test(topText) && (titleClearlyDescribesSet || /\b(saree|sari|jumpsuit|one[- ]?piece|dress|gown)\b/.test(topText)))
  if (isCompleteSet) {
    products = products.filter((p) => {
      const category = String(p.category || '').toLowerCase()
      return !['pants', 'trousers', 'jeans', 'skirts', 'bottom', 'bottoms'].includes(category)
    })
  }

  const items = products.map((product, index) => ({
    item_index: index,
    category: product.category,
    product, // same object reference as saved: nothing copied or altered
    visual_source: product.image_url ? 'product_image' : null,
    color_variations: Array.isArray(product.color_variations) ? product.color_variations : [],
    alternatives: [],
    error: null,
  }))

  const allPlaced = items.every((i) => slotForCategory(i.category) !== null)
  return {
    status: allPlaced ? 'ready' : 'incomplete',
    // No mannequin image asset exists in this project yet, so `asset` is empty.
    mannequin: { gender, asset: '' },
    outfit: {
      status: allPlaced ? 'ready' : 'incomplete',
      selected_products: items.map((i) => ({
        product_id: i.product.product_id,
        category: i.category,
        item_index: i.item_index,
      })),
      total_price: totalPrice(products).amount ?? 0,
      missing_items: [],
    },
    items,
  }
}

/**
 * Sum of the valid prices of the given products.
 * { amount, currency, counted, skipped } -- amount is null if nothing is priced
 * or the products use more than one currency (never add up mixed currencies).
 */
export function totalPrice(products) {
  const list = products.filter(Boolean)
  const priced = list.filter((p) => validPrice(p) !== null)
  const currencies = new Set(priced.map((p) => p.currency || 'INR'))
  if (priced.length === 0 || currencies.size !== 1) {
    return { amount: null, currency: null, counted: priced.length, skipped: list.length - priced.length }
  }
  return {
    amount: priced.reduce((sum, p) => sum + validPrice(p), 0),
    currency: [...currencies][0],
    counted: priced.length,
    skipped: list.length - priced.length,
  }
}

/** Rows shown in "Style Your Look", in display order. */
export const ROW_GROUPS = [
  { key: 'top', label: 'Top', slots: ['top', 'shirt', 't_shirt', 'dress'] },
  { key: 'bottom', label: 'Bottom', slots: ['pants', 'jeans', 'skirt'] },
  { key: 'footwear', label: 'Footwear', slots: ['shoes'] },
  { key: 'accessories', label: 'Accessories', slots: ['bag', 'watch', 'sunglasses', 'accessory'] },
]

export const SLOT_LABELS = {
  shirt: 'Shirt',
  t_shirt: 'T-shirt',
  top: 'Top',
  pants: 'Pants',
  jeans: 'Jeans',
  skirt: 'Skirt',
  dress: 'Dress',
  shoes: 'Shoes',
  watch: 'Watch',
  sunglasses: 'Sunglasses',
  bag: 'Bag',
  accessory: 'Accessory',
}

export function groupForSlot(slot) {
  return ROW_GROUPS.find((g) => g.slots.includes(slot)) || null
}

// ---------------------------------------------------------------- colours

const COLOR_HEX = {
  black: '#1f1b18', white: '#fbfaf7', ivory: '#f4ecd8', cream: '#eadfc6', beige: '#d9c7a6',
  camel: '#c19a62', tan: '#c8a77a', brown: '#6b4a32', navy: '#2c3556', blue: '#41588a',
  green: '#2f5b43', olive: '#6b6b3a', emerald: '#1f6b4f', sage: '#9aa88a', teal: '#2f7a7a',
  maroon: '#6b2230', burgundy: '#5c1f2e', wine: '#5c2236', red: '#b03a35', rust: '#a4502d',
  pink: '#d9929a', rose: '#c9777f', blush: '#e6bdb8', peach: '#eeb99a', orange: '#d9792f',
  mustard: '#c9a032', yellow: '#e0c24f', gold: '#c9a45c', grey: '#8c8a86', charcoal: '#403d3a',
  silver: '#b9b8b4', purple: '#6b4a7a', lavender: '#b7a6cf', khaki: '#b3a577', denim: '#4a6285',
  turquoise: '#3aa5a0', coral: '#e0705f', nude: '#dcb9a0',
}

/** A CSS colour for a colour name, or null when the name isn't a known colour. */
export function swatchHex(name) {
  const key = normalizeColorName(name)
  if (!key) return null
  if (COLOR_HEX[key]) return COLOR_HEX[key]
  const words = key.split(' ')
  for (const w of [...words].reverse()) if (COLOR_HEX[w]) return COLOR_HEX[w]
  return null
}

/**
 * Colour names to offer as swatches for a product. Real sources only: the
 * product's own colour, any colour_variations the backend attached, and the
 * stylist's own colour palette. Capped, de-duplicated by normalised name.
 */
export function swatchOptions(product, palette = [], max = 5) {
  if (!product) return []
  const variations = Array.isArray(product.color_variations) ? product.color_variations.map((v) => v && v.color) : []
  const seen = new Set()
  const out = []
  for (const name of [product.color, ...variations, ...(Array.isArray(palette) ? palette : [])]) {
    if (typeof name !== 'string') continue
    const key = normalizeColorName(name)
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(name.trim())
    if (out.length >= max) break
  }
  return out
}
