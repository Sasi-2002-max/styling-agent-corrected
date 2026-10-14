import { describe, expect, it } from 'vitest'
import { deleteSavedLook, readSavedLooks, saveSavedLook, SAVED_LOOKS_KEY } from './savedLooks.js'

function memoryStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
}

const product = {
  product_id: 'serp-shirt-1',
  store: 'SerpApi / Example Store',
  title: 'Blue office shirt',
  category: 'shirts',
  price: 799,
  currency: 'INR',
  image_url: 'https://images.example.com/shirt.jpg',
  product_url: 'https://shop.example.com/shirt',
  internal_note: 'must not be persisted',
}

describe('saved looks storage', () => {
  it('saves a look and keeps its product links and prices', () => {
    const storage = memoryStorage()
    const look = saveSavedLook(
      { products: [product], occasion: 'Office', totalPrice: 799 },
      storage,
    )

    expect(look.name).toBe('Office outfit')
    expect(look.products[0].product_url).toBe(product.product_url)
    expect(look.products[0].internal_note).toBeUndefined()
    expect(readSavedLooks(storage)).toEqual([look])
  })

  it('returns no looks for corrupt saved data', () => {
    const storage = memoryStorage()
    storage.setItem(SAVED_LOOKS_KEY, '{bad json')
    expect(readSavedLooks(storage)).toEqual([])
  })

  it('does not save an empty outfit and can delete a saved look', () => {
    const storage = memoryStorage()
    expect(saveSavedLook({ products: [] }, storage)).toBeNull()
    const look = saveSavedLook({ products: [product] }, storage)
    expect(deleteSavedLook(look.id, storage)).toBe(true)
    expect(readSavedLooks(storage)).toEqual([])
  })
})
