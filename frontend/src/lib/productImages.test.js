import { describe, expect, it } from 'vitest'
import { placeholderImageFor, productImageFor, usableImageUrl } from './productImages.js'

const CATEGORIES = ['shirts', 't-shirts', 'tops', 'pants', 'jeans', 'skirts', 'dresses', 'shoes', 'watches', 'bags', 'sunglasses', 'accessories']

describe('usableImageUrl', () => {
  it('accepts real http(s) addresses', () => {
    expect(usableImageUrl('https://images.example-shop.com/a.jpg')).toBe('https://images.example-shop.com/a.jpg')
    expect(usableImageUrl('  http://cdn.shop.in/x.png ')).toBe('http://cdn.shop.in/x.png')
  })

  it('rejects empty, non-string, non-http and reserved demo hosts', () => {
    for (const bad of [null, undefined, '', '   ', 42, 'not a url', 'javascript:alert(1)', 'data:image/png;base64,AAAA', 'ftp://x.com/a.jpg']) {
      expect(usableImageUrl(bad)).toBe('')
    }
    // the demo catalogue's addresses can never load
    expect(usableImageUrl('https://cdn.mockfashionstore.test/images/mock001.jpg')).toBe('')
    expect(usableImageUrl('https://a.example/x.jpg')).toBe('')
  })
})

describe('placeholderImageFor', () => {
  it('draws every catalogue category', () => {
    for (const category of CATEGORIES) {
      const src = placeholderImageFor({ category, color: 'navy' })
      expect(src.startsWith('data:image/svg+xml;charset=utf-8,')).toBe(true)
      expect(decodeURIComponent(src)).toContain('<svg')
    }
  })

  it('tints with the product colour and differs between colours', () => {
    const navy = decodeURIComponent(placeholderImageFor({ category: 'shirts', color: 'Navy' }))
    const red = decodeURIComponent(placeholderImageFor({ category: 'shirts', color: 'red' }))
    expect(navy).toContain('#2c3556')
    expect(red).toContain('#b03a35')
    expect(navy).not.toBe(red)
  })

  it('uses a neutral tint for an unknown or missing colour', () => {
    expect(decodeURIComponent(placeholderImageFor({ category: 'bags', color: 'chartreuse-ish' }))).toContain('#cfc2a8')
    expect(decodeURIComponent(placeholderImageFor({ category: 'bags', color: null }))).toContain('#cfc2a8')
  })

  it('returns "" for an unknown category or no product', () => {
    expect(placeholderImageFor({ category: 'capes', color: 'red' })).toBe('')
    expect(placeholderImageFor({})).toBe('')
    expect(placeholderImageFor(null)).toBe('')
  })

  it('never mutates the product', () => {
    const product = Object.freeze({ product_id: 'p1', category: 'pants', color: 'black', image_url: null })
    expect(() => placeholderImageFor(product)).not.toThrow()
  })
})

describe('productImageFor', () => {
  const real = { category: 'shirts', color: 'white', image_url: 'https://images.shop.com/a.jpg' }

  it('prefers the real image', () => {
    expect(productImageFor(real)).toBe('https://images.shop.com/a.jpg')
  })

  it('falls back to the placeholder when the real image failed to load', () => {
    expect(productImageFor(real, true)).toBe(placeholderImageFor(real))
  })

  it('falls back for demo-host, null and missing image_url', () => {
    for (const image_url of ['https://cdn.mockfashionstore.test/i/1.jpg', null, undefined, '']) {
      const p = { category: 'pants', color: 'black', image_url }
      expect(productImageFor(p)).toBe(placeholderImageFor(p))
      expect(productImageFor(p)).not.toBe('')
    }
  })

  it('is empty only when nothing can be drawn', () => {
    expect(productImageFor({ category: 'capes', image_url: null })).toBe('')
    expect(productImageFor(null)).toBe('')
  })
})
