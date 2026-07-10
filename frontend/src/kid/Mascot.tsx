/**
 * Pip the fox: the kid surface's friendly guide. A choose-your-own adventure
 * is a journey down forking trails, so a small explorer companion appears at
 * the moments a child might feel lost or triumphant: the welcome door, empty
 * shelves, and the ending screen.
 *
 * Decorative by default (aria-hidden): the surrounding copy carries the
 * meaning, so the art is not announced to screen readers. Pass a `title` only
 * when the fox is the sole content of an otherwise unlabelled element.
 *
 * These are placeholder vector glyphs; the curated illustrated set replaces
 * them later (tracked alongside the avatar art, issue #65) without touching
 * callers.
 */

export interface MascotProps {
  /** Pixel size of the square viewport. Defaults to 96. */
  size?: number
  /** Accessible name; when set the SVG is exposed as an image instead of hidden. */
  title?: string
  className?: string
}

export function Mascot({ size = 96, title, className }: MascotProps) {
  const label = title?.trim() || undefined
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <ellipse cx="50" cy="92" rx="26" ry="5" fill="rgba(0,0,0,0.10)" />
      <path d="M18 30 L14 8 L40 24 Z" fill="var(--color-amber, #e07f2e)" />
      <path d="M82 30 L86 8 L60 24 Z" fill="var(--color-amber, #e07f2e)" />
      <path d="M22 20 L20 12 L32 22 Z" fill="var(--color-amber-hover, #c4681c)" />
      <path d="M78 20 L80 12 L68 22 Z" fill="var(--color-amber-hover, #c4681c)" />
      <path
        d="M50 24 C24 24 16 44 16 60 C16 80 32 92 50 92 C68 92 84 80 84 60 C84 44 76 24 50 24 Z"
        fill="var(--color-amber, #e07f2e)"
      />
      <path
        d="M50 52 C36 52 26 60 24 72 C30 86 40 92 50 92 C60 92 70 86 76 72 C74 60 64 52 50 52 Z"
        fill="#fdf3e6"
      />
      <circle cx="38" cy="58" r="5.5" fill="var(--color-ink, #2c1a0e)" />
      <circle cx="62" cy="58" r="5.5" fill="var(--color-ink, #2c1a0e)" />
      <circle cx="39.6" cy="56.4" r="1.8" fill="#fff" />
      <circle cx="63.6" cy="56.4" r="1.8" fill="#fff" />
      <path d="M50 66 L45 72 Q50 76 55 72 Z" fill="var(--color-ink, #2c1a0e)" />
      <path
        d="M50 74 L50 79"
        stroke="var(--color-ink, #2c1a0e)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
