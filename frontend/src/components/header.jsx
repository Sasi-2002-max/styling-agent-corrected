import { logout } from '../lib/auth.js'
const LINKS = [
  { label: 'Home', path: '/' },
  { label: 'My Profile', path: '/profile' },
  { label: 'AI Stylist', path: '/ai-stylist' },
  { label: 'Fitting Room', path: '/fitting-room' },
  { label: 'My Wardrobe', path: '/wardrobe' },
]

function Header({ currentPath }) {
  return (
    <header className="header">
      <a className="logo" href="#/">
        Style<span>AI</span>
      </a>
      <nav className="nav" aria-label="Main navigation">
        {LINKS.map((link) => (
          <a
            key={link.path}
            href={'#' + link.path}
            className={currentPath === link.path ? 'active' : ''}
          >
            {link.label}
          </a>
        ))}
        <button type="button" className="nav-logout" onClick={() => { logout(); window.location.hash = '#/login'; window.location.reload() }}>Log out</button>
      </nav>
    </header>
  )
}

export default Header