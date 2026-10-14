
import { useState } from 'react'
import {
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Heart,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
  Shirt,
} from 'lucide-react'
import { authenticate } from '../lib/auth'
import './Auth.css'

export default function Auth({
  onAuthenticated,
  initialMode = 'login',
}) {
  const [mode, setMode] = useState(() =>
  window.location.hash.replace(/^#/, '').split('?')[0] === '/signup'
    ? 'signup'
    : initialMode
  )
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function changeMode(nextMode) {
    setMode(nextMode)
    setError('')
    setPassword('')
    setConfirm('')

    // Keep the URL and displayed form synchronized.
    const nextHash = nextMode === 'signup' ? '#/signup' : '#/login'

    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash
    }
  }

  async function submit(event) {
    event.preventDefault()
    setError('')

    if (mode === 'signup' && password !== confirm) {
      setError('Your passwords do not match. Please try again.')
      return
    }

    setBusy(true)

    try {
      await authenticate(mode, email.trim(), password)
      onAuthenticated?.()
    } catch (e) {
      setError(
        e?.response?.data?.detail ||
          'Unable to connect to StyleAI. Please check your connection and try again.'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-visual" aria-label="Welcome to StyleAI">
        <div className="auth-visual-overlay" />

        <a className="auth-brand" href="#/login" aria-label="StyleAI login">
          <span className="auth-brand-mark">
            <Sparkles size={29} strokeWidth={1.5} />
          </span>

          <span>
            <span className="auth-brand-name">StyleAI</span>
            <span className="auth-brand-tagline">
              Your Personal Style Assistant
            </span>
          </span>
        </a>

        <div className="auth-editorial">
          <span className="auth-overline">YOUR STYLE. YOUR STORY.</span>

          <h1>
            Better Style.
            <br />
            <span>Smarter You.</span>
          </h1>

          <p className="auth-editorial-description">
            Discover your signature look with personalized outfit suggestions,
            styling tips, and fashion guidance powered by AI.
          </p>

          <div className="auth-benefits">
            <div className="auth-benefit">
              <span className="auth-benefit-icon">
                <Sparkles size={22} />
              </span>
              <span>
                <strong>AI-powered suggestions</strong>
                <small>Outfits tailored to your style and mood</small>
              </span>
            </div>

            <div className="auth-benefit">
              <span className="auth-benefit-icon">
                <Shirt size={22} />
              </span>
              <span>
                <strong>Personalized style</strong>
                <small>Looks for every occasion</small>
              </span>
            </div>

            <div className="auth-benefit">
              <span className="auth-benefit-icon">
                <Heart size={22} />
              </span>
              <span>
                <strong>Stay inspired</strong>
                <small>Discover trends and fresh ideas</small>
              </span>
            </div>
          </div>
        </div>

        <p className="auth-editorial-signoff">
          Dress better.
          <br />
          Feel confident.
          <Heart size={15} fill="currentColor" />
        </p>

        <span className="auth-image-credit">
          YOUR PERSONAL STYLE COMPANION
        </span>
      </section>

      <section className="auth-form-panel">
        <div className="auth-card">
          <a className="auth-mobile-brand" href="#/login">
            <Sparkles size={23} />
            <span>StyleAI</span>
          </a>

          <div className="auth-tabs" role="tablist" aria-label="Account access">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'login'}
              className={`auth-tab ${mode === 'login' ? 'is-active' : ''}`}
              onClick={() => changeMode('login')}
            >
              Sign In
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={mode === 'signup'}
              className={`auth-tab ${mode === 'signup' ? 'is-active' : ''}`}
              onClick={() => changeMode('signup')}
            >
              Create Account
            </button>
          </div>

          <div className="auth-heading">
            <span className="auth-heading-sparkle">
              <Sparkles size={19} />
            </span>

            <h2>
              {mode === 'login'
                ? 'Welcome Back'
                : 'Your Style Starts Here'}
            </h2>

            <p>
              {mode === 'login'
                ? 'Sign in to your StyleAI account to continue your style journey.'
                : 'Create your account and discover a style that feels like you.'}
            </p>
          </div>

          <form className="auth-form" onSubmit={submit}>
            <div className="auth-field">
              <label htmlFor="auth-email">Email Address</label>

              <div className="auth-input-wrap">
                <Mail size={19} aria-hidden="true" />

                <input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div className="auth-field">
              <label htmlFor="auth-password">Password</label>

              <div className="auth-input-wrap">
                <LockKeyhole size={19} aria-hidden="true" />

                <input
                  id="auth-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={
                    mode === 'login' ? 'current-password' : 'new-password'
                  }
                  minLength={8}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={
                    mode === 'login'
                      ? 'Enter your password'
                      : 'At least 8 characters'
                  }
                />

                <button
                  type="button"
                  className="auth-password-toggle"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? (
                    <EyeOff size={19} />
                  ) : (
                    <Eye size={19} />
                  )}
                </button>
              </div>
            </div>

            {mode === 'signup' && (
              <div className="auth-field">
                <label htmlFor="auth-confirm">Confirm Password</label>

                <div className="auth-input-wrap">
                  <ShieldCheck size={19} aria-hidden="true" />

                  <input
                    id="auth-confirm"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    minLength={8}
                    required
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    placeholder="Enter your password again"
                  />
                </div>
              </div>
            )}

            {mode === 'login' && (
              <div className="auth-form-options">
                <label className="auth-remember">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                  />

                  <span className="auth-custom-checkbox">
                    <Check size={13} />
                  </span>

                  Remember me
                </label>

                <button
                  type="button"
                  className="auth-text-link"
                  onClick={() =>
                    setError(
                      'Password recovery is not configured yet. Please contact your StyleAI administrator.'
                    )
                  }
                >
                  Forgot password?
                </button>
              </div>
            )}

            {error && (
              <p className="auth-error" role="alert">
                {error}
              </p>
            )}

            <button className="auth-submit" type="submit" disabled={busy}>
              <span>
                {busy
                  ? 'Please wait…'
                  : mode === 'login'
                    ? 'Sign In'
                    : 'Create Account'}
              </span>

              {!busy && <ArrowRight size={20} />}
            </button>
          </form>

          <p className="auth-switch">
            {mode === 'login'
              ? "Don't have an account?"
              : 'Already have an account?'}

            <button
              type="button"
              onClick={() =>
                changeMode(mode === 'login' ? 'signup' : 'login')
              }
            >
              {mode === 'login' ? 'Create one' : 'Sign in'}
            </button>
          </p>

          <div className="auth-security">
            <span className="auth-security-icon">
              <ShieldCheck size={25} />
            </span>

            <span>
              <strong>Your style journey, protected</strong>
              <small>
                Your account details are handled securely by StyleAI.
              </small>
            </span>
          </div>

          <p className="auth-terms">
            By continuing, you agree to use StyleAI responsibly.
          </p>
        </div>
      </section>
    </main>
  )
}
