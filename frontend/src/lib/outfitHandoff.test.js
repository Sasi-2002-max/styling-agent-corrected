import { describe, expect, it } from 'vitest'
import {
  STORAGE_KEY,
  clearSelectedOutfit,
  extractOutfit,
  loadSelectedOutfit,
  saveSelectedOutfit,
  summarizeOutfit,
} from './outfitHandoff.js'

const memoryStorage = () => {
  const data = new Map()
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
  }
}

const response = {
  status: 'approved',
  outfit_plan: {
    occasion: 'wedding',
    style: 'elegant',
    items: [
      { category: 'top', item: 'kurta', color: 'navy' },
      { category: 'bottom', item: 'trousers', color: 'cream' },
      { category: 'shoes', item: 'loafers' },
      { category: 'outer', item: 'bandhgala' },
      { category: 'extra', item: 'stole' },
    ],
  },
  selected_products: [{ product_id: 'p1', title: 'Navy Kurta', price: 2000, currency: 'INR' }],
}

describe('extractOutfit', () => {
  it('keeps the backend plan and products unmodified', () => {
    const outfit = extractOutfit(response, { userQuery: 'q', requestedBudget: 5000 })
    expect(outfit.outfit_plan).toBe(response.outfit_plan)
    expect(outfit.selected_products).toEqual(response.selected_products)
    expect(outfit.approved).toBe(true)
    expect(outfit.requestedBudget).toBe(5000)
  })

  it('returns null for empty or malformed responses', () => {
    expect(extractOutfit(null)).toBeNull()
    expect(extractOutfit({})).toBeNull()
    expect(extractOutfit({ outfit_plan: { occasion: 'x', items: 'nope' }, selected_products: 5 })).toBeNull()
  })
})

describe('summarizeOutfit', () => {
  it('shows occasion, style, capped key items and the typed budget', () => {
    const s = summarizeOutfit(extractOutfit(response, { requestedBudget: 5000 }))
    expect(s.occasion).toBe('wedding')
    expect(s.keyItems).toEqual(['navy kurta', 'cream trousers', 'loafers', 'bandhgala'])
    expect(s.extraItemCount).toBe(1)
    expect(s.budget).toEqual({ amount: 5000, currency: 'INR' })
  })

  it('prefers plan.budget and omits the budget when unknown', () => {
    const withPlan = extractOutfit({ outfit_plan: { items: [{ item: 'shirt' }], budget: 3000, currency: 'INR' } }, { requestedBudget: 5000 })
    expect(summarizeOutfit(withPlan).budget.amount).toBe(3000)
    const none = extractOutfit({ outfit_plan: { items: [{ item: 'shirt' }] } })
    expect(summarizeOutfit(none).budget).toBeNull()
  })

  it('falls back to selected product titles when the plan has no items', () => {
    const s = summarizeOutfit(extractOutfit({ selected_products: [{ title: 'Blue Shirt' }] }))
    expect(s.keyItems).toEqual(['Blue Shirt'])
    expect(s.occasion).toBe('')
  })
})

describe('handoff storage', () => {
  it('round-trips and clears', () => {
    const storage = memoryStorage()
    const outfit = extractOutfit(response)
    expect(saveSelectedOutfit(outfit, storage)).toBe(true)
    expect(loadSelectedOutfit(storage).outfit_plan).toEqual(response.outfit_plan)
    clearSelectedOutfit(storage)
    expect(loadSelectedOutfit(storage)).toBeNull()
  })

  it('fails safely when storage is missing, throws, or holds junk', () => {
    const outfit = extractOutfit(response)
    expect(saveSelectedOutfit(outfit, null)).toBe(false)
    expect(saveSelectedOutfit(outfit, { setItem: () => { throw new Error('full') } })).toBe(false)
    const junk = memoryStorage()
    junk.setItem(STORAGE_KEY, '{not json')
    expect(loadSelectedOutfit(junk)).toBeNull()
  })
})
