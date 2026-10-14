
import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const TOKEN_KEY = 'styleai_access_token'
export const USER_KEY = 'styleai_user'

// Get the saved authentication token
function isExpired(jwt) {
  try {
    const payload = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.exp ? payload.exp * 1000 < Date.now() : false
  } catch {
    return false // not a readable JWT: leave it alone
  }
}

export const token = () => {
  const saved = localStorage.getItem(TOKEN_KEY)
  if (!saved) return null
  if (isExpired(saved)) {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    return null
  }
  return saved
}

// Add the token to API request headers when available
export const authHeaders = () => {
  const accessToken = token()

  return accessToken
    ? { Authorization: `Bearer ${accessToken}` }
    : {}
}

// Sign up or log in
export async function authenticate(mode, email, password) {
  if (!['login', 'signup'].includes(mode)) {
    throw new Error('Invalid authentication mode.')
  }

  const response = await axios.post(
    `${API_BASE_URL}/api/auth/${mode}`,
    {
      email: email.trim(),
      password,
    },
    {
      timeout: 20000,
    }
  )

  const { access_token, user } = response.data

  if (!access_token) {
    throw new Error('Authentication succeeded without an access token.')
  }

  // Save the authentication session
  localStorage.setItem(TOKEN_KEY, access_token)

  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }

  return user ?? null
}

// Log out and clear the saved session
export function logout() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// Get the saved user profile
export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}
