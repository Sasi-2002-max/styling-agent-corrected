import { useEffect, useRef, useState } from 'react'
import profileHero from '../assets/profile-hero.jpg'
import axios from 'axios'
import { API_BASE_URL, authHeaders, getStoredUser, logout } from '../lib/auth.js'
import './Profile.css'
import './Profile.Premium.css'
import './Profile.Finish.css'

// ---------------------------------------------------------------------------
// Options for the form. "value" matches what the backend profile model expects.
// ---------------------------------------------------------------------------
const GENDERS = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
]

// sizes = half-widths of [shoulders, waist, hips], used to draw a simple silhouette.
const BODY_SHAPES = [
  { value: 'hourglass', label: 'Hourglass', text: 'Defined waist, balanced shoulders and hips', sizes: [22, 13, 22] },
  { value: 'pear', label: 'Pear', text: 'Wider hips, narrower shoulders', sizes: [15, 15, 24] },
  { value: 'apple', label: 'Apple', text: 'Fuller around the middle, narrower hips', sizes: [20, 24, 17] },
  { value: 'rectangle', label: 'Rectangle', text: 'Shoulders, waist and hips are similar', sizes: [20, 20, 20] },
  { value: 'inverted_triangle', label: 'Inverted triangle', text: 'Wider shoulders, narrower hips', sizes: [25, 17, 14] },
]

// The colours are only approximate swatches to help you pick the closest match.
const SKIN_TONES = [
  { value: 'very_light', label: 'Very light', color: '#F8E3D3' },
  { value: 'light', label: 'Light', color: '#EBC3A0' },
  { value: 'medium', label: 'Medium', color: '#D9A27A' },
  { value: 'tan', label: 'Tan', color: '#BE8758' },
  { value: 'brown', label: 'Brown', color: '#8D5A3B' },
  { value: 'deep', label: 'Deep', color: '#5A3825' },
]

const CLOTHING_STYLES = [
  { value: 'classic', label: 'Classic' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'boho', label: 'Boho' },
  { value: 'streetwear', label: 'Streetwear' },
  { value: 'luxury', label: 'Luxury' },
  { value: 'casual', label: 'Casual' },
  { value: 'vintage', label: 'Vintage' },
  { value: 'trendy', label: 'Trendy' },
]

// Optional body measurements. "line" = [x1, y1, x2, y2] of the dashed line drawn on the icon.
const MEASUREMENTS = [
  { value: 'bust', label: 'Bust / Chest', min: 50, max: 180, line: [17, 36, 43, 36] },
  { value: 'underbust', label: 'Underbust', min: 50, max: 160, line: [18, 45, 42, 45] },
  { value: 'waist', label: 'Waist', min: 40, max: 180, line: [19, 54, 41, 54] },
  { value: 'hips', label: 'Hips', min: 50, max: 200, line: [15, 70, 45, 70] },
  { value: 'shoulder', label: 'Shoulder', min: 25, max: 70, line: [18, 22, 42, 22] },
  { value: 'arm', label: 'Arm', min: 40, max: 100, line: [13, 25, 8, 64] },
  { value: 'inseam', label: 'Inseam', min: 40, max: 120, line: [37, 82, 37, 104] },
  { value: 'neck', label: 'Neck', min: 20, max: 60, line: [25, 17, 35, 17] },
]

// Underbust is only offered for female profiles.
function availableMeasurements(gender) {
  return MEASUREMENTS.filter((m) => !(m.value === 'underbust' && gender === 'male'))
}

// Optional body details (a 3-point scale: low / average / high).
const BODY_DETAILS = [
  { key: 'armLength', label: 'Arm length', low: 'Short', high: 'Long' },
  { key: 'shoulder', label: 'Shoulder', low: 'Small', high: 'Wide' },
  { key: 'upperArm', label: 'Upper arm', low: 'Thin', high: 'Thick' },
  { key: 'bust', label: 'Bust / Chest', low: 'Thin', high: 'Thick' },
  { key: 'waist', label: 'Waist', low: 'Thin', high: 'Thick' },
]

// Each step shows some fields. "fields" is used to validate one step at a time.
const STEPS = [
  { title: 'About you', short: 'About You', text: "Let's start with some basic details.", fields: ['name', 'gender', 'age', 'style'] },
  { title: 'Style preferences', short: 'Style Preferences', text: 'Your shape, colouring and budget help us pick what suits you.', fields: ['bodyShape', 'skinTone', 'budget'] },
  {
    title: 'Measurements',
    short: 'Measurements',
    text: 'Set your height and weight. Body measurements and details are optional.',
    fields: ['height', 'weight', ...MEASUREMENTS.map((m) => 'measure_' + m.value)],
  },
  { title: 'Review', short: 'Review', text: 'Check your details, then save your profile.', fields: [] },
]

// Height and weight start at a middle value you can change. Most other fields start empty.
const EMPTY_FORM = {
  name: '',
  age: '',
  gender: '',
  height: '165',
  weight: '60',
  bodyShape: '',
  skinTone: '',
  style: '',
  budget: '',
  parts: ['bust', 'waist', 'hips'], // body parts chosen for measuring
  measures: {}, // centimetres for each chosen part, e.g. { bust: '90' }
  details: { armLength: 'average', shoulder: 'average', upperArm: 'average', bust: 'average', waist: 'average' },
}

// ---------------------------------------------------------------------------
// Validation: returns an object of error messages. Empty object = all good.
// ---------------------------------------------------------------------------
function validate(values) {
  const errors = {}

  if (!values.name.trim()) errors.name = 'Please enter your name.'

  if (values.age === '') {
    errors.age = 'Please enter your age.'
  } else {
    const age = Number(values.age)
    if (!Number.isInteger(age) || age < 1 || age > 120) {
      errors.age = 'Age must be a whole number between 1 and 120.'
    }
  }

  if (!values.gender) errors.gender = 'Please choose a gender.'

  const height = Number(values.height)
  if (values.height === '' || height < 100 || height > 230) {
    errors.height = 'Height must be between 100 and 230 cm.'
  }

  const weight = Number(values.weight)
  if (values.weight === '' || weight < 25 || weight > 200) {
    errors.weight = 'Weight must be between 25 and 200 kg.'
  }

  if (!values.bodyShape) errors.bodyShape = 'Please choose a body shape.'
  if (!values.skinTone) errors.skinTone = 'Please choose a skin tone.'
  if (!values.style) errors.style = 'Please choose a clothing style.'

  if (values.budget === '') {
    errors.budget = 'Please enter your preferred budget.'
  } else if (Number(values.budget) <= 0) {
    errors.budget = 'Budget must be more than 0.'
  }

  // Every body part that is ticked needs a value.
  availableMeasurements(values.gender).forEach((m) => {
    if (!values.parts.includes(m.value)) return
    const typed = values.measures[m.value]
    const key = 'measure_' + m.value
    if (typed === undefined || typed === '') {
      errors[key] = 'Enter this measurement in cm, or untick it above.'
    } else if (Number(typed) < m.min || Number(typed) > m.max) {
      errors[key] = m.label + ' must be between ' + m.min + ' and ' + m.max + ' cm.'
    }
  })

  return errors
}

function labelOf(list, value) {
  const found = list.find((item) => item.value === value)
  return found ? found.label : ''
}

// ---------------------------------------------------------------------------
// Hero photo behind the title. To use your own photo, save it as
// src/assets/wardrobe-bg.jpg (or .png / .webp); it is picked up automatically.
// ---------------------------------------------------------------------------
const photoFiles = import.meta.glob('../assets/wardrobe-bg.*', { eager: true, import: 'default' })
const heroPhoto = Object.values(photoFiles)[0] || profileHero

// The page is designed for a window about 1536px wide. On a wider window (or when the browser is
// zoomed out) the whole layout is scaled up so it keeps the same look and proportions.
const BASE_WIDTH = 1536
function currentScale() {
  return Math.min(3, Math.max(1, Math.round((window.innerWidth / BASE_WIDTH) * 100) / 100))
}
function usePageScale() {
  const [scale, setScale] = useState(currentScale)
  useEffect(() => {
    const onResize = () => setScale(currentScale())
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return scale > 1 ? { zoom: scale } : undefined
}

// Header used only on this page (logo, links, round profile picture).
function ProfileHeader({ style }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  // Close the menu when clicking elsewhere or pressing Escape.
  useEffect(() => {
    if (!menuOpen) return undefined
    const onClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  function handleLogout() {
    setMenuOpen(false)
    logout()
    window.location.hash = '#/login'
  }

  const user = getStoredUser()

  return (
    <header className="pf-header" style={style}>
      <a className="pf-logo" href="#/">
        Style<span>AI</span>
      </a>
      <nav className="pf-nav" aria-label="Main">
        <a href="#/">Home</a>
        <a href="#/profile" className="active" aria-current="page">
          My Profile
        </a>
        <a href="#/ai-stylist">AI Stylist</a>
        <div className="pf-account" ref={menuRef}>
          <button
            type="button"
            className="pf-avatar"
            aria-label="Account menu"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <svg viewBox="0 0 40 40" aria-hidden="true">
              <circle cx="20" cy="20" r="20" fill="#d9c8ad" />
              <circle cx="20" cy="15" r="7" fill="#7a5a3c" />
              <path d="M5 36c1.5-8 8-12 15-12s13.500 4 15 12z" fill="#7a5a3c" />
            </svg>
          </button>

          {menuOpen && (
            <div className="pf-menu" role="menu">
              {user?.email && <p className="pf-menu-email">{user.email}</p>}
              <a href="#/profile" role="menuitem" onClick={() => setMenuOpen(false)}>
                My Profile
              </a>
              <button type="button" role="menuitem" onClick={handleLogout}>
                Log out
              </button>
            </div>
          )}
        </div>
      </nav>
    </header>
  )
}

function Scene({ children }) {
  const scaleStyle = usePageScale()
  return (
    <>
      <div className="profile-bg" style={{ backgroundImage: 'url(' + heroPhoto + ')' }} aria-hidden="true" />
      <ProfileHeader style={scaleStyle} />
      <div className="profile-layout" style={scaleStyle}>
        <div className="profile-intro-col">
          <p className="hero-brand">
            Style<span>AI</span>
          </p>
          <h1>
            Your Style
            <br />
            Your Story
          </h1>
          <p className="profile-intro">Tell us a little more about you so we can style you better.</p>
        </div>
        <div className="profile-body">{children}</div>
      </div>
    </>
  )
}

// Numbered progress: one circle per step.
function Stepper({ step }) {
  return (
    <ol className="stepper-nav" aria-hidden="true">
      {STEPS.map((s, i) => (
        <li key={s.title} className={i === step ? 'current' : i < step ? 'done' : ''}>
          <span className="stepper-dot">{i + 1}</span>
          <span className="stepper-label">{s.short}</span>
        </li>
      ))}
    </ol>
  )
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

// Label + input + optional hint + optional error message.
function Field({ id, label, hint, error, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <p className="hint">{hint}</p>}
      {error && (
        <p className="error" id={id + '-error'} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

// Round choice buttons (used for gender and clothing style). perRow puts that many buttons on each line.
function OptionPills({ name, options, value, onChange, perRow }) {
  const pill = (option) => (
    <label key={option.value} className={value === option.value ? 'pill selected' : 'pill'}>
      <input
        type="radio"
        className="visually-hidden"
        name={name}
        value={option.value}
        checked={value === option.value}
        onChange={() => onChange(name, option.value)}
      />
      {option.label}
    </label>
  )
  if (!perRow) return <div className="pills">{options.map(pill)}</div>
  const rows = []
  for (let i = 0; i < options.length; i += perRow) rows.push(options.slice(i, i + perRow))
  return (
    <div className="pill-rows">
      {rows.map((row, i) => (
        <div key={i} className="pills">
          {row.map(pill)}
        </div>
      ))}
    </div>
  )
}

// A simple body silhouette drawn from three widths.
function Silhouette({ sizes }) {
  const [s, w, h] = sizes
  const c = 2 * w - (s + h) / 2 // curve control point so the waist ends up the right width
  const path =
    'M ' + (30 - s) + ' 8 L ' + (30 + s) + ' 8 Q ' + (30 + c) + ' 40 ' + (30 + h) + ' 72 ' +
    'L ' + (30 - h) + ' 72 Q ' + (30 - c) + ' 40 ' + (30 - s) + ' 8 Z'
  return (
    <svg className="silhouette" viewBox="0 0 60 80" aria-hidden="true">
      <path d={path} fill="currentColor" />
    </svg>
  )
}

// A body outline with a dashed line showing where the measurement is taken.
function MeasureIcon({ line }) {
  const [x1, y1, x2, y2] = line
  return (
    <svg className="measure-icon" viewBox="0 0 60 110" aria-hidden="true">
      <circle className="body" cx="30" cy="10" r="6" />
      <path
        className="body"
        d="M18 22 Q30 18 42 22 L44 38 Q41 48 41 54 Q46 62 45 72 L42 106 L33 106 L30 80 L27 106 L18 106 L15 72 Q14 62 19 54 Q19 48 16 38 Z"
      />
      <line className="measure-line" x1={x1} y1={y1} x2={x2} y2={y2} />
    </svg>
  )
}

// Slider with − and + buttons.
function RangeField({ id, label, unit, min, max, value, onChange, onNudge }) {
  return (
    <div className="range-field">
      <div className="range-head">
        <label htmlFor={id}>{label}</label>
        <strong>
          {value} {unit}
        </strong>
      </div>
      <div className="range-row">
        <button type="button" aria-label={'Decrease ' + label.toLowerCase()} onClick={() => onNudge(-1)}>
          −
        </button>
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button type="button" aria-label={'Increase ' + label.toLowerCase()} onClick={() => onNudge(1)}>
          +
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------
function Profile() {
  const [values, setValues] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState({})
  const [step, setStep] = useState(0)
  const [done, setDone] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')

  useEffect(() => {
    let active = true
    async function loadProfile() {
      const user = getStoredUser()
      if (!user?.id) return
      try {
        const response = await axios.get(`${API_BASE_URL}/api/profile/${user.id}`, { headers: authHeaders() })
        if (!active) return
        const p = response.data
        setValues(old => ({ ...old, name: p.name || old.name, age: String(p.age ?? old.age), gender: p.gender || old.gender, bodyShape: p.body_shape || old.bodyShape, skinTone: p.skin_tone || old.skinTone, height: String(p.height_cm ?? old.height), weight: String(p.weight_kg ?? old.weight) }))
        setDone(true)
      } catch (e) { if (e?.response?.status !== 404 && active) setSaveError('Could not load your saved profile. Please try refreshing.') }
    }
    loadProfile()
    return () => { active = false }
  }, [])

  const isLastStep = step === STEPS.length - 1
  const measurements = availableMeasurements(values.gender)
  const activeParts = measurements.filter((m) => values.parts.includes(m.value))

  function setValue(name, value) {
    setValues((old) => ({ ...old, [name]: value }))
    setErrors((old) => ({ ...old, [name]: '' })) // clear the error for this field
  }

  function setMeasure(part, value) {
    setValues((old) => ({ ...old, measures: { ...old.measures, [part]: value } }))
    setErrors((old) => ({ ...old, ['measure_' + part]: '' }))
  }

  function setDetail(key, level) {
    setValues((old) => ({ ...old, details: { ...old.details, [key]: level } }))
  }

  function togglePart(part) {
    const alreadyChosen = values.parts.includes(part)
    setValue('parts', alreadyChosen ? values.parts.filter((p) => p !== part) : [...values.parts, part])
    setErrors((old) => ({ ...old, ['measure_' + part]: '' }))
  }

  // Used by the − and + buttons. "start" is used when the box is still empty.
  function nudge(name, change, min, max, start) {
    const current = values[name] === '' ? start : Number(values[name])
    const next = Math.min(max, Math.max(min, current + change))
    setValue(name, String(next))
  }

  // Keep only the errors that belong to the given step.
  function errorsForStep(allErrors, stepIndex) {
    const result = {}
    STEPS[stepIndex].fields.forEach((field) => {
      if (allErrors[field]) result[field] = allErrors[field]
    })
    return result
  }

  function goNext() {
    const stepErrors = errorsForStep(validate(values), step)
    setErrors(stepErrors)
    if (Object.keys(stepErrors).length === 0) setStep(step + 1)
  }

  function save() {
    const allErrors = validate(values)
    const badStep = STEPS.findIndex((_, i) => Object.keys(errorsForStep(allErrors, i)).length > 0)
    if (badStep !== -1) {
      setStep(badStep) // jump back to the first step that needs fixing
      setErrors(errorsForStep(allErrors, badStep))
      return
    }
    setErrors({})
    setSaveError('')
    const user = getStoredUser()
    if (!user?.id) { setSaveError('Please log in again to save your profile.'); return }
    axios.post(`${API_BASE_URL}/api/profile`, {
      user_id: user.id,
      name: values.name.trim(),
      age: Number(values.age),
      gender: values.gender,
      body_shape: values.bodyShape,
      skin_tone: values.skinTone,
      height_cm: Number(values.height),
      weight_kg: Number(values.weight),
    }, { headers: { ...authHeaders(), 'Content-Type': 'application/json' } })
      .then(() => { setSaveMessage('Your profile has been saved to your account.'); setDone(true) })
      .catch((error) => { setSaveError(error?.response?.data?.detail || 'Could not save your profile. Please try again.') })
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (isLastStep) save()
    else goNext()
  }

  function inputProps(name) {
    return {
      id: name,
      name,
      value: values[name],
      onChange: (event) => setValue(name, event.target.value),
      'aria-invalid': errors[name] ? 'true' : 'false',
      'aria-describedby': errors[name] ? name + '-error' : undefined,
    }
  }

  // Rows shown on the Review step (and after saving).
  const measureText = activeParts.map((m) => m.label + ' ' + (values.measures[m.value] || '-') + ' cm').join(', ')
  const detailText = BODY_DETAILS.filter((d) => values.details[d.key] !== 'average')
    .map((d) => d.label + ': ' + (values.details[d.key] === 'low' ? d.low : d.high))
    .join(', ')
  const rows = [
    ['Name', values.name.trim()],
    ['Age', values.age],
    ['Gender', labelOf(GENDERS, values.gender)],
    ['Clothing style', labelOf(CLOTHING_STYLES, values.style)],
    ['Body shape', labelOf(BODY_SHAPES, values.bodyShape)],
    ['Skin tone', labelOf(SKIN_TONES, values.skinTone)],
    ['Budget', values.budget ? '₹' + values.budget : ''],
    ['Height', values.height + ' cm'],
    ['Weight', values.weight + ' kg'],
    ['Measurements', measureText || 'None added'],
    ['Body details', detailText || 'All average'],
  ]

  // ---------- After "Save Profile" ----------
  if (done) {
    return (
      <section className="profile">
        <Scene>
          <div className="wizard">
            <div className="wizard-body wizard-done">
              <h2 className="step-title">Your profile details</h2>
              <p className="notice notice-info" role="status">{saveMessage || 'Your saved profile is linked to your account.'}</p>
              {saveError && <p className="notice notice-error" role="alert">{saveError}</p>}
              <dl className="summary">
                {rows.map(([label, value]) => (
                  <div key={label} className="summary-row">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="wizard-actions">
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => {
                    setDone(false)
                    setStep(0)
                  }}
                >
                  Edit Profile
                </button>
                <a className="btn btn-gold" href="#/">
                  Back to Home
                </a>
              </div>
            </div>
          </div>
        </Scene>
      </section>
    )
  }

  // ---------- The step-by-step form ----------
  return (
    <section className="profile">
      <Scene>
        <form className="wizard" onSubmit={handleSubmit} noValidate>
          <Stepper step={step} />

          <div className="wizard-body">
            <p className="step-count">
              Step {step + 1} of {STEPS.length}
            </p>
            <h2 className="step-title">{STEPS[step].title}</h2>
            <p className="step-text">{STEPS[step].text}</p>

            {/* ---------- Step 1: About you + style preferences ---------- */}
            {step === 0 && (
              <>
                <Field id="name" label="Name" error={errors.name}>
                  <input type="text" placeholder="Your name" {...inputProps('name')} />
                </Field>

                <fieldset className="field">
                  <legend>Gender</legend>
                  <OptionPills name="gender" options={GENDERS} value={values.gender} onChange={setValue} />
                  {errors.gender && (
                    <p className="error" role="alert">
                      {errors.gender}
                    </p>
                  )}
                </fieldset>

                <Field id="age" label="Age" error={errors.age}>
                  <div className="stepper">
                    <button type="button" aria-label="Decrease age" onClick={() => nudge('age', -1, 1, 120, 24)}>
                      −
                    </button>
                    <input type="number" inputMode="numeric" placeholder="25" {...inputProps('age')} />
                    <button type="button" aria-label="Increase age" onClick={() => nudge('age', 1, 1, 120, 24)}>
                      +
                    </button>
                  </div>
                </Field>

                <h3 className="subhead">Style preferences</h3>
                <p className="subtext">What styles do you love?</p>
                <div className="field">
                  <OptionPills name="style" options={CLOTHING_STYLES} value={values.style} onChange={setValue} perRow={4} />
                  {errors.style && (
                    <p className="error" role="alert">
                      {errors.style}
                    </p>
                  )}
                </div>
              </>
            )}

            {/* ---------- Step 2: body shape, skin tone, budget ---------- */}
            {step === 1 && (
              <>
                <h3 className="subhead first">Body shape</h3>
                <p className="subtext">Choose the one closest to yours. This helps adjust silhouettes.</p>
                <div className="shape-grid" role="radiogroup" aria-label="Body shape">
                  {BODY_SHAPES.map((option) => (
                    <label
                      key={option.value}
                      className={values.bodyShape === option.value ? 'shape-card selected' : 'shape-card'}
                    >
                      <input
                        type="radio"
                        className="visually-hidden"
                        name="bodyShape"
                        value={option.value}
                        checked={values.bodyShape === option.value}
                        onChange={() => setValue('bodyShape', option.value)}
                      />
                      <span className="check" aria-hidden="true">
                        ✓
                      </span>
                      <Silhouette sizes={option.sizes} />
                      <span className="card-name">{option.label}</span>
                      <span className="card-text">{option.text}</span>
                    </label>
                  ))}
                </div>
                {errors.bodyShape && (
                  <p className="error" role="alert">
                    {errors.bodyShape}
                  </p>
                )}

                <h3 className="subhead">Skin tone</h3>
                <p className="subtext">Pick the closest match. This helps suggest colours that suit you.</p>
                <div className="skin-grid" role="radiogroup" aria-label="Skin tone">
                  {SKIN_TONES.map((option) => (
                    <label
                      key={option.value}
                      className={values.skinTone === option.value ? 'swatch selected' : 'swatch'}
                    >
                      <input
                        type="radio"
                        className="visually-hidden"
                        name="skinTone"
                        value={option.value}
                        checked={values.skinTone === option.value}
                        onChange={() => setValue('skinTone', option.value)}
                      />
                      <span className="dot" style={{ background: option.color }} />
                      <span className="card-name">{option.label}</span>
                    </label>
                  ))}
                </div>
                {errors.skinTone && (
                  <p className="error" role="alert">
                    {errors.skinTone}
                  </p>
                )}

                <h3 className="subhead">Budget</h3>
                <Field
                  id="budget"
                  label="Preferred budget"
                  hint="The most you would like to spend, in rupees."
                  error={errors.budget}
                >
                  <div className="prefix">
                    <span>₹</span>
                    <input type="number" inputMode="numeric" placeholder="5000" {...inputProps('budget')} />
                  </div>
                </Field>
              </>
            )}

            {/* ---------- Step 3: height, weight, measurements, body details ---------- */}
            {step === 2 && (
              <>
                <RangeField
                  id="height"
                  label="Height"
                  unit="cm"
                  min={100}
                  max={230}
                  value={values.height}
                  onChange={(v) => setValue('height', v)}
                  onNudge={(change) => nudge('height', change, 100, 230, 165)}
                />
                <RangeField
                  id="weight"
                  label="Weight"
                  unit="kg"
                  min={25}
                  max={200}
                  value={values.weight}
                  onChange={(v) => setValue('weight', v)}
                  onNudge={(change) => nudge('weight', change, 25, 200, 60)}
                />

                <h3 className="subhead">Body measurements</h3>
                <p className="subtext">Optional. Choose the parts you want to measure, then enter each in centimetres.</p>
                <div className="measure-grid">
                  {measurements.map((m) => {
                    const chosen = values.parts.includes(m.value)
                    return (
                      <label
                        key={m.value}
                        className={chosen ? 'shape-card measure-card selected' : 'shape-card measure-card'}
                      >
                        <input
                          type="checkbox"
                          className="visually-hidden"
                          checked={chosen}
                          onChange={() => togglePart(m.value)}
                        />
                        <span className="check" aria-hidden="true">
                          ✓
                        </span>
                        <MeasureIcon line={m.line} />
                        <span className="card-name">{m.label}</span>
                      </label>
                    )
                  })}
                </div>

                {activeParts.length === 0 ? (
                  <p className="empty-note">No body parts chosen. You can continue without measurements.</p>
                ) : (
                  <div className="measure-inputs">
                    {activeParts.map((m) => {
                      const id = 'measure_' + m.value
                      return (
                        <Field key={m.value} id={id} label={m.label + ' (cm)'} error={errors[id]}>
                          <input
                            id={id}
                            type="number"
                            inputMode="decimal"
                            placeholder="e.g. 90"
                            value={values.measures[m.value] ?? ''}
                            onChange={(e) => setMeasure(m.value, e.target.value)}
                            aria-invalid={errors[id] ? 'true' : 'false'}
                            aria-describedby={errors[id] ? id + '-error' : undefined}
                          />
                        </Field>
                      )
                    })}
                  </div>
                )}

                <h3 className="subhead">Body details</h3>
                <p className="subtext">Optional. Adjust only what differs for your height and weight; otherwise leave it on Average.</p>
                <div className="details">
                  {BODY_DETAILS.map((d) => (
                    <div key={d.key} className="detail-row">
                      <span className="detail-name">{d.label}</span>
                      <div className="scale">
                        <div className="scale-ends">
                          <span>{d.low}</span>
                          <span>{d.high}</span>
                        </div>
                        <div className="scale-points" role="radiogroup" aria-label={d.label}>
                          {[
                            ['low', d.low],
                            ['average', 'Average'],
                            ['high', d.high],
                          ].map(([level, text]) => (
                            <label
                              key={level}
                              className={values.details[d.key] === level ? 'point selected' : 'point'}
                            >
                              <input
                                type="radio"
                                className="visually-hidden"
                                name={'detail_' + d.key}
                                value={level}
                                checked={values.details[d.key] === level}
                                onChange={() => setDetail(d.key, level)}
                              />
                              <span className="circle" />
                              <span className="visually-hidden">{text}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* ---------- Step 4: review ---------- */}
            {step === 3 && (
              <dl className="summary">
                {rows.map(([label, value]) => (
                  <div key={label} className="summary-row">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            )}

            {saveError && <p className="notice notice-error" role="alert">{saveError}</p>}
            <div className="wizard-actions">
              {step > 0 && (
                <button type="button" className="btn btn-outline" onClick={() => setStep(step - 1)}>
                  Back
                </button>
              )}
              <button type="submit" className="btn btn-gold next">
                {isLastStep ? 'Save Profile' : 'Next →'}
              </button>
            </div>
          </div>
        </form>
      </Scene>
    </section>
  )
}

export default Profile
