import { useState } from 'react'
import { productImageFor } from '../lib/productImages.js'
import { mannequinImageFor } from '../lib/mannequinAsset.js'

/**
 * Mannequin panel.
 *
 * The mannequin is a local picture (src/assets/mannequin/, see mannequinAsset.js); the garment zones below are calibrated to it.
 * Over it, the product pictures of the selected outfit are layered by body zone.
 * That is a layered preview, NOT a fitted try-on: the garments are not warped to the
 * body and the mannequin's own picture never changes. Genuine garment replacement
 * needs per-garment cut-outs or a try-on service. The panel says so.
 */

// Position of each slot inside the figure box (percent of the figure's width/height).
const ZONES = {
  bottom: { left: 17, top: 46, width: 66, height: 42 },
  top: { left: 12, top: 14, width: 76, height: 36 },
  dress: { left: 11, top: 14, width: 78, height: 68 },
  shoes: { left: 22, top: 89, width: 56, height: 10 },
  bag: { left: 70, top: 49, width: 30, height: 14 },
  watch: { left: -4, top: 44, width: 16, height: 7 },
  sunglasses: { left: 33, top: 3, width: 34, height: 6 },
  accessory: { left: 34, top: 12, width: 32, height: 6 },
}
// Calibration for the bundled mannequin pictures (src/assets/mannequin/*.png).
// `aspect` is the picture's width / height; zones are percentages of the picture, measured on
// the cut-out figures. If you replace a picture with one of a different pose or crop, re-measure
// these numbers. The built-in silhouette (used only when a picture is missing) keeps ZONES above.
const FIGURES = {
  female: {
    aspect: 331 / 1124,
    zones: {
      top: { left: 13, top: 17, width: 72, height: 33 },
      bottom: { left: 16, top: 40, width: 58, height: 48 },
      dress: { left: 12, top: 17, width: 72, height: 69 },
      shoes: { left: 30, top: 93, width: 40, height: 5 },
      bag: { left: 70, top: 50, width: 30, height: 11 },
      watch: { left: 0, top: 43, width: 13, height: 5 },
      sunglasses: { left: 37, top: 5.5, width: 22, height: 3.5 },
      accessory: { left: 36, top: 14.5, width: 26, height: 4 },
    },
  },
  male: {
    aspect: 730 / 1100,
    zones: {
      top: { left: 22, top: 17, width: 56, height: 33 },
      bottom: { left: 32, top: 45, width: 36, height: 45 },
      dress: { left: 25, top: 17, width: 50, height: 70 },
      shoes: { left: 30, top: 91, width: 40, height: 8 },
      bag: { left: 76, top: 50, width: 22, height: 9 },
      watch: { left: 4, top: 40, width: 10, height: 4 },
      sunglasses: { left: 43, top: 6.5, width: 14, height: 3 },
      accessory: { left: 44, top: 14.5, width: 12, height: 3.5 },
    },
  },
}
const ZONE_FOR_SLOT = { shirt: 'top', t_shirt: 'top', top: 'top', pants: 'bottom', jeans: 'bottom', skirt: 'bottom' }
// Back-to-front paint order.
const PAINT_ORDER = ['bottom', 'top', 'dress', 'shoes', 'bag', 'watch', 'sunglasses', 'accessory']

function Garment({ zone, zones, product }) {
  // Remember WHICH url failed: this component is reused when the slot's product changes.
  const [failedUrl, setFailedUrl] = useState(null)
  const url = product.image_url || null
  // Real image_url when it can load; otherwise a generic, colour-tinted picture of the category.
  const src = productImageFor(product, url !== null && failedUrl === url, true)
  const z = zones[zone]
  return (
    <div
      className={'fr-garment fr-garment-' + zone + (src.startsWith('data:') ? ' fr-garment-flat' : '')}
      style={{ left: z.left + '%', top: z.top + '%', width: z.width + '%', height: z.height + '%' }}
    >
      {src ? (
        <img src={src} alt={product.title || 'Selected item'} onError={() => setFailedUrl(url)} />
      ) : (
        <span className="fr-garment-fallback">{product.title || 'Selected item'}</span>
      )}
    </div>
  )
}

// Used only if the mannequin picture is missing or fails to load.
function Silhouette() {
  return (
    <svg className="fr-figure-svg" viewBox="0 0 200 480" aria-hidden="true" focusable="false">
      <g fill="#e3d2b6" stroke="#d3bf9d" strokeWidth="1.2" strokeLinejoin="round">
        <ellipse cx="100" cy="38" rx="19" ry="24" />
        <rect x="92" y="58" width="16" height="24" rx="6" />
        <path d="M62 84 C74 77 88 80 92 80 L108 80 C112 80 126 77 138 84 C147 102 145 142 137 170 C132 192 134 212 141 234 L59 234 C66 212 68 192 63 170 C55 142 53 102 62 84Z" />
        <path d="M62 88 C48 104 43 152 39 202 L33 228 L46 232 L54 206 C60 162 66 124 71 102Z" />
        <path d="M138 88 C152 104 157 152 161 202 L167 228 L154 232 L146 206 C140 162 134 124 129 102Z" />
        <path d="M59 232 L100 232 L97 438 L91 466 L71 466 L73 438Z" />
        <path d="M141 232 L100 232 L103 438 L109 466 L129 466 L127 438Z" />
      </g>
    </svg>
  )
}

export default function MannequinPreview({ selectedOutfit, note, tryOnImage = null }) {
  const gender = selectedOutfit && selectedOutfit.mannequin
  const src = mannequinImageFor(gender)
  // Remember WHICH picture failed, so switching gender never inherits a stale failure.
  const [failedSrc, setFailedSrc] = useState(null)
  const usePicture = Boolean(src) && src !== failedSrc && Boolean(FIGURES[gender])
  // Picture: its calibrated zones and aspect. No picture: the silhouette and the original zones.
  const zones = usePicture ? FIGURES[gender].zones : ZONES

  // When an AI result exists, show it instead of the approximate layered preview.
  if (tryOnImage) {
    return (
      <div className="fr-stage fr-stage-ai">
        <div className="fr-ai-tryon-frame">
          <img
            className="fr-ai-tryon-image"
            src={tryOnImage}
            alt="AI-generated virtual try-on preview"
          />
        </div>
        <p className="fr-stage-note">
          {note || 'AI-generated outfit preview. Appearance is illustrative, not a size-fit guarantee.'}
        </p>
      </div>
    )
  }

  const layers = []
  for (const [slot, product] of Object.entries(selectedOutfit || {})) {
    if (slot === 'mannequin' || !product) continue
    const zone = ZONES[slot] ? slot : ZONE_FOR_SLOT[slot]
    if (zone) layers.push({ zone, product, slot })
  }
  layers.sort((a, b) => PAINT_ORDER.indexOf(a.zone) - PAINT_ORDER.indexOf(b.zone))
  // A dress covers the top and bottom zones.
  const hasDress = layers.some((l) => l.zone === 'dress')
  const visible = hasDress ? layers.filter((l) => l.zone !== 'top' && l.zone !== 'bottom') : layers

  return (
    <div className="fr-stage">
      <div className="fr-figure" style={usePicture ? { aspectRatio: String(FIGURES[gender].aspect) } : undefined}>
        {usePicture ? (
          <img className="fr-figure-img" src={src} alt="Mannequin" onError={() => setFailedSrc(src)} />
        ) : (
          <Silhouette />
        )}
        {visible.map((l) => (
          <Garment key={l.slot} zone={l.zone} zones={zones} product={l.product} />
        ))}
      </div>
      <p className="fr-stage-note">{note || 'Layered preview of your selected pieces. Not a fitted try-on.'}</p>
    </div>
  )
}
