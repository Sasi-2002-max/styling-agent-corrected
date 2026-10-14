import { useEffect } from 'react'
import { Heart, Shirt, Sparkles, UserRound } from 'lucide-react'
import heroImg from '../assets/styleai-aura-home.jpg'
import './Home.css'

const LEFT_LINKS = [
  { label: 'Home', path: '/' },
  { label: 'My Profile', path: '/profile' },
  { label: 'AI Stylist', path: '/ai-stylist' },
]

const RIGHT_LINKS = [
  { label: 'Fitting Room', path: '/fitting-room' },
  { label: 'My Wardrobe', path: '/wardrobe' },
]

const SHORTCUTS = [
  { kicker: 'Your style', title: 'My Profile', text: 'Set your fit, preferences, and personal style.', path: '/profile', icon: UserRound },
  { kicker: 'Get inspired', title: 'AI Stylist', text: 'Describe the occasion. Get a complete outfit.', path: '/ai-stylist', icon: Sparkles },
  { kicker: 'See the look', title: 'Fitting Room', text: 'Review your selected pieces and shop alternatives.', path: '/fitting-room', icon: Shirt },
  { kicker: 'Saved for you', title: 'My Wardrobe', text: 'Return to saved looks and pieces you love.', path: '/wardrobe', icon: Heart },
]

// Critical layout for the background photo, set inline so no global `img` rule
// (or a stale stylesheet) can drop it back into normal page flow. Responsive
// bits (object-position) stay in Home.css.
const BG_STYLE = {
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  zIndex: -2,
}

function Home() {
  // lets Home.css hide the site-wide header while this page is showing
  useEffect(() => {
    document.body.classList.add('is-home')
    return () => document.body.classList.remove('is-home')
  }, [])

  return (
    <main className="aura">
      <img
        className="aura__bg"
        style={BG_STYLE}
        src={heroImg}
        alt=""
        fetchPriority="high"
      />
      <div className="aura__shade" aria-hidden="true" />

      <header className="aura__nav">
        <nav className="aura__links" aria-label="Primary">
          {LEFT_LINKS.map(({ label, path }) => (
            <a key={label} href={'#' + path} aria-current={path === '/' ? 'page' : undefined}>
              {label}
            </a>
          ))}
        </nav>

        <a className="aura__logo" href="#/" aria-label="StyleAI home">
          Style<span>AI</span>
        </a>

        <nav className="aura__links aura__links--right" aria-label="Secondary">
          {RIGHT_LINKS.map(({ label, path }) => (
            <a key={label} href={'#' + path}>
              {label}
            </a>
          ))}
        </nav>
      </header>

      <section className="aura__hero" aria-label="Personal styling">
        <p className="aura__eyebrow">Personal styling</p>
        <h1 className="aura__title">
          Luxury, made
          <br />
          personal.
        </h1>
        <p className="aura__sub">
          A thoughtful outfit for wherever you’re going, styled around you and
          found from real retailer listings.
        </p>
        <a className="aura__cta" href="#/ai-stylist">
          Explore the AI Stylist
        </a>
      </section>

      <nav className="aura__cards" aria-label="StyleAI tools">
        {SHORTCUTS.map(({ kicker, title, text, path, icon: Icon }) => (
          <a key={path} className="aura__card" href={'#' + path}>
            <span className="aura__icon"><Icon size={20} strokeWidth={1.4} /></span>
            <span className="aura__cardtext">
              <small>{kicker}</small>
              <strong>{title}</strong>
              <span>{text}</span>
            </span>
          </a>
        ))}
      </nav>
    </main>
  )
}

export default Home
