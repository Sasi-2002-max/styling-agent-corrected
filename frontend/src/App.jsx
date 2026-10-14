import { useEffect, useState } from 'react'
import Header from './components/header.jsx'
import Home from './pages/Home.jsx'
import Profile from './pages/Profile.jsx'
import AIStylist from './pages/AIStylist.jsx'
import FittingRoom from './pages/FittingRoom.jsx'
import Wardrobe from './pages/Wardrobe.jsx'
import Placeholder from './pages/placeholder.jsx'
import Auth from './pages/Auth.jsx'
import { token } from './lib/auth.js'
import './App.css'

// If someone opens /signup or /login (no #), convert it to the
// hash route (/#/signup) that this app actually uses.
function normalizeUrl() {
  const { pathname, hash } = window.location

  if (pathname !== '/' && !hash) {
    window.history.replaceState(null, '', '/#' + pathname)
  }
}

function readLocation() {
  normalizeUrl()

  const raw = window.location.hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')

  return {
    path: path || '/',
    params: new URLSearchParams(query),
  }
}

function App() {
  const [location, setLocation] = useState(readLocation)
  const [authenticated, setAuthenticated] = useState(() =>
    Boolean(token())
  )

  useEffect(() => {
    const onChange = () => {
      setLocation(readLocation())
      setAuthenticated(Boolean(token()))
      window.scrollTo(0, 0)
    }

    window.addEventListener('hashchange', onChange)

    return () => {
      window.removeEventListener('hashchange', onChange)
    }
  }, [])

  const { path, params } = location

  function handleAuthenticated() {
    setAuthenticated(Boolean(token()))
    window.location.hash = '#/'
  }

  // Login and signup routes are checked before the
  // authentication guard so users can always reach these pages.
  if (path === '/login' || path === '/signup') {
    return (
      <Auth
        key={path}
        initialMode={path === '/signup' ? 'signup' : 'login'}
        onAuthenticated={handleAuthenticated}
      />
    )
  }

  // Protect the application pages.
  if (!authenticated || !token()) {
    return (
      <Auth
        initialMode="signup"
        onAuthenticated={handleAuthenticated}
      />
    )
  }

  if (path === '/ai-stylist') {
    return <AIStylist key={params.toString()} params={params} />
  }

  if (path === '/fitting-room') {
    return <FittingRoom />
  }

  if (path === '/wardrobe') {
    return <Wardrobe />
  }

  if (path === '/profile') {
    return <Profile />
  }

  let page

  if (path === '/') {
    page = <Home />
  } else {
    page = <Placeholder title="Page not found" params={params} />
  }

  return (
    <div className="app">
      <Header currentPath={path} />

      <main className={path === '/' ? 'main main-home' : 'main'}>
        {page}
      </main>

      <footer className="footer">© StyleAI</footer>
    </div>
  )
}

export default App
