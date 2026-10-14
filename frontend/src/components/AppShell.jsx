import { useState } from 'react'
import { House, UserRound, Sparkles, Shirt, LayoutGrid, Menu, X } from 'lucide-react'
import './AppShell.css'

// Same five pages and hash paths as the Home page header.
const NAV_ITEMS = [
  { label: 'Home', icon: House, path: '/' },
  { label: 'My Profile', icon: UserRound, path: '/profile' },
  { label: 'AI Stylist', icon: Sparkles, path: '/ai-stylist' },
  { label: 'Fitting Room', icon: Shirt, path: '/fitting-room' },
  { label: 'My Wardrobe', icon: LayoutGrid, path: '/wardrobe' },
]

/**
 * Desktop workspace layout: fixed left sidebar + top header + main area.
 * Used by the AI Stylist page. Under 960px the sidebar slides in from a menu button.
 */
export default function AppShell({ currentPath, title, actions, variant, children }) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className={variant === 'dark' ? 'shell shell-dark' : 'shell'}>
      <aside className={menuOpen ? 'shell-side shell-side-open' : 'shell-side'}>
        <div className="shell-brand">
          <a className="shell-logo" href="#/">
            Style<span>AI</span>
            {variant === 'dark' && <small>Your personal stylist</small>}
          </a>
          <button
            type="button"
            className="shell-icon-btn shell-close"
            aria-label="Close menu"
            onClick={() => setMenuOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        <nav className="shell-nav" aria-label="Main navigation">
          {NAV_ITEMS.map(({ label, icon: Icon, path }) => {
            const active = path === currentPath
            return (
              <a
                key={path}
                href={'#' + path}
                className={active ? 'shell-link shell-link-active' : 'shell-link'}
                aria-current={active ? 'page' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                <Icon size={18} strokeWidth={1.7} />
                {label}
              </a>
            )
          })}
        </nav>

        {variant === 'dark' ? (
          <p className="shell-tagline">
            Better style.
            <br />
            Smarter choices.
          </p>
        ) : (
          <p className="shell-tagline">Discover your style. Build your look.</p>
        )}
      </aside>

      {menuOpen && <div className="shell-scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}

      <div className="shell-body">
        <header className={title ? 'shell-top' : 'shell-top shell-top-bare'}>
          <div className="shell-top-left">
            <button
              type="button"
              className="shell-icon-btn shell-menu"
              aria-label="Open menu"
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={22} />
            </button>
            {title && <h1>{title}</h1>}
          </div>
          <div>{actions}</div>
        </header>
        <main className="shell-main">{children}</main>
      </div>
    </div>
  )
}
