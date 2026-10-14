const LINKS = [
  { label: 'Home', path: '/' },
  { label: 'My Profile', path: '/profile' },
  { label: 'AI Stylist', path: '/ai-stylist' },
  { label: 'Recommendations', path: '/recommendations' },
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
      </nav>
    </header>
  )
}

export default Header