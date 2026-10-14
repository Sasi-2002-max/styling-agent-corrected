import { useState } from 'react'

const SLOT_ORDER = [
  'dress',
  'top',
  'shirt',
  't_shirt',
  'pants',
  'jeans',
  'skirt',
  'shoes',
  'necklace',
  'accessory',
  'accessories',
  'bag',
  'watch',
  'sunglasses',
]

const SLOT_LABELS = {
  dress: 'Outfit',
  top: 'Top',
  shirt: 'Top',
  t_shirt: 'Top',
  pants: 'Bottom',
  jeans: 'Bottom',
  skirt: 'Bottom',
  shoes: 'Footwear',
  necklace: 'Necklace',
  accessory: 'Accessory',
  accessories: 'Accessories',
  bag: 'Bag',
  watch: 'Watch',
  sunglasses: 'Sunglasses',
}

function safeImageUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const url = new URL(value.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

function retailerName(value) {
  return typeof value === 'string' ? value.replace(/^SerpApi\s*\/\s*/i, '').trim() : ''
}

function ProductPhoto({ slot, product }) {
  const url = safeImageUrl(product.image_url)
  const shopUrl = safeImageUrl(product.product_url)
  const [failedUrl, setFailedUrl] = useState('')
  const title = product.title || 'Selected retailer product'
  const store = retailerName(product.store)
  const price = typeof product.price === 'number' && Number.isFinite(product.price)
    ? `${product.currency && product.currency !== 'INR' ? `${product.currency} ` : '₹'}${product.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
    : ''
  const photo = (
    <div className="fr-product-photo">
      {url && failedUrl !== url ? (
        <img
          src={url}
          alt={title}
          loading="lazy"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <div className="fr-product-photo-missing" role="img" aria-label="Retailer image unavailable">
          Retailer image unavailable
        </div>
      )}
    </div>
  )

  return (
    <article className="fr-product-card">
      {shopUrl ? <a className="fr-product-shop-link" href={shopUrl} target="_blank" rel="noopener noreferrer" aria-label={`Shop ${title} at ${store || 'retailer'}`}>{photo}</a> : photo}
      <div className="fr-product-caption">
        <span className="fr-product-category">{SLOT_LABELS[slot] || product.category || 'Item'}</span>
        <span className="fr-product-title" title={title}>{title}</span>
        {(store || price) && <span className="fr-product-meta">{[store, price].filter(Boolean).join(' · ')}</span>}
      </div>
    </article>
  )
}

export default function RetailerProductPreview({ selectedOutfit }) {
  const items = Object.entries(selectedOutfit || {})
    .filter(([slot, product]) => slot !== 'mannequin' && product && typeof product === 'object')
    .map(([slot, product]) => ({ slot, product }))
    .sort((a, b) => {
      const aIndex = SLOT_ORDER.indexOf(a.slot)
      const bIndex = SLOT_ORDER.indexOf(b.slot)
      return (aIndex < 0 ? SLOT_ORDER.length : aIndex) - (bIndex < 0 ? SLOT_ORDER.length : bIndex)
    })

  return (
    <div className="fr-stage">
      {items.length > 0 ? (
        <div className={'fr-product-grid' + (items.length === 1 ? ' fr-product-grid-single' : '')}>
          {items.map(({ slot, product }) => (
            <ProductPhoto
              key={slot + ':' + (product.product_id || product.image_url || product.title || '')}
              slot={slot}
              product={product}
            />
          ))}
        </div>
      ) : (
        <div className="fr-product-empty">No product images are available for this outfit yet.</div>
      )}
      <p className="fr-stage-note">
        Original retailer photos shown directly. Each item is previewed separately.
      </p>
    </div>
  )
}
