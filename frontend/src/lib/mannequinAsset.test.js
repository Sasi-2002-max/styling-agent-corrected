import { describe, expect, it } from 'vitest'
import { mannequinImageFor, pickMannequinUrl } from './mannequinAsset.js'

describe('pickMannequinUrl', () => {
  it('matches a gender by whole file name ("male" must not pick up "female")', () => {
    const files = { '../assets/mannequin/female-mannequin.png': '/f.png' }
    expect(pickMannequinUrl(files, 'female')).toBe('/f.png')
    expect(pickMannequinUrl(files, 'male')).toBe('')
  })

  it('accepts both naming styles', () => {
    expect(pickMannequinUrl({ '../assets/mannequin/male.webp': '/m.webp' }, 'male')).toBe('/m.webp')
    expect(pickMannequinUrl({ '../assets/mannequin/male-mannequin.jpg': '/m.jpg' }, 'male')).toBe('/m.jpg')
  })

  it('prefers a photo over the bundled SVG', () => {
    const files = {
      '../assets/mannequin/female-mannequin.svg': '/f.svg',
      '../assets/mannequin/female-mannequin.png': '/f.png',
    }
    expect(pickMannequinUrl(files, 'female')).toBe('/f.png')
    expect(pickMannequinUrl({ '../assets/mannequin/female-mannequin.svg': '/f.svg' }, 'female')).toBe('/f.svg')
  })

  it('returns "" for unknown genders, other files and empty input', () => {
    expect(pickMannequinUrl({ '../assets/mannequin/female.png': '/f.png' }, 'other')).toBe('')
    expect(pickMannequinUrl({ '../assets/mannequin/notes.png': '/n.png' }, 'female')).toBe('')
    expect(pickMannequinUrl({}, 'female')).toBe('')
    expect(pickMannequinUrl(null, 'female')).toBe('')
    expect(pickMannequinUrl({ '../assets/mannequin/female.png': '/f.png' }, undefined)).toBe('')
  })
})

describe('mannequinImageFor (bundled assets)', () => {
  it('finds the bundled female and male mannequins, each a different picture', () => {
    expect(mannequinImageFor('female')).toBeTruthy()
    expect(mannequinImageFor('male')).toBeTruthy()
    expect(mannequinImageFor('male')).not.toBe(mannequinImageFor('female'))
  })
})
