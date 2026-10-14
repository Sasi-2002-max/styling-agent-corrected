/**
 * Local demo data for the My Wardrobe page (display only).
 *
 * The wardrobe API (/api/wardrobe/*) needs a signed-in user id and a database, and the
 * catalog's product image URLs are reserved ".test" hosts that can never load. So this page
 * uses a small local dataset and the project's own image helper (productImageFor), which draws
 * a colour-tinted garment picture as a data: URI. `shape` is the catalog category used for that
 * drawing; `group` is the label shown on the page.
 */
export const GROUPS = ['Tops', 'Bottoms', 'Dresses', 'Outerwear', 'Shoes', 'Bags', 'Accessories']

const SINGULAR = {
  Tops: 'Top', Bottoms: 'Bottom', Dresses: 'Dress', Outerwear: 'Outerwear',
  Shoes: 'Shoes', Bags: 'Bag', Accessories: 'Accessory',
}
export const singular = (group) => SINGULAR[group] || group

// [id, name, group, shape, color]. Listed newest first; `addedAt` is derived from the position.
const ROWS = [
  ['kurta', 'Embroidered Kurta', 'Tops', 'tops', 'White'],
  ['jeans', 'High-Waist Jeans', 'Bottoms', 'jeans', 'Blue'],
  ['blazer', 'Tailored Blazer', 'Outerwear', 'shirts', 'Black'],
  ['aline', 'A-Line Dress', 'Dresses', 'dresses', 'Burgundy'],
  ['sneakers', 'Casual Sneakers', 'Shoes', 'shoes', 'White'],
  ['handbag', 'Leather Handbag', 'Bags', 'bags', 'Black'],
  ['hoops', 'Gold Hoop Earrings', 'Accessories', 'accessories', 'Gold'],
  ['knit', 'Striped Knit Top', 'Tops', 'tops', 'Navy'],
  ['trousers', 'Tailored Trousers', 'Bottoms', 'pants', 'Charcoal'],
  ['wrap', 'Wrap Dress', 'Dresses', 'dresses', 'Emerald'],
  ['heels', 'Block Heels', 'Shoes', 'shoes', 'Tan'],
  ['blouse', 'Silk Blouse', 'Tops', 'shirts', 'Cream'],
  ['palazzo', 'Wide-Leg Palazzo', 'Bottoms', 'pants', 'Beige'],
  ['coat', 'Camel Coat', 'Outerwear', 'shirts', 'Camel'],
  ['tote', 'Everyday Tote', 'Bags', 'bags', 'Camel'],
  ['linen', 'Linen Shirt', 'Tops', 'shirts', 'Sage'],
  ['midi', 'Pleated Midi Skirt', 'Bottoms', 'skirts', 'Olive'],
  ['maxi', 'Floral Maxi Dress', 'Dresses', 'dresses', 'Rose'],
  ['loafers', 'Leather Loafers', 'Shoes', 'shoes', 'Brown'],
  ['denimjk', 'Denim Jacket', 'Outerwear', 'shirts', 'Denim'],
  ['tee', 'Classic Cotton Tee', 'Tops', 't-shirts', 'White'],
  ['chinos', 'Straight Chinos', 'Bottoms', 'pants', 'Khaki'],
  ['shirtdress', 'Shirt Dress', 'Dresses', 'dresses', 'Navy'],
  ['tunic', 'Printed Tunic', 'Tops', 'tops', 'Mustard'],
]

const DAY = 86400000
const BASE = Date.UTC(2025, 2, 10)

export const WARDROBE_ITEMS = ROWS.map(([id, name, group, shape, color], i) => ({
  id, name, group, shape, color,
  addedAt: BASE - i * 3 * DAY,
  favorite: ['kurta', 'blazer', 'aline', 'handbag', 'knit', 'hoops'].includes(id),
}))

export const SAVED_LOOKS = [
  { id: 'festive', name: 'Festive Look', date: 'Mar 08, 2025', itemIds: ['kurta', 'palazzo', 'hoops'] },
  { id: 'smart', name: 'Smart Casual', date: 'Mar 02, 2025', itemIds: ['blazer', 'jeans', 'loafers'] },
  { id: 'evening', name: 'Evening Look', date: 'Feb 24, 2025', itemIds: ['aline', 'handbag', 'heels'] },
  { id: 'brunch', name: 'Weekend Brunch', date: 'Feb 16, 2025', itemIds: ['knit', 'jeans', 'sneakers'] },
  { id: 'office', name: 'Office Ready', date: 'Feb 09, 2025', itemIds: ['blouse', 'trousers', 'tote'] },
  { id: 'cosy', name: 'Cosy Layers', date: 'Jan 28, 2025', itemIds: ['coat', 'tee', 'chinos'] },
]

export const STYLE_SUGGESTIONS = [
  { id: 's1', name: 'Casual Day Out', itemIds: ['kurta', 'jeans', 'sneakers'] },
  { id: 's2', name: 'Office Ready', itemIds: ['blazer', 'trousers', 'handbag', 'heels'] },
  { id: 's3', name: 'Weekend Brunch', itemIds: ['knit', 'jeans', 'sneakers'] },
  { id: 's4', name: 'Dinner Date', itemIds: ['aline', 'handbag', 'heels'] },
]

export const STYLE_MATCHES = 18
