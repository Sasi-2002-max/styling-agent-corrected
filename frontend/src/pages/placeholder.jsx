// Temporary page for routes that are not built yet.
function Placeholder({ title, params }) {
  const prompt = params.get('prompt')
  const occasion = params.get('occasion')

  return (
    <section className="placeholder">
      <h1>{title}</h1>
      <p>This page is coming soon.</p>
      {(prompt || occasion) && (
        <div className="placeholder-box">
          <p>Received from the Home page:</p>
          <p>Prompt: {prompt || '(none)'}</p>
          <p>Occasion: {occasion || '(none)'}</p>
        </div>
      )}
      <a className="btn btn-gold" href="#/">
        Back to Home
      </a>
    </section>
  )
}

export default Placeholder