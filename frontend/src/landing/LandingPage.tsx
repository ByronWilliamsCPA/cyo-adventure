import { Link } from 'react-router-dom'

import { Mascot } from '../kid/Mascot'
import { GUARDIAN_CONSOLE_PATH, KID_PICKER_PATH } from '../routes'

import './landing.css'

/**
 * Root landing page: the one page both audiences see. Static by design (no
 * data fetching, no auth) so it imports neither the guardian/Supabase chunk nor
 * any kid data hooks: only the presentational Mascot glyph is shared, which
 * keeps the router's two-surface split intact.
 */
export function LandingPage() {
  return (
    <main className="landing">
      <div className="landing__hero">
        <Mascot size={128} />
        <h1 className="landing__title">CYO Adventure</h1>
        <p className="landing__tagline">Choose-your-own adventures for young readers.</p>
      </div>
      <nav className="landing__doors" aria-label="Pick who you are">
        <Link className="landing-door landing-door--kids" to={KID_PICKER_PATH}>
          <span className="landing-door__icon" aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
              <path
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 5 C7 3 10 3 12 5 C14 3 17 3 20 5 V19 C17 17 14 17 12 19 C10 17 7 17 4 19 Z M12 5 V19"
              />
            </svg>
          </span>
          <span className="landing-door__text">
            <span className="landing-door__heading">Kids</span>
            <span className="landing-door__sub">Start reading</span>
          </span>
        </Link>
        <Link className="landing-door landing-door--guardian" to={GUARDIAN_CONSOLE_PATH}>
          <span className="landing-door__icon" aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
              <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
              <path fill="currentColor" d="M12 12 L15.5 8.5 L13 12 Z M12 12 L8.5 15.5 L11 12 Z" />
            </svg>
          </span>
          <span className="landing-door__text">
            <span className="landing-door__heading">Grown-ups</span>
            <span className="landing-door__sub">Guardian console</span>
            <span className="landing-door__note">Admins sign in here too</span>
          </span>
        </Link>
      </nav>
    </main>
  )
}
