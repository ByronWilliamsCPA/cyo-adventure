import { useEffect } from 'react'

const BASE_TITLE = 'CYO Adventure'

/**
 * Sets `document.title` for the page currently mounted at a route.
 *
 * Generalizes the ad hoc pattern LoginPage.tsx already used
 * (`useEffect(() => { document.title = '...' }, [])`) so every routed page
 * gets the same treatment instead of just the one page that happened to
 * need it first. index.html's static `<title>CYO Adventure</title>` is the
 * app-wide default before any route mounts; without a per-page call here it
 * is also the ONLY title, unchanged by React Router navigation, so a
 * guardian's browser tab/history looked identical whether they were on the
 * library, mid-story, or in the admin console.
 *
 * No restore-on-unmount: the next page to mount sets its own title before
 * the previous page's cleanup would matter, so restoring here would only
 * add a flash of the wrong title during navigation, not fix anything.
 *
 * @param title - Page-specific segment, e.g. "My Books". Suffixed with the
 *   app name ("My Books - CYO Adventure") unless `bare` is set.
 * @param options.bare - Use `title` as the whole document title, unsuffixed.
 *   For the landing page, whose title IS the app name.
 */
export function usePageTitle(title: string, options?: { bare?: boolean }): void {
  const bare = options?.bare ?? false
  useEffect(() => {
    document.title = bare ? title : `${title} - ${BASE_TITLE}`
    // #ASSUME: data-integrity: `title` is always a short, human-authored
    // string literal or static label at each call site (page names, not
    // interpolated user content like a story title or a child's display
    // name) -- see ReaderRoute/GuardianReviewDetailPage, which pass their
    // own descriptive label rather than raw data.
    // #VERIFY: if a future call site interpolates a story title or profile
    // name here, confirm it cannot inject something misleading into the
    // browser tab/history (document.title has no HTML-injection risk, but a
    // spoofed title is still a legitimate concern for a kids' app).
  }, [title, bare])
}
