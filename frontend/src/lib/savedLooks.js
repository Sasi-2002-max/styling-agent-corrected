export const SAVED_LOOKS_KEY = 'styleai.savedLooks.v1'
export const SAVED_LOOKS_UPDATED_EVENT = 'styleai:saved-looks-updated'

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)

function defaultStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

function newId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  return `look-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function storedProduct(product) {
  const allowedFields = [
    'product_id',
    'store',
    'brand',
    'title',
    'category',
    'color',
    'price',
    'currency',
    'sizes',
    'image_url',
    'product_url',
    'availability',
  ]
  return Object.fromEntries(
    allowedFields
      .filter((key) => product[key] !== undefined)
      .map((key) => [key, product[key]]),
  )
}

export function readSavedLooks(storage = defaultStorage()) {
  if (!storage) return []
  try {
    const parsed = JSON.parse(storage.getItem(SAVED_LOOKS_KEY) || '[]')
    return Array.isArray(parsed)
      ? parsed
        .filter((look) => isObject(look) && typeof look.id === 'string' && Array.isArray(look.products))
        .map((look) => ({ ...look, products: look.products.filter(isObject) }))
      : []
  } catch {
    return []
  }
}

export function saveSavedLook(
  { products, occasion = '', style = '', totalPrice = null, currency = 'INR' },
  storage = defaultStorage(),
) {
  if (!storage || !Array.isArray(products)) return null

  const cleanProducts = products
    .filter((product) => isObject(product) && (product.product_id || product.title))
    .map(storedProduct)
  if (cleanProducts.length === 0) return null

  const cleanOccasion = typeof occasion === 'string' ? occasion.trim() : ''
  const cleanStyle = typeof style === 'string' ? style.trim() : ''
  const name = cleanOccasion
    ? `${cleanOccasion} outfit`
    : cleanStyle
      ? `${cleanStyle} outfit`
      : 'Outfit of the Day'
  const numericTotal = totalPrice === null || totalPrice === undefined || totalPrice === ''
    ? Number.NaN
    : Number(totalPrice)
  const look = {
    id: newId(),
    name,
    occasion: cleanOccasion,
    style: cleanStyle,
    createdAt: new Date().toISOString(),
    totalPrice: Number.isFinite(numericTotal) && numericTotal >= 0 ? numericTotal : null,
    currency: typeof currency === 'string' && currency ? currency : 'INR',
    products: cleanProducts,
  }

  try {
    const savedLooks = readSavedLooks(storage)
    storage.setItem(SAVED_LOOKS_KEY, JSON.stringify([look, ...savedLooks]))
    try {
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(SAVED_LOOKS_UPDATED_EVENT, { detail: look }))
    } catch {
      // The saved record is already persisted; notification is only for refreshing open views.
    }
    return look
  } catch {
    return null
  }
}

export function deleteSavedLook(lookId, storage = defaultStorage()) {
  if (!storage || typeof lookId !== 'string') return false
  try {
    const savedLooks = readSavedLooks(storage)
    const next = savedLooks.filter((look) => look.id !== lookId)
    if (next.length === savedLooks.length) return false
    storage.setItem(SAVED_LOOKS_KEY, JSON.stringify(next))
    try {
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(SAVED_LOOKS_UPDATED_EVENT, { detail: { id: lookId } }))
    } catch {
      // The saved record is already persisted; notification is only for refreshing open views.
    }
    return true
  } catch {
    return false
  }
}
