import { useEffect, useState } from 'react'
import Header from './components/header.jsx'
import Home from './pages/home.jsx'
import Profile from './pages/Profile.jsx'
import AIStylist from './pages/AIStylist.jsx'
import FittingRoom from './pages/FittingRoom.jsx'
import Wardrobe from './pages/Wardrobe.jsx'
import Placeholder from './pages/placeholder.jsx'
import './App.css'

// Tiny hash router (no extra package). Links look like #/ai-stylist?prompt=...&occasion=...
function readLocation() {
  const raw = window.location.hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')
  return { path: path || '/', params: new URLSearchParams(query) }
}

function App() {
  const [location, setLocation] = useState(readLocation)

  useEffect(() => {
    const onChange = () => {
      setLocation(readLocation())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const { path, params } = location

  // The AI Stylist is a full-screen workspace with its own sidebar.
  if (path === '/ai-stylist') {
    return <AIStylist key={params.toString()} params={params} />
  }

  // The Fitting Room is also a full-screen workspace with the shared sidebar.
  if (path === '/fitting-room') {
    return <FittingRoom />
  }

  // My Wardrobe is a full-screen workspace with the shared sidebar.
  if (path === '/wardrobe') {
    return <Wardrobe />
  }

  // My Profile is a full-page screen with its own header and photo background.
  if (path === '/profile') {
    return <Profile />
  }

  let page
  if (path === '/' || path === '/recommendations') page = <Home />
  else page = <Placeholder title="Page not found" params={params} />

  return (
    <div className="app">
      <Header currentPath={path} />
      <main className={path === '/' ? 'main main-home' : 'main'}>{page}</main>
      <footer className="footer">© StyleAI</footer>
    </div>
  )
}

export default App
