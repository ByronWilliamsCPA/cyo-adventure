import { Link } from 'react-router-dom'

import { GUARDIAN_CONSOLE_PATH, KID_PICKER_PATH } from '../routes'

import './landing.css'

/**
 * Root landing page: the one page both audiences see. Static by design (no
 * data fetching, no auth) so it imports neither the kid chrome nor the
 * guardian/Supabase chunk, preserving the router's two-surface split.
 */
export function LandingPage() {
  return (
    <main className="landing">
      <h1 className="landing__title">CYO Adventure</h1>
      <p className="landing__tagline">Choose-your-own adventures for young readers.</p>
      <nav className="landing__doors" aria-label="Pick who you are">
        <Link className="landing-door landing-door--kids" to={KID_PICKER_PATH}>
          <span className="landing-door__heading">Kids</span>
          <span className="landing-door__sub">Start reading</span>
        </Link>
        <Link className="landing-door landing-door--guardian" to={GUARDIAN_CONSOLE_PATH}>
          <span className="landing-door__heading">Grown-ups</span>
          <span className="landing-door__sub">Guardian console</span>
          <span className="landing-door__note">Admins sign in here too</span>
        </Link>
      </nav>
    </main>
  )
}
