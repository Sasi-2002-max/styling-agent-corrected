/**
 * Outfit handoff: AI Stylist chat -> (future) Fitting Room page.
 *
 * Pure helpers plus one tiny storage slot. Nothing here calls the backend and
 * nothing is invented: every value comes from the POST /api/style response
 * (outfit_plan, selected_products, status, approved) or from what the user typed.
 *
 * Handoff contract (stored as JSON under STORAGE_KEY in sessionStorage):
 *   {
 *     version: 1,
 *     savedAt: ISO string,
 *     userQuery: string | null,        // exact query sent to /api/style
 *     requestedBudget: number | null,  // budget typed in the chat, if any
 *     status: string | null,           // backend `status`
 *     approved: boolean,               // backend approval (approved === true || status === 'approved')
 *     outfit_plan: object,             // backend outfit_plan, unmodified
 *     selected_products: object[]      // backend selected_products, unmodified
 *   }
 * The next task reads it with loadSelectedOutfit().
 */

export const HANDOFF_VERSION = 1
export const STORAGE_KEY = 'styleai.selectedOutfit'

const asArray = (value) => (Array.isArray(value) ? value : [])
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)

const hasValue = (value) => value !== undefined && value !== null && value !== ''

function toFiniteNumber(value) {
  if (!hasValue(value)) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Pull the outfit data out of a backend response. Returns null when the
 * response carries nothing usable (so the UI can show a graceful fallback
 * instead of a button that would hand off an empty outfit).
 */
export function extractOutfit(result, { userQuery = null, requestedBudget = null } = {}) {
  if (!isObject(result)) return null

  const plan = isObject(result.outfit_plan) ? result.outfit_plan : {}
  const products = asArray(result.selected_products).filter(isObject)
  const items = asArray(plan.items).filter(isObject)
  const accessories = asArray(plan.accessories).filter(isObject)

  const usable = items.length > 0 || accessories.length > 0 || products.length > 0
  if (!usable) return null

  return {
    version: HANDOFF_VERSION,
    savedAt: new Date().toISOString(),
    userQuery: typeof userQuery === 'string' && userQuery ? userQuery : null,
    requestedBudget: toFiniteNumber(requestedBudget),
    status: typeof result.status === 'string' ? result.status : null,
    approved: result.approved === true || result.status === 'approved',
    outfit_plan: plan,
    selected_products: products,
  }
}

/**
 * Short summary fields for the chat. Every field is optional:
 *   { occasion, style, keyItems: string[], extraItemCount, budget: {amount, currency} | null }
 * Budget prefers the backend's plan.budget, then the budget the user typed.
 */
export function summarizeOutfit(outfit) {
  if (!outfit) return null
  const plan = outfit.outfit_plan || {}
  const products = outfit.selected_products

  const pieceName = (piece) => [piece.color, piece.item].filter(hasValue).join(' ').trim()
  let names = asArray(plan.items).map(pieceName).filter(Boolean)
  if (names.length === 0) {
    // No planned items: fall back to the real products the backend selected.
    names = products.map((p) => (typeof p.title === 'string' ? p.title : p.name)).filter(hasValue)
  }

  const MAX_KEY_ITEMS = 4
  const planBudget = toFiniteNumber(plan.budget)
  const amount = planBudget !== null ? planBudget : outfit.requestedBudget
  const currency =
    planBudget !== null && typeof plan.currency === 'string' && plan.currency ? plan.currency : 'INR'

  return {
    occasion: hasValue(plan.occasion) ? String(plan.occasion) : '',
    style: hasValue(plan.style) ? String(plan.style) : '',
    keyItems: names.slice(0, MAX_KEY_ITEMS),
    extraItemCount: Math.max(0, names.length - MAX_KEY_ITEMS),
    budget: amount !== null && amount > 0 ? { amount, currency } : null,
  }
}

// sessionStorage can be missing or throw (private mode, blocked storage, SSR/tests).
function defaultStorage() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null
  } catch {
    return null
  }
}

/** Save the chosen outfit for the next page. Returns true if it was stored. */
export function saveSelectedOutfit(outfit, storage = defaultStorage()) {
  if (!outfit || !storage) return false
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(outfit))
    return true
  } catch {
    return false
  }
}

/** Read the saved outfit back; null if nothing valid is stored. */
export function loadSelectedOutfit(storage = defaultStorage()) {
  if (!storage) return null
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return isObject(parsed) && parsed.version === HANDOFF_VERSION ? parsed : null
  } catch {
    return null
  }
}

export function clearSelectedOutfit(storage = defaultStorage()) {
  try {
    if (storage) storage.removeItem(STORAGE_KEY)
  } catch {
    // nothing to clear
  }
}
