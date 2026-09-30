import Brand from "../components/Brand";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.5-.2-2.2H12v4.2h5.4a4.6 4.6 0 0 1-2 3v2.7h3.5c2-1.9 3.2-4.6 3.2-7.7Z" />
      <path fill="#34A853" d="M12 22c2.9 0 5.3-1 7-2.6l-3.5-2.7a6.3 6.3 0 0 1-9.4-3.3H2.5v2.8A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.1 13.4a6 6 0 0 1 0-3.8V6.8H2.5a10 10 0 0 0 0 9.4l3.6-2.8Z" />
      <path fill="#EA4335" d="M12 5.9c1.7 0 3.1.6 4.3 1.7l3.2-3.2A10 10 0 0 0 2.5 6.8l3.6 2.8A6 6 0 0 1 12 5.9Z" />
    </svg>
  );
}

export default function Login() {
  return (
    <main className="auth-page">
      <div className="auth-shell">
        <section className="auth-story">
          <Brand />
          <div className="auth-message">
            <p className="eyebrow">Files that know when to leave</p>
            <h1>Share what matters.<br /><span>Keep nothing forever.</span></h1>
            <p className="auth-lead">
              Private, temporary file delivery with simple expiry controls and direct uploads to Cloudflare R2.
            </p>
          </div>
          <div className="auth-features">
            <div>
              <span className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none"><path d="M12 3 5 6v5c0 4.7 2.9 8.2 7 10 4.1-1.8 7-5.3 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></svg>
              </span>
              <span><strong>Private by default</strong><small>Files stay in a private R2 bucket</small></span>
            </div>
            <div>
              <span className="feature-icon">
                <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3 2" /></svg>
              </span>
              <span><strong>Built to disappear</strong><small>Time-based or first-download expiry</small></span>
            </div>
          </div>
        </section>

        <section className="auth-card-wrap">
          <div className="auth-card">
            <span className="auth-card-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" /></svg>
            </span>
            <p className="section-kicker">Welcome to QuickDrop</p>
            <h2>Your private drop space</h2>
            <p>Sign in to upload, manage, and share files. Recipients never need an account.</p>
            <a className="google-button" href="/api/auth/google">
              <GoogleIcon />
              <span>Continue with Google</span>
              <svg className="button-arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
            </a>
            <div className="auth-note">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
              <span>Secure Google sign-in. We never receive your password.</span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
