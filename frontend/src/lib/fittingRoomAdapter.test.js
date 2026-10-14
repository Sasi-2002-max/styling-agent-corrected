import { describe, expect, it } from 'vitest'
import { fittingRoomReducer, createInitialState } from '../fitting-room/fittingRoomState'
import { buildFittingRoomResponse, swatchHex, swatchOptions, totalPrice } from './fittingRoomAdapter.js'

const kurta = { product_id: 'k1', category: 'tops', title: 'Kurta', color: 'Green', price: 1699, currency: 'INR', image_url: 'x' }
const pants = { product_id: 'p1', category: 'pants', title: 'Palazzo', color: 'Beige', price: 1299, currency: 'INR', image_url: null }
const odd = { product_id: 'o1', category: 'capes', title: 'Cape', price: 100, currency: 'INR' }

describe('buildFittingRoomResponse', () => {
  it('returns null without usable products', () => {
    expect(buildFittingRoomResponse(null)).toBeNull()
    expect(buildFittingRoomResponse({ selected_products: [] })).toBeNull()
    expect(buildFittingRoomResponse({ selected_products: [{ title: 'no id' }] })).toBeNull()
  })

  it('feeds the existing reducer without altering products', () => {
    const res = buildFittingRoomResponse({ selected_products: [kurta, pants] })
    expect(res.status).toBe('ready')
    const state = fittingRoomReducer(createInitialState('female'), { type: 'INIT_FROM_RESPONSE', response: res })
    expect(state.selectedOutfit.top).toBe(kurta)
    expect(state.selectedOutfit.pants).toBe(pants)
    expect(res.outfit.total_price).toBe(2998)
  })

  it('marks the outfit incomplete when a category has no slot', () => {
    expect(buildFittingRoomResponse({ selected_products: [kurta, odd] }).status).toBe('incomplete')
  })
})

describe('totalPrice', () => {
  it('sums valid prices and skips invalid ones', () => {
    expect(totalPrice([kurta, pants, { price: 'abc' }, null])).toMatchObject({ amount: 2998, currency: 'INR', skipped: 1 })
  })
  it('refuses to add mixed currencies', () => {
    expect(totalPrice([kurta, { ...pants, currency: 'USD' }]).amount).toBeNull()
  })
})

describe('swatches', () => {
  it('uses real colour sources only, de-duplicated', () => {
    expect(swatchOptions(kurta, ['green', 'Maroon', 'navy blue'])).toEqual(['Green', 'Maroon', 'navy blue'])
    expect(swatchOptions(null)).toEqual([])
  })
  it('maps names to a hex, or null when unknown', () => {
    expect(swatchHex('Dark Green')).toBe(swatchHex('green'))
    expect(swatchHex('unicorn')).toBeNull()
  })
})
