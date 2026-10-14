/**
 * Finds the mannequin picture for a gender among the files in src/assets/mannequin/.
 *
 * Accepted names (same naming the backend uses for its asset paths):
 *   female.<ext>   female-mannequin.<ext>   male.<ext>   male-mannequin.<ext>
 * where <ext> is png, webp, jpg, jpeg or svg. If several exist for one gender, a photo
 * wins over the SVG, so dropping in `female-mannequin.png` replaces the bundled drawing
 * without touching any code.
 *
 * import.meta.glob matches whatever files exist at build time, so a missing picture can
 * never break the build: mannequinImageFor() just returns '' and MannequinPreview draws
 * its built-in silhouette instead.
 */

const FILES = import.meta.glob('../assets/mannequin/*.{png,webp,jpg,jpeg,svg}', {
  eager: true,
  query: '?url',
  import: 'default',
})

const EXTENSION_PREFERENCE = ['png', 'webp', 'jpg', 'jpeg', 'svg']

/** Pure part, so it can be tested without the file system: { path: url } -> url or ''. */
export function pickMannequinUrl(files, gender) {
  const wanted = String(gender || '').toLowerCase()
  if (wanted !== 'female' && wanted !== 'male') return ''
  // Whole-name match on purpose: "male" is a substring of "female".
  const pattern = new RegExp('^' + wanted + '(-mannequin)?\\.(png|webp|jpe?g|svg)$', 'i')

  const matches = []
  for (const [path, url] of Object.entries(files || {})) {
    const name = path.split('/').pop() || ''
    const hit = pattern.exec(name)
    if (hit && typeof url === 'string' && url) {
      matches.push({ url, rank: EXTENSION_PREFERENCE.indexOf(hit[2].toLowerCase().replace('jpeg', 'jpg')) })
    }
  }
  matches.sort((a, b) => a.rank - b.rank)
  return matches.length ? matches[0].url : ''
}

export function mannequinImageFor(gender) {
  return pickMannequinUrl(FILES, gender)
}
