/**
 * Product image helpers for the Fitting Room.
 *
 * DISPLAY ONLY. Nothing here is written back into a product or into the
 * fitting-room state, and the backend contract is untouched: when a product has
 * no usable image_url, the backend still says so (image_url stays null). The
 * placeholder below is just what the page draws in that case, so a card is never
 * an empty box. It is a generic picture of the product's category in the
 * product's own colour -- NOT a photo of that product.
 */

import { swatchHex } from './fittingRoomAdapter.js'

/**
 * The image address to try loading, or '' when it is not worth trying.
 * Only real http(s) addresses pass. Reserved demo hosts (.test, .example,
 * .invalid, .localhost) can never load, so they are rejected up front.
 */
export function usableImageUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  try {
    const url = new URL(value.trim())
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
    if (/\.(test|example|invalid|localhost)$/i.test(url.hostname)) return ''
    return url.href
  } catch {
    return ''
  }
}

// backend category -> drawing. Keys are the catalog categories (see categoryMap.ts).
const SHAPE_FOR_CATEGORY = {
  shirts: 'shirt',
  't-shirts': 'tee',
  tops: 'tee',
  pants: 'pants',
  jeans: 'jeans',
  skirts: 'skirt',
  dresses: 'dress',
  shoes: 'shoe',
  watches: 'watch',
  bags: 'bag',
  sunglasses: 'sunglasses',
  accessories: 'ring',
}

// Each drawing sits inside x 10..90, y 10..90 of a 100x100 box so that both
// "cover" thumbnails and "contain" garment layers show all of it.
// `c` is the product colour; the outline is a fixed dark line so pale colours stay visible.
const DRAWINGS = {
  tee: (c) => `<path d="M35 16 L16 28 L24 44 L33 39 L33 84 L67 84 L67 39 L76 44 L84 28 L65 16 Q50 28 35 16Z" fill="${c}"/>`,
  shirt: (c) =>
    `<path d="M36 14 L14 30 L20 72 L31 70 L33 40 L33 86 L67 86 L67 40 L69 70 L80 72 L86 30 L64 14 L50 26Z" fill="${c}"/>` +
    '<path d="M36 14 L50 32 L64 14 M50 32 L50 86" fill="none"/>',
  pants: (c) => `<path d="M32 12 L68 12 L72 88 L54 88 L50 42 L46 88 L28 88Z" fill="${c}"/><path d="M32 20 L68 20" fill="none"/>`,
  jeans: (c) =>
    `<path d="M32 12 L68 12 L72 88 L54 88 L50 42 L46 88 L28 88Z" fill="${c}"/>` +
    '<path d="M32 20 L68 20 M36 20 Q40 34 46 30 M64 20 Q60 34 54 30" fill="none"/>',
  skirt: (c) => `<path d="M36 16 L64 16 L84 84 L16 84Z" fill="${c}"/><path d="M36 24 L64 24" fill="none"/>`,
  dress: (c) => `<path d="M40 10 L46 10 L50 22 L54 10 L60 10 L62 38 L74 88 L26 88 L38 38Z" fill="${c}"/><path d="M38 38 L62 38" fill="none"/>`,
  shoe: (c) =>
    `<path d="M12 64 L12 48 Q30 52 38 38 L50 46 Q66 56 88 62 Q94 64 94 72 L94 76 L12 76Z" fill="${c}"/>` +
    '<path d="M12 76 L94 76" fill="none" stroke-width="4"/>',
  watch: (c) =>
    `<path d="M42 8 L58 8 L61 32 L39 32Z M39 68 L61 68 L58 92 L42 92Z" fill="${c}"/>` +
    `<circle cx="50" cy="50" r="19" fill="${c}"/><circle cx="50" cy="50" r="13" fill="#f4efe3"/>` +
    '<path d="M50 50 L50 41 M50 50 L57 54" fill="none"/>',
  bag: (c) =>
    `<path d="M20 40 L80 40 L88 88 L12 88Z" fill="${c}"/>` +
    '<path d="M36 40 Q36 16 50 16 Q64 16 64 40 M20 54 L80 54" fill="none"/>',
  sunglasses: (c) =>
    `<ellipse cx="29" cy="54" rx="17" ry="13" fill="${c}"/><ellipse cx="71" cy="54" rx="17" ry="13" fill="${c}"/>` +
    '<path d="M46 52 Q50 46 54 52 M12 50 L8 42 M88 50 L92 42" fill="none"/>',
  ring: (c) => `<circle cx="50" cy="56" r="26" fill="none" stroke="${c}" stroke-width="10"/><path d="M42 24 L50 14 L58 24Z" fill="${c}"/>`,
}

// Where each drawing actually sits inside its 100x100 box. The mannequin crops to this so a
// garment fills its zone exactly; cards and thumbnails keep the whole box (with its margins).
const BOUNDS = {
  tee: [16, 16, 84, 84],
  shirt: [14, 14, 86, 86],
  pants: [28, 12, 72, 88],
  jeans: [28, 12, 72, 88],
  skirt: [16, 16, 84, 84],
  dress: [26, 10, 74, 88],
  shoe: [12, 38, 94, 76],
  watch: [39, 8, 61, 92],
  bag: [12, 16, 88, 88],
  sunglasses: [12, 41, 88, 67],
  ring: [24, 14, 76, 82],
}
const STROKE_PAD = 2

const NEUTRAL = '#cfc2a8'

/**
 * A generic, colour-tinted picture of the product's category, as a data: URI.
 * '' when the category isn't one the catalog knows (callers then show their own empty state).
 */
export function placeholderImageFor(product, tight = false) {
  const shape = product && SHAPE_FOR_CATEGORY[product.category]
  if (!shape) return ''
  const [x0, y0, x1, y1] = BOUNDS[shape]
  const viewBox = tight
    ? [x0 - STROKE_PAD, y0 - STROKE_PAD, x1 - x0 + 2 * STROKE_PAD, y1 - y0 + 2 * STROKE_PAD].join(' ')
    : '0 0 100 100'
  const colour = swatchHex(product.color) || NEUTRAL
  const svg =
    // preserveAspectRatio="none" lets the mannequin stretch the drawing to a garment zone;
    // the style keeps the outline the same thickness when it is stretched.
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + viewBox + '" preserveAspectRatio="none">' +
    '<style>*{vector-effect:non-scaling-stroke}</style>' +
    '<g stroke="#2b1f16" stroke-opacity="0.5" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">' +
    DRAWINGS[shape](colour) +
    '</g></svg>'
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

/**
 * What to put in an <img> for this product.
 *   1. its real image_url, when that is worth loading and has not failed (`failed`);
 *   2. otherwise the display-only placeholder (`tight`: cropped to the drawing, for the mannequin);
 *   3. otherwise '' (unknown category).
 */
export function productImageFor(product, failed = false, tight = false) {
  const real = failed ? '' : usableImageUrl(product && product.image_url)
  return real || placeholderImageFor(product, tight)
}
